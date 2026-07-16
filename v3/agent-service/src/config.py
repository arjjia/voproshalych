"""Конфигурация agent-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    agent_port: int = 8001

    litellm_url: str = "http://litellm:4000"
    litellm_master_key: str = "sk-litellm-master-key-v3"

    # Приоритет моделей (первая доступная = самая приоритетная)
    model_priority: list[str] = [
        "nemotron-ultra-free",
        "nemotron-super-or",
        "gpt-oss-or",
        "deepseek-v4-flash-free",
        "llama-70b-or",
        "qwen-coder-or",
        "gemma-31b-or",
        "hy3-free",
        "mimo-free",
        "mistral-nemo",
        "code-free",
        "pickle-free",
    ]

    mcp_kb_url: str = "http://mcp-kb:9010"
    mcp_news_url: str = "http://mcp-news:9011"
    mcp_fetch_url: str = "http://mcp-fetch:9015"

    model_config = {"env_prefix": "", "env_file": ".env.v3", "extra": "ignore"}


settings = Settings()
