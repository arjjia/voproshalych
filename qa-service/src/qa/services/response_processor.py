"""Постобработка ответа LLM: парсинг JSON, очистка markdown, извлечение ссылок."""

import json
import logging
import re

from ..models.request import SourceLink

logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4000


class ParsedLLMResponse:
    """Результат парсинга ответа LLM для type=1 (БЗ).

    Attributes:
        relevance_type: «a» (релевантный контекст) или «b» (нерелевантный).
        relevant_sources: Номера релевантных источников.
        irrelevant_sources: Номера нерелевантных источников.
        answer: Чистый текст ответа.
    """

    __slots__ = ("relevance_type", "relevant_sources", "irrelevant_sources", "answer")

    def __init__(
        self,
        relevance_type: str = "b",
        relevant_sources: list[int] | None = None,
        irrelevant_sources: list[int] | None = None,
        answer: str = "",
    ):
        self.relevance_type = relevance_type
        self.relevant_sources = relevant_sources or []
        self.irrelevant_sources = irrelevant_sources or []
        self.answer = answer


def parse_llm_json_response(raw_answer: str) -> ParsedLLMResponse:
    """Парсинг JSON ответа LLM для type=1.

    Ожидаемый формат:
    {
      "relevance_type": "a" | "b",
      "relevant_sources": [1, 3],
      "irrelevant_sources": [2, 4, 5],
      "answer": "текст ответа"
    }

    Args:
        raw_answer: Сырой ответ от LLM.

    Returns:
        ParsedLLMResponse с распарсенными данными.
    """
    try:
        json_match = re.search(r"\{[^{}]*\}", raw_answer, re.DOTALL)
        if not json_match:
            parsed_fallback = _parse_structured_text_fallback(raw_answer)
            if parsed_fallback is not None:
                return parsed_fallback

            logger.warning(
                f"[PARSE_JSON] No JSON found, treating as plain text: "
                f"'{raw_answer[:200]}'"
            )
            cleaned = clean_markdown(raw_answer)
            return ParsedLLMResponse(
                relevance_type="b",
                answer=cleaned,
            )

        parsed = json.loads(json_match.group())

        rel_type = parsed.get("relevance_type", "b")
        if rel_type not in ("a", "b"):
            rel_type = "b"

        relevant = parsed.get("relevant_sources", [])
        if not isinstance(relevant, list):
            relevant = []
        relevant = [int(x) for x in relevant if isinstance(x, (int, str)) and str(x).isdigit()]

        irrelevant = parsed.get("irrelevant_sources", [])
        if not isinstance(irrelevant, list):
            irrelevant = []
        irrelevant = [int(x) for x in irrelevant if isinstance(x, (int, str)) and str(x).isdigit()]

        answer = parsed.get("answer", "")
        if not isinstance(answer, str) or not answer.strip():
            answer = raw_answer

        answer = clean_markdown(answer)

        logger.info(
            f"[PARSE_JSON] type={rel_type}, "
            f"relevant={relevant}, irrelevant={irrelevant}, "
            f"answer_len={len(answer)}"
        )

        return ParsedLLMResponse(
            relevance_type=rel_type,
            relevant_sources=relevant,
            irrelevant_sources=irrelevant,
            answer=answer,
        )

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[PARSE_JSON] Failed: {e}, raw='{raw_answer[:200]}'")
        cleaned = clean_markdown(raw_answer)
        return ParsedLLMResponse(
            relevance_type="b",
            answer=cleaned,
        )


def _parse_structured_text_fallback(raw_answer: str) -> ParsedLLMResponse | None:
    """Распарсить псевдо-структурированный ответ без JSON.

    Некоторые модели могут вернуть формат вида:
    relevance_type: "b"
    relevant_sources: []
    irrelevant_sources: []
    answer: "..."
    """
    rel_type_match = re.search(
        r"relevance_type\s*:\s*['\"]?([ab])['\"]?",
        raw_answer,
        flags=re.IGNORECASE,
    )
    answer_match = re.search(
        r"answer\s*:\s*['\"](.+?)['\"]\s*$",
        raw_answer,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not rel_type_match and not answer_match:
        return None

    rel_type = (rel_type_match.group(1).lower() if rel_type_match else "b")
    answer = answer_match.group(1).strip() if answer_match else raw_answer

    relevant_sources = [
        int(x)
        for x in re.findall(
            r"relevant_sources\s*:\s*\[([^\]]*)\]",
            raw_answer,
            flags=re.IGNORECASE,
        )[:1]
        for x in re.findall(r"\d+", x)
    ]
    irrelevant_sources = [
        int(x)
        for x in re.findall(
            r"irrelevant_sources\s*:\s*\[([^\]]*)\]",
            raw_answer,
            flags=re.IGNORECASE,
        )[:1]
        for x in re.findall(r"\d+", x)
    ]

    cleaned_answer = clean_markdown(answer)
    logger.info(
        f"[PARSE_JSON] Fallback parsed structured text: "
        f"type={rel_type}, relevant={relevant_sources}, "
        f"irrelevant={irrelevant_sources}, answer_len={len(cleaned_answer)}"
    )
    return ParsedLLMResponse(
        relevance_type=rel_type if rel_type in ("a", "b") else "b",
        relevant_sources=relevant_sources,
        irrelevant_sources=irrelevant_sources,
        answer=cleaned_answer,
    )


def build_source_links(
    relevant_source_indices: list[int],
    source_index: dict[str, str],
) -> list[SourceLink]:
    """Построить список SourceLink для inline-кнопок из релевантных источников.

    Args:
        relevant_source_indices: Номера релевантных источников.
        source_index: Маппинг {номер: URL}.

    Returns:
        Список SourceLink с URL и label.
    """
    links: list[SourceLink] = []
    for idx in relevant_source_indices:
        url = source_index.get(str(idx))
        if url and url.startswith("http"):
            links.append(
                SourceLink(
                    url=url,
                    label=f"Подробнее {len(links) + 1}",
                )
            )
    return links


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
    text = re.sub(r"<(\s*https?://[^>]+)\s*>", r"\1", text)
    text = re.sub(r"<entity:[^>]*>", "", text)
    text = re.sub(r"【\d+†[^】]*】", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
    """Полный пайплайн постобработки ответа LLM (для type=2,3).

    1. Очистка markdown
    2. Удаление строки об использованных источниках
    3. Извлечение ссылок
    4. Форматирование (обрезка)

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

    cleaned = re.sub(r"^нет\.\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\([^)]*\)\s*", "", cleaned)

    cleaned = re.sub(
        r"\n*[Ии]спользованн?ые?\s+источники:\s*[\d,\s]+\n*",
        "\n",
        cleaned,
    ).strip()

    cleaned, links = extract_links(cleaned)
    logger.info(
        f"[POSTPROCESS] After link extraction: "
        f"{len(cleaned)} chars, {len(links)} links"
    )

    formatted = format_answer(cleaned)
    logger.info(f"[POSTPROCESS] Final: {len(formatted)} chars")

    return formatted, links


def extract_links(text: str) -> tuple[str, list[str]]:
    """Извлечь URL из текста и вернуть чистый текст + список ссылок.

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
            link_part = link_part.strip("<>").strip()
            found_urls = url_pattern.findall(link_part)
            urls.extend(found_urls)
            continue

        if stripped.lower().startswith("references"):
            continue

        if stripped.lower().startswith("источники"):
            continue

        if re.match(r"^\[\d+\]\s*https?://", stripped):
            found_urls = url_pattern.findall(stripped)
            urls.extend(found_urls)
            continue

        if re.match(r"^-\s*\[\d+\]\s*https?://", stripped):
            found_urls = url_pattern.findall(stripped)
            urls.extend(found_urls)
            continue

        line_clean = stripped
        line_clean = line_clean.replace("<https://", "https://")
        line_clean = line_clean.replace("https://>", "https://")
        line_clean = line_clean.replace("<http://", "http://")
        line_clean = line_clean.replace("http://>", "http://")

        clean_lines.append(line_clean)

    clean_text = "\n".join(clean_lines).strip()
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)

    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return clean_text, unique_urls
