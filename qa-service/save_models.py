"""Скачивает и кэширует модели при сборке Docker."""

import os

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "deepvk/USER-bge-m3"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


def main() -> None:
    hf_token = os.getenv("HF_TOKEN")
    print(f"Using HuggingFace token: {'yes' if hf_token else 'no (anonymous)'}")

    print(f"Downloading embedding model: {EMBEDDING_MODEL}")
    emb = SentenceTransformer(EMBEDDING_MODEL)
    print(f"Embedding dim: {emb.get_sentence_embedding_dimension()}")

    if os.getenv("RERANKER_ENABLED", "true").lower() == "true":
        from sentence_transformers import CrossEncoder

        print(f"Downloading reranker model: {RERANKER_MODEL}")
        reranker = CrossEncoder(RERANKER_MODEL, max_length=512)
        print(f"Reranker max_length: {reranker.max_length}")
    else:
        print("RERANKER_ENABLED != true, skipping reranker download")

    print("Done.")


if __name__ == "__main__":
    main()
