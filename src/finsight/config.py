"""Central settings for FinSight. Import `settings` anywhere you need config."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (src/finsight/config.py -> finsight/)
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"

# Put every .env value into os.environ.
# LangChain and LangSmith read OPENAI_API_KEY and LANGSMITH_* straight from the
# environment, so this must happen before any model is called.
load_dotenv(ENV_FILE)


class Settings(BaseSettings):
    """Typed config. Field names match .env keys (case-insensitive)."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Secrets: SecretStr hides the value if you ever print settings
    openai_api_key: SecretStr

    # Database
    database_url: str

    # Models, in "provider:model" format for init_chat_model / init_embeddings
    chat_model: str = "openai:gpt-4o-mini"          # small, fast tasks: router, HyDE, chunk context
    answer_model: str = "openai:gpt-5-mini"         # writes FinSight's answers (reasoning model, M6)
    embedding_model: str = "openai:text-embedding-3-small"
    judge_model: str = "openai:gpt-4.1-mini"

    # Observability
    langsmith_project: str = "finsight"

    @property
    def psycopg_url(self) -> str:
        """Plain psycopg wants 'postgresql://', not SQLAlchemy-style 'postgresql+psycopg://'."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")


settings = Settings()