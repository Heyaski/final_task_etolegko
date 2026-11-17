from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    keitaro_base_url: str = "https://tdgk.host"
    keitaro_api_key: str = ""
    database_url: str = f"sqlite:///{DATA_DIR / 'app.db'}"
    domain_name: str = "kylovoa.com"
    group_name: str = "FORTESTS"
    source_name: str = "FORTESTS"
    timezone: str = "Europe/Moscow"
    keitaro_mock: bool = False


settings = Settings()
