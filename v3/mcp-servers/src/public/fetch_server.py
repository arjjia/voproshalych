import logging
import re

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = "VoproshalychBot/1.0"
MAX_TEXT_LENGTH = 8000

_UNWANTED_TAGS = {
    "script", "style", "nav", "footer", "header", "aside",
    "noscript", "iframe", "svg", "form", "button", "input",
    "select", "textarea", "label",
}

_UNWANTED_CLASS_PATTERNS = re.compile(
    r"(footer|header|nav|menu|sidebar|chat|comment|social|share|"
    r"cookie|popup|modal|overlay|banner|advert|sponsor|related)",
    re.I,
)


async def fetch_url(url: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Fetch a URL and extract clean text content.

    Args:
        url: The URL to fetch
        max_length: Maximum characters to return (default 8000)

    Returns:
        Markdown-formatted text content extracted from the page
    """
    logger.info(f"fetch_url: {url}")
    max_length = max(500, min(50000, max_length))

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            text = response.text
            if len(text) > max_length:
                text = text[:max_length] + "\n\n... (truncated)"
            return f"*Content from:* {url}\n\n```\n{text}\n```"

        soup = BeautifulSoup(response.text, "lxml")

        for tag_name in _UNWANTED_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        for tag in soup.find_all(class_=True):
            classes = " ".join(tag.get("class", []))
            if _UNWANTED_CLASS_PATTERNS.search(classes):
                tag.decompose()

        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        main_content = _find_main_content(soup)
        if not main_content:
            main_content = soup.find("body") or soup

        text = main_content.get_text(separator="\n", strip=True)
        text = _clean_text(text)

        if len(text) > max_length:
            text = text[:max_length] + "\n\n... (truncated)"

        result = f"# {title}\n\n" if title else ""
        result += f"*Source:* [{url}]({url})\n\n"
        result += text

        return result

    except httpx.TimeoutException:
        return f"Ошибка: таймаут при загрузке {url}"
    except httpx.HTTPStatusError as e:
        return f"Ошибка HTTP {e.response.status_code} при загрузке {url}"
    except Exception as e:
        logger.error(f"fetch_url error: {e}")
        return f"Ошибка при загрузке {url}: {e}"


def _find_main_content(soup: BeautifulSoup) -> BeautifulSoup | None:
    selectors = [
        "main",
        "[role=main]",
        "article",
        ".content",
        "#content",
        ".post-content",
        ".article-content",
        ".entry-content",
        ".main-content",
        "#main-content",
        ".page-content",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            return el
    return None


def _clean_text(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) < 3:
            continue
        if _looks_like_menu(line):
            continue
        lines.append(line)
    return "\n\n".join(lines)


_MENU_PATTERNS = re.compile(
    r"^(главная|новости|контакты|поиск|вход|регистрация|"
    r"личный кабинет|корзина|избранное|о нас|услуги|"
    r"продукты|цены|отзывы|вакансии|партнёрам|eng|"
    r"menu|home|about|contact|search|login|register|cart|shop)$",
    re.I,
)


def _looks_like_menu(text: str) -> bool:
    if bool(_MENU_PATTERNS.match(text.strip())):
        return True
    return False
