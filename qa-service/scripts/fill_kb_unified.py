"""Скрипт для заполнения Базы Знаний через LightRAG.

Единый пайплайн: парсит PDF → сразу отправляет в LightRAG → создаётся чанки + эмбеддинги + граф знаний.

Аргументы:
    --clear   Очистить LightRAG хранилище перед заполнением
    --source  Индексировать только выбранный источник (confluence/sveden/utmn/confluence_study)
    --limit   Ограничить количество документов для тестирования

Пример использования:
    # Очистить и заполнить с нуля (все источники)
    python scripts/fill_kb_unified.py --clear

    # Только Sveden
    python scripts/fill_kb_unified.py --clear --source sveden

    # Тест с лимитом
    python scripts/fill_kb_unified.py --limit 5
"""

import argparse
import asyncio
import hashlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from sqlalchemy import create_engine, text

from qa.kb.config import get_kb_config
from qa.kb.parsers import ConfluenceHelpParser, ConfluenceStudyParser, SvedenParser, UtmnParser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Нормализовать URL для дедупликации."""
    if not url:
        return ""
    try:
        parsed = urlsplit(url.strip())
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = unquote(parsed.path or "/")
        path = f"/{path.strip('/')}" if path else "/"
        return urlunsplit(("https", host, path, "", ""))
    except Exception:
        return url.strip()


def make_doc_key(source_type: str, file_url: str | None, page_url: str, title: str) -> str:
    """Сформировать стабильный ключ документа."""
    base = normalize_url(file_url or page_url)
    if not base:
        base = f"{source_type}:{unquote(title)}"
    payload = f"{source_type}:{base}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class Config:
    """Конфигурация источников."""

    sveden_url: str = "https://sveden.utmn.ru/sveden/document/"

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
    """Модель документа."""

    url: str
    title: str
    text_content: str
    source_type: str
    file_url: str | None = None


def get_engine():
    """Получить движок БД."""
    import socket

    try:
        socket.gethostbyname("postgres")
        docker_host = "postgres"
    except socket.gaierror:
        docker_host = "localhost"

    env_host = os.getenv("POSTGRES_HOST", "")
    host = docker_host if env_host in ("", "localhost") else env_host

    db = os.getenv("POSTGRES_DB", "voproshalych")
    user = os.getenv("POSTGRES_USER", "voproshalych")
    password = os.getenv("POSTGRES_PASSWORD", "voproshalych")
    port = os.getenv("POSTGRES_PORT", "5432")

    db_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    logger.info(f"Подключение к БД: {host}:{port}/{db}")
    return create_engine(db_url)


def clear_lightrag_storage():
    """Очистить LightRAG хранилище (все таблицы)."""
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE 'lightrag_%' "
            "ORDER BY table_name"
        ))
        tables = [row[0] for row in result]

        for table in tables:
            try:
                conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                logger.info(f"Cleared: {table}")
            except Exception as e:
                logger.warning(f"Could not clear {table}: {e}")
        conn.commit()

    logger.info(f"LightRAG storage cleared ({len(tables)} tables)")


async def init_lightrag():
    """Инициализировать LightRAG."""
    from qa.main import init_lightrag as init_lr, is_lightrag_ready

    if not is_lightrag_ready():
        logger.info("Initializing LightRAG...")
        await init_lr()
        logger.info("LightRAG initialized")
    else:
        logger.info("LightRAG already initialized")


async def insert_document_to_lightrag(rag, doc: Document, doc_idx: int, no_graph: bool = False) -> bool:
    """Вставить документ в LightRAG."""
    try:
        content = f"{doc.title}\n\n{doc.text_content}"
        doc_key = make_doc_key(doc.source_type, doc.file_url, doc.url, doc.title)
        doc_id = hashlib.sha1(doc_key.encode("utf-8")).hexdigest()[:16]

        await rag.ainsert(
            [content],
            ids=[doc_id],
            file_paths=[doc.file_url or doc.url],
        )

        logger.info(f"[{doc_idx}] Indexed: {doc.title}")
        return True

    except Exception as e:
        logger.error(f"[{doc_idx}] Failed to index '{doc.title}': {e}")
        return False


async def iterate_confluence_help(limit: int | None = None):
    """Итератор для Confluence Help (пространство help)."""
    parser = ConfluenceHelpParser()
    count = 0

    for page_id, meta in parser.__class__.__mro__[0].__dict__.get("HELP_PAGES", {}).items() if False else []:
        pass

    from qa.kb.parsers.confluence_help import HELP_PAGES, HELP_PDF_URLS

    for page_id, meta in HELP_PAGES.items():
        if limit and count >= limit:
            return

        title = meta["title"]
        page_url = f"{parser._host}/pages/viewpage.action?pageId={page_id}"
        logger.info(f"Парсинг HTML страницы: {title}")

        html_doc = await parser._parse_page_html(page_id, title, page_url)
        if html_doc and html_doc.text_content.strip():
            yield Document(
                url=page_url,
                title=title,
                text_content=html_doc.text_content,
                source_type="confluence_help",
                file_url=None,
            )
            count += 1

        if meta.get("children"):
            child_docs = await parser._get_child_pages_recursive(page_id)
            for child in child_docs:
                if limit and count >= limit:
                    return
                yield Document(
                    url=child.url,
                    title=child.title,
                    text_content=child.text_content,
                    source_type="confluence_help",
                    file_url=None,
                )
                count += 1

    for pdf_title, pdf_url in HELP_PDF_URLS:
        if limit and count >= limit:
            return
        logger.info(f"OCR парсинг PDF: {pdf_title}")
        doc = await parser._parse_pdf(pdf_url, pdf_title, parser._host)
        if doc:
            yield Document(
                url=parser._host,
                title=doc.title,
                text_content=doc.text_content,
                source_type="confluence_help",
                file_url=pdf_url,
            )
            count += 1


async def iterate_sveden(config: Config, limit: int | None = None):
    """Итератор для Sveden (только whitelist PDF)."""
    parser = SvedenParser()
    logger.info(f"Поиск PDF ссылок: {config.sveden_url}")

    pdf_urls = await parser._find_pdf_links(config.sveden_url)
    logger.info(f"Sveden: найдено {len(pdf_urls)} PDF из whitelist")

    count = 0
    for pdf_url in pdf_urls:
        if limit and count >= limit:
            return

        logger.info(f"[{count + 1}/{len(pdf_urls)}] Парсинг PDF: {pdf_url}")

        doc = await parser._parse_pdf(pdf_url)
        if doc:
            yield Document(
                url=config.sveden_url,
                title=doc.title,
                text_content=doc.text_content,
                source_type="sveden",
                file_url=pdf_url,
            )
            count += 1


async def iterate_utmn(config: Config, limit: int | None = None):
    """Итератор для Utmn."""
    parser = UtmnParser()
    count = 0

    for page_url in config.utmn_pages:
        if limit and count >= limit:
            return

        pdf_urls = await parser._find_pdf_links(page_url)

        for pdf_url in pdf_urls:
            if limit and count >= limit:
                return

            doc = await parser._parse_pdf(pdf_url)
            if doc:
                yield Document(
                    url=page_url,
                    title=doc.title,
                    text_content=doc.text_content,
                    source_type="utmn",
                    file_url=pdf_url,
                )
                count += 1


async def iterate_confluence_study(limit: int | None = None):
    """Итератор для Confluence Study."""
    parser = ConfluenceStudyParser()

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

    count = 0
    for page in all_pages:
        if limit and count >= limit:
            return

        page_id = page["id"]
        has_children = await parser._has_child_pages(page_id)
        if has_children:
            continue

        page_title = page.get("title", "Untitled")
        page_url = parser._host + page["_links"]["webui"]

        html_doc = await parser._parse_page_html(page_id, page_title, page_url)
        if html_doc and html_doc.text_content.strip():
            yield Document(
                url=page_url,
                title=html_doc.title,
                text_content=html_doc.text_content,
                source_type="confluence_study",
                file_url=None,
            )
            count += 1

        if limit and count >= limit:
            return

        pdf_docs = await parser._parse_page_attachments(page_id, page_title, page_url)
        for pdf_doc in pdf_docs:
            if limit and count >= limit:
                return

            yield Document(
                url=page_url,
                title=pdf_doc.title,
                text_content=pdf_doc.text_content,
                source_type="confluence_study",
                file_url=pdf_doc.url,
            )
            count += 1


async def main(clear: bool, source_filter: str, limit: int | None, no_graph: bool):
    logger.info("=" * 50)
    logger.info("Заполнение Базы Знаний (LightRAG Unified)")
    logger.info("=" * 50)

    await init_lightrag()

    from qa.main import get_lightrag
    rag = get_lightrag()

    if no_graph:
        async def _dummy_llm_func(prompt, **kwargs):
            return "[]"
        rag.llm_model_func = _dummy_llm_func
        logger.info("Graph building DISABLED (--no-graph)")

    if clear:
        logger.info("Очистка LightRAG хранилища...")
        clear_lightrag_storage()

    config = Config()

    source_jobs = {
        "confluence_help": ("Confluence Help", lambda: iterate_confluence_help(limit)),
        "sveden": ("Sveden", lambda: iterate_sveden(config, limit)),
        "utmn": ("Utmn", lambda: iterate_utmn(config, limit)),
        "confluence_study": ("ConfluenceStudy", lambda: iterate_confluence_study(limit)),
    }

    selected_sources = [source_filter] if source_filter != "all" else list(source_jobs.keys())

    total_docs = 0
    total_indexed = 0

    for source_name in selected_sources:
        display_name, iterator = source_jobs[source_name]

        logger.info(f"\n{'=' * 50}")
        logger.info(f"Источник: {display_name}")
        logger.info(f"{'=' * 50}")

        doc_count = 0
        indexed_count = 0

        async for doc in iterator():
            doc_count += 1
            doc_idx = doc_count

            success = await insert_document_to_lightrag(rag, doc, doc_idx, no_graph)
            if success:
                indexed_count += 1

            if doc_count % 10 == 0:
                logger.info(f"Прогресс: {doc_count} документов обработано")

        logger.info(f"Источник {display_name}: {doc_count} документов, {indexed_count} проиндексировано")
        total_docs += doc_count
        total_indexed += indexed_count

    logger.info("")
    logger.info("=" * 50)
    logger.info(f"Заполнение завершено!")
    logger.info(f"Всего документов: {total_docs}")
    logger.info(f"Проиндексировано: {total_indexed}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Заполнение Базы Знаний через LightRAG")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Очистить LightRAG хранилище перед заполнением",
    )
    parser.add_argument(
        "--source",
        choices=["all", "confluence_help", "sveden", "utmn", "confluence_study"],
        default="all",
        help="Индексировать только выбранный источник",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить количество документов (для тестирования)",
    )
    parser.add_argument(
        "--no-graph",
        action="store_true",
        help="Отключить построение графа знаний (только чанки + эмбеддинги)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.clear, args.source, args.limit, args.no_graph))