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
    embedding_model: str = "mistral-embed"
    chunk_size: int = 300
    chunk_overlap: int = 30
    top_k: int = 10
    llm_model: str = "mistral-nemo"
    classifier_model: str = "mistral-classifier"

    model_config = {"env_file": ".env"}


settings = Settings()
