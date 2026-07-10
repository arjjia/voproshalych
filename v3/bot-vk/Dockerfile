FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling && pip install --no-cache-dir .
COPY src/ src/
CMD ["python", "-m", "bot_vk"]
