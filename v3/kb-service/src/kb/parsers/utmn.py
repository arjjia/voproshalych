"""Парсер HTML-страниц официального сайта ТюмГУ (www.utmn.ru).

Обходит страницы в ширину (BFS) от стартового URL, собирает
текстовое содержимое каждой HTML-страницы (без PDF).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .base import BaseParser, ParsedDocument

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (compatible; VoproshalychBot/1.0; "
    "+https://voproshalych.ru)"
)

# Максимум страниц для сканирования
_MAX_PAGES = 50
# Максимум ссылок на странице для обхода
_MAX_LINKS_PER_PAGE = 100

# Паттерны путей, которые стоит сканировать (основные разделы)
_INCLUDE_PATTERNS = [
    "/about/", "/education/", "/science/", "/abiturient/",
    "/students/", "/contacts/", "/sveden/", "/upload/",
]
# Паттерны, которые НЕ стоит сканировать
_EXCLUDE_PATTERNS = [
    r"\.pdf$", r"\.docx?$", r"\.xlsx?$", r"\.pptx?$",
    r"\.jpg$", r"\.png$", r"\.gif$", r"\.svg$", r"\.ico$",
    r"\.zip$", r"\.rar$", r"\.tar\.gz$",
    r"/cdn/", r"/bitrix/", r"/local/",
    r"#", r"javascript:",
]


class UtmnParser(BaseParser):
    """Парсер HTML-страниц сайта ТюмГУ.

    Использует BFS-обход от указанного URL, собирая все
    доступные HTML-страницы того же домена.
    """

    def __init__(self) -> None:
        self._base_url = "https://www.utmn.ru"
        self._domain = "www.utmn.ru"

    def get_source_type(self) -> str:
        return "utmn"

    def _should_include(self, url: str) -> bool:
        """Проверить, стоит ли включать URL в обход."""
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != self._domain:
            return False
        path = parsed.path or "/"
        # Исключаем файлы
        if any(re.search(p, path, re.IGNORECASE) for p in _EXCLUDE_PATTERNS):
            return False
        return True

    def _extract_title(self, soup: BeautifulSoup, url: str) -> str:
        """Извлечь заголовок страницы."""
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)
        return url

    def _extract_text(self, soup: BeautifulSoup) -> str:
        """Извлечь текстовое содержимое страницы."""
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "form", "aside", "noscript"]):
            tag.decompose()

        container = (
            soup.find("article")
            or soup.select_one(".main__content")
            or soup.select_one(".content")
            or soup.select_one("main")
            or soup.body
            or soup
        )
        text = container.get_text(separator="\n", strip=True)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines)

    async def get_documents(self, source_url: str, max_pages: int = _MAX_PAGES) -> list[ParsedDocument]:
        """Обойти страницы сайта и собрать документы.

        Args:
            source_url: Стартовый URL для обхода.
            max_pages: Максимум страниц для сканирования.

        Returns:
            Список распарсенных HTML-документов.
        """
        visited: set[str] = set()
        to_visit: list[str] = [source_url]
        documents: list[ParsedDocument] = []

        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True,
            headers={"User-Agent": _UA},
        ) as client:
            while to_visit and len(visited) < max_pages:
                url = to_visit.pop(0)
                if url in visited:
                    continue
                if not self._should_include(url):
                    continue
                visited.add(url)

                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                except Exception as exc:
                    logger.debug("Skip %s: %s", url, exc)
                    continue

                # Проверяем, что это HTML
                ct = resp.headers.get("content-type", "")
                if "text/html" not in ct and "text/plain" not in ct:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                title = self._extract_title(soup, url)
                text = self._extract_text(soup)

                if text.strip():
                    documents.append(ParsedDocument(
                        url=url,
                        title=title,
                        text_content=text,
                        source_type=self.get_source_type(),
                    ))

                # Собираем ссылки для дальнейшего обхода
                links_found = 0
                for a in soup.find_all("a", href=True):
                    if links_found >= _MAX_LINKS_PER_PAGE:
                        break
                    href = a["href"].strip()
                    full_url = urljoin(url, href)
                    parsed = urlparse(full_url)
                    # Только тот же домен
                    if parsed.netloc and parsed.netloc != self._domain:
                        continue
                    # Нормализуем URL (убираем query/fragment)
                    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    if clean_url not in visited and clean_url not in to_visit:
                        if self._should_include(clean_url):
                            to_visit.append(clean_url)
                            links_found += 1

                logger.info(
                    "[%d/%d] %s — %s (%d symbols)",
                    len(documents), max_pages, title, url, len(text),
                )

        logger.info(
            "Utmn crawl done (max_pages=%d): %d pages visited, %d documents collected",
            max_pages, len(visited), len(documents),
        )
        return documents
