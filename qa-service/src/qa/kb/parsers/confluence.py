"""Парсер для Confluence (confluence.utmn.ru).

Использует REST API Confluence для получения ссылок на PDF документы,
скачивает их и парсит в текст.
"""

import logging
import os
import re
from io import BytesIO
from urllib.parse import urljoin
from typing import Any

import httpx
import pdfplumber
import pytesseract
from bs4 import BeautifulSoup
from PIL import Image

from .base import BaseParser, ParsedDocument
from .ocr_cache import get_ocr_config, get_tesseract_version


logger = logging.getLogger(__name__)

ALLOWED_PDF_TITLES = [
    "terms.4be25f01",
    "247_1",
    "514-1",
    "540-1",
    "Политика обеспечения информационной безопасности",
    "Положение о безопасности автоматизированного рабочего места",
    "Положение о порядке предоставления удаленного доступа",
]


class ConfluenceParser(BaseParser):
    """Парсер для Confluence API.

    Получает страницу Confluence, находит ссылки на PDF документы,
    скачивает и парсит их. Парсит только разрешённые PDF.
    """

    def __init__(self) -> None:
        """Инициализировать парсер."""
        self._host = os.getenv("CONFLUENCE_HOST", "https://confluence.utmn.ru")
        self._token = os.getenv("CONFLUENCE_TOKEN", "")
        self._headers: dict[str, str] = {}
        if self._token:
            self._headers["Authorization"] = f"Bearer {self._token}"
        self._headers["Accept"] = "application/json"

    def get_source_type(self) -> str:
        """Вернуть тип источника."""
        return "confluence"

    def _is_allowed_pdf(self, title: str) -> bool:
        """Проверить, разрешён ли PDF для парсинга.

        Args:
            title: Название PDF

        Returns:
            True если PDF разрешён
        """
        title_lower = title.lower()
        for allowed in ALLOWED_PDF_TITLES:
            if allowed.lower() in title_lower or title_lower in allowed.lower():
                return True
        return False

    async def get_documents(self, source_url: str) -> list[ParsedDocument]:
        """Получить PDF документы со страницы Confluence.

        Args:
            source_url: URL страницы Confluence с PDF ссылками

        Returns:
            Список распарсенных PDF документов
        """
        page_id = self._extract_page_id(source_url)
        if not page_id:
            logger.error(f"Не удалось извлечь page_id из URL: {source_url}")
            return []

        attachments = await self._get_attachments(page_id)
        logger.info(f"Найдено {len(attachments)} вложений на странице {page_id}")

        allowed_count = sum(
            1 for a in attachments if self._is_allowed_pdf(a.get("title", ""))
        )
        logger.info(f"Разрешённых PDF для парсинга: {allowed_count}")

        documents = []
        for attachment in attachments:
            title = attachment.get("title", "")

            if not self._is_allowed_pdf(title):
                logger.debug(f"Пропуск PDF (не в списке): {title}")
                continue

            download_url = attachment["_links"]["download"]
            if not download_url.startswith("http"):
                download_url = self._host + download_url

            media_type = attachment.get("metadata", {}).get(
                "mediaType", ""
            ) or attachment.get("extensions", {}).get("mediaType", "")

            if "pdf" in str(media_type).lower() or download_url.lower().endswith(
                ".pdf"
            ):
                doc = await self._parse_pdf(download_url, title, source_url)
                if doc:
                    documents.append(doc)

        return documents

    def _extract_page_id(self, url: str) -> str | None:
        """Извлечь pageId из URL страницы Confluence.

        Args:
            url: URL страницы Confluence

        Returns:
            ID страницы или None
        """
        match = re.search(r"pageId[=/](\d+)", url)
        if match:
            return match.group(1)
        return None

    async def _get_attachments(self, page_id: str) -> list[dict[str, Any]]:
        """Получить список вложений (аттачментов) со страницы.

        Args:
            page_id: ID страницы Confluence

        Returns:
            Список аттачментов с метаданными
        """
        url = f"{self._host}/rest/api/content/{page_id}/child/attachment"
        params = {"limit": 100}

        attachments = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            while url:
                response = await client.get(url, headers=self._headers, params=params)
                response.raise_for_status()
                data = response.json()

                attachments.extend(data.get("results", []))

                url = data.get("_links", {}).get("next")
                params = {}

        return attachments

    async def _parse_pdf(
        self, download_url: str, title: str, page_url: str
    ) -> ParsedDocument | None:
        """Скачать и распарсить PDF файл.

        Всегда использует Tesseract OCR для извлечения текста из любого PDF.

        Args:
            download_url: URL для скачивания PDF файла
            title: Название документа
            page_url: Оригинальный URL страницы Confluence

        Returns:
            ParsedDocument с содержимым или None при ошибке
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0)",
            "Authorization": f"Bearer {self._token}" if self._token else "",
        }

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
        """Извлечь текст из PDF с использованием OCR (Tesseract).

        Args:
            pdf_bytes: PDF файл в памяти

        Returns:
            Текст из PDF
        """
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
        """Очистить текст от артефактов PDF.

        Args:
            text: Сырой текст из PDF

        Returns:
            Очищенный текст
        """
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

        text = re.sub(r"([а-яёА-ЯЁa-zA-Z0-9])\s{2,}", r"\1 ", text)

        text = re.sub(r"\n{3,}", "\n\n", text)

        lines = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                lines.append(line)

        return "\n".join(lines)
