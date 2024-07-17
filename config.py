import logging
from functools import lru_cache
from typing import Union, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, PostgresDsn, DirectoryPath, Field, validator

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="/home/abdullah/Documents/hdd/projects/ansari/ansari-backend/.env", env_file_encoding="utf-8", case_sensitive=True)
    
    DATABASE_URL: PostgresDsn = Field(default="postgresql://mwk@localhost:5432/mwk")
    MAX_THREAD_NAME_LENGTH: int = Field(default=100)

    SECRET_KEY: SecretStr = Field(default="secret")
    ALGORITHM: str = Field(default="HS256")
    ENCODING: str = Field(default="utf-8")
    ACCESS_TOKEN_EXPIRY_HOURS: int = Field(default=2)
    REFRESH_TOKEN_EXPIRY_HOURS: int = Field(default=24*90)

    ORIGINS: Union[str, list[str]] = Field(default=["https://ansari.chat", "http://ansari.chat"], env="ORIGINS")
    API_SERVER_PORT: int = Field(default=8000)

    OPENAI_API_KEY: SecretStr
    PGPASSWORD: SecretStr
    KALEMAT_API_KEY: SecretStr
    VECTARA_AUTH_TOKEN: SecretStr
    VECTARA_CUSTOMER_ID: str
    VECTARA_CORPUS_ID: str
    DISCORD_TOKEN: Optional[SecretStr] = Field(default=None)
    SENDGRID_API_KEY: Optional[SecretStr] = Field(default=None)
    LANGFUSE_SECRET_KEY: Optional[SecretStr] = Field(default=None)

    template_dir: DirectoryPath = Field(default="resources/templates")
    diskcache_dir: str = Field(default="diskcache_dir")

    MODEL: str = Field(default="gpt-4o-2024-05-13")
    MAX_FUNCTION_TRIES: int = Field(default=3)
    MAX_FAILURES: int = Field(default=1)
    SYSTEM_PROMPT_FILE_NAME: str = Field(default="system_msg_fn")

    @validator("ORIGINS", pre=True)
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.strip('"').split(",")]
        elif isinstance(v, list):
            return v
        raise ValueError(f"Invalid ORIGINS format: {v}. Expected a comma-separated string or a list.")

@lru_cache()
def get_settings() -> Settings:
    try:
        settings = Settings()
        return settings
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        raise
