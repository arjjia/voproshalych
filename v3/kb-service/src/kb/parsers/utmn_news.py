"""Парсер новостного портала ТюмГУ (utmn.ru/news/).

Источники:
    - новости:     https://www.utmn.ru/news/stories/
    - мероприятия: https://www.utmn.ru/news/events/

Структура list-страницы (Bitrix, серверный HTML):
    <ul class="last-news_list ...">
      <li class="news-page__el">
        <article class="article ...">
          <a href="/news/stories/<category>/<id>/">            <!-- ссылка -->
          <div class="date"><div class="month">июл</div>
                            <div class="day"><a>13</a></div>
                            <div class="year">2026</div></div>
          <div class="category_title"><a>Образование</a></div>   <!-- категория -->
          <div class="article_title ..."><a>Заголовок</a></div>  <!-- заголовок -->
        </article>
      </li>

Пагинация — Bitrix-стандарт: добавляем ?PAGEN_1=<номер страницы>.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseParser, ParsedDocument

logger = logging.getLogger(__name__)

NewsKind = Literal["news", "events"]

_DEFAULT_URLS = {
    "news": "https://www.utmn.ru/news/stories/",
    "events": "https://www.utmn.ru/news/events/",
}
_UA = (
    "Mozilla/5.0 (compatible; VoproshalychBot/1.0; "
    "+https://voproshalych.ru)"
)
_ARTICLE_CONCURRENCY = 5


class UtmnNewsParser(BaseParser):
    """Парсер ленты новостей/мероприятий utmn.ru.

    Args:
        kind: ``"news"`` (stories) или ``"events"`` (мероприятия).
    """

    def __init__(self, kind: NewsKind = "news") -> None:
        if kind not in _DEFAULT_URLS:
            raise ValueError(f"Unknown news kind: {kind}")
        self._kind = kind

    def get_source_type(self) -> str:
        return self._kind

    async def get_documents(
        self,
        source_url: str | None = None,
        max_pages: int = 3,
        fetch_articles: bool = True,
    ) -> list[ParsedDocument]:
        """Собрать документы из ленты.

        Args:
            source_url: URL первой страницы (иначе берётся стандартный для kind).
            max_pages: сколько страниц ленты пройти (Bitrix ``?PAGEN_1=N``).
            fetch_articles: ходить ли за полным текстом в каждую карточку.

        Returns:
            Список :class:`ParsedDocument`.
        """
        base = source_url or _DEFAULT_URLS[self._kind]
        seen: set[str] = set()
        items: list[dict] = []

        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": _UA}
        ) as client:
            for page in range(1, max_pages + 1):
                url = base if page == 1 else self._with_pagen(base, page)
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning("List page %s failed: %s", url, exc)
                    break

                page_items = self._parse_list(resp.text, base)
                if not page_items:
                    logger.info("No more items at page %d", page)
                    break

                new = [it for it in page_items if it["url"] not in seen]
                if not new:
                    break
                seen.update(it["url"] for it in new)
                items.extend(new)
                logger.info(
                    "Parsed %d items from %s (kind=%s)",
                    len(new), url, self._kind,
                )

            if fetch_articles and items:
                await self._enrich_with_articles(client, items)

        return [self._to_document(it) for it in items]

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _with_pagen(base: str, page: int) -> str:
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}PAGEN_1={page}"

    def _parse_list(self, html: str, base: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []

        # Новости (stories): li.news-page__el > article
        for li in soup.select("li.news-page__el"):
            article = li.find("article", class_=lambda c: c and "article" in c)
            if not article:
                continue

            item = self._extract_from_article(article, base)
            if item:
                out.append(item)

        # Мероприятия (events): article напрямую
        if not out:
            for article in soup.find_all("article", class_=lambda c: c and "article" in c):
                item = self._extract_from_article(article, base)
                if item:
                    out.append(item)

        return out

    def _extract_from_article(self, article, base: str) -> dict | None:
        title_link = article.select_one(".article_title a") or article.find("a")
        if not title_link:
            return None
        href = title_link.get("href")
        title = title_link.get_text(strip=True)
        if not href or not title:
            return None
        url = urljoin(base, href)

        category = ""
        cat_tag = article.select_one(".category_title a")
        if cat_tag:
            category = cat_tag.get_text(strip=True)

        date = self._extract_date(article)

        return {
            "url": url,
            "title": title,
            "category": category,
            "date": date,
            "full_text": "",
        }

    @staticmethod
    def _extract_date(article) -> str:
        date_block = article.select_one(".date")
        if not date_block:
            return ""
        month = (
            date_block.select_one(".month").get_text(strip=True)
            if date_block.select_one(".month")
            else ""
        )
        day = ""
        day_tag = date_block.select_one(".day")
        if day_tag:
            day = day_tag.get_text(strip=True)
        year = (
            date_block.select_one(".year").get_text(strip=True)
            if date_block.select_one(".year")
            else ""
        )
        return " ".join(p for p in (day, month, year) if p)

    async def _enrich_with_articles(
        self, client: httpx.AsyncClient, items: list[dict]
    ) -> None:
        sem = asyncio.Semaphore(_ARTICLE_CONCURRENCY)

        async def fetch_one(it: dict) -> None:
            async with sem:
                try:
                    resp = await client.get(it["url"])
                    resp.raise_for_status()
                    it["full_text"] = self._extract_article_text(resp.text)
                except httpx.HTTPError as exc:
                    logger.warning("Article %s failed: %s", it["url"], exc)

        await asyncio.gather(*(fetch_one(it) for it in items))

    @staticmethod
    def _extract_article_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "form"]):
            tag.decompose()

        container = (
            soup.find("article")
            or soup.select_one(".news_detail")
            or soup.select_one(".article-detail")
            or soup.select_one("main")
            or soup.body
            or soup
        )
        text = container.get_text(separator="\n", strip=True)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines)

    def _to_document(self, it: dict) -> ParsedDocument:
        header = []
        if it.get("title"):
            header.append(it["title"])
        if it.get("category"):
            header.append(f"Категория: {it['category']}")
        if it.get("date"):
            header.append(f"Дата: {it['date']}")
        header.append(f"URL: {it['url']}")

        body = it.get("full_text") or it.get("title") or ""
        text_content = "\n\n".join(["\n".join(header), body]).strip()

        return ParsedDocument(
            url=it["url"],
            title=it.get("title") or it["url"],
            text_content=text_content,
            source_type=self.get_source_type(),
        )
