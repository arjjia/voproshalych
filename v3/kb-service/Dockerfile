FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    sqlalchemy[asyncio] \
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
    pdfminer.six

COPY src/ src/

ENV PYTHONPATH="/app/src:${PYTHONPATH}"

EXPOSE 8004

CMD ["uvicorn", "kb.main:app", "--host", "0.0.0.0", "--port", "8004"]
