"""MCP-сервер «Сведения об организации» (mcp-sveden).

Предоставляет информацию из раздела «Сведения об образовательной организации»
ТюмГУ: руководство, структура, стипендии, питание, документы.
"""

import logging
import os
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("voproshalych-sveden", port=int(os.getenv("MCP_PORT", "9014")))

SVEDEN_BASE = "https://sveden.utmn.ru"

SVEDEN_PAGES = [
    ("https://sveden.utmn.ru/sveden/managers/", "Руководство ТюмГУ"),
    ("https://sveden.utmn.ru/sveden/catering/", "Организация питания в ТюмГУ"),
    ("https://sveden.utmn.ru/sveden/struct", "Структура и органы управления ТюмГУ"),
]


@mcp.tool(
    name="get_sveden_info",
    description="Получить информацию из раздела «Сведения об организации» ТюмГУ. "
    "Поддерживаемые темы: руководство, структура, питание, стипендии, "
    "правила приёма, общежитие, платные услуги.",
)
async def get_sveden_info(topic: str = "") -> str:
    """Поиск по разделу «Сведения об образовательной организации» ТюмГУ.

    Args:
        topic: Тема запроса (руководство, структура, питание, стипендии,
               правила приёма, общежитие и т.д.). Если пусто — общая информация.
    """
    logger.info(f"get_sveden_info: topic={topic!r}")

    results = []
    topic_lower = topic.lower().strip() if topic else ""

    for url, title in SVEDEN_PAGES:
        page = await _parse_sveden_page(url, title)
        if not page:
            continue

        if topic_lower:
            if topic_lower in page.lower() or topic_lower in title.lower():
                results.append(page)
        else:
            results.append(page)

    if not results:
        all_text = "\n\n".join(
            [r for r in [await _parse_sveden_page(u, t) for u, t in SVEDEN_PAGES] if r]
        )
        if all_text:
            info = all_text[:2000]
            return f"📋 *Сведения об организации ТюмГУ*\n\n{info}\n\n*Полный раздел:* {SVEDEN_BASE}/sveden/"
        return "Не удалось загрузить информацию."

    joined = "\n\n---\n\n".join(results)
    return f"📋 *Сведения об организации ТюмГУ*\n\n{joined}"


@mcp.tool(
    name="get_structure",
    description="Получить структуру и органы управления ТюмГУ: "
    "ректорат, подразделения, филиалы, институты.",
)
async def get_structure() -> str:
    """Получить информацию о структуре ТюмГУ."""
    logger.info("get_structure")

    page = await _parse_sveden_page(
        "https://sveden.utmn.ru/sveden/struct",
        "Структура и органы управления",
    )

    if page:
        return f"📋 *Структура ТюмГУ*\n\n{page}"
    return "Не удалось загрузить структуру."


@mcp.tool(
    name="get_management",
    description="Получить информацию о руководстве ТюмГУ: ректор, "
    "проректоры, директора институтов.",
)
async def get_management() -> str:
    """Получить информацию о руководстве ТюмГУ."""
    logger.info("get_management")

    page = await _parse_sveden_page(
        "https://sveden.utmn.ru/sveden/managers/",
        "Руководство ТюмГУ",
    )

    if page:
        return f"👤 *Руководство ТюмГУ*\n\n{page}"
    return "Не удалось загрузить руководство."


async def _parse_sveden_page(url: str, title: str) -> str | None:
    """Парсит HTML-страницу sveden.utmn.ru."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "VoproshalychBot/1.0"},
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        content = (
            soup.find("div", class_="main-content")
            or soup.find("div", class_="content")
            or soup.find("main")
            or soup.find("div", class_="container")
            or soup.body
        )
        if not content:
            content = soup

        sections = []
        for section_div in content.find_all("div", recursive=False):
            section_heading = section_div.find(["h2", "h3", "h4"])
            if not section_heading:
                continue

            section_title = section_heading.get_text(strip=True)
            tables = section_div.find_all("table")
            if not tables:
                text = section_div.get_text(strip=True)
                if text and len(text) > 20:
                    sections.append(f"**{section_title}**\n{text}")
                continue

            tables_text = []
            for table in tables:
                rows = table.find_all("tr")
                row_texts = []
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    cell_texts = []
                    for cell in cells:
                        ct = cell.get_text(separator=" ", strip=True)
                        ct = re.sub(r"\s+", " ", ct)
                        if ct:
                            cell_texts.append(ct)
                    if cell_texts:
                        row_texts.append(" | ".join(cell_texts))
                if row_texts:
                    tables_text.append("\n".join(row_texts))

            if tables_text:
                sections.append(f"**{section_title}**\n\n" + "\n\n".join(tables_text))

        if not sections:
            text = content.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)
            if text:
                sections.append(text)

        if not sections:
            return None

        combined = "\n\n".join(sections)
        if len(combined) > 2000:
            combined = combined[:2000] + "\n\n..."

        return combined

    except Exception as e:
        logger.error(f"Error parsing {url}: {e}")
        return None


def main() -> None:
    import uvicorn
    logger.info("Starting mcp-sveden server...")
    uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=int(os.getenv("MCP_PORT", "9014")))


if __name__ == "__main__":
    main()
