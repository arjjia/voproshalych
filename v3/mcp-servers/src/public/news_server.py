import logging
import os
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USER_AGENT = "VoproshalychBot/1.0"
NEWS_URL = "https://www.utmn.ru/news/"
EVENTS_URL = "https://www.utmn.ru/news/events/"


async def _fetch_page(url: str) -> str:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.text


def _fetch_page_sync(url: str) -> str:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.text


def _extract_items(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items = []

    article_selectors = [
        "div.news-list__item",
        "div.news-item",
        "div.news_card",
        "article",
        "li.news-list__item",
        "div.event-item",
    ]
    for sel in article_selectors:
        found = soup.select(sel)
        if found:
            for el in found:
                title_el = el.select_one(
                    "h2, h3, h4, .news-list__title, .news-item__title, "
                    ".news_card__title, a.news-list__title, a.news-item__title"
                )
                if not title_el:
                    title_el = el.find("a")
                date_el = el.select_one(
                    ".news-list__date, .news-item__date, .news_card__date, "
                    "time, .date, .day, .month"
                )
                link_el = title_el if title_el and title_el.name == "a" else (
                    title_el.find("a") if title_el else el.find("a")
                )

                title = title_el.get_text(strip=True) if title_el else ""
                date = date_el.get_text(strip=True) if date_el else ""
                url = ""
                if link_el:
                    href = link_el.get("href", "")
                    url = href if href.startswith("http") else f"https://www.utmn.ru{href}"

                title = " ".join(title.split())
                if title:
                    items.append({"title": title, "date": date, "url": url})
            break

    return items


async def get_news(limit: int = 5) -> str:
    logger.info(f"get_news: limit={limit}")
    limit = max(1, min(20, limit))

    try:
        html = await _fetch_page(NEWS_URL)
        items = _extract_items(html)

        if not items:
            return _fallback_to_rss(limit)

        result = []
        for item in items[:limit]:
            date = item["date"]
            title = item["title"]
            url = item["url"]
            if date and url:
                result.append(f"• {date} — [{title}]({url})")
            elif url:
                result.append(f"• [{title}]({url})")
            else:
                result.append(f"• {title}")

        if not result:
            return _fallback_to_rss(limit)

        header = f"📰 *Последние новости ТюмГУ* ({datetime.now().strftime('%d.%m.%Y')})\n\n"
        return header + "\n".join(result)

    except Exception as e:
        logger.error(f"get_news error: {e}")
        return _fallback_to_rss(limit)


async def get_events(limit: int = 5) -> str:
    logger.info(f"get_events: limit={limit}")
    limit = max(1, min(20, limit))

    try:
        html = await _fetch_page(EVENTS_URL)
        items = _extract_items(html)

        if not items:
            return "Мероприятия не найдены."

        result = []
        for item in items[:limit]:
            date = item["date"]
            title = item["title"]
            url = item["url"]
            if date and url:
                result.append(f"• {date} — [{title}]({url})")
            elif url:
                result.append(f"• [{title}]({url})")
            else:
                result.append(f"• {title}")

        if not result:
            return "Мероприятия не найдены."

        return f"🗓 *Ближайшие мероприятия ТюмГУ*\n\n" + "\n".join(result)

    except Exception as e:
        logger.error(f"get_events error: {e}")
        return f"Ошибка загрузки мероприятий: {e}"


def _fallback_to_rss(limit: int) -> str:
    try:
        import xml.etree.ElementTree as ET

        html = _fetch_page_sync("https://www.utmn.ru/rss/")
        root = ET.fromstring(html.encode())
        items = root.findall(".//item")[:limit]

        result = []
        for item in items:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            if title:
                line = f"• {pub_date} — [{title}]({link})" if pub_date else f"• [{title}]({link})"
                result.append(line)

        if result:
            header = f"📰 *Последние новости ТюмГУ* ({datetime.now().strftime('%d.%m.%Y')})\n\n"
            return header + "\n".join(result)
    except Exception as e:
        logger.error(f"RSS fallback error: {e}")

    return "Не удалось загрузить новости. Попробуйте позже."
