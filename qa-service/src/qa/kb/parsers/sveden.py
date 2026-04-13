"""Парсер для портала Сведения об организации (sveden.utmn.ru).

Получает страницу https://sveden.utmn.ru/sveden/document/,
находит все ссылки на PDF документы, скачивает и парсит их.
"""

import logging
import re
from io import BytesIO
from urllib.parse import urljoin

import httpx
import pdfplumber
import pytesseract
from bs4 import BeautifulSoup
from PIL import Image

from .base import BaseParser, ParsedDocument
from .ocr_cache import get_ocr_config, get_tesseract_version


logger = logging.getLogger(__name__)


class SvedenParser(BaseParser):
    """Парсер для портала Сведения.

    Получает страницу, находит ссылки на PDF, парсит каждый PDF.
    """

    def __init__(self) -> None:
        """Инициализировать парсер."""
        self._base_url = "https://sveden.utmn.ru"

    def get_source_type(self) -> str:
        """Вернуть тип источника."""
        return "sveden"

    async def get_documents(self, source_url: str) -> list[ParsedDocument]:
        """Получить PDF документы со страницы Сведения.

        Args:
            source_url: URL страницы Сведения (обычно sveden.utmn.ru/sveden/document/)

        Returns:
            Список распарсенных PDF документов
        """
        pdf_urls = await self._find_pdf_links(source_url)
        logger.info(f"Найдено {len(pdf_urls)} PDF ссылок на {source_url}")

        documents = []
        for pdf_url in pdf_urls:
            doc = await self._parse_pdf(pdf_url)
            if doc:
                documents.append(doc)

        return documents

    async def _find_pdf_links(self, url: str) -> list[str]:
        """Найти все ссылки на PDF на странице.

        Args:
            url: URL страницы для поиска

        Returns:
            Список URL PDF файлов
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0)",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            pdf_urls = set()
            for link in soup.find_all("a", href=True):
                href = str(link.get("href", ""))
                if ".pdf" in href.lower():
                    full_url = urljoin(self._base_url, href)
                    pdf_urls.add(full_url)

            return list(pdf_urls)

        except Exception as e:
            logger.error(f"Ошибка поиска PDF ссылок на {url}: {e}")
            return []

    async def _parse_pdf(self, url: str) -> ParsedDocument | None:
        """Скачать и распарсить PDF файл.

        Всегда использует Tesseract OCR для извлечения текста из любого PDF.

        Args:
            url: URL PDF файла

        Returns:
            ParsedDocument с содержимым или None при ошибке
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0)",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

            pdf_bytes = BytesIO(response.content)

            text_content = await self._extract_text_ocr(pdf_bytes)

            text_content = self._clean_text(text_content)

            if not text_content.strip():
                logger.warning(f"Пустой контент в PDF: {url}")
                return None

            title = self._extract_title_from_url(url)
            logger.info(f"Распарсен PDF: {title}")

            return ParsedDocument(
                url=url,
                title=title,
                text_content=text_content,
                source_type=self.get_source_type(),
            )

        except Exception as e:
            logger.error(f"Ошибка парсинга PDF {url}: {e}")
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

    def _extract_title_from_url(self, url: str) -> str:
        """Извлечь название из URL PDF.

        Args:
            url: URL PDF файла

        Returns:
            Название документа
        """
        filename = url.split("/")[-1]
        filename = re.sub(r"\?.*$", "", filename)
        filename = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
        filename = filename.replace("-", " ").replace("_", " ")
        return filename
