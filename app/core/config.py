from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str
    DATABASE_URL: str
    API_KEY_MESIN: str

    model_config= SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings= Settings()