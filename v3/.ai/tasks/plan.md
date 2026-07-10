# Plan

## Статус: ✅ Все 9/9 curl smoke tests проходят

### Создано — новая архитектура v3

**kb-service/** — Собственная база знаний без LightRAG
- `src/kb/main.py` — FastAPI + JSON-RPC (POST /api/v1/tools), GET /health
- `src/kb/config.py` — Pydantic BaseSettings
- `src/kb/db.py` — async SQLAlchemy + asyncpg
- `src/kb/models.py` — KBChunk + KBEmbedding (pgvector, 1024d, HNSW index)
- `src/kb/chunking.py` — sentence-aware chunking (портирован из v2)
- `src/kb/embedding.py` — эмбеддинги через LiteLLM mistral-embed
- `src/kb/search.py` — pgvector cosine similarity (`<=>`)
- `src/kb/preprocessing.py` — классификация + расширение аббревиатур (портирован из v2 question_router.py)
- `src/kb/tools.py` — 4 MCP инструмента: kb_search, classify_query, kb_search_classified, store_document
- `src/kb/parsers/` — 10 файлов, портированы из v2 без изменений

**db/migration/versions/019_add_kb_tables.py** — Миграция: kb_chunks + kb_embeddings + HNSW index

**bot-vk/** — VK бот (vkbottle), портирован из v2. Вызывает agent-service POST /chat

**bot-max/** — Max бот (Go), портирован из v2. Вызывает agent-service POST /chat

**Обновлено:**
- `docker-compose.yml` — добавлены kb-service, bot-vk, bot-max; mcp-kb → kb-service
- `mcp-servers/src/kb/qa_client.py` — переписан на JSON-RPC к kb-service
- `.env` — KB_SERVICE_URL, VK_BOT_TOKEN, MAX_BOT_TOKEN

### Известные проблемы
- Mistral API key возвращает 429/401 — ключ в .env может быть невалидным
- Docker registry (docker.io) недоступен — пересборка образов невозможна без фикса
