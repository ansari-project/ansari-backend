from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import DirectoryPath, Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Can't use get_logger() here due to circular import
# logger = get_logger()


class Settings(BaseSettings):
    """Field value precedence in Pydantic Settings (highest to lowest priority):

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

    def get_resource_path(filename):
        # Get the directory of the current script
        script_dir = Path(__file__).resolve()
        # Construct the path to the resources directory
        resources_dir = script_dir.parent / "resources"
        # Construct the full path to the resource file
        path = resources_dir / filename
        return path

    DATABASE_URL: PostgresDsn = Field(
        default="postgresql://postgres:password@localhost:5432/ansari",
    )
    MAX_THREAD_NAME_LENGTH: int = Field(default=100)

    SECRET_KEY: SecretStr = Field(default="secret")
    # Literal ensures the allowed value(s), and frozen ensures it can't be changed after initialization
    ALGORITHM: Literal["HS256"] = Field(default="HS256", frozen=True)
    ENCODING: Literal["utf-8"] = Field(default="utf-8", frozen=True)
    ACCESS_TOKEN_EXPIRY_HOURS: int = Field(default=2)
    REFRESH_TOKEN_EXPIRY_HOURS: int = Field(default=24 * 90)

    # Will later contain ZROK_SHARE_TOKEN and localhost origins
    ORIGINS: str | list[str] = Field(
        default=["https://ansari.chat", "http://ansari.chat"],
    )
    API_SERVER_PORT: int = Field(default=8000)

    OPENAI_API_KEY: SecretStr
    ANTHROPIC_API_KEY: SecretStr
    PGPASSWORD: SecretStr = Field(default="password")
    KALEMAT_API_KEY: SecretStr

    VECTARA_API_KEY: SecretStr

    MAX_FAILURES: int = Field(default=3)

    MAWSUAH_VECTARA_CORPUS_KEY: str = Field(
        alias="MAWSUAH_VECTARA_CORPUS_KEY",
        default="mawsuah_unstructured",
    )
    MAWSUAH_FN_NAME: str = Field(default="search_mawsuah")
    MAWSUAH_FN_DESCRIPTION: str = Field(
        default="Search and retrieve relevant rulings "
        "from the Islamic jurisprudence (fiqh) encyclopedia based on a specific topic. "
        "Returns a list of potentially relevant matches that may span multiple paragraphs. "
        "The search will be based on the 'query' parameter, which must be provided.",
    )
    MAWSUAH_TOOL_PARAMS: list = Field(
        default=[
            {
                "name": "query",
                "type": "string",
                "description": "Topic or subject matter to search for "
                "within the fiqh encyclopedia. Write the query in Arabic.",
            },
        ],
    )
    MAWSUAH_TOOL_REQUIRED_PARAMS: list = Field(default=["query"])

    TAFSIR_VECTARA_CORPUS_KEY: str = Field(
        alias="TAFSIR_VECTARA_CORPUS_KEY",
        default="tafsirs",
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
        """,
    )
    TAFSIR_TOOL_PARAMS: list = Field(
        default=[
            {
                "name": "query",
                "type": "string",
                "description": "The topic to search for in Tafsir Ibn Kathir. You will translate this query into English.",
            },
        ],
    )
    TAFSIR_TOOL_REQUIRED_PARAMS: list = Field(default=["query"])

    DISCORD_TOKEN: SecretStr | None = Field(default=None)
    SENDGRID_API_KEY: SecretStr | None = Field(default=None)
    QURAN_DOT_COM_API_KEY: SecretStr = Field(alias="QURAN_DOT_COM_API_KEY")
    WHATSAPP_RECIPIENT_WAID: SecretStr | None = Field(default=None)
    WHATSAPP_API_VERSION: str | None = Field(default="v21.0")
    WHATSAPP_BUSINESS_PHONE_NUMBER_ID: SecretStr | None = Field(default=None)
    WHATSAPP_TEST_BUSINESS_PHONE_NUMBER_ID: SecretStr | None = Field(default=None)
    WHATSAPP_ACCESS_TOKEN_FROM_SYS_USER: SecretStr | None = Field(default=None)
    WHATSAPP_VERIFY_TOKEN_FOR_WEBHOOK: SecretStr | None = Field(default=None)
    WHATSAPP_CHAT_RETENTION_HOURS: int = Field(default=3)  # This is hardcoded to 0.05 when DEBUG_MODE is True
    ZROK_SHARE_TOKEN: SecretStr = Field(default="")
    template_dir: DirectoryPath = Field(default=get_resource_path("templates"))
    diskcache_dir: str = Field(default="diskcache_dir")

    MODEL: str = Field(default="gpt-4o")
    MAX_TOOL_TRIES: int = Field(default=3)
    SYSTEM_PROMPT_FILE_NAME: str = Field(default="system_msg_tool")
    AYAH_SYSTEM_PROMPT_FILE_NAME: str = Field(default="system_msg_ayah")
    PROMPT_PATH: str = Field(default=str(get_resource_path("prompts")))
    AGENT: str = Field(default="AnsariClaude")
    ANTHROPIC_MODEL: str = Field(default="claude-3-5-sonnet-latest")
    LOGGING_LEVEL: str = Field(default="INFO")
    DEBUG_MODE: bool = Field(default=False)

    @field_validator("ORIGINS")
    def parse_origins(cls, v):
        if isinstance(v, str):
            origins = [origin.strip() for origin in v.strip('"').split(",")]
        elif isinstance(v, list):
            origins = v
        else:
            raise ValueError(
                f"Invalid ORIGINS format: {v}. Expected a comma-separated string or a list.",
            )
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
