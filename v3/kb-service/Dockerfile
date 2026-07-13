FROM python:3.12-slim-bookworm

WORKDIR /app

COPY pyproject.toml ./

# Основные Python-зависимости
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    "sqlalchemy[asyncio]" \
    asyncpg \
    pgvector \
    httpx \
    pydantic \
    pydantic-settings \
    beautifulsoup4 \
    lxml \
    pdfplumber \
    pytesseract \
    Pillow \
    python-multipart \
    "numpy>=2.0.0" \
    "sentence-transformers>=3.0.0"

COPY src/ src/
COPY tests/ tests/

ENV PYTHONPATH="/app/src:${PYTHONPATH}"
ENV HF_HOME="/hf-cache"

# torch (CPU-сборка) — отдельным шагом из CPU-индекса
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Предзагрузка модели deepvk/USER-bge-m3 при сборке
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('deepvk/USER-bge-m3'); print('model preloaded')" \
    || echo "WARN: model preload skipped"

RUN pip install --no-cache-dir "pytest>=8.0.0" "pytest-asyncio>=0.24.0"

EXPOSE 8004

CMD ["uvicorn", "kb.main:app", "--host", "0.0.0.0", "--port", "8004"]
