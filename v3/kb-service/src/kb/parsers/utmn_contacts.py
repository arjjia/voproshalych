"""Парсер страницы контактов ТюмГУ (www.utmn.ru/kontakty/).

Парсит блоки контактов, сохраняя привязку данных к заголовкам.
Ссылки внутри блоков сохраняются в исходном виде.
"""

import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseParser, ParsedDocument

logger = logging.getLogger(__name__)

CONTACTS_URL = "https://www.utmn.ru/kontakty/"


class UtmnContactsParser(BaseParser):
    """Парсер страницы контактов ТюмГУ.

    Каждый блок контактов (заголовок + содержимое) превращается
    в отдельный ParsedDocument.
    """

    def __init__(self) -> None:
        self._base_url = "https://www.utmn.ru"

    def get_source_type(self) -> str:
        return "utmn_contacts"

    async def get_documents(self, source_url: str) -> list[ParsedDocument]:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0)",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(source_url, headers=headers)
                response.raise_for_status()
        except Exception as e:
            logger.error(f"Ошибка загрузки контактов {source_url}: {e}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        documents: list[ParsedDocument] = []

        blocks = soup.select(".footer-contacts__block")
        for block in blocks:
            title_el = block.select_one(".footer-contacts__title")
            content_el = block.select_one(".footer-contacts__content")
            if not title_el or not content_el:
                continue

            title = title_el.get_text(strip=True)
            text = self._extract_block_text(content_el)

            if not text.strip():
                continue

            documents.append(
                ParsedDocument(
                    url=source_url,
                    title=f"Контакты — {title}",
                    text_content=f"{title}\n{text}",
                    source_type=self.get_source_type(),
                )
            )
            logger.info(f"Контакты: блок «{title}»")

        h2_sections = soup.select("h2")
        for h2 in h2_sections:
            section_title = h2.get_text(strip=True)
            next_sibling = h2.find_next_sibling()
            if not next_sibling:
                continue

            if section_title == "Институты":
                institute_links = next_sibling.select("a[href]")
                if institute_links:
                    lines = []
                    for link in institute_links:
                        name = link.get_text(strip=True)
                        href = link.get("href", "")
                        full_url = urljoin(self._base_url, href)
                        lines.append(f"{name}: {full_url}")
                    text = "\n".join(lines)
                    documents.append(
                        ParsedDocument(
                            url=source_url,
                            title=f"Контакты — {section_title}",
                            text_content=f"{section_title}\n{text}",
                            source_type=self.get_source_type(),
                        )
                    )
                    logger.info(f"Контакты: секция «{section_title}»")

        logger.info(f"Страница контактов: {len(documents)} блоков из {source_url}")
        return documents

    def _extract_block_text(self, content_el) -> str:
        """Извлечь текст из блока контактов, сохраняя ссылки."""
        parts: list[str] = []
        for child in content_el.children:
            text = self._process_element(child)
            if text:
                parts.append(text)
        return "\n".join(parts)

    def _process_element(self, el) -> str:
        """Рекурсивно обработать HTML-элемент, сохраняя ссылки."""
        if isinstance(el, str):
            text = el.strip()
            return text if text else ""

        if el.name in ("script", "style"):
            return ""

        if el.name == "a":
            href = el.get("href", "")
            text = el.get_text(strip=True)
            if href.startswith("mailto:"):
                return text
            if href.startswith("tel:"):
                return text
            full_url = urljoin(self._base_url, href)
            return f"{text}: {full_url}"

        if el.name == "ul":
            items = []
            for li in el.select(":scope > li"):
                li_text = self._process_element(li)
                if li_text:
                    items.append(li_text)
            return "\n".join(items)

        if el.name == "li":
            parts = []
            for child in el.children:
                text = self._process_element(child)
                if text:
                    parts.append(text)
            return " ".join(parts)

        parts = []
        for child in el.children:
            text = self._process_element(child)
            if text:
                parts.append(text)
        return "\n".join(parts)
