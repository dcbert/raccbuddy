"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """RaccBuddy configuration loaded from environment."""

    # Telegram
    telegram_bot_token: str = ""
    owner_telegram_id: int = 0  # Set after first /start to lock the bot

    # WhatsApp
    owner_whatsapp_number: str = ""  # Owner's WhatsApp number for recognition

    # Database
    database_url: str = (
        "postgresql+asyncpg://raccbuddy:raccbuddy@localhost:5432/raccbuddy"
    )

    # LLM provider selection ("ollama", "xai", …)
    llm_provider: str = "ollama"

    # Embedding provider selection ("ollama", "xai", …)
    # Default to ollama for embeddings regardless of main LLM provider
    embedding_provider: str = "ollama"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_embed_model: str = "nomic-embed-text"

    # xAI (Grok)
    xai_api_key: str = ""
    xai_model: str = "grok-3-mini"
    xai_embed_model: str = "v1"
    xai_embed_dimensions: int = 768

    # Token limits
    max_context_tokens: int = 2000
    max_summary_words: int = 150

    # REST API
    api_port: int = 8000

    # Nudges
    nudge_check_interval_minutes: int = 60

    # Memory retention
    owner_memory_retention_days: int = 90

    # Sentiment / mood model (Ollama)
    sentiment_model: str = "llama3.2:3b"

    # Relationship scoring weights
    rel_weight_frequency: float = 0.30
    rel_weight_recency: float = 0.30
    rel_weight_sentiment: float = 0.25
    rel_weight_reply_rate: float = 0.15

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
