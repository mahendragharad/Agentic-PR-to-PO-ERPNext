import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import jwt
import httpx

from src.auth.erp_next_auth import create_secure_jwt, AsyncERPNextService, get_authenticated_erp_service

user_router = APIRouter(prefix="/user", tags=["user_sessions"])

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secure-production-key-change-me-987654321!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
COOKIE_NAME = "erpnext_auth_token"
ERPNEXT_BASE_URL = os.getenv("ERPNEXT_BASE_URL").rstrip('/')
FRONTEND_MAIN_UI_URL = os.getenv("FRONTEND_MAIN_UI_URL", "http://localhost:3000/dashboard")

@user_router.post("/auth/login")
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """
    Acts as a secure proxy to authenticate users against ERPNext,
    captures backend authentication cookies, and returns a secure application JWT.
    """
    login_url = f"{ERPNEXT_BASE_URL}/api/method/login"
    payload = {"usr": form_data.username, "pwd": form_data.password}
    
    async with httpx.AsyncClient() as client:
        try:
            # ERPNext expects urlencoded form submission parameters during the sign-in sequence
            erp_response = await client.post(login_url, data=payload, timeout=15.0)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Unable to contact ERPNext authentication node: {str(e)}")

    if erp_response.status_code != 200 or erp_response.json().get("message") != "Logged In":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or rejected ERPNext profile path.",
        )
    
    # Extract structural session details generated natively by ERPNext (specifically the 'sid' cookie)
    erpnext_cookies = dict(erp_response.cookies)
    if not erpnext_cookies.get("sid"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ERPNext login succeeded but did not return a session cookie.",
        )
    
    # Convert captured session maps securely into our self-contained application JWT
    app_jwt = create_secure_jwt(email=form_data.username, erpnext_cookies=erpnext_cookies)
    
    # Write the JWT directly onto an absolute HttpOnly, SameSite tracking cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=app_jwt,
        httponly=True,       # Mitigates malicious client-side JavaScript execution (XSS defense)
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",      # Defends against cross-site request forgery attacks (CSRF defense)
        secure=request.url.scheme == "https",
    )
    
    return {"status": "success", "message": "Successfully synchronized server context session."}


@user_router.get("/auth/verify-and-redirect")
async def verify_and_redirect(erp_service: AsyncERPNextService = Depends(get_authenticated_erp_service)):
    """
    Authenticates structural access tokens. If authorized, issues an HTTP 307 redirect
    seamlessly dispatching the user profile straight into the primary UI Dashboard environment.
    """
    return RedirectResponse(url=FRONTEND_MAIN_UI_URL, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@user_router.get("/api/erpnext/me")
async def get_my_erpnext_profile(erp_service: AsyncERPNextService = Depends(get_authenticated_erp_service)):
    """
    Example protected proxy route: Authenticates calls automatically through injection filters,
    allowing clean and secure access to the authenticated user's ERPNext context profile.
    """
    profile_endpoint = "api/method/frappe.auth.get_logged_user"
    profile_data = await erp_service.execute_request(method="GET", endpoint=profile_endpoint)
    return {"status": "success", "data": profile_data}


@user_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """
    Clears the secure HttpOnly cookie from the user's browser session.
    """
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https"
    )
    return {"status": "success", "message": "Logged out successfully context dropped."}
