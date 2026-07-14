"""MCP tool definitions for KB service."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kb.chunking import sentence_aware_chunking
from kb.config import settings
from kb.db import get_engine
from kb.embedding import get_embedding, get_embeddings_batch
from kb.models import KBChunk, KBEmbedding
from kb.parsers import (
    ConfluenceHelpParser,
    ConfluenceStudyParser,
    ParsedDocument,
    SvedenParser,
    UtmnContactsParser,
    UtmnFaqParser,
    UtmnNewsParser,
    UtmnParser,
    WebPageParser,
)
from kb.preprocessing import QUESTION_TYPE_KB, QuestionClassification, classify_and_expand
from kb.search import vector_search

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "kb_search",
        "description": "Поиск по базе знаний ТюмГУ. Возвращает релевантные фрагменты документов.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос"},
                "top_k": {"type": "integer", "description": "Количество результатов (макс 20)", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "classify_query",
        "description": "Классификация и нормализация вопроса. Определяет тип вопроса (БЗ/системный/общий) и расширяет аббревиатуры.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Текст вопроса"},
                "dialog_context": {"type": "string", "description": "Контекст диалога (опционально)"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "kb_search_classified",
        "description": "Классифицирует запрос, ищет по БЗ, возвращает контекст для ответа. Оптимизирован для использования в ReAct агенте.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Текст запроса"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "store_document",
        "description": "Добавить документ в базу знаний. Разбивает на чанки, вычисляет эмбеддинги, сохраняет.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL документа"},
                "source_type": {"type": "string", "description": "Тип источника (web, pdf)"},
            },
            "required": ["url", "source_type"],
        },
    },
    {
        "name": "crawl_utmn",
        "description": "Сканировать HTML-страницы utmn.ru начиная с указанного URL (BFS-обход). Извлекает текст и сохраняет в базу знаний.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": "Базовый URL для сканирования (по умолчанию https://www.utmn.ru)", "default": "https://www.utmn.ru"},
                "max_pages": {"type": "integer", "description": "Максимум страниц для сканирования", "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "crawl_sveden",
        "description": "Сканировать портал sveden.utmn.ru. Извлекает PDF и HTML документы, сохраняет в базу знаний.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base_url": {
                    "type": "string",
                    "description": "Базовый URL (по умолчанию https://sveden.utmn.ru/sveden/)",
                    "default": "https://sveden.utmn.ru/sveden/",
                },
            },
            "required": [],
        },
    },
    {
        "name": "crawl_confluence_help",
        "description": "Сканировать Confluence Help space. Извлекает страницы и сохраняет в базу знаний.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_url": {"type": "string", "description": "Базовый URL Confluence space"},
            },
            "required": ["source_url"],
        },
    },
    {
        "name": "crawl_confluence_study",
        "description": "Сканировать Confluence Study space. Извлекает страницы и сохраняет в базу знаний.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_url": {"type": "string", "description": "Базовый URL Confluence space"},
            },
            "required": ["source_url"],
        },
    },
    {
        "name": "crawl_utmn_faq",
        "description": "Сканировать FAQ разделы utmn.ru. Сохраняет в базу знаний.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_url": {"type": "string", "description": "URL FAQ раздела"},
            },
            "required": ["source_url"],
        },
    },
    {
        "name": "crawl_utmn_contacts",
        "description": "Сканировать контакты на utmn.ru. Сохраняет в базу знаний.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_url": {"type": "string", "description": "URL раздела с контактами"},
            },
            "required": ["source_url"],
        },
    },
    {
        "name": "crawl_utmn_news",
        "description": "Сканировать ленту новостей utmn.ru (stories). Сохраняет в базу знаний.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_url": {"type": "string", "description": "URL ленты новостей", "default": "https://www.utmn.ru/news/stories/"},
                "max_pages": {"type": "integer", "description": "Количество страниц пагинации", "default": 3},
            },
            "required": [],
        },
    },
    {
        "name": "crawl_utmn_events",
        "description": "Сканировать ленту мероприятий utmn.ru (events). Сохраняет в базу знаний.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_url": {"type": "string", "description": "URL ленты мероприятий", "default": "https://www.utmn.ru/news/events/"},
                "max_pages": {"type": "integer", "description": "Количество страниц пагинации", "default": 3},
            },
            "required": [],
        },
    },
]


def _log_separator(title: str = "") -> None:
    """Вывести разделитель с заголовком источника."""
    line = "=" * 55
    if title:
        logger.info("")
        logger.info(line)
        logger.info("  %s", title)
        logger.info(line)
    else:
        logger.info(line)


def _log_doc_progress(idx: int, total: int, doc: ParsedDocument, phase: str = "Parsed") -> None:
    """Вывести прогресс обработки документа."""
    logger.info("[%d/%d] %s: %s", idx, total, phase, doc.title)
    logger.info("       URL: %s", doc.url)
    logger.info("       Length: %d chars", len(doc.text_content))


async def _store_parsed_document_logged(
    doc: ParsedDocument, idx: int, total: int,
) -> dict:
    """Chunk → Embed → Store с детальным логгированием."""
    content = doc.text_content
    if not content.strip():
        logger.warning("  [%d/%d] SKIP (empty): %s", idx, total, doc.title)
        return {"status": "skipped", "reason": "empty content", "url": doc.url}

    # Chunking
    logger.info("  [%d/%d] Chunking: %s ...", idx, total, doc.title)
    chunks = await sentence_aware_chunking(
        content,
        max_chars=settings.max_chars,
        overlap=settings.overlap,
    )
    if not chunks:
        logger.warning("  [%d/%d] SKIP (no chunks): %s", idx, total, doc.title)
        return {"status": "skipped", "reason": "no chunks", "url": doc.url}
    logger.info("  [%d/%d] → %d chunks", idx, total, len(chunks))

    # Embedding
    logger.info("  [%d/%d] Embedding %d chunks ...", idx, total, len(chunks))
    texts = [c["content"] for c in chunks]
    embeddings = await get_embeddings_batch(texts)
    logger.info("  [%d/%d] → %d embeddings (dim=%d)", idx, total, len(embeddings), len(embeddings[0]) if embeddings else 0)

    # Store
    doc_id = str(uuid.uuid4())
    session_maker = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        for i, (chunk_data, emb) in enumerate(zip(chunks, embeddings)):
            chunk = KBChunk(
                id=str(uuid.uuid4()),
                doc_id=doc_id,
                chunk_order_index=chunk_data.get("chunk_order_index", i),
                tokens=chunk_data.get("tokens", 0),
                content=chunk_data["content"],
                title=doc.title,
                source_url=doc.url,
                source_type=doc.source_type,
            )
            session.add(chunk)
            await session.flush()

            embedding_row = KBEmbedding(
                chunk_id=chunk.id,
                embedding=emb,
                model=settings.embedding_model,
            )
            session.add(embedding_row)

        await session.commit()

    logger.info("  [%d/%d] ✓ Stored: %s (%d chunks)", idx, total, doc.title, len(chunks))
    return {
        "status": "ok",
        "chunks": len(chunks),
        "doc_id": doc_id,
        "url": doc.url,
        "title": doc.title,
    }


def _format_context(results: list[dict]) -> str:
    """Format vector search results into a readable context string."""
    if not results:
        return "Нет релевантных результатов."

    parts = []
    for i, r in enumerate(results, 1):
        part = f"Источник {i}: {r['content']}"
        if r.get("source_url"):
            part += f"\nURL: {r['source_url']}"
        parts.append(part)

    return "\n\n---\n\n".join(parts)


async def kb_search(query: str, top_k: int = 10) -> dict:
    """Search knowledge base by query embedding."""
    embedding = await get_embedding(query)
    top_k = min(top_k, 20)

    session_maker = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        results = await vector_search(
            query_embedding=embedding,
            top_k=top_k,
            session=session,
        )

    context = _format_context(results)

    return {
        "query": query,
        "results": results,
        "context": context,
    }


async def classify_query(question: str, dialog_context: str = "") -> dict:
    """Classify and normalize a question."""
    result = await classify_and_expand(question, dialog_context=dialog_context)

    return {
        "question_type": result.question_type,
        "expanded_query": result.expanded_query,
        "context_expanded_query": result.context_expanded_query,
        "confidence": result.confidence,
    }


async def kb_search_classified(query: str) -> dict:
    """Classify query, search KB, return context for answer."""
    classification = await classify_and_expand(query)
    search_query = classification.context_expanded_query or classification.expanded_query or query

    embedding = await get_embedding(search_query)

    session_maker = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        results = await vector_search(
            query_embedding=embedding,
            top_k=settings.top_k,
            session=session,
        )

    context = _format_context(results)

    return {
        "classification": {
            "question_type": classification.question_type,
            "expanded_query": classification.expanded_query,
            "context_expanded_query": classification.context_expanded_query,
            "confidence": classification.confidence,
        },
        "results": results,
        "context": context,
    }


async def _parse_document(url: str, source_type: str) -> str:
    """Fetch and extract text content from a document URL."""
    parser = WebPageParser()
    try:
        parsed: ParsedDocument = await parser.parse(url)
        if not parsed.text_content.strip():
            logger.warning(f"No text extracted from {url}")
        return parsed.text_content
    except NotImplementedError:
        if source_type == "pdf":
            raise NotImplementedError(
                "PDF parsing requires Tesseract OCR. "
                "Ensure tesseract-ocr and tesseract-ocr-rus are installed."
            )
        raise


async def _store_parsed_document(doc: ParsedDocument) -> dict:
    """Chunk, embed, and store a single parsed document in the knowledge base."""
    content = doc.text_content
    if not content.strip():
        logger.warning("SKIP (empty): %s", doc.title)
        return {"status": "skipped", "reason": "empty content", "url": doc.url}

    logger.info("Chunking: %s ...", doc.title)
    chunks = await sentence_aware_chunking(
        content,
        max_chars=settings.max_chars,
        overlap=settings.overlap,
    )
    if not chunks:
        logger.warning("SKIP (no chunks): %s", doc.title)
        return {"status": "skipped", "reason": "no chunks", "url": doc.url}
    logger.info("→ %d chunks", len(chunks))

    logger.info("Embedding %d chunks for: %s ...", len(chunks), doc.title)
    texts = [c["content"] for c in chunks]
    embeddings = await get_embeddings_batch(texts)
    logger.info("→ %d embeddings done", len(embeddings))

    doc_id = str(uuid.uuid4())

    session_maker = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        for i, (chunk_data, emb) in enumerate(zip(chunks, embeddings)):
            chunk = KBChunk(
                id=str(uuid.uuid4()),
                doc_id=doc_id,
                chunk_order_index=chunk_data.get("chunk_order_index", i),
                tokens=chunk_data.get("tokens", 0),
                content=chunk_data["content"],
                title=doc.title,
                source_url=doc.url,
                source_type=doc.source_type,
            )
            session.add(chunk)
            await session.flush()

            embedding_row = KBEmbedding(
                chunk_id=chunk.id,
                embedding=emb,
                model=settings.embedding_model,
            )
            session.add(embedding_row)

        await session.commit()

    logger.info("✓ Stored: %s (%d chunks)", doc.title, len(chunks))
    return {
        "status": "ok",
        "chunks": len(chunks),
        "doc_id": doc_id,
        "url": doc.url,
        "title": doc.title,
    }


async def store_document(url: str, source_type: str) -> dict:
    """Parse, chunk, embed, and store a document in the knowledge base."""
    parser = WebPageParser()
    parsed = await parser.parse(url)
    parsed.source_type = source_type
    return await _store_parsed_document(parsed)


async def crawl_utmn(base_url: str = "https://www.utmn.ru", max_pages: int = 50) -> dict:
    """Crawl utmn.ru pages and store in knowledge base."""
    _log_separator("Источник: utmn.ru (HTML-страницы)")
    parser = UtmnParser()
    docs = await parser.get_documents(base_url, max_pages=max_pages)
    total = len(docs)
    results = []
    for idx, doc in enumerate(docs, 1):
        _log_doc_progress(idx, total, doc, "Crawled")
        result = await _store_parsed_document_logged(doc, idx, total)
        results.append(result)
    stored = sum(1 for r in results if r["status"] == "ok")
    logger.info("")
    logger.info("Источник utmn.ru: %d документов, %d сохранено", total, stored)
    _log_separator()
    return {
        "status": "ok",
        "total": total,
        "stored": stored,
        "results": results,
    }


async def crawl_sveden(base_url: str = "https://sveden.utmn.ru/sveden/") -> dict:
    """Crawl sveden.utmn.ru and store in knowledge base."""
    _log_separator("Источник: sveden.utmn.ru")
    parser = SvedenParser()
    docs = await parser.get_documents(base_url)
    total = len(docs)
    results = []
    for idx, doc in enumerate(docs, 1):
        _log_doc_progress(idx, total, doc, "Parsed")
        result = await _store_parsed_document_logged(doc, idx, total)
        results.append(result)
    stored = sum(1 for r in results if r["status"] == "ok")
    logger.info("")
    logger.info("Источник sveden: %d документов, %d сохранено", total, stored)
    _log_separator()
    return {
        "status": "ok",
        "total": total,
        "stored": stored,
        "results": results,
    }


async def crawl_confluence_help(source_url: str) -> dict:
    """Crawl Confluence Help space."""
    _log_separator("Источник: Confluence Help")
    parser = ConfluenceHelpParser()
    docs = await parser.get_documents(source_url)
    total = len(docs)
    results = []
    for idx, doc in enumerate(docs, 1):
        _log_doc_progress(idx, total, doc, "Parsed")
        result = await _store_parsed_document_logged(doc, idx, total)
        results.append(result)
    stored = sum(1 for r in results if r["status"] == "ok")
    logger.info("Источник Confluence Help: %d документов, %d сохранено", total, stored)
    _log_separator()
    return {
        "status": "ok",
        "total": total,
        "stored": stored,
        "results": results,
    }


async def crawl_confluence_study(source_url: str) -> dict:
    """Crawl Confluence Study space."""
    _log_separator("Источник: Confluence Study")
    parser = ConfluenceStudyParser()
    docs = await parser.get_documents(source_url)
    total = len(docs)
    results = []
    for idx, doc in enumerate(docs, 1):
        _log_doc_progress(idx, total, doc, "Parsed")
        result = await _store_parsed_document_logged(doc, idx, total)
        results.append(result)
    stored = sum(1 for r in results if r["status"] == "ok")
    logger.info("Источник Confluence Study: %d документов, %d сохранено", total, stored)
    _log_separator()
    return {
        "status": "ok",
        "total": total,
        "stored": stored,
        "results": results,
    }


async def crawl_utmn_faq(source_url: str) -> dict:
    """Crawl utmn.ru FAQ sections."""
    _log_separator("Источник: utmn.ru FAQ")
    parser = UtmnFaqParser()
    docs = await parser.get_documents(source_url)
    total = len(docs)
    results = []
    for idx, doc in enumerate(docs, 1):
        _log_doc_progress(idx, total, doc, "Parsed")
        result = await _store_parsed_document_logged(doc, idx, total)
        results.append(result)
    stored = sum(1 for r in results if r["status"] == "ok")
    logger.info("Источник FAQ: %d документов, %d сохранено", total, stored)
    _log_separator()
    return {
        "status": "ok",
        "total": total,
        "stored": stored,
        "results": results,
    }


async def crawl_utmn_contacts(source_url: str) -> dict:
    """Crawl utmn.ru contacts."""
    _log_separator("Источник: utmn.ru Контакты")
    parser = UtmnContactsParser()
    docs = await parser.get_documents(source_url)
    total = len(docs)
    results = []
    for idx, doc in enumerate(docs, 1):
        _log_doc_progress(idx, total, doc, "Parsed")
        result = await _store_parsed_document_logged(doc, idx, total)
        results.append(result)
    stored = sum(1 for r in results if r["status"] == "ok")
    logger.info("Источник Контакты: %d документов, %d сохранено", total, stored)
    _log_separator()
    return {
        "status": "ok",
        "total": total,
        "stored": stored,
        "results": results,
    }


async def crawl_utmn_news(
    source_url: str = "https://www.utmn.ru/news/stories/",
    max_pages: int = 3,
) -> dict:
    """Crawl новостей utmn.ru (stories) и сохранить в БЗ."""
    _log_separator("Источник: utmn.ru Новости")
    parser = UtmnNewsParser(kind="news")
    docs = await parser.get_documents(source_url, max_pages=max_pages)
    total = len(docs)
    results = []
    for idx, doc in enumerate(docs, 1):
        _log_doc_progress(idx, total, doc, "Parsed")
        result = await _store_parsed_document_logged(doc, idx, total)
        results.append(result)
    stored = sum(1 for r in results if r["status"] == "ok")
    logger.info("Источник Новости: %d документов, %d сохранено", total, stored)
    _log_separator()
    return {
        "status": "ok",
        "total": total,
        "stored": stored,
        "results": results,
    }


async def crawl_utmn_events(
    source_url: str = "https://www.utmn.ru/news/events/",
    max_pages: int = 3,
) -> dict:
    """Crawl мероприятий utmn.ru (events) и сохранить в БЗ."""
    _log_separator("Источник: utmn.ru Мероприятия")
    parser = UtmnNewsParser(kind="events")
    docs = await parser.get_documents(source_url, max_pages=max_pages)
    total = len(docs)
    results = []
    for idx, doc in enumerate(docs, 1):
        _log_doc_progress(idx, total, doc, "Parsed")
        result = await _store_parsed_document_logged(doc, idx, total)
        results.append(result)
    stored = sum(1 for r in results if r["status"] == "ok")
    logger.info("Источник Мероприятия: %d документов, %d сохранено", total, stored)
    _log_separator()
    return {
        "status": "ok",
        "total": total,
        "stored": stored,
        "results": results,
    }


TOOL_FUNCTIONS = {
    "kb_search": kb_search,
    "classify_query": classify_query,
    "kb_search_classified": kb_search_classified,
    "store_document": store_document,
    "crawl_utmn": crawl_utmn,
    "crawl_sveden": crawl_sveden,
    "crawl_confluence_help": crawl_confluence_help,
    "crawl_confluence_study": crawl_confluence_study,
    "crawl_utmn_faq": crawl_utmn_faq,
    "crawl_utmn_contacts": crawl_utmn_contacts,
    "crawl_utmn_news": crawl_utmn_news,
    "crawl_utmn_events": crawl_utmn_events,
}


async def execute_tool(name: str, arguments: dict) -> dict:
    """Dispatch tool execution by name."""
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        raise ValueError(f"Unknown tool: {name}")
    return await func(**arguments)
