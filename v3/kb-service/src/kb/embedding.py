import logging

import httpx

from kb.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)


async def get_embedding(text: str, settings: Settings | None = None) -> list[float]:
    s = settings or default_settings
    url = f"{s.litellm_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {s.litellm_master_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": s.embedding_model, "input": text}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Embedding HTTP error: {e.response.status_code} {e.response.text}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected embedding response format: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Embedding request failed: {e}")
            raise


async def get_embeddings_batch(texts: list[str], settings: Settings | None = None) -> list[list[float]]:
    s = settings or default_settings
    url = f"{s.litellm_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {s.litellm_master_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": s.embedding_model, "input": texts}

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            results = [None] * len(texts)
            for item in data["data"]:
                results[item["index"]] = item["embedding"]
            if any(r is None for r in results):
                missing = [i for i, r in enumerate(results) if r is None]
                logger.warning(f"Missing embeddings for indices: {missing}")
            return results
        except httpx.HTTPStatusError as e:
            logger.error(f"Batch embedding HTTP error: {e.response.status_code} {e.response.text}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected batch embedding response format: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Batch embedding request failed: {e}")
            raise
