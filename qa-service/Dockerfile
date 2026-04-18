FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY pyproject.toml ./

ENV UV_SYSTEM_PYTHON=1
ENV UV_LINK_MODE=copy

RUN uv pip install --system langchain-core langchain-text-splitters pydantic-settings gigachat

RUN uv sync

COPY save_models.py ./
RUN test -f /run/secrets/hf_token && HF_TOKEN=$(cat /run/secrets/hf_token) uv run python save_models.py || uv run python save_models.py

COPY src/ ./src/
COPY scripts/ ./scripts/

ENV PYTHONPATH=/app/src:/usr/local/lib/python3.12/site-packages
ENV HF_TOKEN=${HF_TOKEN:-}

EXPOSE 8004

CMD ["uv", "run", "uvicorn", "qa.main:app", "--host", "0.0.0.0", "--port", "8004", "--log-level", "info"]
