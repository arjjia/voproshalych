"""MCP-сервер новостей ТюмГУ (mcp-news).

Парсит RSS-ленту новостей с www.utmn.ru и список мероприятий.
"""

import logging
import os
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("voproshalych-news", port=int(os.getenv("MCP_PORT", "9011")))

NEWS_URL = "https://www.utmn.ru/news/"
EVENTS_URL = "https://www.utmn.ru/news/events/"
RSS_URL = "https://www.utmn.ru/rss/"


@mcp.tool(
    name="get_news",
    description="Получить последние новости ТюмГУ. "
    "Возвращает заголовки, даты и ссылки на новости университета.",
)
async def get_news(limit: int = 5) -> str:
    """Получить последние новости ТюмГУ.

    Args:
        limit: Количество новостей (1-20)
    """
    logger.info(f"get_news: limit={limit}")
    limit = max(1, min(20, limit))

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                NEWS_URL,
                headers={"User-Agent": "VoproshalychBot/1.0"},
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        news_items = soup.select(".news-list__item, .news-item, .news_card, article")
        if not news_items:
            news_items = soup.select(
                "a[href*='/news/stories/'], a[href*='/news/events/']"
            )
            if news_items:
                return await _format_links_as_news(news_items[:limit])

        if not news_items:
            return _fallback_to_rss(limit)

        result = []
        for item in news_items[:limit]:
            title_el = item.select_one(
                "h2, h3, h4, .news-list__title, .news-item__title, .news_card__title, a"
            )
            date_el = item.select_one(
                ".news-list__date, .news-item__date, .news_card__date, time, .date"
            )
            link_el = item.find("a") if not title_el else title_el.find("a") or title_el

            title = (title_el or link_el).get_text(strip=True) if (title_el or link_el) else "Новость"
            date = date_el.get_text(strip=True) if date_el else ""
            url = ""
            if link_el and link_el.name == "a":
                href = link_el.get("href", "")
                url = href if href.startswith("http") else f"https://www.utmn.ru{href}"
            elif link_el and link_el.name != "a":
                a = link_el.find("a")
                if a:
                    href = a.get("href", "")
                    url = href if href.startswith("http") else f"https://www.utmn.ru{href}"

            title = " ".join(title.split())
            result.append(f"• {date} — [{title}]({url})" if date and url else f"• [{title}]({url})")

        if not result:
            return _fallback_to_rss(limit)

        header = f"📰 *Последние новости ТюмГУ* ({datetime.now().strftime('%d.%m.%Y')})\n\n"
        return header + "\n".join(result)

    except Exception as e:
        logger.error(f"get_news error: {e}")
        return _fallback_to_rss(limit)


@mcp.tool(
    name="get_events",
    description="Получить список ближайших мероприятий ТюмГУ. "
    "Возвращает дату, название и ссылку на мероприятие.",
)
async def get_events(limit: int = 5) -> str:
    """Получить ближайшие мероприятия ТюмГУ.

    Args:
        limit: Количество мероприятий (1-20)
    """
    logger.info(f"get_events: limit={limit}")
    limit = max(1, min(20, limit))

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                EVENTS_URL,
                headers={"User-Agent": "VoproshalychBot/1.0"},
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        items = soup.select(".events-list__item, .event-item, .news-list__item, a[href*='/news/events/']")

        if not items:
            return "Не удалось загрузить мероприятия. Попробуйте позже."

        result = []
        for item in items[:limit]:
            if item.name == "a":
                title = item.get_text(strip=True)
                href = item.get("href", "")
                url = href if href.startswith("http") else f"https://www.utmn.ru{href}"
                if title and len(title) > 10:
                    result.append(f"• [{title}]({url})")
                continue

            title_el = item.select_one("h2, h3, h4, .event-item__title, .news-list__title, a")
            date_el = item.select_one(
                ".event-item__date, .news-list__date, time, .date, .day, .month"
            )
            link_el = item.find("a") if not title_el else (
                title_el.find("a") if title_el.name != "a" else title_el
            )

            title = " ".join((title_el or link_el).get_text(strip=True).split()) if (title_el or link_el) else ""
            date = date_el.get_text(strip=True) if date_el else ""

            url = ""
            if link_el and link_el.name == "a":
                href = link_el.get("href", "")
                url = href if href.startswith("http") else f"https://www.utmn.ru{href}"

            if title:
                result.append(f"• {date} — [{title}]({url})" if date else f"• [{title}]({url})")

        if not result:
            return "Мероприятия не найдены."

        return f"🗓 *Ближайшие мероприятия ТюмГУ*\n\n" + "\n".join(result)

    except Exception as e:
        logger.error(f"get_events error: {e}")
        return f"Ошибка загрузки мероприятий: {e}"


async def _format_links_as_news(links: list) -> str:
    result = []
    seen = set()
    for a in links[:10]:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if not title or not href:
            continue
        url = href if href.startswith("http") else f"https://www.utmn.ru{href}"
        if url in seen:
            continue
        seen.add(url)
        result.append(f"• [{title}]({url})")

    if not result:
        return "Новости не найдены."

    header = f"📰 *Последние новости ТюмГУ* ({datetime.now().strftime('%d.%m.%Y')})\n\n"
    return header + "\n".join(result)


def _fallback_to_rss(limit: int) -> str:
    try:
        import xml.etree.ElementTree as ET

        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                RSS_URL,
                headers={"User-Agent": "VoproshalychBot/1.0"},
            )
            response.raise_for_status()

        root = ET.fromstring(response.content)
        items = root.findall(".//item")[:limit]

        result = []
        for item in items:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            if title:
                result.append(f"• {pub_date} — [{title}]({link})" if pub_date else f"• [{title}]({link})")

        if result:
            header = f"📰 *Последние новости ТюмГУ* ({datetime.now().strftime('%d.%m.%Y')})\n\n"
            return header + "\n".join(result)
    except Exception as e:
        logger.error(f"RSS fallback error: {e}")

    return "Не удалось загрузить новости. Попробуйте позже."


def main() -> None:
    import uvicorn
    logger.info("Starting mcp-news server...")
    uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=int(os.getenv("MCP_PORT", "9011")))


if __name__ == "__main__":
    main()
