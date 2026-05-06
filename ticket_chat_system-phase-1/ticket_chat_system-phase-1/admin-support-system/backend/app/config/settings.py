from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "ticket_support_db"
    # URL of the customer backend — used to forward typing events cross-service
    CUSTOMER_BACKEND_URL: str = "http://localhost:8000"
    # PRODUCTION: use ALLOWED_ORIGINS env var (comma-separated)
    # ALLOWED_ORIGINS: str = "https://your-admin.vercel.app"
    REDIS_URL: str = "redis://localhost:6379/1"

    class Config:
        env_file = ".env"


settings = Settings()
