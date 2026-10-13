import os
import json
import time
import logging
import threading
import requests
from typing import Dict, Any
from config.logging_config import logger

class ERPNextAuthorizationCodeManager:
    """
    Manages OAuth2 Authorization Code flow tokens for ERPNext.
    Uses long-lived Refresh Tokens to fetch fresh Access Tokens completely in the background,
    avoiding interactive browser permission popups after initial setup.
    """
    def __init__(self, token_url: str, client_id: str, client_secret: str, scope: str = "all openid", cache_file: str = "tokens.json"):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.cache_file = cache_file
        
        self._lock = threading.Lock()
        
        # Core runtime credentials state
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self.expiry_buffer = 300  # 5-minute proactive refresh window

        # Load tokens from storage if they exist from a previous run
        self._load_token_cache()

    def _load_token_cache(self) -> None:
        """Loads existing tokens from disk to maintain state across process restarts."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                    self._access_token = data.get("access_token")
                    self._refresh_token = data.get("refresh_token")
                    self._expires_at = float(data.get("expires_at", 0.0))
                logger.info("Loaded active session state from disk cache.")
            except Exception as e:
                logger.warning(f"Could not read token cache file: {e}. Starting fresh.")

    def _save_token_cache(self) -> None:
        """Saves active tokens securely to disk storage."""
        try:
            with open(self.cache_file, "w") as f:
                json.dump({
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                    "expires_at": self._expires_at
                }, f)
        except Exception as e:
            logger.error(f"Failed to persist tokens to disk cache: {e}")

    def _refresh_access_token(self) -> None:
        """Uses the long-lived refresh_token to securely pull a fresh 1-hour access_token."""
        if not self._refresh_token:
            raise ValueError(
                "No Refresh Token found! You must perform the initial interactive browser authorization "
                "via Postman or a configuration endpoint once, then populate the tokens.json cache file."
            )

        # Preparing fields based on your configuration parameters
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        logger.info("Proactively exchanging refresh token for a new access token...")
        try:
            response = requests.post(self.token_url, data=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            self._access_token = data["access_token"]
            # Update refresh token if the server rolls/rotates it
            if "refresh_token" in data:
                self._refresh_token = data["refresh_token"]

            expires_in = float(data.get("expires_in", 3600))
            self._expires_at = time.time() + expires_in

            # Sync to storage immediately
            self._save_token_cache()
            logger.info("Tokens successfully rotated and stored securely.")
            
        except requests.RequestException as e:
            logger.critical(f"Failed to refresh background access token: {e}")
            raise RuntimeError(f"ERPNext rejected token rotation payload: {e}") from e

    def _get_valid_token(self) -> str:
        """Thread-safe gateway ensuring agents always receive an active access token."""
        current_time = time.time()
        
        if current_time >= (self._expires_at - self.expiry_buffer):
            with self._lock:
                if time.time() >= (self._expires_at - self.expiry_buffer):
                    self._refresh_access_token()
                    
        return self._access_token
