# src/auth/exceptions.py
from typing import Optional, Any

class ERPNextAuthError(Exception):
    """
    Base exception for all authentication and authorization failures 
    interacting with the ERPNext ecosystem.
    """
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.details = details  # Holds raw server responses, status codes, or error payloads

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class TokenCacheNotFoundError(ERPNextAuthError):
    """
    Raised when the 'tokens.json' file is completely missing or empty,
    meaning the system has no seed refresh token to start with.
    Action: Human-in-the-loop intervention required to generate the initial token.
    """
    pass


class TokenCorruptError(ERPNextAuthError):
    """
    Raised when the 'tokens.json' file exists but contains invalid JSON or
    is missing critical structural data elements (like 'refresh_token').
    """
    pass


class TokenServerError(ERPNextAuthError):
    """
    Raised when the ERPNext authentication server returns a server error (5xx) 
    or the network drops completely during a token exchange attempt.
    Action: The agent can safely retry this operation using an exponential backoff.
    """
    pass


class InvalidCredentialsError(ERPNextAuthError):
    """
    Raised when ERPNext explicitly rejects the client_id or client_secret (HTTP 401).
    Action: Stop execution immediately. Retrying will not fix this.
    """
    pass


class RefreshTokenExpiredError(ERPNextAuthError):
    """
    Raised when the OAuth2 server explicitly states that the refresh token itself 
    has expired or been revoked/blacklisted on the ERPNext dashboard (HTTP 400 'invalid_grant').
    Action: Alert system admin. A human must log into the browser again.
    """
    pass


class InsufficientPermissionsError(ERPNextAuthError):
    """
    Raised when the authentication succeeds, but the authenticated user role
    does not have read/write access to the targeted Doctype (like Material Request) (HTTP 403).
    Action: Verify user permissions inside the ERPNext Role Permission Manager.
    """
    pass
