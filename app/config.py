from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RAG Chatbot"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"

    azure_sql_connection_string: str = (
        "mssql+pyodbc://@localhost/RAGChatbotDB?driver=ODBC+Driver+18+for+SQL+Server"
    )

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    rag_top_k: int = 4

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
