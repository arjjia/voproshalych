"""Постобработка ответа LLM: очистка markdown, извлечение ссылок."""

import logging
import re

logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4000


def clean_markdown(text: str) -> str:
    """Удалить markdown форматирование из текста.

    Убирает: ##, ###, **, *, нумерованные списки, дефисные списки,
    ссылки в формате [text](url), теги <entity:...>, маркеры cite.

    Args:
        text: Исходный текст с markdown.

    Returns:
        Чистый текст без markdown.
    """
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"<entity:[^>]*>", "", text)
    text = re.sub(r"【\d+†[^】]*】", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_links(text: str) -> tuple[str, list[str]]:
    """Извлечь URL из текста и вернуть чистый текст + список ссылок.

    Ищет ссылки в форматах:
    - Подробнее: URL
    - References / Источники секции с URL
    - Голые URL

    Args:
        text: Текст для обработки.

    Returns:
        Кортеж (clean_text, list_of_urls).
    """
    urls = []
    clean_lines = []
    url_pattern = re.compile(
        r"https?://[^\s<>\[\](){}\"']*[^\s<>\[\](){}\"'.,;:!]"
    )

    for line in text.split("\n"):
        stripped = line.strip()

        if stripped.lower().startswith("подробнее:"):
            link_part = stripped[len("подробнее:"):].strip()
            found_urls = url_pattern.findall(link_part)
            urls.extend(found_urls)
            continue

        if stripped.lower().startswith("references"):
            continue

        if stripped.startswith("http://") or stripped.startswith("https://"):
            found_urls = url_pattern.findall(stripped)
            if found_urls and not stripped.startswith("http"):
                urls.extend(found_urls)
                continue

        if re.match(r"^\[\d+\]\s*", stripped):
            found_urls = url_pattern.findall(stripped)
            urls.extend(found_urls)
            continue

        if re.match(r"^-\s*\[?\d+\]?\s*https?://", stripped):
            found_urls = url_pattern.findall(stripped)
            urls.extend(found_urls)
            continue

        clean_lines.append(line)

    clean_text = "\n".join(clean_lines).strip()
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)

    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return clean_text, unique_urls


def format_answer(text: str, max_length: int = 1500) -> str:
    """Обрезать ответ до max_length с сохранением целостности абзацев.

    Args:
        text: Текст для обрезки.
        max_length: Максимальная длина.

    Returns:
        Обрезанный текст.
    """
    if len(text) <= max_length:
        return text

    truncated = text[:max_length]
    last_para = truncated.rfind("\n\n")
    last_newline = truncated.rfind("\n")

    cut_point = last_para if last_para > max_length * 0.7 else last_newline
    if cut_point < max_length * 0.5:
        cut_point = max_length

    result = text[:cut_point].strip()
    return result


def process_llm_response(raw_answer: str) -> tuple[str, list[str]]:
    """Полный пайплайн постобработки ответа LLM.

    1. Очистка markdown
    2. Извлечение ссылок
    3. Форматирование (обрезка)

    Args:
        raw_answer: Сырой ответ от LLM.

    Returns:
        Кортеж (clean_answer, links).
    """
    logger.info(
        f"[POSTPROCESS] Input: {len(raw_answer)} chars"
    )

    cleaned = clean_markdown(raw_answer)
    logger.info(f"[POSTPROCESS] After markdown clean: {len(cleaned)} chars")

    cleaned, links = extract_links(cleaned)
    logger.info(
        f"[POSTPROCESS] After link extraction: "
        f"{len(cleaned)} chars, {len(links)} links"
    )

    formatted = format_answer(cleaned)
    logger.info(f"[POSTPROCESS] Final: {len(formatted)} chars")

    return formatted, links
