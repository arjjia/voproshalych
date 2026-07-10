import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def vector_search(
    query_embedding: list[float],
    top_k: int = 10,
    workspace: str = "default",
    session: AsyncSession = None,
) -> list[dict]:
    sql = text("""
        SELECT
            c.id AS chunk_id,
            c.content,
            c.title,
            c.source_url,
            c.source_type,
            1 - (e.embedding <=> CAST(:query_embedding AS vector)) AS score
        FROM kb_chunks c
        JOIN kb_embeddings e ON e.chunk_id = c.id
        WHERE c.workspace = :workspace
        ORDER BY e.embedding <=> CAST(:query_embedding AS vector)
        LIMIT :top_k
    """)
    result = await session.execute(sql, {
        "query_embedding": "[" + ",".join(str(x) for x in query_embedding) + "]",
        "workspace": workspace,
        "top_k": top_k,
    })
    rows = result.fetchall()
    return [
        {
            "chunk_id": row.chunk_id,
            "content": row.content,
            "title": row.title,
            "source_url": row.source_url,
            "source_type": row.source_type,
            "score": float(row.score),
        }
        for row in rows
    ]


async def hybrid_search(
    query: str,
    query_embedding: list[float],
    top_k: int = 10,
    workspace: str = "default",
    session: AsyncSession = None,
) -> list[dict]:
    return await vector_search(
        query_embedding=query_embedding,
        top_k=top_k,
        workspace=workspace,
        session=session,
    )
