"""Парсер для пространства help на Confluence (confluence.utmn.ru).

Парсит HTML страницы + отдельные PDF документы.
PDF вложения со страниц НЕ парсятся — ссылки остаются как текст.
"""

import logging
import os
import re
from io import BytesIO
from typing import Any

import httpx
import pdfplumber
import pytesseract
from bs4 import BeautifulSoup

from .base import BaseParser, ParsedDocument
from .ocr_cache import get_ocr_config, get_tesseract_version

logger = logging.getLogger(__name__)

HELP_PAGES: dict[str, dict[str, Any]] = {
    "8037241": {"title": "Карты доступа", "children": False},
    "8037222": {"title": "Корпоративная учетная запись", "children": False},
    "62586931": {"title": "Яндекс 360", "children": True},
    "121923452": {"title": "Единый личный кабинет ТюмГУ", "children": True},
    "121906735": {"title": "Основы работы с LMS", "children": False},
    "8037245": {"title": "Беспроводная сеть Wi-Fi", "children": False},
}

HELP_PDF_URLS: list[tuple[str, str]] = [
    (
        "Условия по использованию услуг Wi-Fi",
        "https://confluence.utmn.ru/download/attachments/8037875/terms.4be25f01.pdf"
        "?version=1&modificationDate=1615881981974&api=v2",
    ),
    (
        "Положение о порядке использования сети Интернет и электронной почты в ТюмГУ",
        "https://confluence.utmn.ru/download/attachments/8037875/247_1.pdf"
        "?version=1&modificationDate=1621592539032&api=v2",
    ),
]


class ConfluenceHelpParser(BaseParser):
    """Парсер для пространства help на Confluence.

    Парсит HTML контент страниц. PDF вложения со страниц не обрабатываются
    (ссылки остаются в тексте). Отдельные PDF документы парсятся через OCR.
    """

    def __init__(self) -> None:
        self._host = os.getenv("CONFLUENCE_HOST", "https://confluence.utmn.ru")
        self._token = os.getenv("CONFLUENCE_TOKEN", "")
        self._headers: dict[str, str] = {}
        if self._token:
            self._headers["Authorization"] = f"Bearer {self._token}"
        self._headers["Accept"] = "application/json"

    def get_source_type(self) -> str:
        return "confluence_help"

    async def get_documents(self, source_url: str) -> list[ParsedDocument]:
        documents: list[ParsedDocument] = []

        page_ids = list(HELP_PAGES.keys())
        for page_id in page_ids:
            meta = HELP_PAGES[page_id]
            title = meta["title"]
            page_url = f"{self._host}/pages/viewpage.action?pageId={page_id}"

            html_doc = await self._parse_page_html(page_id, title, page_url)
            if html_doc and html_doc.text_content.strip():
                documents.append(html_doc)

            if meta.get("children"):
                child_docs = await self._get_child_pages_recursive(page_id)
                documents.extend(child_docs)

        for pdf_title, pdf_url in HELP_PDF_URLS:
            doc = await self._parse_pdf(pdf_url, pdf_title, self._host)
            if doc:
                documents.append(doc)

        return documents

    async def _parse_page_html(
        self, page_id: str, title: str, page_url: str
    ) -> ParsedDocument | None:
        try:
            url = f"{self._host}/rest/api/content/{page_id}"
            params = {"expand": "body.export_view"}
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._headers, params=params)
                response.raise_for_status()
                data = response.json()

            page_body = data.get("body", {}).get("export_view", {}).get("value", "")
            if len(page_body) < 50:
                return None

            soup = BeautifulSoup(page_body, "html.parser")
            page_content = soup.get_text(separator=" ")

            if len(page_content.strip()) < 50:
                return None

            return ParsedDocument(
                url=page_url,
                title=title,
                text_content=page_content,
                source_type=self.get_source_type(),
            )
        except Exception as e:
            logger.error(f"Error parsing page HTML {page_id}: {e}")
            return None

    async def _get_child_pages_recursive(
        self, parent_id: str, visited: set[str] | None = None
    ) -> list[ParsedDocument]:
        if visited is None:
            visited = set()
        if parent_id in visited:
            return []
        visited.add(parent_id)

        documents: list[ParsedDocument] = []
        url = f"{self._host}/rest/api/content/{parent_id}/child/page"
        params = {"limit": 100}

        async with httpx.AsyncClient(timeout=30.0) as client:
            while url:
                response = await client.get(url, headers=self._headers, params=params)
                if response.status_code != 200:
                    break
                data = response.json()
                results = data.get("results", [])

                for page in results:
                    child_id = page["id"]
                    child_title = page.get("title", "Untitled")
                    child_url = self._host + page.get("_links", {}).get("webui", "")

                    html_doc = await self._parse_page_html(
                        child_id, child_title, child_url
                    )
                    if html_doc and html_doc.text_content.strip():
                        documents.append(html_doc)

                    child_docs = await self._get_child_pages_recursive(
                        child_id, visited
                    )
                    documents.extend(child_docs)

                next_url = data.get("_links", {}).get("next")
                url = None
                if next_url:
                    url = next_url if next_url.startswith("http") else self._host + next_url
                    params = {}

        return documents

    async def _parse_pdf(
        self, download_url: str, title: str, page_url: str
    ) -> ParsedDocument | None:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0)",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(download_url, headers=headers)
                response.raise_for_status()

            pdf_bytes = BytesIO(response.content)
            text_content = await self._extract_text_ocr(pdf_bytes)
            text_content = self._clean_text(text_content)

            if not text_content.strip():
                logger.warning(f"Пустой контент в PDF: {download_url}")
                return None

            logger.info(f"Распарсен PDF: {title}")
            return ParsedDocument(
                url=page_url,
                title=title,
                text_content=text_content,
                source_type=self.get_source_type(),
            )
        except Exception as e:
            logger.error(f"Ошибка парсинга PDF {download_url}: {e}")
            return None

    async def _extract_text_ocr(self, pdf_bytes: BytesIO) -> str:
        get_tesseract_version()
        ocr_config = get_ocr_config()
        pdf_bytes.seek(0)

        with pdfplumber.open(pdf_bytes) as pdf:
            pages_text = []
            for page in pdf.pages:
                page_image = page.to_image(resolution=220)
                pil_image = page_image.original
                ocr_text = pytesseract.image_to_string(
                    pil_image,
                    lang="rus+eng",
                    config=" ".join(ocr_config),
                )
                if ocr_text and ocr_text.strip():
                    pages_text.append(ocr_text.strip())

            if pages_text:
                return "\n".join(pages_text)

        return ""

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
        text = re.sub(r"([а-яёА-ЯЁa-zA-Z0-9])\s{2,}", r"\1 ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        lines = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                lines.append(line)

        return "\n".join(lines)
