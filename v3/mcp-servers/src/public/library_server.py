"""MCP-сервер библиотеки ТюмГУ (mcp-library).

Предоставляет информацию о библиотечно-музейном комплексе ТюмГУ:
часы работы, контакты, правила, информация о новых поступлениях,
и поиск по электронному каталогу.
"""

import logging
import os
import re

import httpx
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("voproshalych-library", port=int(os.getenv("MCP_PORT", "9013")))

LIBRARY_URL = "https://bmk.utmn.ru/ru/"
NEW_LIBRARY_URL = "https://lib.utmn.ru/ru"
CATALOG_URL = "https://ruslan.utmn.ru/pwb/"
ASK_URL = "https://bmk.utmn.ru/ru/ask_librarian/"
CONTACTS_URL = "https://bmk.utmn.ru/ru/pages/cont/"


@mcp.tool(
    name="get_library_info",
    description="Получить информацию о библиотеке ТюмГУ: адрес, телефон, "
    "email, часы работы, правила пользования.",
)
async def get_library_info() -> str:
    """Получить контактную информацию и часы работы библиотеки ТюмГУ."""
    logger.info("get_library_info")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                CONTACTS_URL,
                headers={"User-Agent": "VoproshalychBot/1.0"},
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        content = soup.select_one(".main-content, .content, main, .container")
        if not content:
            content = soup

        text = content.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        if text:
            return f"🏛 *Библиотечно-музейный комплекс ТюмГУ*\n\n{text}\n\n*Официальный сайт:* {NEW_LIBRARY_URL}"

        return (
            f"🏛 *Библиотечно-музейный комплекс ТюмГУ*\n\n"
            f"*Адрес:* г. Тюмень, ул. Семакова, 18\n"
            f"*Телефон:* +7 (3452) 45-63-09\n"
            f"*Email:* bmk@utmn.ru\n"
            f"*Сайт:* {NEW_LIBRARY_URL}\n\n"
            f"У библиотеки появился новый сайт: {NEW_LIBRARY_URL}. "
            f"Рекомендуем пользоваться им для актуальной информации."
        )

    except Exception as e:
        logger.error(f"get_library_info error: {e}")
        return (
            f"🏛 *Библиотечно-музейный комплекс ТюмГУ*\n\n"
            f"*Адрес:* г. Тюмень, ул. Семакова, 18\n"
            f"*Телефон:* +7 (3452) 45-63-09\n"
            f"*Email:* bmk@utmn.ru\n"
            f"*Сайт:* {LIBRARY_URL}\n"
            f"*Новый сайт:* {NEW_LIBRARY_URL}"
        )


@mcp.tool(
    name="get_library_services",
    description="Получить список услуг и сервисов библиотеки ТюмГУ: "
    "электронный каталог, доступ к базам данных, услуги для читателей.",
)
async def get_library_services() -> str:
    """Получить информацию о сервисах библиотеки ТюмГУ."""
    logger.info("get_library_services")

    return (
        "📚 *Сервисы библиотеки ТюмГУ*\n\n"
        "1. **Электронный каталог** — поиск книг и изданий\n"
        f"   {CATALOG_URL}\n\n"
        "2. **Электронная библиотека ТюмГУ** — полнотекстовые издания\n"
        "   https://library.utmn.ru/\n\n"
        "3. **Научный репозиторий** — публикации сотрудников и студентов\n"
        "   https://elib.utmn.ru/jspui/\n\n"
        "4. **EBSCO Discovery Service** — поиск по мировым научным ресурсам\n"
        "   https://search.ebscohost.com/\n\n"
        "5. **Реестр баз данных** — подписные базы данных\n"
        f"   {LIBRARY_URL}ru/erm/\n\n"
        "6. **Задать вопрос библиотекарю** — онлайн-консультация\n"
        f"   {ASK_URL}"
    )


@mcp.tool(
    name="get_library_guides",
    description="Получить гайды и инструкции по работе с библиотекой ТюмГУ.",
)
async def get_library_guides() -> str:
    """Получить информацию о гайдах для читателей библиотеки."""
    logger.info("get_library_guides")

    return (
        "📖 *Гайды библиотеки ТюмГУ*\n\n"
        "Библиотека предоставляет гайды и инструкции для студентов:\n\n"
        "• **Первокурснику** — инструкции по работе с библиотекой\n"
        "  http://lib.utmn.tilda.ws/student/freshman\n\n"
        "• **Гайды по ресурсам** — подробные руководства по работе с БД\n"
        f"  {LIBRARY_URL}ru/pages/guide/\n\n"
        "• **Книжные выставки** — виртуальные выставки в библиотеке\n"
        f"  {LIBRARY_URL}ru/exhibition/\n\n"
        "• **Фотогалерея** — мероприятия библиотеки\n"
        f"  {LIBRARY_URL}ru/gallery/"
    )


def main() -> None:
    import uvicorn
    logger.info("Starting mcp-library server...")
    uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=int(os.getenv("MCP_PORT", "9013")))


if __name__ == "__main__":
    main()
