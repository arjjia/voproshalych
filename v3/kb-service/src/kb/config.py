from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str = "postgres"
    db_port: int = 5432
    db_user: str = "voproshalych"
    db_password: str = "voproshalych"
    db_name: str = "voproshalych"
    kb_port: int = 8004
    litellm_url: str = "http://litellm:4000"
    litellm_master_key: str = "sk-litellm-master-key-v3"
    embedding_model: str = "deepvk/USER-bge-m3"
    top_k: int = 10
    llm_model: str = "mistral-nemo"
    classifier_model: str = "mistral-classifier"

    # Чанкинг (символы)
    max_chars: int = 500
    overlap: int = 50

    # Приоритет моделей (первая доступная = самая приоритетная)
    model_priority: list[str] = [
        "nemotron-super-or",
        "nemotron-ultra-free",
        "gpt-oss-or",
        "deepseek-v4-flash-free",
        "llama-70b-or",
        "qwen-coder-or",
        "gemma-31b-or",
        "hy3-free",
        "mimo-free",
        "code-free",
        "pickle-free",
        "glm-5.2",
        "mistral-nemo",
    ]

    model_config = {"env_file": ".env"}


settings = Settings()
