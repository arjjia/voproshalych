"""Очистка базы знаний: удаляет все чанки и эмбеддинги.

Использование:
  python scripts/clear_kb.py --db-host localhost --db-port 5433

Через psql (без Python):
  docker compose exec postgres psql -U voproshalych -d voproshalych \
    -c "TRUNCATE kb_embeddings CASCADE; TRUNCATE kb_chunks CASCADE;"
"""

import argparse
import asyncio
import os

import asyncpg

DB_HOST = os.environ.get("POSTGRES_HOST", "postgres")
DB_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
DB_USER = os.environ.get("POSTGRES_USER", "voproshalych")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "voproshalych")
DB_NAME = os.environ.get("POSTGRES_DB", "voproshalych")


async def clear_knowledge_base(host, port, user, password, dbname):
    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=dbname,
    )

    try:
        emb_count = await conn.fetchval("SELECT COUNT(*) FROM kb_embeddings")
        chunk_count = await conn.fetchval("SELECT COUNT(*) FROM kb_chunks")

        print(f"Найдено: {chunk_count} чанков, {emb_count} эмбеддингов")
        print("Очистка...")

        await conn.execute("TRUNCATE TABLE kb_embeddings CASCADE")
        print("  ✓ kb_embeddings очищена")

        await conn.execute("TRUNCATE TABLE kb_chunks CASCADE")
        print("  ✓ kb_chunks очищена")

        print("Готово. База знаний пуста.")
    except Exception as e:
        print(f"Ошибка: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Очистка базы знаний")
    parser.add_argument("--db-host", default=DB_HOST)
    parser.add_argument("--db-port", type=int, default=DB_PORT)
    parser.add_argument("--db-user", default=DB_USER)
    parser.add_argument("--db-password", default=DB_PASSWORD)
    parser.add_argument("--db-name", default=DB_NAME)
    args = parser.parse_args()

    asyncio.run(
        clear_knowledge_base(
            host=args.db_host,
            port=args.db_port,
            user=args.db_user,
            password=args.db_password,
            dbname=args.db_name,
        )
    )
