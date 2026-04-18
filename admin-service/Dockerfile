FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir \
        "fastapi>=0.115.0" \
        "uvicorn>=0.34.0" \
        "sqlalchemy>=2.0.0" \
        "psycopg2-binary>=2.9.0" \
        "pydantic>=2.10.0" \
        "pydantic-settings>=2.6.0" \
        "python-dotenv>=1.0.0"

COPY src/ ./src/

ENV PYTHONPATH=/app/src

EXPOSE 8005

CMD ["uvicorn", "admin.main:app", "--host", "0.0.0.0", "--port", "8005"]
