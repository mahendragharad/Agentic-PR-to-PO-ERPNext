from pathlib import Path
from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

# Automatically locate the directory containing config/settings.py, then go up 1 level to the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

class AppSettings(BaseSettings):
    """
    Validates and manages all application configuration parameters.
    Automatically loads variables from environment or a local .env file.
    """
    # ---------------------------------------------------------
    # 1. Core ERPNext Configurations (Strict Validation)
    # ---------------------------------------------------------
    erpnext_base_url: HttpUrl = Field(..., alias="ERPNEXT_BASE_URL")
    token_url : HttpUrl = Field(..., alias="TOKEN_REFRESH_URL")
    erpnext_client_id: str = Field(..., alias="ERPNEXT_CLIENT_ID")
    erpnext_client_secret: str = Field(..., alias="ERPNEXT_CLIENT_SECRET")
    erpnext_scope: str = Field(default="all openid", alias="ERPNEXT_SCOPE")
    
    # ---------------------------------------------------------
    # 2. Application & Operations Settings
    # ---------------------------------------------------------
    app_env: str = Field(default="production", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def absolute_token_path(self) -> str:
        """Forces tokens.json to always resolve to the absolute base project root directory."""
        return str(PROJECT_ROOT / "tokens.json")
    
    # ---------------------------------------------------------
    # 3. API Services Vallidations 
    # ---------------------------------------------------------
    groq_api_key : str = Field(..., alias="GROQ_API_KEY")
    model_name : str = Field(..., alias="MODEL_NAME")

    # ---------------------------------------------------------
    # 4. Observibility services (Langfuse)
    # ---------------------------------------------------------   
    LANGFUSE_SECRET_KEY : str = Field(..., alias="LANGFUSE_SECRET_KEY")
    LANGFUSE_PUBLIC_KEY : str = Field(..., alias="LANGFUSE_PUBLIC_KEY")
    LANGFUSE_BASE_URL : str = Field(..., alias="LANGFUSE_BASE_URL")
    BASE_API_URL : str = Field(..., alias="BASE_API_URL")

    LOGIN_URL : str = f"{BASE_API_URL}/api/v2/user/auth/login"
    FASTAPI_STREAM_URL : str = f"{BASE_API_URL}/api/v1/chat/stream"
    RESUME_URL : str = f"{BASE_API_URL}/api/v1/chat/resume"

    # ---------------------------------------------------------
    # 5. Configuration Metadata Layer
    # ---------------------------------------------------------
    # Configures Pydantic to read directly from a local `.env` file
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"  # Safely ignores unexpected system environment variables
    )

# 5. Instantiate a single, global settings instance to import anywhere
settings = AppSettings()
