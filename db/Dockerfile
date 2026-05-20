FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml src/ ./src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "sqlalchemy>=2.0.0" \
        "alembic>=1.13.0" \
        "psycopg2-binary>=2.9.0" \
        "python-dotenv>=1.0.0"

COPY alembic.ini migration/ ./

ENV PYTHONPATH=/app/src

CMD ["alembic", "upgrade", "head"]
