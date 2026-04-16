"""Парсер для пространства Study на Confluence."""

import asyncio
import concurrent.futures
from io import BytesIO
import logging
import os
from typing import Generator

import httpx
from bs4 import BeautifulSoup
import pdfplumber
import pytesseract
from PIL import Image

from .base import BaseParser, ParsedDocument

logger = logging.getLogger(__name__)

OCR_WORKERS = int(os.getenv("OCR_WORKERS", "4"))
OCR_RESOLUTION = int(os.getenv("OCR_RESOLUTION", "150"))


class ConfluenceStudyParser(BaseParser):
    """Парсер для извлечения документов из пространства Study на Confluence."""

    def __init__(self):
        """Инициализирует парсер."""
        self._host = os.getenv("CONFLUENCE_HOST", "https://confluence.utmn.ru")
        self._token = os.getenv("CONFLUENCE_TOKEN", "")
        self._headers = {"Authorization": f"Bearer {self._token}"}

    async def _get_page(self, page_id: str) -> dict:
        """Получить данные страницы по ID.

        Args:
            page_id: ID страницы

        Returns:
            dict с данными страницы
        """
        url = f"{self._host}/rest/api/content/{page_id}"
        params = {"expand": "space,body.export_view,_links"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers, params=params)
            response.raise_for_status()
            return response.json()

    async def _parse_page_html(
        self, page_id: str, title: str, page_url: str
    ) -> ParsedDocument | None:
        """Парсит HTML контент страницы.

        Args:
            page_id: ID страницы
            title: заголовок страницы
            page_url: URL страницы

        Returns:
            ParsedDocument или None
        """
        try:
            page = await self._get_page(page_id)
            page_body = page.get("body", {}).get("export_view", {}).get("value", "")

            if len(page_body) > 50:
                soup = BeautifulSoup(page_body, "html.parser")
                
                page_content = soup.get_text(separator=" ")
                
                if len(page_content.strip()) < 100:
                    logger.info(f"Skipping page {page_id} ('{title}') - content too short after cleanup")
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

    async def _has_child_pages(self, page_id: str) -> bool:
        """Проверяет есть ли дочерние страницы.

        Args:
            page_id: ID страницы

        Returns:
            True если есть дочерние страницы
        """
        url = f"{self._host}/rest/api/search"
        params = {"cql": f"parent={page_id}", "limit": 1}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers, params=params)
            if response.status_code == 200:
                data = response.json()
                return len(data.get("results", [])) > 0
        return False

    async def _get_attachments(self, page_id: str) -> list[dict]:
        """Получает вложения страницы.

        Args:
            page_id: ID страницы

        Returns:
            Список вложений
        """
        url = f"{self._host}/rest/api/content/{page_id}/child/attachment"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("results", [])
        return []

    def _ocr_pdf_sync(self, pdf_bytes: BytesIO) -> str:
        """Синхронный OCR для PDF (для параллельного выполнения).

        Args:
            pdf_bytes: PDF файл в памяти

        Returns:
            Распознанный текст
        """
        try:
            pdf_bytes.seek(0)
            with pdfplumber.open(pdf_bytes) as pdf:
                pages_text = []
                for page in pdf.pages:
                    page_image = page.to_image(resolution=OCR_RESOLUTION)
                    pil_image = page_image.original
                    ocr_text = pytesseract.image_to_string(
                        pil_image,
                        lang="rus+eng",
                    )
                    if ocr_text and ocr_text.strip():
                        pages_text.append(ocr_text.strip())

                if pages_text:
                    return "\n".join(pages_text)
        except Exception as e:
            logger.warning(f"OCR failed: {e}")

        return ""

    async def _ocr_pdf(self, pdf_bytes: BytesIO) -> str:
        """Параллельный OCR для PDF.

        Args:
            pdf_bytes: PDF файл в памяти

        Returns:
            Распознанный текст
        """
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=OCR_WORKERS) as executor:
            result = await loop.run_in_executor(
                executor, self._ocr_pdf_sync, pdf_bytes
            )
        return result

    async def _parse_page_attachments(
        self, page_id: str, title: str, page_url: str
    ) -> list[ParsedDocument]:
        """Парсит PDF вложения страницы с параллельным OCR.

        Args:
            page_id: ID страницы
            title: заголовок страницы
            page_url: URL страницы

        Returns:
            Список ParsedDocument для PDF вложений
        """
        attachments = await self._get_attachments(page_id)
        documents: list[ParsedDocument] = []
        
        pdf_attachments = []
        for attachment in attachments:
            att_title = attachment.get("title", "")
            media_type = (
                attachment.get("metadata", {}).get("mediaType", "")
                or attachment.get("extensions", {}).get("mediaType", "")
            )
            is_pdf = (
                "pdf" in str(media_type).lower()
                or att_title.lower().endswith(".pdf")
            )

            if not is_pdf:
                continue

            download_url = attachment.get("_links", {}).get("download", "")
            if not download_url.startswith("http"):
                download_url = self._host + download_url

            pdf_attachments.append((att_title, download_url))

        if not pdf_attachments:
            return documents

        async def download_and_ocr(att_title: str, download_url: str):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.get(download_url)
                    response.raise_for_status()
                    pdf_bytes = BytesIO(response.content)

                text_content = await self._ocr_pdf(pdf_bytes)

                if text_content:
                    return ParsedDocument(
                        url=download_url,
                        title=att_title,
                        text_content=text_content,
                        source_type=self.get_source_type(),
                    )
            except Exception as e:
                logger.error(f"Error parsing PDF {att_title}: {e}")
            return None

        semaphore = asyncio.Semaphore(2)

        async def download_and_ocr_with_limit(att_title: str, download_url: str):
            async with semaphore:
                return await download_and_ocr(att_title, download_url)

        tasks = [download_and_ocr_with_limit(title, url) for title, url in pdf_attachments]
        results = await asyncio.gather(*tasks)

        for result in results:
            if result:
                documents.append(result)

        return documents

    async def _get_study_pages(self) -> list[dict]:
        """Получить все страницы пространства study через REST API."""
        url = f"{self._host}/rest/api/search"
        params = {"cql": "space.key=study order by id", "start": 0, "limit": 100}
        all_pages: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                response = await client.get(url, headers=self._headers, params=params)
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                all_pages.extend(r["content"] for r in results if "content" in r)

                if len(results) < 100:
                    break
                params["start"] += 100

        return all_pages

    async def get_documents(self, source_url: str) -> list[ParsedDocument]:
        """Получить документы из пространства Study (ВСЕ страницы).

        Args:
            source_url: URL (не используется, парсит всё пространство)

        Returns:
            Список распарсенных документов
        """
        pages = await self._get_study_pages()
        logger.info(f"Found {len(pages)} pages in study space")

        logger.info(f"Processing ALL pages (not only leaf): {len(pages)}")

        documents: list[ParsedDocument] = []
        
        for page in pages:
            page_id = page["id"]
            title = page.get("title", "Untitled")
            page_url = self._host + page.get("_links", {}).get("webui", "")

            html_doc = await self._parse_page_html(page_id, title, page_url)
            if html_doc and html_doc.text_content.strip():
                documents.append(html_doc)

            pdf_docs = await self._parse_page_attachments(page_id, title, page_url)
            documents.extend(pdf_docs)

        return documents

    def parse(self) -> Generator[ParsedDocument, None, None]:
        """Парсит все страницы из пространства Study.

        Yields:
            ParsedDocument для каждого документа
        """
        import asyncio

        documents = asyncio.run(self.get_documents(source_url=""))
        for document in documents:
            yield document

    def get_source_type(self) -> str:
        """Получить тип источника.

        Returns:
            'confluence_study'
        """
        return "confluence_study"
