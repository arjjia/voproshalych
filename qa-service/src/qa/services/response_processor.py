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
        relevant_sources: Номера релевантных источников.
        answer: Чистый текст ответа.
    """

    __slots__ = ("relevant_sources", "answer")

    def __init__(
        self,
        relevant_sources: list[int] | None = None,
        answer: str = "",
    ):
        self.relevant_sources = relevant_sources or []
        self.answer = answer


def parse_llm_json_response(raw_answer: str) -> ParsedLLMResponse:
    """Парсинг JSON ответа LLM для type=1.

    Ожидаемый формат:
    {
      "relevant_sources": [1, 3],
      "answer": "текст ответа"
    }

    Последовательность попыток:
    1. Strip markdown-обёрток (```json ... ```)
    2. Прямой JSON parse
    3. Структурированный текст (key: value)
    4. Починка обрезанного JSON
    5. Regex-извлечение answer из сырого JSON
    6. Plain text fallback

    Args:
        raw_answer: Сырой ответ от LLM.

    Returns:
        ParsedLLMResponse с распарсенными данными.
    """
    try:
        cleaned_input = _strip_json_wrappers(raw_answer)

        json_match = _extract_json_string(cleaned_input)
        if json_match:
            try:
                parsed = json.loads(json_match)
            except json.JSONDecodeError:
                parsed = None

            if parsed and isinstance(parsed, dict):
                relevant = parsed.get("relevant_sources", [])
                if not isinstance(relevant, list):
                    relevant = []
                relevant = [
                    int(x)
                    for x in relevant
                    if isinstance(x, (int, str))
                    and str(x).isdigit()
                ]

                answer = parsed.get("answer", "")
                if not isinstance(answer, str) or not answer.strip():
                    answer = raw_answer

                answer = clean_markdown(answer)

                logger.info(
                    f"[PARSE_JSON] relevant={relevant}, "
                    f"answer_len={len(answer)}"
                )

                return ParsedLLMResponse(
                    relevant_sources=relevant,
                    answer=answer,
                )

        parsed_fallback = _parse_structured_text_fallback(cleaned_input)
        if parsed_fallback is not None:
            return _sanitize_answer(parsed_fallback)

        repaired = _try_repair_truncated_json(cleaned_input)
        if repaired is not None:
            return _sanitize_answer(repaired)

        regex_fallback = _extract_answer_by_regex(cleaned_input)
        if regex_fallback is not None:
            return _sanitize_answer(regex_fallback)

        logger.warning(
            f"[PARSE_JSON] No JSON found, treating as plain text: "
            f"'{raw_answer[:200]}'"
        )
        cleaned = clean_markdown(raw_answer)
        return ParsedLLMResponse(answer=cleaned)

    except Exception as e:
        logger.warning(
            f"[PARSE_JSON] Failed: {e}, raw='{raw_answer[:200]}'"
        )
        result = _extract_answer_by_regex(raw_answer)
        if result is not None:
            return result
        cleaned = clean_markdown(raw_answer)
        return ParsedLLMResponse(answer=cleaned)


def _parse_structured_text_fallback(raw_answer: str) -> ParsedLLMResponse | None:
    """Распарсить псевдо-структурированный ответ без JSON.

    Некоторые модели могут вернуть формат вида:
    relevant_sources: [1, 3]
    answer: "..."
    """
    answer_match = re.search(
        r"answer\s*:\s*['\"](.+?)['\"]\s*$",
        raw_answer,
        flags=re.IGNORECASE | re.DOTALL,
    )

    has_sources = bool(
        re.search(r"relevant_sources\s*:\s*\[", raw_answer, flags=re.IGNORECASE)
    )

    if not has_sources and not answer_match:
        return None

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

    cleaned_answer = clean_markdown(answer)
    logger.info(
        f"[PARSE_JSON] Fallback parsed structured text: "
        f"relevant={relevant_sources}, answer_len={len(cleaned_answer)}"
    )
    return ParsedLLMResponse(
        relevant_sources=relevant_sources,
        answer=cleaned_answer,
    )


def _try_repair_truncated_json(raw_answer: str) -> ParsedLLMResponse | None:
    """Попытаться извлечь данные из обрезанного JSON-ответа LLM.

    LLM может не успеть дописать JSON до конца из-за лимита токенов.
    Формат: {"relevant_sources": [1, 2], "answer": "текст...}

    Args:
        raw_answer: Сырой ответ от LLM.

    Returns:
        ParsedLLMResponse или None, если не похоже на JSON.
    """
    text = raw_answer.strip()
    if not text.startswith("{") or "relevant_sources" not in text:
        return None

    sources_match = re.search(
        r'"relevant_sources"\s*:\s*\[([^\]]*)\]', text
    )
    if not sources_match:
        return None

    relevant = [
        int(x) for x in re.findall(r"\d+", sources_match.group(1))
    ]

    answer_match = re.search(r'"answer"\s*:\s*"', text)
    if not answer_match:
        return ParsedLLMResponse(relevant_sources=relevant, answer="")

    answer_text = text[answer_match.end():]
    answer_text = re.sub(r'"\s*\}?\s*$', "", answer_text)

    cleaned = clean_markdown(answer_text)
    logger.info(
        f"[PARSE_JSON] Repaired truncated JSON: "
        f"relevant={relevant}, answer_len={len(cleaned)}"
    )
    return ParsedLLMResponse(relevant_sources=relevant, answer=cleaned)


def _strip_json_wrappers(text: str) -> str:
    """Убрать markdown-обёртки вокруг JSON.

    LLM может вернуть JSON внутри ```json ... ``` или ``` ... ```.
    Также убирает лидирующие/трейлингные теги вроде 'json' или 'JSON'.

    Args:
        text: Сырой текст ответа LLM.

    Returns:
        Очищенный текст.
    """
    text = text.strip()

    text = re.sub(
        r"^```(?:json)?\s*\n?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\n?```\s*$",
        "",
        text,
    )

    return text.strip()


def _extract_json_string(text: str) -> str | None:
    """Извлечь JSON-строку из текста.

    Ищет сбалансированные фигурные скобки, содержащие
    "relevant_sources" или "answer".

    Args:
        text: Текст для поиска JSON.

    Returns:
        JSON-строка или None.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        c = text[i]

        if escape_next:
            escape_next = False
            continue

        if c == "\\":
            escape_next = True
            continue

        if c == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                if "relevant_sources" in candidate or '"answer"' in candidate:
                    return candidate
                start = text.find("{", i + 1)
                if start == -1:
                    return None
                depth = 0

    return None


def _extract_answer_by_regex(text: str) -> ParsedLLMResponse | None:
    """Извлечь answer и relevant_sources regex'ом из сырого текста.

    Последняя линия защиты: срабатывает когда JSON невалидный
    или обёрнут в мусор, но поля "answer" и "relevant_sources"
    читаемы.

    Args:
        text: Сырой текст.

    Returns:
        ParsedLLMResponse или None.
    """
    if '"answer"' not in text and '"relevant_sources"' not in text:
        return None

    relevant = []
    sources_match = re.search(
        r'"relevant_sources"\s*:\s*\[([^\]]*)\]', text
    )
    if sources_match:
        relevant = [
            int(x) for x in re.findall(r"\d+", sources_match.group(1))
        ]

    answer = ""
    answer_match = re.search(
        r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', text
    )
    if answer_match:
        answer = answer_match.group(1)
        answer = answer.replace('\\"', '"')
        answer = answer.replace("\\n", "\n")
        answer = answer.replace("\\\\", "\\")
        answer = answer.strip()

    if not answer:
        return None

    answer = clean_markdown(answer)
    logger.warning(
        f"[PARSE_JSON] Regex fallback: "
        f"relevant={relevant}, answer_len={len(answer)}"
    )
    return ParsedLLMResponse(relevant_sources=relevant, answer=answer)


def _sanitize_answer(response: ParsedLLMResponse) -> ParsedLLMResponse:
    """Проверить, не выглядит ли answer как сырой JSON.

    Если answer начинается с '{' и содержит '"answer"' —
    попытаться вытащить текст ответа ещё раз.

    Args:
        response: Результат парсинга для проверки.

    Returns:
        Тот же или исправленный ParsedLLMResponse.
    """
    answer = response.answer.strip()

    if answer.startswith("{") and '"answer"' in answer:
        logger.warning(
            "[PARSE_JSON] Answer looks like raw JSON, "
            "extracting answer field"
        )
        extracted = _extract_answer_by_regex(answer)
        if extracted and extracted.answer.strip():
            response.answer = extracted.answer
            if extracted.relevant_sources:
                response.relevant_sources = extracted.relevant_sources

    return response


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
    seen_urls: set[str] = set()
    for idx in relevant_source_indices:
        url = source_index.get(str(idx))
        if url and url.startswith("http") and url not in seen_urls:
            seen_urls.add(url)
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
