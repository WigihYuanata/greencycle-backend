from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str
    DATABASE_URL: str
    API_KEY_MESIN: str
    SECRET_KEY: str
    WHATSAPP_API_URL: str
    WHATSAPP_API_TOKEN: str
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str

    ALGORITHM: str="HS256"
    ORIGINS_DIIZINKAN: str="http://localhost:3000"
    BASE_URL: str="http://localhost:8000"

    model_config= SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings= Settings()