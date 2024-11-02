import logging
from functools import lru_cache
from typing import Literal, Optional, Union

from pydantic import DirectoryPath, Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Field value precedence in Pydantic Settings (highest to lowest priority):

    1. CLI arguments (if cli_parse_args is enabled).
    2. Arguments passed to the Settings initializer.
    3. Environment variables.
    4. Variables from a dotenv (.env) file.
    5. Variables from the secrets directory.
    6. Default field values in the Settings model.

    For more details, refer to the Pydantic documentation:
    [https://docs.pydantic.dev/latest/concepts/pydantic_settings/#field-value-priority].
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        missing="ignore",
    )

    DATABASE_URL: PostgresDsn = Field(
        default="postgresql://postgres:password@localhost:5432/ansari"
    )
    MAX_THREAD_NAME_LENGTH: int = Field(default=100)

    SECRET_KEY: SecretStr = Field(default="secret")
    # Literal ensures the allowed value(s), and frozen ensures it can't be changed after initialization
    ALGORITHM: Literal["HS256"] = Field(default="HS256", frozen=True)
    ENCODING: Literal["utf-8"] = Field(default="utf-8", frozen=True)
    ACCESS_TOKEN_EXPIRY_HOURS: int = Field(default=2)
    REFRESH_TOKEN_EXPIRY_HOURS: int = Field(default=24 * 90)

    ORIGINS: Union[str, list[str]] = Field(
        default=["https://ansari.chat", "http://ansari.chat"], env="ORIGINS"
    )
    API_SERVER_PORT: int = Field(default=8000)

    OPENAI_API_KEY: SecretStr
    PGPASSWORD: SecretStr = Field(default="password")
    KALEMAT_API_KEY: SecretStr
    VECTARA_AUTH_TOKEN: SecretStr
    VECTARA_CUSTOMER_ID: str
    VECTARA_CORPUS_ID: str
    DISCORD_TOKEN: Optional[SecretStr] = Field(default=None)
    SENDGRID_API_KEY: Optional[SecretStr] = Field(default=None)
    LANGFUSE_SECRET_KEY: Optional[SecretStr] = Field(default=None)
    LANGFUSE_PUBLIC_KEY: Optional[SecretStr] = Field(default=None)
    LANGFUSE_HOST: Optional[str] = Field(default=None)
    WHATSAPP_RECIPIENT_WAID: Optional[SecretStr] = Field(default=None)
    WHATSAPP_API_VERSION: Optional[str] = Field(default="v13.0")
    WHATSAPP_BUSINESS_PHONE_NUMBER_ID: Optional[SecretStr] = Field(default=None)
    WHATSAPP_ACCESS_TOKEN_FROM_SYS_USER: Optional[SecretStr] = Field(default=None)
    WHATSAPP_VERIFY_TOKEN_FOR_WEBHOOK: Optional[SecretStr] = Field(default=None)

    template_dir: DirectoryPath = Field(default="resources/templates")
    diskcache_dir: str = Field(default="diskcache_dir")

    MODEL: str = Field(default="gpt-4o")
    MAX_TOOL_TRIES: int = Field(default=3)
    MAX_FAILURES: int = Field(default=1)
    SYSTEM_PROMPT_FILE_NAME: str = Field(default="system_msg_tool")

    LOGGING_LEVEL: str = Field(default="INFO")

    @field_validator("ORIGINS")
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.strip('"').split(",")]
        elif isinstance(v, list):
            return v
        raise ValueError(
            f"Invalid ORIGINS format: {v}. Expected a comma-separated string or a list."
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
