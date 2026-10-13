from requests.auth import AuthBase
from config.logging_config import logger

class ERPNextBearerAuth(AuthBase) :

    def __init__(self, token_manager) :
        self.token_manager = token_manager

    def __call__(self, r) :

        logger.info("Accepting the valid token and creating authorization payload")
        token = self.token_manager._get_valid_token()
        r.headers["Authorization"] = f"Bearer {token}"

        logger.info(f"r--- value -- {token}")

        return r
