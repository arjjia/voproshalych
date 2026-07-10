"""Парсер веб-страниц и PDF."""

import logging
import re
from io import BytesIO

import httpx
import pdfplumber
import pytesseract
from bs4 import BeautifulSoup
from PIL import Image

from .base import ParsedDocument
from .ocr_cache import get_ocr_config, get_tesseract_version


logger = logging.getLogger(__name__)


class WebPageParser:
    """Парсер для извлечения контента с веб-страниц и PDF."""

    async def parse(self, url: str) -> ParsedDocument:
        """Распарсить веб-страницу или PDF и извлечь контент.

        Args:
            url: URL страницы или PDF для парсинга

        Returns:
            ParsedDocument с извлечённым контентом

        Raises:
            httpx.HTTPStatusError: Если запрос неуспешен
        """
        if url.lower().endswith(".pdf"):
            return await self._parse_pdf(url)
        return await self._parse_html(url)

    async def _parse_html(self, url: str) -> ParsedDocument:
        """Распарсить HTML-страницу."""
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0; +https://voproshalych.ru)",
        }

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for script in soup(["script", "style"]):
            script.decompose()

        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        content = soup.get_text(separator="\n", strip=True)

        lines = (line.strip() for line in content.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text_content = "\n".join(chunk for chunk in chunks if chunk)

        logger.info(f"Распарсен HTML с {url}: title='{title[:50]}...'")

        return ParsedDocument(
            url=url,
            title=title,
            text_content=text_content,
            source_type="web",
        )

    async def _parse_pdf(self, url: str) -> ParsedDocument:
        """Распарсить PDF-файл.

        Всегда использует Tesseract OCR для извлечения текста из любого PDF.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0; +https://voproshalych.ru)",
        }

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

        pdf_bytes = BytesIO(response.content)

        text_content = await self._extract_text_ocr(pdf_bytes)

        text_content = self._clean_text(text_content)

        title = self._extract_title_from_url(url)

        logger.info(f"Распарсен PDF с {url}: title='{title}'")

        return ParsedDocument(
            url=url,
            title=title,
            text_content=text_content,
            source_type="pdf",
        )

    async def _extract_text_ocr(self, pdf_bytes: BytesIO) -> str:
        """Извлечь текст из PDF с помощью Tesseract OCR.

        Args:
            pdf_bytes: PDF файл в памяти

        Returns:
            Текст из PDF
        """
        try:
            get_tesseract_version()
            ocr_config = get_ocr_config()
            pdf_bytes.seek(0)
            with pdfplumber.open(pdf_bytes) as pdf:
                pages_text = []
                for page in pdf.pages:
                    page_image = page.to_image(resolution=300)
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

        except Exception as e:
            logger.warning(f"OCR не сработал: {e}")

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

    def _extract_title_from_url(self, url: str) -> str:
        """Извлечь название документа из URL.

        Args:
            url: URL документа

        Returns:
            Название документа
        """
        filename = url.split("/")[-1]
        filename = re.sub(r"\?.*$", "", filename)
        filename = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
        filename = filename.replace("-", " ").replace("_", " ")
        filename = re.sub(r"\s+", " ", filename)
        return filename.strip()
