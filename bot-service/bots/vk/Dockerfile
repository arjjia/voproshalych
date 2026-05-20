FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /tmp/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --no-build-isolation "/tmp[vk]"

COPY bots/vk /app

CMD ["python", "bot.py"]
