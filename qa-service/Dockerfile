FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen

RUN uv pip install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch --force-reinstall

COPY save_models.py ./
RUN --mount=type=secret,id=hf_token \
    --mount=type=cache,target=/hf-cache \
    sh -c 'export HF_TOKEN="$(cat /run/secrets/hf_token)" && \
           export HF_HOME=/hf-cache && \
           export TRANSFORMERS_CACHE=/hf-cache && \
           export PYTHONUNBUFFERED=1 && \
           uv run python -u save_models.py && \
           mkdir -p /root/.cache && \
           rm -rf /root/.cache/huggingface && \
           cp -a /hf-cache /root/.cache/huggingface'

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY benchmarks/ ./benchmarks/

ENV PYTHONPATH=/app/src

EXPOSE 8004

CMD ["uv", "run", "uvicorn", "qa.main:app", "--host", "0.0.0.0", "--port", "8004", "--log-level", "info"]
