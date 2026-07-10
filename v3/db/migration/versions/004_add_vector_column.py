"""Добавить колонку embedding_vector для pgvector.

Добавляет поддержку векторного поиска в PostgreSQL:
1. Создаёт новую колонку embedding_vector с типом vector(1024)
2. Конвертирует существующие данные из JSON в векторный формат
3. Создаёт индекс IVFFlat для быстрого поиска по векторам

Зачем это нужно:
    - Позволяет выполнять семантический поиск через косинусное сходство
    - Ищем "похожие" документы, а не точные совпадения
    - Работает на основе эмбеддингов (векторных представлений текста)

Пример использования:
    # Найти документы похожие на вопрос
    SELECT c.*
    FROM chunks c
    JOIN embeddings e ON c.id = e.chunk_id
    ORDER BY e.embedding_vector <=> [0.1, 0.2, ...]::vector
    LIMIT 5

Тип vector(1024):
    - 1024 dimensions (соответствует модели deepvk/USER-bge-m3)
    - Поддерживает операции: <=> (косинусное сходство), <= (L2), <# (inner product)

Индекс IVFFlat:
    - Approximate Nearest Neighbor (ANN) индекс
    - Быстрый поиск, но с небольшой погрешностью
    - lists = 100 - количество кластеров (подбирается под размер данных)

Revision ID: 004_add_vector_column
Revises: 003_users_ts_defaults
Create Date: 2026-03-24
"""

from alembic import op


revision = "004_add_vector_column"
down_revision = "003_users_ts_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавить векторную колонку и индекс для семантического поиска.

    Этапы:
    1. Добавить колонку embedding_vector типа vector(1024)
    2. Конвертировать данные из JSON в вектор
    3. Создать IVFFlat индекс для быстрого поиска

    Примечание:
        Конвертация из JSON работает если данные хранились как массив чисел.
        Если данные в другом формате, миграция может потребовать корректировки.
    """
    # Добавить векторную колонку
    op.execute("""
        ALTER TABLE embeddings 
        ADD COLUMN embedding_vector vector(1024)
    """)

    # Конвертировать JSON в вектор (если есть данные)
    op.execute("""
        UPDATE embeddings 
        SET embedding_vector = 
            (SELECT array_agg(elem::float) 
             FROM jsonb_array_elements_text(embedding::jsonb) AS elem)
        WHERE embedding IS NOT NULL
    """)

    # Создать индекс для векторного поиска
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_vector 
        ON embeddings USING ivfflat (embedding_vector vector_cosine_ops)
        WITH (lists = 100)
    """)


def downgrade() -> None:
    """Удалить векторную колонку и индекс.

    Внимание: после отката векторный поиск будет недоступен!
    """
    op.execute("DROP INDEX IF EXISTS idx_embeddings_vector")
    op.execute("ALTER TABLE embeddings DROP COLUMN IF EXISTS embedding_vector")
