import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import jwt
import httpx

# =====================================================================
# 1. GLOBAL PRODUCTION SETTINGS & ENVIRONMENT CONFIGURATION
# =====================================================================
# In production, replace default fallbacks with real environment variables!
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secure-production-key-change-me-987654321!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
COOKIE_NAME = "erpnext_auth_token"
ERPNEXT_BASE_URL = os.getenv("ERPNEXT_BASE_URL", "https://erpnext-ai-integration.m.frappe.cloud").rstrip('/')
FRONTEND_MAIN_UI_URL = os.getenv("FRONTEND_MAIN_UI_URL", "http://localhost:3000/dashboard")

# =====================================================================
# 2. STATELESS PRODUCTION SERVICE PATTERN (Asynchronous ERPNext Client)
# =====================================================================
class AsyncERPNextService:
    """
    Stateless wrapper handling dynamic payload dispatches back to ERPNext.
    Does not preserve instance-level memory across HTTP request cycles.
    """
    def __init__(self, base_url: str, cookies: Optional[Dict[str, str]] = None):
        self.base_url = base_url
        # Explicitly forward the authenticated cookies passed from the incoming JWT
        self.cookies = cookies or {}

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        erpnext_sid: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Dispatches an async HTTP request directly to the underlying ERPNext node."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        if "timeout" not in kwargs:
            kwargs["timeout"] = 30.0

        cookies = {"sid": erpnext_sid} if erpnext_sid else self.cookies
        if not cookies:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="ERPNext session context is missing. Please log in again.",
            )

        async with httpx.AsyncClient(cookies=cookies) as client:
            try:
                response = await client.request(method.upper(), url, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise HTTPException(status_code=401, detail="ERPNext session context expired or invalid.")
                raise HTTPException(status_code=e.response.status_code, detail=f"ERPNext Error: {e.response.text}")
            except httpx.RequestError as e:
                raise HTTPException(status_code=503, detail=f"ERPNext gateway unreachable: {str(e)}")

# =====================================================================
# 3. CORE SECURITY HELPER FUNCTIONS
# =====================================================================
def create_secure_jwt(email: str, erpnext_cookies: dict) -> str:
    """Signs user session details and raw session cookies securely inside an encrypted JWT payload."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": email,
        "exp": expire,
        "erp_cookies": erpnext_cookies  # Persisting ERPNext state inside the JWT
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# =====================================================================
# 4. DEPENDENCY INJECTION MECHANISM
# =====================================================================
async def get_authenticated_erp_service(request: Request) -> AsyncERPNextService:
    """
    FastAPI Dependency: Extract, decode and convert incoming browser cookie context
    back into a functional, validated ERPNext service pipeline.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session missing. Access denied.")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        erp_cookies: dict = payload.get("erp_cookies", {})
        if not email or not erp_cookies.get("sid"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed session signature.")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid application security signature.")

    # Yield instantiated stateless service wrapped in active user context
    return AsyncERPNextService(base_url=ERPNEXT_BASE_URL, cookies=erp_cookies)

