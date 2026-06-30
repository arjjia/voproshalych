import datetime as _dt
import io
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -----------------------------
# Models
# -----------------------------

@dataclass
class FileLink:
    url: str
    text: str = ""
    ext: str = ""              # ".pdf", ".docx", ...
    content_type: str = ""     # if known (optional)


@dataclass
class HtmlTable:
    headers: List[str]
    rows: List[List[str]]
    caption: Optional[str] = None
    row_itemprops: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AnchorBlock:
    anchor_id: str
    title: str
    text: str
    tables: List[HtmlTable] = field(default_factory=list)
    files: List[FileLink] = field(default_factory=list)


@dataclass
class SectionBlock:
    key: str
    title: str
    level: int
    text: str
    tables: List[HtmlTable] = field(default_factory=list)
    files: List[FileLink] = field(default_factory=list)


@dataclass
class RawData:
    source_url: str
    final_url: str
    status_code: int
    fetched_at_utc: str

    kind: str = "html"  # "html" | "pdf" | "other"

    html: Optional[str] = None
    text: str = ""

    tables: List[HtmlTable] = field(default_factory=list)
    files: List[FileLink] = field(default_factory=list)

    # Addressable blocks
    anchors: Dict[str, AnchorBlock] = field(default_factory=dict)
    sections: Dict[str, SectionBlock] = field(default_factory=dict)

    # Optional “machine layer”
    microdata: Dict[str, Any] = field(default_factory=dict)

    # If the caller used a URL with #fragment
    requested_fragment: str = ""
    fragment_block: Optional[Union[AnchorBlock, SectionBlock]] = None


# -----------------------------
# Helpers
# -----------------------------

_FILE_EXTS = {
    ".pdf", ".doc", ".docx", ".rtf", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".zip", ".rar", ".7z"
}

_INVALID_HREFS = {"нет", "Отсутствует", "#", "javascript:void(0)", "javascript:;"}


def clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def guess_ext(url: str) -> str:
    path = urllib.parse.urlsplit(url).path.lower()
    for ext in _FILE_EXTS:
        if path.endswith(ext):
            return ext
    return ""


def normalize_href(base_url: str, href: str) -> Optional[str]:
    """
    Делает href абсолютным, чинит обратные слеши, пробелы и т.п.
    Возвращает None для псевдо-ссылок вроде 'нет'/'Отсутствует'.
    """
    if not href:
        return None
    href = href.strip().replace("\\", "/")
    if href in _INVALID_HREFS:
        return None

    abs_url = urllib.parse.urljoin(base_url, href)
    abs_url = abs_url.replace(" ", "%20")

    parts = urllib.parse.urlsplit(abs_url)

    # Аккуратно “докодируем” путь (оставляя % и /)
    path = urllib.parse.quote(parts.path, safe="/%:@")
    query = urllib.parse.quote_plus(parts.query, safe="=&%:@/?")
    frag = parts.fragment

    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, frag))


def slugify_ru(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^0-9a-zа-яё]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "section"


def itemprop_value(el: Tag, base_url: str) -> Union[str, List[str]]:
    """
    Для itemprop-элемента предпочитаем:
    1) content="..."
    2) href (если это <a>…)
    3) первый href внутри
    4) иначе текст
    """
    if el.has_attr("content"):
        return clean_text(str(el["content"]))

    if el.name == "a" and el.get("href"):
        href = normalize_href(base_url, el.get("href"))
        return href or clean_text(el.get_text(" ", strip=True))

    links: List[str] = []
    for a in el.select("a[href]"):
        href = normalize_href(base_url, a.get("href"))
        if href:
            links.append(href)

    if links:
        return links[0] if len(links) == 1 else links

    return clean_text(el.get_text(" ", strip=True))


# -----------------------------
# HTTP client (requests + retry)
# -----------------------------

class HttpClient:
    def __init__(
        self,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        timeout: Tuple[float, float] = (10.0, 30.0),
        max_retries: int = 4,
        backoff_factor: float = 0.6,
    ):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get(self, url: str) -> requests.Response:
        resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        return resp


# -----------------------------
# HTML parsing
# -----------------------------

def parse_html_table(table: Tag, base_url: str) -> HtmlTable:
    caption = clean_text(table.caption.get_text(" ", strip=True)) if table.caption else None

    headers: List[str] = []
    thead = table.find("thead")
    if thead:
        tr = thead.find("tr")
        if tr:
            headers = [clean_text(th.get_text(" ", strip=True)) for th in tr.find_all(["th", "td"])]

    if not headers:
        first = table.find("tr")
        if first and first.find_all("th"):
            headers = [clean_text(th.get_text(" ", strip=True)) for th in first.find_all("th")]

    rows: List[List[str]] = []
    for tr in table.find_all("tr"):
        if tr.find_parent("thead"):
            continue
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        rows.append([clean_text(c.get_text(" ", strip=True)) for c in cells])

    row_itemprops: List[Dict[str, Any]] = []
    for tr in table.find_all("tr", attrs={"itemprop": True}):
        obj: Dict[str, Any] = {"_itemprop": tr.get("itemprop", "")}
        for sub in tr.find_all(attrs={"itemprop": True}):
            if sub is tr:
                continue
            obj[sub["itemprop"]] = itemprop_value(sub, base_url)
        row_itemprops.append(obj)

    return HtmlTable(headers=headers, rows=rows, caption=caption, row_itemprops=row_itemprops)


def extract_microdata(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    root = soup.select_one("#vikon-content") or soup
    micro: Dict[str, Any] = {}

    # “Одиночные” itemprop (не внутри tr[itemprop], и не сами tr)
    for el in root.find_all(attrs={"itemprop": True}):
        if getattr(el, "name", "") == "tr":
            continue
        if el.find_parent("tr", attrs={"itemprop": True}):
            continue
        key = el["itemprop"]
        val = itemprop_value(el, base_url)
        micro.setdefault(key, [])
        if val not in micro[key]:
            micro[key].append(val)

    # Строки-объекты: tr[itemprop] -> dict полей
    for tr in root.find_all("tr", attrs={"itemprop": True}):
        key = tr["itemprop"]
        obj: Dict[str, Any] = {}
        for sub in tr.find_all(attrs={"itemprop": True}):
            if sub is tr:
                continue
            obj[sub["itemprop"]] = itemprop_value(sub, base_url)
        micro.setdefault(key, [])
        micro[key].append(obj)

    return micro


def extract_anchor_blocks(soup: BeautifulSoup, base_url: str) -> Dict[str, AnchorBlock]:
    root = soup.select_one("#vikon-content") or soup
    anchors: Dict[str, AnchorBlock] = {}

    for heading in root.select('[id^="anchor_"]'):
        anchor_id = heading.get("id")
        if not anchor_id:
            continue

        title = clean_text(heading.get_text(" ", strip=True))

        # Берём “контент после заголовка” до следующего заголовка в том же родителе
        nodes: List[Tag] = []
        for sib in heading.next_siblings:
            if isinstance(sib, NavigableString):
                continue
            if isinstance(sib, Tag) and sib.name and re.match(r"h[1-6]$", sib.name, re.I):
                break
            if isinstance(sib, Tag):
                nodes.append(sib)

        text = clean_text("\n".join(n.get_text("\n", strip=True) for n in nodes))
        tables = [parse_html_table(t, base_url) for n in nodes for t in n.find_all("table")]

        files: List[FileLink] = []
        for n in nodes:
            for a in n.select("a[href]"):
                href = normalize_href(base_url, a.get("href"))
                if not href:
                    continue
                ext = guess_ext(href)
                if ext:
                    files.append(FileLink(url=href, text=clean_text(a.get_text(" ", strip=True)), ext=ext))

        anchors[anchor_id] = AnchorBlock(
            anchor_id=anchor_id,
            title=title,
            text=text,
            tables=tables,
            files=files,
        )

    return anchors


def extract_sections(soup: BeautifulSoup, base_url: str) -> Dict[str, SectionBlock]:
    """
    Универсальные секции по заголовкам h2..h6.
    Полезно для страниц, где нужные блоки не имеют anchor_* (например, 'Административные подразделения').
    """
    root = soup.select_one("#vikon-content") or soup
    sections: Dict[str, SectionBlock] = {}

    headings = root.find_all(re.compile(r"^h[1-6]$"))
    for h in headings:
        if h.name == "h1":  # обычно это заголовок страницы целиком
            continue

        title = clean_text(h.get_text(" ", strip=True))
        if not title:
            continue

        level = int(h.name[1])
        key = h.get("id") or slugify_ru(title)

        nodes: List[Tag] = []
        for sib in h.next_siblings:
            if isinstance(sib, NavigableString):
                continue
            if isinstance(sib, Tag) and sib.name and re.match(r"h[1-6]$", sib.name, re.I):
                sib_level = int(sib.name[1])
                if sib_level <= level:
                    break
            if isinstance(sib, Tag):
                nodes.append(sib)

        text = clean_text("\n".join(n.get_text("\n", strip=True) for n in nodes))
        tables = [parse_html_table(t, base_url) for n in nodes for t in n.find_all("table")]

        files: List[FileLink] = []
        for n in nodes:
            for a in n.select("a[href]"):
                href = normalize_href(base_url, a.get("href"))
                if not href:
                    continue
                ext = guess_ext(href)
                if ext:
                    files.append(FileLink(url=href, text=clean_text(a.get_text(" ", strip=True)), ext=ext))

        sections[key] = SectionBlock(key=key, title=title, level=level, text=text, tables=tables, files=files)

    return sections


def parse_html_page(html: str, base_url: str, source_url: str, status_code: int) -> RawData:
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("#vikon-content") or soup

    text = clean_text(root.get_text("\n", strip=True))
    tables = [parse_html_table(t, base_url) for t in root.find_all("table")]

    # Файловые ссылки по всему контенту
    files: List[FileLink] = []
    for a in root.select("a[href]"):
        href = normalize_href(base_url, a.get("href"))
        if not href:
            continue
        ext = guess_ext(href)
        if ext:
            files.append(FileLink(url=href, text=clean_text(a.get_text(" ", strip=True)), ext=ext))

    now_utc = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # ----------------------------------------------------------------------------------------------------------
    # если кто то сюда доберётся во время код ревью с меня конфетка только  скажите мне об этом :3
    # ----------------------------------------------------------------------------------------------------------


    return RawData(
        source_url=source_url,
        final_url=base_url,
        status_code=status_code,
        fetched_at_utc=now_utc,
        kind="html",
        html=html,
        text=text,
        tables=tables,
        files=files,
        anchors=extract_anchor_blocks(soup, base_url),
        sections=extract_sections(soup, base_url),
        microdata=extract_microdata(soup, base_url),
    )


# -----------------------------
# PDF parsing
# -----------------------------

def parse_pdf_bytes(pdf_bytes: bytes, max_pages: Optional[int] = None) -> Dict[str, Any]:
    """
    Возвращает минимальный универсальный результат:
    - text: общий текст
    - tables: таблицы (если удалось)
    """
    result: Dict[str, Any] = {"text": "", "tables": []}
    try:

        import pdfplumber  # type: ignore

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = pdf.pages[:max_pages] if max_pages else pdf.pages
            texts: List[str] = []
            tables: List[Any] = []
            for p in pages:
                t = p.extract_text() or ""
                if t:
                    texts.append(t)
                try:
                    tbls = p.extract_tables() or []
                    if tbls:
                        tables.extend(tbls)
                except Exception:
                    pass

            result["text"] = "\n".join(texts).strip()
            result["tables"] = tables
            return result
    except ImportError:
        pass



# -----------------------------
# High-level parser
# -----------------------------

class SvedenParser:
    def __init__(self, client: Optional[HttpClient] = None):
        self.client = client or HttpClient()

    def parse_url(self, url: str, parse_pdf: bool = False, pdf_max_pages: Optional[int] = None) -> RawData:
        # Отделяем #fragment не участвует в HTTP-запросе
        base_url, frag = urllib.parse.urldefrag(url)

        resp = self.client.get(base_url)
        status = resp.status_code
        final_url = resp.url  # учёт редиректов

        content_type = (resp.headers.get("Content-Type") or "").lower()

        # PDF?
        if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
            now_utc = _dt.datetime.now(_dt.timezone.utc).isoformat()
            raw = RawData(
                source_url=url,
                final_url=final_url,
                status_code=status,
                fetched_at_utc=now_utc,
                kind="pdf",
                requested_fragment=frag,
            )
            if parse_pdf and resp.content:
                pdf_info = parse_pdf_bytes(resp.content, max_pages=pdf_max_pages)
                raw.text = clean_text(pdf_info.get("text", ""))
            return raw

        if resp.encoding is None:
            resp.encoding = resp.apparent_encoding

        html = resp.text
        raw = parse_html_page(html=html, base_url=final_url, source_url=url, status_code=status)
        raw.requested_fragment = frag

        if frag:
            raw.fragment_block = raw.anchors.get(frag) or raw.sections.get(frag)

        return raw


parser = SvedenParser()

raw = parser.parse_url("https://sveden.utmn.ru/redirect/struct/index.php")

# ----------------------------------------------------------------------------------------------------------
# тут показательный пример того что можно парсить таблицы со sveden и то что они очень информативны
# ----------------------------------------------------------------------------------------------------------

admin = raw.sections["административные_подразделения"]
table = admin.tables[0]

# Строки как матрица
print(table.headers)
print(*table.rows[:5], sep="\n")

# Если в таблице есть itemprop на <tr>, можно читать row_itemprops
print(table.row_itemprops[:2])
print()
print()
print()

# ----------------------------------------------------------------------------------------------------------
# вот ещё пару примеров
# ----------------------------------------------------------------------------------------------------------

parser = SvedenParser()

raw = parser.parse_url("https://sveden.utmn.ru/sveden/common/")

# 1) наиболее “машинно”
full_name = (raw.microdata.get("fullName") or [None])[0]
short_name = (raw.microdata.get("shortName") or [None])[0]
reg_date = (raw.microdata.get("regDate") or [None])[0]

# 2) по якорям
reg_date_block = raw.anchors.get("anchor_regDate")
print(reg_date_block.title, reg_date_block.text)
