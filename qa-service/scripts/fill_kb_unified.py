"""Скрипт для заполнения Базы Знаний через LightRAG.

Единый пайплайн: парсит PDF → сразу отправляет в LightRAG → создаётся чанки + эмбеддинги + граф знаний.

Аргументы:
    --clear      Очистить LightRAG хранилище перед заполнением
    --source     Индексировать только выбранный источник
    --limit      Ограничить количество документов для тестирования
    --no-graph   Отключить построение графа знаний
    --url        Инкрементальное: индексировать конкретный URL (можно несколько раз)
    --force      С --url: переиндексировать даже если документ уже в БД

Примеры:
    # Полная переиндексация
    python scripts/fill_kb_unified.py --clear

    # Один источник
    python scripts/fill_kb_unified.py --clear --source sveden

    # Инкрементальное: добавить один PDF
    python scripts/fill_kb_unified.py --url "https://sveden.utmn.ru/sveden/files/vie/Prikaz.pdf"

    # Инкрементальное: добавить несколько документов
    python scripts/fill_kb_unified.py \\
        --url "https://sveden.utmn.ru/sveden/managers/" \\
        --url "https://sveden.utmn.ru/sveden/files/vie/Prikaz.pdf"

    # Переиндексировать конкретный документ (удалить старый + вставить новый)
    python scripts/fill_kb_unified.py --force --url "https://sveden.utmn.ru/sveden/managers/"
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
from urllib.parse import parse_qs, unquote, urlparse, urlsplit, urlunsplit

from sqlalchemy import create_engine, text

from qa.kb.config import get_kb_config
from qa.kb.parsers import (
    ConfluenceHelpParser,
    ConfluenceStudyParser,
    SvedenParser,
    UtmnContactsParser,
    UtmnFaqParser,
    UtmnParser,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlsplit(url.strip())
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = unquote(parsed.path or "/")
        path = f"/{path.strip('/')}" if path else "/"
        query = parsed.query
        return urlunsplit(("https", host, path, query, ""))
    except Exception:
        return url.strip()


def make_doc_key(
    source_type: str, file_url: str | None, page_url: str, title: str
) -> str:
    base = normalize_url(file_url or page_url)
    if not base:
        base = f"{source_type}:{unquote(title)}"
    payload = f"{source_type}:{base}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class Config:
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
    url: str
    title: str
    text_content: str
    source_type: str
    file_url: str | None = None


def get_engine():
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
    engine = get_engine()

    graphs = []

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        result = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE 'lightrag_%' "
                "ORDER BY table_name"
            )
        )
        tables = [row[0] for row in result]

        for table in tables:
            try:
                conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                logger.info(f"Cleared: {table}")
            except Exception as e:
                logger.warning(f"Could not clear {table}: {e}")

    with engine.begin() as conn:
        try:
            conn.execute(text("LOAD 'age'"))
            conn.execute(text('SET search_path = ag_catalog, "$user", public'))
            graph_result = conn.execute(text("SELECT name FROM ag_graph"))
            graphs = [row[0] for row in graph_result]

            for graph_name in graphs:
                try:
                    conn.execute(text(f"SELECT drop_graph('{graph_name}', true)"))
                    logger.info(f"Dropped AGE graph: {graph_name}")
                except Exception as e:
                    logger.warning(f"Could not drop AGE graph {graph_name}: {e}")
        except Exception as e:
            logger.warning(f"AGE not available: {e}")

    logger.info(
        f"LightRAG storage cleared ({len(tables)} tables, {len(graphs)} AGE graphs)"
    )


async def init_lightrag():
    from qa.main import init_lightrag as init_lr, is_lightrag_ready

    if not is_lightrag_ready():
        logger.info("Initializing LightRAG...")
        await init_lr()
        logger.info("LightRAG initialized")
    else:
        logger.info("LightRAG already initialized")


async def insert_document_to_lightrag(
    rag, doc: Document, doc_idx: int, no_graph: bool = False
) -> bool:
    try:
        content = f"{doc.title}\n\n{doc.text_content}"
        doc_key = make_doc_key(doc.source_type, doc.file_url, doc.url, doc.title)
        doc_id = hashlib.sha1(doc_key.encode("utf-8")).hexdigest()[:16]

        if no_graph:
            await _insert_chunks_only(rag, content, doc_id, doc)
        else:
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


async def _insert_chunks_only(
    rag, content: str, doc_id: str, doc: Document
) -> None:
    """Прямая вставка чанков + эмбеддингов без entity extraction.

    Обходит pipeline LightRAG (ainsert) и пишет напрямую в:
    - full_docs (полный текст документа)
    - text_chunks (чанки)
    - chunks_vdb (векторные эмбеддинги)
    - doc_status (статус документа)

    Не трогает: entities, relations, graph, llm_cache.
    """
    from lightrag.utils import compute_mdhash_id, sanitize_text_for_encoding

    from qa.kb.embedding import get_embeddings_batch
    from qa.lightrag_adapter import get_lightrag_tokenizer, sentence_aware_chunking

    content = sanitize_text_for_encoding(content)
    file_path = doc.file_url or doc.url

    doc_key = f"doc-{doc_id}"
    new_docs = {
        doc_key: {"content": content, "file_path": file_path}
    }

    _add_doc_keys = await rag.full_docs.filter_keys({doc_key})
    new_docs = {k: v for k, v in new_docs.items() if k in _add_doc_keys}
    if not new_docs:
        logger.warning("Document already in storage, skipping")
        return

    tokenizer = get_lightrag_tokenizer()
    kb_config = get_kb_config()
    raw_chunks = sentence_aware_chunking(
        tokenizer,
        content,
        chunk_token_size=kb_config.chunk_size,
        chunk_overlap_token_size=kb_config.chunk_overlap,
    )

    inserting_chunks: dict[str, dict] = {}
    chunk_texts: list[str] = []

    for index, chunk_data in enumerate(raw_chunks):
        chunk_text = sanitize_text_for_encoding(
            chunk_data.get("content", "")
        )
        if not chunk_text.strip():
            continue
        chunk_key = compute_mdhash_id(chunk_text, prefix="chunk-")
        inserting_chunks[chunk_key] = {
            "content": chunk_text,
            "full_doc_id": doc_key,
            "tokens": chunk_data.get("tokens", len(tokenizer.encode(chunk_text))),
            "chunk_order_index": index,
            "file_path": file_path,
        }
        chunk_texts.append(chunk_text)

    if not inserting_chunks:
        logger.warning("No chunks produced, skipping document")
        return

    add_chunk_keys = await rag.text_chunks.filter_keys(
        set(inserting_chunks.keys())
    )
    inserting_chunks = {
        k: v for k, v in inserting_chunks.items() if k in add_chunk_keys
    }
    if not inserting_chunks:
        logger.warning("All chunks already in storage")
        return

    chunk_list = list(inserting_chunks.items())
    chunk_texts_for_embed = [v["content"] for _, v in chunk_list]
    embeddings = get_embeddings_batch(chunk_texts_for_embed)
    for i, (chunk_key, chunk_data) in enumerate(chunk_list):
        chunk_data["embedding"] = embeddings[i]

    await rag.chunks_vdb.upsert(inserting_chunks)
    await rag.full_docs.upsert(new_docs)
    await rag.text_chunks.upsert(inserting_chunks)

    for storage_inst in [
        rag.full_docs,
        rag.text_chunks,
        rag.chunks_vdb,
    ]:
        if storage_inst is not None:
            await storage_inst.index_done_callback()

    logger.info(
        "Inserted %d chunks (no-graph, direct)", len(inserting_chunks)
    )


def _extract_title_from_url(url: str) -> str:
    filename = url.rstrip("/").split("/")[-1]
    filename = re.sub(r"\?.*$", "", filename)
    filename = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    filename = unquote(filename)
    filename = filename.replace("-", " ").replace("_", " ")
    return filename if filename else "Untitled"


# ---------------------------------------------------------------------------
# URL routing for incremental indexing
# ---------------------------------------------------------------------------

_ROUTE_CONFLUENCE_HELP_HTML = "confluence_help_html"
_ROUTE_CONFLUENCE_HELP_PDF = "confluence_help_pdf"
_ROUTE_SVEDEN_HTML = "sveden_html"
_ROUTE_SVEDEN_PDF = "sveden_pdf"
_ROUTE_UTMN_PDF = "utmn_pdf"
_ROUTE_UTMN_CONTACTS = "utmn_contacts"
_ROUTE_UTMN_FAQ = "utmn_faq"
_ROUTE_GENERIC_PDF = "generic_pdf"


def route_url(url: str) -> tuple[str, str]:
    """Определить source_type и doc_type по URL.

    Returns:
        (source_type, doc_type) where doc_type is one of:
        - _ROUTE_CONFLUENCE_HELP_HTML  — Confluence REST API → HTML
        - _ROUTE_CONFLUENCE_HELP_PDF   — PDF через OCR
        - _ROUTE_SVEDEN_HTML           — HTML с таблицами
        - _ROUTE_SVEDEN_PDF            — PDF через OCR
        - _ROUTE_UTMN_PDF              — PDF через OCR
        - _ROUTE_UTMN_CONTACTS         — Контакты ТюмГУ (блоки)
        - _ROUTE_UTMN_FAQ              — FAQ абитуриентов
        - _ROUTE_GENERIC_PDF           — PDF через OCR (fallback)
    """
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().replace("www.", "")
    path_lower = (parsed.path or "").lower()
    query = parsed.query or ""

    is_pdf = ".pdf" in path_lower or ".pdf" in url.lower()

    if "confluence.utmn.ru" in host:
        if "pageid=" in query.lower():
            return "confluence_help", _ROUTE_CONFLUENCE_HELP_HTML
        if is_pdf:
            return "confluence_help", _ROUTE_CONFLUENCE_HELP_PDF
        return "confluence_help", _ROUTE_CONFLUENCE_HELP_HTML

    if "sveden.utmn.ru" in host:
        if is_pdf:
            return "sveden", _ROUTE_SVEDEN_PDF
        from qa.kb.parsers.sveden import SVEDEN_HTML_PAGES

        sveden_html_urls = {p["url"].rstrip("/") for p in SVEDEN_HTML_PAGES}
        if url.rstrip("/") in sveden_html_urls:
            return "sveden", _ROUTE_SVEDEN_HTML
        return "sveden", _ROUTE_SVEDEN_HTML

    if "utmn.ru" in host:
        if is_pdf:
            return "utmn", _ROUTE_UTMN_PDF
        normalized = url.split("?")[0].rstrip("/")
        if normalized == "https://www.utmn.ru/kontakty":
            return "utmn_contacts", _ROUTE_UTMN_CONTACTS
        if normalized == "https://www.utmn.ru/abiturient/faq":
            return "utmn_faq", _ROUTE_UTMN_FAQ

    if is_pdf:
        return "utmn", _ROUTE_GENERIC_PDF

    raise ValueError(
        f"Не удалось определить тип документа для URL: {url}\n"
        f"Поддерживаемые форматы:\n"
        f"  - Confluence HTML: .../pages/viewpage.action?pageId=XXX\n"
        f"  - Confluence PDF:  .../download/attachments/.../*.pdf\n"
        f"  - Sveden HTML:     .../sveden/managers/ | /catering/ | /struct\n"
        f"  - Sveden PDF:      .../sveden/files/.../*.pdf\n"
        f"  - UTMN PDF:        .../utmn.ru/.../*.pdf\n"
        f"  - UTMN Контакты:   https://www.utmn.ru/kontakty/\n"
        f"  - UTMN FAQ:        https://www.utmn.ru/abiturient/faq/\n"
        f"  - Любой PDF:       *.pdf"
    )


async def process_single_url(url: str) -> Document | None:
    """Парсинг одного URL. Возвращает Document или None."""
    source_type, doc_type = route_url(url)

    if doc_type == _ROUTE_CONFLUENCE_HELP_HTML:
        parser = ConfluenceHelpParser()
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        page_id = params.get("pageId", [None])[0]
        if not page_id:
            logger.error(f"Не найден pageId в URL: {url}")
            return None

        import httpx

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            api_url = f"{parser._host}/rest/api/content/{page_id}?expand=body.export_view,title"
            resp = await client.get(api_url, headers=parser._headers)
            resp.raise_for_status()
            data = resp.json()

        title = data.get("title", f"Confluence page {page_id}")
        html_body = data.get("body", {}).get("export_view", {}).get("value", "")
        if not html_body:
            logger.error(f"Пустой HTML контент: {url}")
            return None

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text(separator=" ")
        text = re.sub(r"\s+", " ", text).strip()

        return Document(
            url=url,
            title=title,
            text_content=text,
            source_type=source_type,
            file_url=None,
        )

    if doc_type in (
        _ROUTE_CONFLUENCE_HELP_PDF,
        _ROUTE_SVEDEN_PDF,
        _ROUTE_UTMN_PDF,
        _ROUTE_GENERIC_PDF,
    ):
        title = _extract_title_from_url(url)
        logger.info(f"OCR парсинг PDF: {title}")

        parser = SvedenParser()
        doc = await parser._parse_pdf(url)
        if not doc:
            return None

        return Document(
            url=url,
            title=doc.title if doc.title else title,
            text_content=doc.text_content,
            source_type=source_type,
            file_url=url,
        )

    if doc_type == _ROUTE_SVEDEN_HTML:
        parser = SvedenParser()
        from qa.kb.parsers.sveden import SVEDEN_HTML_PAGES

        title = "Sveden page"
        for p in SVEDEN_HTML_PAGES:
            if p["url"].rstrip("/") == url.rstrip("/"):
                title = p["title"]
                break

        doc = await parser._parse_html_page(url, title)
        if not doc or not doc.text_content.strip():
            return None

        return Document(
            url=url,
            title=doc.title,
            text_content=doc.text_content,
            source_type=source_type,
            file_url=None,
        )

    if doc_type == _ROUTE_UTMN_CONTACTS:
        from qa.kb.parsers.utmn_contacts import CONTACTS_URL

        parser = UtmnContactsParser()
        parsed_docs = await parser.get_documents(CONTACTS_URL)
        if not parsed_docs:
            return None
        return Document(
            url=parsed_docs[0].url,
            title="Контакты ТюмГУ (все блоки)",
            text_content="\n\n".join(d.text_content for d in parsed_docs),
            source_type=source_type,
            file_url=None,
        )

    if doc_type == _ROUTE_UTMN_FAQ:
        from qa.kb.parsers.utmn_faq import FAQ_BASE_URL

        parser = UtmnFaqParser()
        parsed_docs = await parser.get_documents(FAQ_BASE_URL)
        if not parsed_docs:
            return None
        return Document(
            url=FAQ_BASE_URL,
            title="FAQ абитуриентов ТюмГУ",
            text_content="\n\n".join(d.text_content for d in parsed_docs),
            source_type=source_type,
            file_url=None,
        )

    logger.error(f"Неизвестный doc_type: {doc_type}")
    return None


def doc_exists_in_db(
    url: str, source_type: str, file_url: str | None, title: str
) -> bool:
    """Проверить, есть ли документ уже в LIGHTRAG_DOC_STATUS."""
    engine = get_engine()
    doc_key = make_doc_key(source_type, file_url, url, title)
    doc_id = hashlib.sha1(doc_key.encode("utf-8")).hexdigest()[:16]

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM lightrag_doc_status WHERE id = :id LIMIT 1"),
            {"id": doc_id},
        )
        return result.fetchone() is not None


def _remove_doc_from_graph_properties(conn, doc_id: str, chunk_ids: list[str]) -> None:
    """Удалить ссылки на документ из properties AGE-графа (source_id, file_path).

    Entities/relations в графе могут быть вмержены из нескольких документов.
    Нужно убрать только chunk_ids и file_path данного документа, сохранив остальные.
    Если после очистки source_id пуст — node/edge можно удалить.
    """
    fp_pattern = f"%{doc_id}%"

    rows = conn.execute(
        text("""
        SELECT id, start_id, end_id, properties::text as props
        FROM chunk_entity_relation."DIRECTED"
        WHERE properties::text LIKE :fp
    """),
        {"fp": fp_pattern},
    ).fetchall()
    logger.info(
        f"force_delete_graph: found {len(rows)} edges to clean for doc {doc_id}"
    )
    _clean_graph_elements(conn, rows, chunk_ids, doc_id, is_edge=True)

    rows_v = conn.execute(
        text("""
        SELECT id, NULL, NULL, properties::text as props
        FROM chunk_entity_relation."base"
        WHERE properties::text LIKE :fp
    """),
        {"fp": fp_pattern},
    ).fetchall()
    logger.info(
        f"force_delete_graph: found {len(rows_v)} vertices to clean for doc {doc_id}"
    )
    _clean_graph_elements(conn, rows_v, chunk_ids, doc_id, is_edge=False)


def _clean_sep_field(value: str | None, remove_ids: set[str]) -> str | None:
    """Убрать remove_ids из <SEP>-разделённого поля. Вернуть None если поле пустое."""
    if not value:
        return value
    parts = [p for p in value.split("<SEP>") if p not in remove_ids]
    return "<SEP>".join(parts) if parts else None


def _escape_cypher_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')


def _clean_graph_elements(
    conn, elements, chunk_ids: list[str], doc_id: str, is_edge: bool
) -> None:
    """Обновить или удалить элементы графа (nodes/edges) после очистки source_id."""
    chunk_set = set(chunk_ids)
    for eid, start_id, end_id, props_text in elements:
        try:
            props = json.loads(props_text) if isinstance(props_text, str) else {}
        except (json.JSONDecodeError, TypeError):
            continue

        new_source = _clean_sep_field(props.get("source_id"), chunk_set)
        new_file_path = _clean_sep_field(props.get("file_path"), {doc_id})

        if not new_source and not new_file_path:
            if is_edge:
                cypher = f"MATCH ()-[r]-() WHERE id(r) = {eid} DELETE r"
            else:
                cypher = f"MATCH (n) WHERE id(n) = {eid} DETACH DELETE n"
            try:
                conn.execute(
                    text(
                        f"SELECT * FROM cypher('chunk_entity_relation', "
                        f"$${cypher}$$) AS (r agtype)"
                    )
                )
                logger.debug(
                    f"force_delete_graph: deleted orphan {'edge' if is_edge else 'vertex'} {eid}"
                )
            except Exception as e:
                logger.warning(f"force_delete_graph: could not delete {eid}: {e}")
        else:
            sets = []
            if new_source is not None:
                sets.append(f"n.source_id = '{_escape_cypher_str(new_source)}'")
            else:
                sets.append("n.source_id = ''")
            if new_file_path is not None:
                sets.append(f"n.file_path = '{_escape_cypher_str(new_file_path)}'")
            else:
                sets.append("n.file_path = ''")
            set_clause = ", ".join(sets)
            try:
                if is_edge:
                    cypher = f"MATCH ()-[n]-() WHERE id(n) = {eid} SET {set_clause}"
                else:
                    cypher = f"MATCH (n) WHERE id(n) = {eid} SET {set_clause}"
                conn.execute(
                    text(
                        f"SELECT * FROM cypher('chunk_entity_relation', "
                        f"$${cypher}$$) AS (r agtype)"
                    )
                )
                logger.debug(
                    f"force_delete_graph: cleaned {'edge' if is_edge else 'vertex'} {eid}"
                )
            except Exception as e:
                logger.warning(f"force_delete_graph: could not update {eid}: {e}")


def force_delete_doc(
    url: str, source_type: str, file_url: str | None, title: str
) -> None:
    """Удалить документ и все его чанки из всех таблиц LightRAG и AGE-графа."""
    engine = get_engine()
    doc_key = make_doc_key(source_type, file_url, url, title)
    doc_id = hashlib.sha1(doc_key.encode("utf-8")).hexdigest()[:16]

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        chunk_rows = conn.execute(
            text("SELECT id FROM lightrag_doc_chunks WHERE full_doc_id = :doc_id"),
            {"doc_id": doc_id},
        ).fetchall()

        chunk_ids = [row[0] for row in chunk_rows]
        logger.info(f"force_delete: doc_id={doc_id}, chunks={len(chunk_ids)}")

        vdb_tables = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE 'LIGHTRAG_VDB_CHUNKS%'"
            )
        ).fetchall()

        for (vdb_table,) in vdb_tables:
            conn.execute(
                text(f"DELETE FROM {vdb_table} WHERE full_doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            logger.info(f"force_delete: removed chunks from {vdb_table}")

        conn.execute(
            text("DELETE FROM lightrag_doc_chunks WHERE full_doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
        conn.execute(
            text("DELETE FROM lightrag_doc_full WHERE id = :doc_id"), {"doc_id": doc_id}
        )
        conn.execute(
            text("DELETE FROM lightrag_doc_status WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )
        conn.execute(
            text("DELETE FROM lightrag_full_entities WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )
        conn.execute(
            text("DELETE FROM lightrag_full_relations WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )

        try:
            conn.execute(text("LOAD 'age'"))
            conn.execute(text('SET search_path = ag_catalog, "$user", public'))
            _remove_doc_from_graph_properties(conn, doc_id, chunk_ids)
        except Exception as e:
            logger.warning(f"force_delete: AGE graph cleanup failed (non-fatal): {e}")

    logger.info(f"force_delete: документ {doc_id} удалён из всех таблиц и графа")


# ---------------------------------------------------------------------------
# Source iterators (bulk mode)
# ---------------------------------------------------------------------------


async def iterate_confluence_help(limit: int | None = None):
    parser = ConfluenceHelpParser()
    count = 0

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
    from qa.kb.parsers.sveden import SVEDEN_HTML_PAGES

    parser = SvedenParser()
    count = 0

    for page_meta in SVEDEN_HTML_PAGES:
        if limit and count >= limit:
            return
        logger.info(f"Sveden HTML: {page_meta['title']}")
        doc = await parser._parse_html_page(page_meta["url"], page_meta["title"])
        if doc and doc.text_content.strip():
            yield Document(
                url=page_meta["url"],
                title=doc.title,
                text_content=doc.text_content,
                source_type="sveden",
                file_url=None,
            )
            count += 1

    logger.info(f"Поиск PDF ссылок: {config.sveden_url}")
    pdf_urls = await parser._find_pdf_links(config.sveden_url)
    logger.info(f"Sveden: найдено {len(pdf_urls)} PDF из whitelist")

    for pdf_url in pdf_urls:
        if limit and count >= limit:
            return

        logger.info(f"[{count + 1}] Парсинг PDF: {pdf_url}")

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


async def iterate_utmn_contacts(limit: int | None = None):
    from qa.kb.parsers.utmn_contacts import CONTACTS_URL

    parser = UtmnContactsParser()
    count = 0

    parsed_docs = await parser.get_documents(CONTACTS_URL)
    for doc in parsed_docs:
        if limit and count >= limit:
            return
        yield Document(
            url=doc.url,
            title=doc.title,
            text_content=doc.text_content,
            source_type="utmn_contacts",
            file_url=None,
        )
        count += 1


async def iterate_utmn_faq(limit: int | None = None):
    from qa.kb.parsers.utmn_faq import FAQ_BASE_URL

    parser = UtmnFaqParser()
    count = 0

    parsed_docs = await parser.get_documents(FAQ_BASE_URL)
    for doc in parsed_docs:
        if limit and count >= limit:
            return
        yield Document(
            url=doc.url,
            title=doc.title,
            text_content=doc.text_content,
            source_type="utmn_faq",
            file_url=None,
        )
        count += 1


async def iterate_confluence_study(limit: int | None = None):
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_incremental(urls: list[str], no_graph: bool, force: bool):
    """Инкрементальное индексирование конкретных URL."""
    logger.info("=" * 50)
    logger.info(f"Инкрементальное индексирование ({len(urls)} URL)")
    if force:
        logger.info("--force: документы будут переиндексированы")
    logger.info("=" * 50)

    await init_lightrag()

    from qa.main import get_lightrag

    rag = get_lightrag()

    if no_graph:
        logger.info(
            "Graph building DISABLED (--no-graph): "
            "direct chunk+embedding insertion, no entity extraction"
        )

    total = 0
    indexed = 0
    skipped = 0

    for i, url in enumerate(urls, 1):
        logger.info(f"\n[{i}/{len(urls)}] {url}")

        try:
            source_type, doc_type = route_url(url)
        except ValueError as e:
            logger.error(str(e))
            continue

        if force:
            title_for_delete = _extract_title_from_url(url)
            file_url_for_delete = url if "pdf" in url.lower() else None
            force_delete_doc(url, source_type, file_url_for_delete, title_for_delete)
            logger.info("Старые данные удалены, переиндексация...")

        doc = await process_single_url(url)
        if not doc:
            logger.warning(f"Не удалось распарсить: {url}")
            continue

        if not force and doc_exists_in_db(
            doc.url, doc.source_type, doc.file_url, doc.title
        ):
            logger.info(f"SKIP (уже в БД): {doc.title}")
            skipped += 1
            continue

        success = await insert_document_to_lightrag(rag, doc, i, no_graph)
        if success:
            indexed += 1
        total += 1

    logger.info("")
    logger.info("=" * 50)
    logger.info(f"Инкрементальное индексирование завершено")
    logger.info(
        f"Всего URL: {len(urls)}, обработано: {total}, проиндексировано: {indexed}, пропущено: {skipped}"
    )
    logger.info("=" * 50)


async def run_bulk(clear: bool, source_filter: str, limit: int | None, no_graph: bool):
    """Массовое индексирование по источникам."""
    logger.info("=" * 50)
    logger.info("Заполнение Базы Знаний (LightRAG Unified)")
    logger.info("=" * 50)

    if clear:
        logger.info("Очистка LightRAG хранилища...")
        clear_lightrag_storage()

    await init_lightrag()

    from qa.main import get_lightrag

    rag = get_lightrag()

    if no_graph:
        logger.info(
            "Graph building DISABLED (--no-graph): "
            "direct chunk+embedding insertion, no entity extraction"
        )

    config = Config()

    source_jobs = {
        "confluence_help": ("Confluence Help", lambda: iterate_confluence_help(limit)),
        "sveden": ("Sveden", lambda: iterate_sveden(config, limit)),
        "utmn": ("Utmn", lambda: iterate_utmn(config, limit)),
        "confluence_study": (
            "ConfluenceStudy",
            lambda: iterate_confluence_study(limit),
        ),
        "utmn_contacts": ("Utmn Contacts", lambda: iterate_utmn_contacts(limit)),
        "utmn_faq": ("Utmn FAQ", lambda: iterate_utmn_faq(limit)),
    }

    selected_sources = (
        [source_filter] if source_filter != "all" else list(source_jobs.keys())
    )

    total_docs = 0
    total_indexed = 0
    total_skipped = 0

    for source_name in selected_sources:
        display_name, iterator = source_jobs[source_name]

        logger.info(f"\n{'=' * 50}")
        logger.info(f"Источник: {display_name}")
        logger.info(f"{'=' * 50}")

        doc_count = 0
        indexed_count = 0
        skipped_count = 0

        async for doc in iterator():
            doc_count += 1
            doc_idx = doc_count

            try:
                if doc_exists_in_db(doc.url, doc.source_type, doc.file_url, doc.title):
                    logger.info(f"[{doc_idx}] SKIP (уже в БД): {doc.title}")
                    skipped_count += 1
                    continue

                success = await insert_document_to_lightrag(rag, doc, doc_idx, no_graph)
                if success:
                    indexed_count += 1
            except Exception as e:
                logger.error(f"[{doc_idx}] ERROR processing '{doc.title}': {e}")
                continue

            if doc_count % 10 == 0:
                logger.info(
                    f"Прогресс: {doc_count} документов обработано, {skipped_count} пропущено"
                )

        logger.info(
            f"Источник {display_name}: {doc_count} документов, {indexed_count} проиндексировано, {skipped_count} пропущено"
        )
        total_docs += doc_count
        total_indexed += indexed_count
        total_skipped += skipped_count

    logger.info("")
    logger.info("=" * 50)
    logger.info(f"Заполнение завершено!")
    logger.info(f"Всего документов: {total_docs}")
    logger.info(f"Проиндексировано: {total_indexed}")
    logger.info(f"Пропущено (дубли): {total_skipped}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Заполнение Базы Знаний через LightRAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  %(prog)s --clear\n"
            "  %(prog)s --clear --source sveden\n"
            '  %(prog)s --url "https://sveden.utmn.ru/sveden/managers/"\n'
            '  %(prog)s --force --url "https://sveden.utmn.ru/sveden/managers/"\n'
            '  %(prog)s --no-graph --url "https://.../file.pdf"\n'
        ),
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Очистить LightRAG хранилище перед заполнением",
    )
    parser.add_argument(
        "--source",
        choices=[
            "all",
            "confluence_help",
            "sveden",
            "utmn",
            "confluence_study",
            "utmn_contacts",
            "utmn_faq",
        ],
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
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="URL документа/страницы для индексации (можно указать несколько раз)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Переиндексировать даже если документ уже в БД (только с --url)",
    )
    args = parser.parse_args()

    if args.urls:
        asyncio.run(run_incremental(args.urls, args.no_graph, args.force))
    else:
        asyncio.run(run_bulk(args.clear, args.source, args.limit, args.no_graph))
