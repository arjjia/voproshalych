"""Конфигурация agent-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    agent_port: int = 8001

    litellm_url: str = "http://litellm:4000"
    litellm_master_key: str = "sk-litellm-master-key-v3"
    llm_model: str = "mistral-nemo"
    classifier_model: str = "mistral-classifier"
    embedding_model: str = "mistral-embed"

    mcp_kb_url: str = "http://mcp-kb:9010"
    mcp_news_url: str = "http://mcp-news:9011"
    mcp_contacts_url: str = "http://mcp-contacts:9012"
    mcp_library_url: str = "http://mcp-library:9013"
    mcp_sveden_url: str = "http://mcp-sveden:9014"

    model_config = {"env_prefix": "", "env_file": ".env.v3", "extra": "ignore"}


settings = Settings()
