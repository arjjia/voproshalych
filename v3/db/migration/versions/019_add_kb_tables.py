"""Добавить таблицы kb_chunks и kb_embeddings для собственной базы знаний.

Revision ID: 019_add_kb_tables
Revises: 018_admin_panel_hardening
Create Date: 2026-07-07
"""

from alembic import op

revision = "019_add_kb_tables"
down_revision = "018_admin_panel_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.execute(
        """
        CREATE TABLE kb_chunks (
            id VARCHAR PRIMARY KEY,
            workspace VARCHAR(255) NOT NULL DEFAULT 'default',
            doc_id VARCHAR(1024) NOT NULL,
            chunk_order_index INTEGER DEFAULT 0,
            tokens INTEGER DEFAULT 0,
            content TEXT NOT NULL,
            source_url TEXT,
            source_type VARCHAR(50),
            title TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            file_path TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE kb_embeddings (
            id SERIAL PRIMARY KEY,
            chunk_id VARCHAR NOT NULL UNIQUE REFERENCES kb_chunks(id) ON DELETE CASCADE,
            embedding vector(1024) NOT NULL,
            model VARCHAR(255) DEFAULT 'mistral-embed',
            created_at TIMESTAMPTZ DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX idx_kb_chunks_doc_id ON kb_chunks(doc_id);"
    )
    op.execute(
        "CREATE INDEX idx_kb_chunks_workspace ON kb_chunks(workspace);"
    )
    op.execute(
        "CREATE INDEX idx_kb_chunks_source_type ON kb_chunks(source_type);"
    )
    op.execute(
        "CREATE INDEX idx_kb_embeddings_chunk_id ON kb_embeddings(chunk_id);"
    )
    op.execute(
        "CREATE INDEX idx_kb_embeddings_vector ON kb_embeddings USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kb_embeddings CASCADE;")
    op.execute("DROP TABLE IF EXISTS kb_chunks CASCADE;")
