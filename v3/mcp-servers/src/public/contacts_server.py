"""MCP-сервер контактов ТюмГУ (mcp-contacts).

Парсит страницу www.utmn.ru/kontakty/ для получения контактной информации
подразделений: приёмная комиссия, деканат, пресс-служба, институты.
"""

import logging
import os
import re

import httpx
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("voproshalych-contacts", port=int(os.getenv("MCP_PORT", "9012")))

CONTACTS_URL = "https://www.utmn.ru/kontakty/"


@mcp.tool(
    name="search_contacts",
    description="Поиск контактов подразделений ТюмГУ: приёмная комиссия, "
    "деканат, пресс-служба, институты, кафедры, ректорат и другие.",
)
async def search_contacts(query: str = "") -> str:
    """Поиск контактов подразделений ТюмГУ.

    Args:
        query: Поисковый запрос (название подразделения). Если пусто — все контакты.
    """
    logger.info(f"search_contacts: query={query!r}")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                CONTACTS_URL,
                headers={"User-Agent": "VoproshalychBot/1.0"},
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        blocks = []

        contacts_blocks = soup.select(".footer-contacts__block")
        for block in contacts_blocks:
            title_el = block.select_one(".footer-contacts__title")
            content_el = block.select_one(".footer-contacts__content")
            if not title_el or not content_el:
                continue
            title = title_el.get_text(strip=True)
            text = _extract_contact_text(content_el)
            if text.strip():
                blocks.append({"title": title, "text": text})

        h2_sections = soup.select("h2")
        for h2 in h2_sections:
            title = h2.get_text(strip=True)
            sibling = h2.find_next_sibling()
            if not sibling:
                continue

            if title == "Институты":
                links = sibling.select("a[href]")
                lines = []
                for link in links:
                    name = link.get_text(strip=True)
                    href = link.get("href", "")
                    if href:
                        url = href if href.startswith("http") else f"https://www.utmn.ru{href}"
                        lines.append(f"{name}: {url}")
                if lines:
                    blocks.append({"title": title, "text": "\n".join(lines)})

        if not blocks:
            return "Не удалось загрузить контакты."

        if query:
            query_lower = query.lower().strip()
            filtered = []
            for b in blocks:
                if query_lower in b["title"].lower() or query_lower in b["text"].lower():
                    filtered.append(b)
            blocks = filtered if filtered else blocks

        result = []
        for b in blocks:
            block_text = f"**{b['title']}**\n{b['text']}"
            result.append(block_text)

        joined = "\n\n---\n\n".join(result)
        header = f"📞 *Контакты ТюмГУ*\n\n" if not query else f"📞 *Контакты ТюмГУ* (по запросу «{query}»)\n\n"
        return header + joined

    except Exception as e:
        logger.error(f"search_contacts error: {e}")
        return f"Ошибка загрузки контактов: {e}"


def _extract_contact_text(content_el) -> str:
    """Извлечь текст из блока контактов."""
    parts = []
    for child in content_el.children:
        text = _process_element(child)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _process_element(el) -> str:
    """Рекурсивно обработать элемент."""
    if isinstance(el, str):
        text = el.strip()
        return text if text else ""

    if el.name in ("script", "style"):
        return ""

    if el.name == "a":
        href = el.get("href", "")
        text = el.get_text(strip=True)
        if href.startswith("mailto:"):
            return f"Email: {text}"
        if href.startswith("tel:"):
            return f"Тел.: {text}"
        return f"{text}: {href}"

    if el.name == "ul":
        items = []
        for li in el.select(":scope > li"):
            li_text = _process_element(li)
            if li_text:
                items.append(li_text)
        return "\n".join(items)

    if el.name == "li":
        parts = []
        for child in el.children:
            text = _process_element(child)
            if text:
                parts.append(text)
        return " ".join(parts)

    parts = []
    for child in el.children:
        text = _process_element(child)
        if text:
            parts.append(text)
    return "\n".join(parts)


def main() -> None:
    import uvicorn
    logger.info("Starting mcp-contacts server...")
    uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=int(os.getenv("MCP_PORT", "9012")))


if __name__ == "__main__":
    main()
