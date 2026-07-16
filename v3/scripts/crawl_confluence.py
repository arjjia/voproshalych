#!/usr/bin/env python3
"""Crawl Confluence from host machine and push documents into kb-service.

Запускается на HOST (где работает VPN).
Парсит Confluence напрямую (обходит Vouch SSO, который блокирует Docker на macOS)
и сохраняет результаты через API kb-service.

Usage:
    cd v3
    python3 scripts/crawl_confluence.py              # все пространства
    python3 scripts/crawl_confluence.py --source study   # только Study
    python3 scripts/crawl_confluence.py --source help    # только Help
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import urllib.parse

import httpx
from bs4 import BeautifulSoup


def _load_env(path: str = ".env") -> None:
    """Load .env file into environment (inline, no deps)."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z_]\w*)=(.*)$", line)
            if m:
                key, val = m.group(1), m.group(2)
                val = re.sub(r'^["\']|["\']$', "", val)
                os.environ.setdefault(key, val)


_load_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

KB_SERVICE_URL = os.getenv("KB_SERVICE_URL", "http://localhost:8005")
CONFLUENCE_HOST = os.getenv("CONFLUENCE_HOST", "https://confluence.utmn.ru")
CONFLUENCE_TOKEN = os.getenv("CONFLUENCE_TOKEN", "")

HELP_PAGES = {
    "8037241": "Карты доступа",
    "8037222": "Корпоративная учетная запись",
    "62586931": "Яндекс 360",
    "121923452": "Единый личный кабинет ТюмГУ",
    "121906735": "Основы работы с LMS",
    "8037245": "Беспроводная сеть Wi-Fi",
}


def get_headers() -> dict:
    headers = {"Accept": "application/json"}
    if CONFLUENCE_TOKEN:
        headers["Authorization"] = f"Bearer {CONFLUENCE_TOKEN}"
    return headers


def store_in_kb(url: str, source_type: str, title: str = "", text: str = "") -> bool:
    """Call kb-service to store a document.

    If title+text are provided, sends them directly as pre-parsed content
    (avoids re-fetching the URL without auth headers).
    Otherwise, kb-service will fetch and parse the URL.
    """
    if title and text:
        method = "store_parsed_document"
        params = {"title": title, "text_content": text, "url": url, "source_type": source_type}
    else:
        method = "store_document"
        params = {"url": url, "source_type": source_type}
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
    }
    try:
        resp = httpx.post(
            f"{KB_SERVICE_URL}/api/v1/tools",
            json=payload,
            timeout=300,
        )
        data = resp.json()
        result = data.get("result", {})
        if result.get("status") == "ok":
            logger.info(f"  ✓ Stored: {url}")
            return True
        logger.warning(f"  ! Store failed: {result}")
        return False
    except Exception as e:
        logger.error(f"  ✗ Error storing: {e}")
        return False


def fetch_page_html(page_id: str) -> tuple[str, str] | None:
    """Fetch Confluence page HTML content. Returns (text, title) or None."""
    url = f"{CONFLUENCE_HOST}/rest/api/content/{page_id}?expand=body.export_view"
    try:
        resp = httpx.get(url, headers=get_headers(), timeout=15)
        if resp.status_code != 200:
            logger.warning(f"  HTTP {resp.status_code} for page {page_id}")
            return None
        data = resp.json()
        title = data.get("title", "Untitled")
        html = data.get("body", {}).get("export_view", {}).get("value", "")
        if not html or len(html) <= 50:
            return None
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ")
        if len(text.strip()) < 100:
            return None
        return text.strip(), title
    except Exception as e:
        logger.error(f"  Error fetching page {page_id}: {e}")
        return None


def crawl_help():
    """Crawl hardcoded Confluence Help pages."""
    logger.info("=== Confluence Help ===")
    count = 0
    for page_id, title in HELP_PAGES.items():
        logger.info(f"  → {title} ({page_id})")
        result = fetch_page_html(page_id)
        if result:
            text, title_text = result
            page_url = f"{CONFLUENCE_HOST}/pages/viewpage.action?pageId={page_id}"
            if store_in_kb(page_url, "confluence_help", title=title_text, text=text):
                count += 1
    logger.info(f"Help: {count} documents stored")
    return count


def crawl_study():
    """Crawl all pages from Confluence Study space."""
    logger.info("=== Confluence Study ===")
    count = 0
    start = 0
    limit = 100

    while True:
        params = {
            "cql": "space.key=study order by id",
            "start": start,
            "limit": limit,
        }
        url = f"{CONFLUENCE_HOST}/rest/api/search"
        try:
            resp = httpx.get(url, headers=get_headers(), params=params, timeout=15)
            if resp.status_code == 302:
                logger.error(
                    "Confluence auth failed (redirect to Vouch). "
                    "Check VPN connection and CONFLUENCE_TOKEN."
                )
                return count
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            for r in results:
                content = r.get("content", {})
                page_id = content.get("id", "")
                title = content.get("title", "Untitled")
                page_url = CONFLUENCE_HOST + content.get("_links", {}).get("webui", "")
                logger.info(f"  → {title} ({page_id})")
                page_result = fetch_page_html(page_id)
                if page_result:
                    text, title_text = page_result
                    if store_in_kb(page_url, "confluence_study", title=title_text, text=text):
                        count += 1
                else:
                    logger.info("    SKIP (empty or error)")

            if len(results) < limit:
                break
            start += limit
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e}")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            break

    logger.info(f"Study: {count} documents stored")
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Crawl Confluence and store documents in kb-service"
    )
    parser.add_argument(
        "--source",
        choices=["help", "study", "all"],
        default="all",
        help="Which Confluence space to crawl",
    )
    args = parser.parse_args()

    if not CONFLUENCE_TOKEN:
        logger.error("CONFLUENCE_TOKEN not set. Create .env with CONFLUENCE_TOKEN=...")
        sys.exit(1)

    total = 0
    if args.source in ("help", "all"):
        total += crawl_help()
    if args.source in ("study", "all"):
        total += crawl_study()

    logger.info(f"Total: {total} documents stored")


if __name__ == "__main__":
    main()
