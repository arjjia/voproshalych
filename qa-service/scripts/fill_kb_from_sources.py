"""Скрипт для заполнения Базы Знаний из источников.

Запускается вручную. Инкрементально обрабатывает документы:
парсит 1 PDF → чанки → эмбеддинги батчами → сохраняет в БД.

Аргументы:
    --clear   Очистить таблицы перед заполнением
    --resume  Продолжить с последнего места (инкрементально)
    --append  Добавить данные без проверки существующих документов
    --source  Индексировать только выбранный источник

Пример использования:
    # Очистить и заполнить с нуля (все источники)
    python scripts/fill_kb_from_sources.py --clear

    # Продолжить с последнего места
    python scripts/fill_kb_from_sources.py --resume

    # Добавить только Confluence Study поверх текущих данных
    python scripts/fill_kb_from_sources.py --append --source confluence_study
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from sqlalchemy import create_engine, text

from qa.kb.chunking import Chunk, TextChunker
from qa.kb.config import get_kb_config
from qa.kb.embedding import get_embeddings_batch
from qa.kb.parsers import ConfluenceParser, ConfluenceStudyParser, SvedenParser, UtmnParser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def sanitize_title(title: str) -> str:
    """Очистить и обрезать заголовок документа.

    Выполняет URL-decoding и удаляет непечатные символы.

    Args:
        title: Заголовок документа

    Returns:
        Очищенный заголовок
    """
    title = unquote(title)
    title = re.sub(r"[\x00-\x1f\x7f]", "", title)
    return title


def sanitize_url(url: str) -> str:
    """Очистить URL от непечатных символов.

    Args:
        url: URL документа

    Returns:
        Очищенный URL
    """
    return re.sub(r"[\x00-\x1f\x7f]", "", url)


def normalize_url(url: str) -> str:
    """Нормализовать URL для дедупликации.

    Нормализация помогает корректно сравнивать URL в --resume:
    - http -> https
    - удаление query/fragment
    - приведение хоста к lowercase
    - удаление префикса www.
    - нормализация percent-encoding в пути
    """
    if not url:
        return ""

    try:
        parsed = urlsplit(url.strip())
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        path = unquote(parsed.path or "/")
        path = re.sub(r"/+", "/", path)
        path = path.rstrip("/") or "/"
        path = re.sub(r"\.pdf$", ".pdf", path, flags=re.IGNORECASE)
        path = quote(path, safe="/-._~")

        return urlunsplit(("https", host, path, "", ""))
    except Exception:
        return url.strip()


def make_doc_key(source_type: str, file_url: str | None, page_url: str, title: str) -> str:
    """Сформировать стабильный ключ документа для инкрементальной индексации."""
    base = normalize_url(file_url or page_url)
    if not base:
        base = f"{source_type}:{sanitize_title(title)}"
    payload = f"{source_type}:{base}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class Config:
    """Конфигурация источников для заполнения Базы Знаний.

    Содержит URL страниц с которых парсятся PDF документы.
    """

    confluence_pages: list[str] = field(
        default_factory=lambda: [
            "https://confluence.utmn.ru/pages/viewpage.action?pageId=8037875",
            "https://confluence.utmn.ru/pages/viewpage.action?pageId=121897057",
        ]
    )
    """Страницы Confluence с PDF документами."""

    sveden_url: str = "https://sveden.utmn.ru/sveden/document/"
    """URL страницы Сведения об организации."""

    utmn_pages: list[str] = field(
        default_factory=lambda: [
            "https://www.utmn.ru/obrazovanie/normativnye-dokumenty/normativnye-dokumenty-tyumgu/otkrytie-op-vo/",
            "https://www.utmn.ru/obrazovanie/normativnye-dokumenty/normativnye-dokumenty-tyumgu/op-vo/",
            "https://www.utmn.ru/obrazovanie/normativnye-dokumenty/normativnye-dokumenty-tyumgu/op-vo-iot/",
            "https://www.utmn.ru/obrazovanie/normativnye-dokumenty/normativnye-dokumenty-tyumgu/gia/",
            "https://www.utmn.ru/obrazovanie/normativnye-dokumenty/normativnye-dokumenty-tyumgu/kontingent/",
            "https://www.utmn.ru/obrazovanie/normativnye-dokumenty/normativnye-dokumenty-tyumgu/praktika/",
            "https://www.utmn.ru/obrazovanie/normativnye-dokumenty/normativnye-dokumenty-tyumgu/uregulirovanie-sporov/",
            "https://www.utmn.ru/obrazovanie/normativnye-dokumenty/normativnye-dokumenty-tyumgu/rezhim-zanyatiy/",
            "https://www.utmn.ru/obrazovanie/normativnye-dokumenty/normativnye-dokumenty-tyumgu/vyshestoyashchikh-organizatsiy/",
            "https://www.utmn.ru/o-tyumgu/organizatsionnaya-skhema-tyumgu/finance/ubnu/dokumenty/",
            "https://www.utmn.ru/o-tyumgu/organizatsionnaya-skhema-tyumgu/finance/economicplan/dokumenty/",
            "https://www.utmn.ru/obrazovanie/oplata-za-obuchenie/stoimost-obucheniya/",
            "https://www.utmn.ru/studentam/obshchezhitiya/studencheskie-obshchezhitiya/stoimost-i-oplata/",
            "https://www.utmn.ru/o-tyumgu/kontaktnaya-informatsiya/",
            "https://www.utmn.ru/aspirantam/aspirantura/dokumenty/",
            "https://www.utmn.ru/obrazovanie/inklyuzivnoe-obrazovanie/dokumenty/",
            "https://www.utmn.ru/o-tyumgu/organizatsionnaya-skhema-tyumgu/upravlenie-po-rabote-s-personalom/struktura/sluzhba-dokumentatsionnogo-obespecheniya/dokumenty-po-deloproizvodstvu/",
            "https://www.utmn.ru/o-tyumgu/organizatsionnaya-skhema-tyumgu/tsentr-informatsionnykh-tekhnologiy/dokumenty/",
            "https://www.utmn.ru/studentam/obshchezhitiya/studencheskie-obshchezhitiya/normativnye-dokumenty/",
            "https://www.utmn.ru/obrazovanie/oplata-za-obuchenie/obraztsy-dogovorov-ob-oplate/",
            "https://www.utmn.ru/o-tyumgu/organizatsionnaya-skhema-tyumgu/kontraktnaya-sluzhba/lokalnye-akty/",
            "https://www.utmn.ru/o-tyumgu/ofitsialnye-dokumenty/prikazy/",
            "https://www.utmn.ru/o-tyumgu/ofitsialnye-dokumenty/federalnye-dokumenty/",
        ]
    )


@dataclass
class Document:
    """Модель документа для обработки.

    Attributes:
        url: user-facing URL страницы источника
        title: Название документа
        text_content: Текстовое содержимое
        source_type: Тип источника (confluence/sveden/utmn)
        file_url: Прямой URL файла (если документ получен из PDF)
    """

    url: str
    title: str
    text_content: str
    source_type: str
    file_url: str | None = None


@dataclass
class ChunkWithMeta:
    """Чанк с метаданными для сохранения в БД.

    Attributes:
        chunk: Объект чанка
        source_type: Тип источника
        document_title: Название документа
    """

    chunk: Chunk
    source_type: str
    document_title: str


def get_db_engine():
    """Создать подключение к базе данных.

    Определяет хост PostgreSQL (docker или localhost) и создаёт движок SQLAlchemy.

    Returns:
        SQLAlchemy Engine для подключения к БД
    """
    import socket

    try:
        socket.gethostbyname("postgres")
        docker_host = "postgres"
    except socket.gaierror:
        docker_host = "localhost"

    env_host = os.getenv("POSTGRES_HOST", "")

    if env_host in ("", "localhost"):
        host = docker_host
    else:
        host = env_host

    db = os.getenv("POSTGRES_DB", "voproshalych")
    user = os.getenv("POSTGRES_USER", "voproshalych")
    password = os.getenv("POSTGRES_PASSWORD", "voproshalych")
    port = os.getenv("POSTGRES_PORT", "5432")

    db_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    logger.info(f"Подключение к БД: {host}:{port}/{db}")
    return create_engine(db_url)


def ensure_registry_table(engine) -> None:
    """Создать таблицу реестра обработанных документов (для resume)."""
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS kb_documents_registry (
                    doc_key TEXT PRIMARY KEY,
                    source_type VARCHAR(50) NOT NULL,
                    page_url TEXT,
                    file_url TEXT,
                    title TEXT,
                    chunks_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.commit()


def load_existing_doc_keys(engine) -> set[str]:
    """Загрузить ключи уже обработанных документов.

    Источники ключей:
    1. Реестр kb_documents_registry (основной)
    2. Legacy fallback из chunks.source_url
    """
    doc_keys: set[str] = set()

    with engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT doc_key FROM kb_documents_registry"))
            doc_keys.update(row[0] for row in result if row[0])
        except Exception:
            pass

        result = conn.execute(
            text(
                "SELECT DISTINCT source_type, source_url FROM chunks WHERE source_url IS NOT NULL"
            )
        )
        for row in result:
            legacy_key = make_doc_key(row.source_type or "unknown", row.source_url, row.source_url, "")
            doc_keys.add(legacy_key)

    logger.info(f"В реестре уже есть {len(doc_keys)} обработанных документов")
    return doc_keys


def upsert_document_registry(engine, doc: Document, doc_key: str, chunks_count: int) -> None:
    """Сохранить документ в реестр обработанных документов."""
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO kb_documents_registry (
                    doc_key, source_type, page_url, file_url, title, chunks_count
                ) VALUES (
                    :doc_key, :source_type, :page_url, :file_url, :title, :chunks_count
                )
                ON CONFLICT (doc_key) DO UPDATE SET
                    page_url = EXCLUDED.page_url,
                    file_url = EXCLUDED.file_url,
                    title = EXCLUDED.title,
                    chunks_count = EXCLUDED.chunks_count,
                    updated_at = NOW()
                """
            ),
            {
                "doc_key": doc_key,
                "source_type": doc.source_type,
                "page_url": sanitize_url(doc.url),
                "file_url": sanitize_url(doc.file_url) if doc.file_url else None,
                "title": sanitize_title(doc.title),
                "chunks_count": chunks_count,
            },
        )
        conn.commit()


def clear_tables(engine) -> None:
    """Очистить таблицы чанков и эмбеддингов.

    Выполняет TRUNCATE с удалением связанных записей.

    Args:
        engine: SQLAlchemy Engine
    """
    logger.info("Очистка таблиц chunks, embeddings и реестра документов...")

    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE embeddings CASCADE"))
        conn.execute(text("TRUNCATE TABLE chunks RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE kb_documents_registry"))
        conn.commit()

    logger.info("Таблицы очищены")


def save_chunks_batch(
    engine,
    chunks_with_meta: list[ChunkWithMeta],
    embeddings: list[list[float]],
) -> int:
    """Сохранить чанки и эмбеддинги в базу данных.

    Выполняет вставку в таблицы chunks и embeddings с применением
    sanitize функций для заголовков и URL.

    Args:
        engine: SQLAlchemy Engine
        chunks_with_meta: Список чанков с метаданными
        embeddings: Список векторов эмбеддингов

    Returns:
        Количество сохранённых чанков
    """
    count = len(chunks_with_meta)
    logger.info(f"  → Сохранение {count} чанков в БД...")

    chunk_rows = []
    embedding_rows = []

    for item, embedding in zip(chunks_with_meta, embeddings):
        chunk_id = str(uuid.uuid4())
        chunk_rows.append(
            {
                "id": chunk_id,
                "text": item.chunk.text,
                "source_url": sanitize_url(item.chunk.source_url),
                "source_type": item.source_type,
                "title": sanitize_title(item.document_title),
            }
        )
        embedding_rows.append(
            {
                "chunk_id": chunk_id,
                "embedding": json.dumps(embedding),
            }
        )

    if not chunk_rows:
        return 0

    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO chunks (id, text, source_url, source_type, title)
                    VALUES (:id, :text, :source_url, :source_type, :title)
                    """
                ),
                chunk_rows,
            )
            conn.execute(
                text(
                    """
                    INSERT INTO embeddings (chunk_id, embedding)
                    VALUES (:chunk_id, :embedding)
                    """
                ),
                embedding_rows,
            )
            conn.commit()
    except Exception as e:
        logger.error(f"  → Ошибка батч-сохранения чанков: {e}")
        return 0

    saved_count = len(chunk_rows)
    logger.info(f"  → Сохранено {saved_count} чанков")
    return saved_count


def chunk_document(
    doc: Document,
    chunker: TextChunker,
) -> list[ChunkWithMeta]:
    """Разбить документ на чанки.

    Args:
        doc: Документ для разбиения
        chunker: Объект TextChunker

    Returns:
        Список чанков с метаданными
    """
    chunks = list(
        chunker.chunk_text(
            text=doc.text_content,
            source_url=doc.url,
            title=doc.title,
        )
    )
    return [
        ChunkWithMeta(chunk=c, source_type=doc.source_type, document_title=doc.title)
        for c in chunks
    ]


def process_document(
    engine,
    chunker: TextChunker,
    doc: Document,
    doc_idx: int,
) -> int:
    """Обработать один документ: чанки → эмбеддинги → сохранение в БД."""

    chunks = chunk_document(doc, chunker)

    if not chunks:
        logger.warning(f"[{doc_idx}] Документ '{doc.title}' без чанков")
        return 0

    EMBEDDING_BATCH = int(os.getenv("KB_EMBEDDING_BATCH_SIZE", "32"))
    total_saved = 0

    for start in range(0, len(chunks), EMBEDDING_BATCH):
        batch = chunks[start : start + EMBEDDING_BATCH]
        texts = [item.chunk.text for item in batch]
        logger.info(f"  → Эмбеддинги для {len(batch)} чанков...")
        embeddings = get_embeddings_batch(texts)
        saved = save_chunks_batch(engine, batch, embeddings)
        total_saved += saved

    logger.info(f"[{doc_idx}] Сохранён: '{doc.title}' — {total_saved} чанков")
    return total_saved


async def run_source(
    engine,
    chunker: TextChunker,
    source_name: str,
    get_docs_func,
    existing_doc_keys: set[str],
    skip_existing: bool = True,
) -> tuple[int, int]:
    """Обработать все документы из источника инкрементально."""

    logger.info(f"\n{'=' * 50}")
    logger.info(f"Источник: {source_name}")
    logger.info(f"{'=' * 50}")

    total_docs = 0
    total_chunks = 0
    skipped = 0

    async for doc in get_docs_func():
        doc_key = make_doc_key(doc.source_type, doc.file_url, doc.url, doc.title)

        if skip_existing and doc_key in existing_doc_keys:
            logger.info(f"[{total_docs + 1}] Пропуск (уже в БД): '{doc.title}'")
            skipped += 1
            total_docs += 1
            continue

        total_docs += 1
        logger.info(f"[{total_docs}] Парсинг: '{doc.title}' (тип: {doc.source_type})")

        saved = process_document(engine, chunker, doc, total_docs)
        total_chunks += saved

        if saved > 0:
            existing_doc_keys.add(doc_key)
            upsert_document_registry(engine, doc, doc_key, saved)

    logger.info(
        f"Источник {source_name}: {total_docs} документов ({skipped} пропущено), {total_chunks} чанков"
    )
    return total_docs, total_chunks


async def iterate_confluence(config: Config, existing_file_urls: set[str]):
    parser = ConfluenceParser()

    for page_url in config.confluence_pages:
        page_id = parser._extract_page_id(page_url)
        if not page_id:
            logger.error(f"Не удалось извлечь page_id из URL: {page_url}")
            continue

        logger.info(f"Получение вложений со страницы {page_id}...")
        attachments = await parser._get_attachments(page_id)
        logger.info(f"Найдено {len(attachments)} вложений на странице {page_id}")

        allowed_count = sum(
            1 for a in attachments if parser._is_allowed_pdf(a.get("title", ""))
        )
        logger.info(f"Разрешённых PDF для парсинга: {allowed_count}")

        for idx, attachment in enumerate(attachments, 1):
            title = attachment.get("title", "")
            is_allowed = parser._is_allowed_pdf(title)
            media_type = attachment.get("metadata", {}).get(
                "mediaType", ""
            ) or attachment.get("extensions", {}).get("mediaType", "")
            is_pdf = "pdf" in str(media_type).lower() or title.lower().endswith(".pdf")
            logger.info(
                f"  [{idx}] '{title}' — allowed={is_allowed}, pdf={is_pdf}, type={media_type}"
            )

            if not is_allowed:
                continue

            download_url = attachment["_links"]["download"]
            if not download_url.startswith("http"):
                download_url = parser._host + download_url

            normalized_file_url = normalize_url(download_url)
            if normalized_file_url in existing_file_urls:
                logger.info(f"  [{idx}] Пропуск PDF (уже в БД): '{title}'")
                continue

            if not is_pdf:
                continue

            logger.info(f"[{idx}] Парсинг PDF: '{title}'")
            existing_file_urls.add(normalized_file_url)

            doc = await parser._parse_pdf(download_url, title, page_url)
            if doc:
                yield Document(
                    url=page_url,
                    title=doc.title,
                    text_content=doc.text_content,
                    source_type="confluence",
                    file_url=download_url,
                )
            else:
                logger.warning(f"[{idx}] Не удалось распарсить: '{title}'")


async def iterate_sveden(config: Config, existing_file_urls: set[str]):
    parser = SvedenParser()
    logger.info(f"Поиск PDF ссылок: {config.sveden_url}")
    pdf_urls = await parser._find_pdf_links(config.sveden_url)
    logger.info(f"Sveden: найдено {len(pdf_urls)} PDF ссылок")

    for idx, pdf_url in enumerate(pdf_urls, 1):
        normalized_file_url = normalize_url(pdf_url)
        if normalized_file_url in existing_file_urls:
            logger.info(f"[{idx}/{len(pdf_urls)}] Пропуск (уже в БД): {pdf_url}")
            continue

        logger.info(f"[{idx}/{len(pdf_urls)}] Парсинг PDF: {pdf_url}")
        existing_file_urls.add(normalized_file_url)

        doc = await parser._parse_pdf(pdf_url)
        if doc:
            yield Document(
                url=config.sveden_url,
                title=doc.title,
                text_content=doc.text_content,
                source_type="sveden",
                file_url=pdf_url,
            )
        else:
            logger.warning(f"[{idx}] Не удалось распарсить: {pdf_url}")


async def iterate_utmn(config: Config, existing_file_urls: set[str]):
    parser = UtmnParser()
    total_pages = len(config.utmn_pages)
    logger.info(f"Парсинг {total_pages} страниц ТюмГУ...")

    for page_idx, page_url in enumerate(config.utmn_pages, 1):
        logger.info(f"  [{page_idx}/{total_pages}] Страница: {page_url}")
        pdf_urls = await parser._find_pdf_links(page_url)
        logger.info(f"    Найдено {len(pdf_urls)} PDF ссылок")

        for pdf_url in pdf_urls:
            normalized_file_url = normalize_url(pdf_url)
            if normalized_file_url in existing_file_urls:
                logger.info(f"    Пропуск (уже в БД): {pdf_url}")
                continue

            existing_file_urls.add(normalized_file_url)

            doc = await parser._parse_pdf(pdf_url)
            if doc:
                yield Document(
                    url=page_url,
                    title=doc.title,
                    text_content=doc.text_content,
                    source_type="utmn",
                    file_url=pdf_url,
                )


async def iterate_confluence_study(existing_file_urls: set[str]):
    """Итератор для парсинга пространства study из Confluence.

    Парсит все листовые страницы (без дочерних) из пространства study,
    включая HTML контент и PDF вложения.

    Args:
        existing_urls: Множество уже существующих URL в БД
    """
    parser = ConfluenceStudyParser()

    logger.info("Получение страниц из пространства study...")

    # Получаем все страницы пространства через REST API
    url = f"{parser._host}/rest/api/search"
    params = {"cql": "space.key=study order by id", "start": 0, "limit": 100}

    import httpx
    all_pages = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        while True:
            response = await client.get(url, headers=parser._headers, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            for r in results:
                if "content" in r:
                    all_pages.append(r["content"])
            
            if len(results) < 100:
                break
            params["start"] += 100

    pages = all_pages
    logger.info(f"Найдено {len(pages)} страниц в пространстве study")

    # Фильтруем листовые страницы
    leaf_pages = []
    for page in pages:
        page_id = page["id"]
        has_children = await parser._has_child_pages(page_id)
        if not has_children:
            leaf_pages.append(page)

    logger.info(f"Листовых страниц (без дочерних): {len(leaf_pages)}")

    for idx, page in enumerate(leaf_pages, 1):
        page_title = page.get("title", "Untitled")
        page_url = parser._host + page["_links"]["webui"]

        logger.info(f"[{idx}] Парсинг страницы: '{page_title}'")

        # Парсим HTML контент
        html_doc = await parser._parse_page_html(page["id"], page_title, page_url)
        if html_doc and html_doc.text_content.strip():
            yield Document(
                url=page_url,
                title=html_doc.title,
                text_content=html_doc.text_content,
                source_type="confluence_study",
                file_url=None,
            )

        # Парсим PDF вложения
        pdf_docs = await parser._parse_page_attachments(page["id"], page_title, page_url)
        for pdf_doc in pdf_docs:
            normalized_file_url = normalize_url(pdf_doc.url)
            if normalized_file_url in existing_file_urls:
                logger.info(f"  → PDF уже в БД: '{pdf_doc.title}'")
                continue

            existing_file_urls.add(normalized_file_url)
            yield Document(
                url=page_url,
                title=pdf_doc.title,
                text_content=pdf_doc.text_content,
                source_type="confluence_study",
                file_url=pdf_doc.url,
            )


async def main(mode: str, source_filter: str) -> None:
    logger.info("Начало заполнения Базы Знаний...")

    engine = get_db_engine()
    kb_config = get_kb_config()

    chunker = TextChunker(
        chunk_size=kb_config.chunk_size,
        chunk_overlap=kb_config.chunk_overlap,
        min_chunk_size=kb_config.min_chunk_size,
    )

    ensure_registry_table(engine)

    if mode == "clear":
        clear_tables(engine)
        existing_doc_keys: set[str] = set()
        existing_file_urls: set[str] = set()
    else:
        existing_doc_keys = load_existing_doc_keys(engine)

        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT DISTINCT source_url FROM chunks WHERE source_url IS NOT NULL")
            )
            existing_file_urls = {normalize_url(row[0]) for row in result if row[0]}
            try:
                reg_files = conn.execute(
                    text(
                        "SELECT DISTINCT file_url FROM kb_documents_registry WHERE file_url IS NOT NULL"
                    )
                )
                existing_file_urls.update(
                    normalize_url(row[0]) for row in reg_files if row[0]
                )
            except Exception:
                pass

    skip_existing = mode == "resume"  # Пропускать только в resume режиме

    config = Config()

    total_docs = 0
    total_chunks = 0

    source_jobs = {
        "confluence": (
            "Confluence",
            lambda: iterate_confluence(config, existing_file_urls),
        ),
        "sveden": (
            "Sveden",
            lambda: iterate_sveden(config, existing_file_urls),
        ),
        "utmn": (
            "Utmn",
            lambda: iterate_utmn(config, existing_file_urls),
        ),
        "confluence_study": (
            "ConfluenceStudy",
            lambda: iterate_confluence_study(existing_file_urls),
        ),
    }

    selected_sources = (
        [source_filter] if source_filter != "all" else list(source_jobs.keys())
    )

    for source_name in selected_sources:
        display_name, iterator = source_jobs[source_name]
        docs, chunks = await run_source(
            engine,
            chunker,
            display_name,
            iterator,
            existing_doc_keys,
            skip_existing=skip_existing,
        )
        total_docs += docs
        total_chunks += chunks

    logger.info("")
    logger.info("=" * 50)
    logger.info(f"Заполнение завершено!")
    logger.info(f"Всего документов: {total_docs}")
    logger.info(f"Всего чанков сохранено: {total_chunks}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Заполнение Базы Знаний из источников")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--clear",
        action="store_true",
        help="Очистить таблицы перед заполнением",
    )
    group.add_argument(
        "--resume",
        action="store_true",
        help="Продолжить с последнего места (без очистки)",
    )
    group.add_argument(
        "--append",
        action="store_true",
        help="Добавить данные поверх текущих без проверки на существование",
    )
    parser.add_argument(
        "--source",
        choices=["all", "confluence", "sveden", "utmn", "confluence_study"],
        default="all",
        help="Индексировать только выбранный источник",
    )
    args = parser.parse_args()

    if args.clear:
        mode = "clear"
    elif args.append:
        mode = "append"
    else:
        mode = "resume"

    asyncio.run(main(mode, args.source))
