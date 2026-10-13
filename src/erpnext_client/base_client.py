import requests
from typing import Dict, Any
from requests.auth import AuthBase
from config.logging_config import logger
from src.auth.erpnext_auth import ERPNextBearerAuth
from src.auth.token_manager import ERPNextAuthorizationCodeManager

class ERPNextBaseClient(AuthBase) :
    """
    Custom Requests Auth plugin for injecting self-healing ERPNext Bearer Tokens.
    """
    def __init__(self, base_url : str, token_manager : ERPNextAuthorizationCodeManager) :
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()

        logger.info("Seamless integration: Attach the auto-refreshing authorization engine")
        self.session.auth = ERPNextBearerAuth(token_manager)

        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })


    def request(self, method : str, endpoint : str, **kwargs) -> Dict[str, Any]  :
        """
        Centralized request method with forced production timeouts and status handling.
        """
        logger.info("-- creating the base URL to with endpoint to make the request --")
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        if "timeout" not in kwargs :
            kwargs["timeout"] = 30

        try :
            logger.info("-- Testing the request --")
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()

            return response.json()
        except requests.HTTPError as e :
            if response.status_code == 401:
                logger.error("ERPNext rejected credentials with 401 Unauthorized.")
                raise PermissionError("ERPNext rejected credentials with 401 Unauthorized.") from e
            raise RuntimeError(f"ERPNext API returned unexpected error {response.status_code}: {response.text}") from e
