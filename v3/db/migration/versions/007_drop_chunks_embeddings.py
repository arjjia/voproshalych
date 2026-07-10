"""Удалить таблицы chunks и embeddings.

Переходим полностью на LightRAG для хранения чанков и эмбеддингов.

Revision ID: 007_drop_chunks_embeddings
Revises: 006_chunks_source_url_length
Create Date: 2026-04-16

"""

from alembic import op

revision = "007_drop_chunks_embeddings"
down_revision = "006_chunks_source_url_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS embeddings CASCADE;")
    op.execute("DROP TABLE IF EXISTS chunks CASCADE;")
    op.execute("DROP TABLE IF EXISTS kb_documents_registry CASCADE;")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE chunks (
            id UUID PRIMARY KEY,
            text TEXT NOT NULL,
            source_url TEXT,
            source_type VARCHAR(50),
            title TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE TABLE embeddings (
            chunk_id UUID REFERENCES chunks(id) ON DELETE CASCADE,
            embedding JSONB,
            embedding_vector vector(1024),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX idx_embeddings_vector ON embeddings 
        USING ivfflat (embedding_vector vector_cosine_ops) WITH (lists = 100);
    """)