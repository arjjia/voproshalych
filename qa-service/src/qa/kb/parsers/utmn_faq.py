"""Парсер FAQ ТюмГУ (www.utmn.ru/abiturient/faq/).

Парсит все 5 страниц FAQ. Каждый вопрос-ответ — отдельный документ.
Ответы скрыты в HTML (accordion), парсятся напрямую без JS.
"""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from .base import BaseParser, ParsedDocument

logger = logging.getLogger(__name__)

FAQ_BASE_URL = "https://www.utmn.ru/abiturient/faq/"
FAQ_TOTAL_PAGES = 5


class UtmnFaqParser(BaseParser):
    """Парсер FAQ абитуриентов ТюмГУ.

    Проходится по всем страницам пагинации (1-5).
    Каждый вопрос-ответ становится отдельным ParsedDocument.
    """

    def __init__(self) -> None:
        self._base_url = "https://www.utmn.ru"

    def get_source_type(self) -> str:
        return "utmn_faq"

    async def get_documents(self, source_url: str) -> list[ParsedDocument]:
        documents: list[ParsedDocument] = []

        for page_num in range(1, FAQ_TOTAL_PAGES + 1):
            if page_num == 1:
                url = source_url
            else:
                url = f"{source_url}?PAGEN_1={page_num}"

            page_docs = await self._parse_faq_page(url, page_num)
            documents.extend(page_docs)

        logger.info(f"FAQ: всего {len(documents)} вопросов-ответов")
        return documents

    async def _parse_faq_page(self, url: str, page_num: int) -> list[ParsedDocument]:
        """Парсинг одной страницы FAQ."""
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0)",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
        except Exception as e:
            logger.error(f"Ошибка загрузки FAQ страница {page_num}: {e}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        documents: list[ParsedDocument] = []

        faq_items = soup.select("li")
        for item in faq_items:
            question_el = item.select_one("a.toggle")
            if not question_el:
                continue

            answer_el = item.select_one("div.inner")
            if not answer_el:
                continue

            question = question_el.get_text(strip=True)
            answer = self._extract_answer(answer_el)

            if not question or not answer:
                continue

            text_content = f"Вопрос: {question}\nОтвет: {answer}"

            documents.append(
                ParsedDocument(
                    url=url,
                    title=question,
                    text_content=text_content,
                    source_type=self.get_source_type(),
                )
            )

        logger.info(f"FAQ страница {page_num}: {len(documents)} вопросов из {url}")
        return documents

    def _extract_answer(self, answer_el) -> str:
        """Извлечь текст ответа, сохраняя ссылки."""
        parts: list[str] = []
        for child in answer_el.children:
            text = self._process_node(child)
            if text:
                parts.append(text)
        result = "\n".join(parts)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    def _process_node(self, node) -> str:
        """Рекурсивно обработать узел ответа."""
        if isinstance(node, str):
            text = node.strip()
            return text if text else ""

        if node.name in ("script", "style"):
            return ""

        if node.name == "a":
            href = node.get("href", "")
            text = node.get_text(strip=True)
            if not text:
                return ""
            full_url = f"{self._base_url}{href}" if href.startswith("/") else href
            return f"{text}: {full_url}"

        if node.name == "br":
            return ""

        parts = []
        for child in node.children:
            text = self._process_node(child)
            if text:
                parts.append(text)
        return "\n".join(parts)
