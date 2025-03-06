from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import DirectoryPath, Field, HttpUrl, PostgresDsn, SecretStr, field_validator
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

    DEPLOYMENT_TYPE: str = Field(default="development")
    SENTRY_DSN: HttpUrl | None = None

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

    # Settings for Tafsir Encyclopedia search tool
    TAFSIR_ENCYC_FN_NAME: str = Field(default="search_tafsir_encyc")
    TAFSIR_ENCYC_FN_DESCRIPTION: str = Field(
        default="""
        Searches specialized tafsir encyclopedias for scholarly interpretations of Quranic verses.
        This tool provides access to rich, contextual explanations from multiple scholarly sources,
        helping to understand deeper meanings and scholarly consensus on Quranic interpretation.
        The search will be based on the 'query' parameter, which must be provided.
        """,
    )
    TAFSIR_ENCYC_TOOL_PARAMS: list = Field(
        default=[
            {
                "name": "query",
                "type": "string",
                "description": "Topic or concept to search for within tafsir encyclopedias. Can be in Arabic or English.",
            },
        ],
    )
    TAFSIR_ENCYC_TOOL_REQUIRED_PARAMS: list = Field(default=["query"])

    # Settings for Usul Fiqh search tool
    USUL_FN_NAME: str = Field(default="search_usul")
    USUL_FN_DESCRIPTION: str = Field(
        default="""
        Searches principles of Islamic jurisprudence (usul al-fiqh) for scholarly methodologies
        and frameworks used to derive Islamic legal rulings. This tool provides access to 
        foundational concepts that govern how Islamic law is derived from primary sources.
        The search will be based on the 'query' parameter, which must be provided.
        """,
    )
    USUL_TOOL_PARAMS: list = Field(
        default=[
            {
                "name": "query",
                "type": "string",
                "description": "Principle, methodology, or concept to search for within usul al-fiqh texts.",
            },
        ],
    )
    USUL_TOOL_REQUIRED_PARAMS: list = Field(default=["query"])

    # Usul.ai API settings
    USUL_API_TOKEN: SecretStr = Field(default="")  # Set via environment variable
    USUL_BASE_URL: str = Field(default="https://semantic-search.usul.ai/v1/vector-search")
    USUL_TOOL_NAME_PREFIX: str = Field(default="search_usul")
    TAFSIR_ENCYC_BOOK_ID: str = Field(default="pet7s2sjr900zvxjsafa3s3b")
    TAFSIR_ENCYC_VERSION_ID: str = Field(default="MT3i8pDNoM")
    TAFSIR_ENCYC_TOOL_NAME: str = Field(default="search_tafsir_encyc")

    DISCORD_TOKEN: SecretStr | None = Field(default=None)
    SENDGRID_API_KEY: SecretStr | None = Field(default=None)
    QURAN_DOT_COM_API_KEY: SecretStr = Field(alias="QURAN_DOT_COM_API_KEY")
    WHATSAPP_API_VERSION: str | None = Field(default="v21.0")
    WHATSAPP_BUSINESS_PHONE_NUMBER_ID: SecretStr | None = Field(default=None)
    WHATSAPP_ACCESS_TOKEN_FROM_SYS_USER: SecretStr | None = Field(default=None)
    WHATSAPP_VERIFY_TOKEN_FOR_WEBHOOK: SecretStr | None = Field(default=None)
    WHATSAPP_CHAT_RETENTION_HOURS: float = Field(default=3)
    ZROK_SHARE_TOKEN: SecretStr = Field(default="")
    template_dir: DirectoryPath = Field(default=get_resource_path("templates"))
    diskcache_dir: str = Field(default="diskcache_dir")

    MODEL: str = Field(default="gpt-4o")
    MAX_TOOL_TRIES: int = Field(default=3)
    SYSTEM_PROMPT_FILE_NAME: str = Field(default="system_msg_tool")
    AYAH_SYSTEM_PROMPT_FILE_NAME: str = Field(default="system_msg_ayah")
    PROMPT_PATH: str = Field(default=str(get_resource_path("prompts")))
    AGENT: str = Field(default="AnsariClaude")
    ANTHROPIC_MODEL: str = Field(default="claude-3-7-sonnet-latest")
    LOGGING_LEVEL: str = Field(default="INFO")
    DEV_MODE: bool = Field(default=False)

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
