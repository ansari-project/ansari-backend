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

    VECTARA_API_KEY: SecretStr

    MAWSUAH_VECTARA_CORPUS_KEY: str = Field(
        alias="MAWSUAH_VECTARA_CORPUS_KEY", default="mawsuah_unstructured"
    )
    MAWSUAH_FN_NAME: str = Field(default="search_mawsuah")
    MAWSUAH_FN_DESCRIPTION: str = Field(
        default="Search and retrieve relevant rulings from the Islamic jurisprudence (fiqh) encyclopedia based on a specific topic. "
        "Returns a list of potentially relevant matches that may span multiple paragraphs. "
        "The search will be based on the 'query' parameter, which must be provided."
    )
    MAWSUAH_TOOL_PARAMS: list = Field(
        default=[
            {
                "name": "query",
                "type": "string",
                "description": "Topic or subject matter to search for within the fiqh encyclopedia. Write the query in Arabic.",
            }
        ]
    )
    MAWSUAH_TOOL_REQUIRED_PARAMS: list = Field(default=["query"])

    TAFSIR_VECTARA_CORPUS_KEY: str = Field(
        alias="TAFSIR_VECTARA_CORPUS_KEY", default="tafsirs"
    )
    TAFSIR_FN_NAME: str = Field(default="search_tafsir")
    TAFSIR_FN_DESCRIPTION: str = Field(
        default="""
        Queries Tafsir Ibn Kathir (the renowned Qur'anic exegesis) for relevant 
        interpretations and explanations. You call this function when you need to 
        provide authoritative Qur'anic commentary and understanding based on Ibn 
        Kathir's work. Regardless of the language used in the original conversation, 
        you will translate the query into English before searching the tafsir. The 
        function returns a list of **potentially** relevant matches, which may include 
        multiple passages of interpretation and analysis.
        """
    )
    TAFSIR_TOOL_PARAMS: list = Field(
        default=[
            {
                "name": "query",
                "type": "string",
                "description": "The topic to search for in Tafsir Ibn Kathir. You will translate this query into English.",
            }
        ]
    )
    TAFSIR_TOOL_REQUIRED_PARAMS: list = Field(default=["query"])

    DISCORD_TOKEN: Optional[SecretStr] = Field(default=None)
    SENDGRID_API_KEY: Optional[SecretStr] = Field(default=None)
    LANGFUSE_SECRET_KEY: Optional[SecretStr] = Field(default=None)

    template_dir: DirectoryPath = Field(default="resources/templates")
    diskcache_dir: str = Field(default="diskcache_dir")

    MODEL: str = Field(default="gpt-4o")
    MAX_TOOL_TRIES: int = Field(default=3)
    MAX_FAILURES: int = Field(default=1)
    SYSTEM_PROMPT_FILE_NAME: str = Field(default="system_msg_tool")

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
