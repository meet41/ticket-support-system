from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "ticket_support_db"
    CUSTOMER_BACKEND_URL: str = "http://localhost:8000"

    # AI / RAG settings
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_CHUNK_SIZE: int = 500
    RAG_TOP_K: int = 5
    RAG_MAX_CONTEXT_TOKENS: int = 3000

    class Config:
        env_file = ".env"


settings = Settings()