"""Парсер для портала Сведения об организации (sveden.utmn.ru).

Парсит:
- PDF документы через OCR (whitelist в ALLOWED_SVEDEN_URLS)
- HTML-страницы с таблицами (руководство, питание, структура)
"""

import logging
import re
from io import BytesIO
from typing import Any
from urllib.parse import urljoin

import httpx
import pdfplumber
import pytesseract
from bs4 import BeautifulSoup, Tag
from PIL import Image

from .base import BaseParser, ParsedDocument
from .ocr_cache import get_ocr_config, get_tesseract_version


logger = logging.getLogger(__name__)


ALLOWED_SVEDEN_URLS = [
    "https://www.utmn.ru/upload/medialibrary/de7/%D0%A3%D1%81%D1%82%D0%B0%D0%B2%202018.pdf",
    "https://www.utmn.ru/upload/medialibrary/bdf/Izmeneniya-v-Ustav-TyumGU-_14.04.2020_.pdf",
    "https://www.utmn.ru/upload/medialibrary/810/Izmeneniya-v-Ustav-TyumGU-_26.12.2019_.pdf",
    "https://www.utmn.ru/upload/medialibrary/715/Izmeneni-v-Ustav-ot-21.03.2022.pdf",
    "https://www.utmn.ru/upload/medialibrary/295/Izmenenie-v-Ustav-2022-_sentyabr_.pdf",
    "https://www.utmn.ru/upload/medialibrary/78e/Izmeneniya-v-Ustav-fevral-2023.pdf",
    "https://www.utmn.ru/upload/medialibrary/1f8/Izmeneniya.pdf",
    "https://www.utmn.ru/upload/ftp/pdf_merged%20%282%29.pdf",
    "https://sveden.utmn.ru/sveden/files/pologhenie_o_tobolyskom_pedagogicheskom_institute_(filial)_tyumgu_(2016).pdf",
    "https://sveden.utmn.ru/sveden/files/pologhenie_o_ishimskom_pedagogicheskom_institute_(filial)_tyumgu_(2016).pdf",
    "https://sveden.utmn.ru/sveden/files/eit/Pravila_vnutrennego_rasporyadka_obuchayuschixsya_FGAOU_VO_Tyumenskii_gosudarstvennyi_universitet.pdf",
    "https://sveden.utmn.ru/sveden/files/aid/Pravila_priema_bakspec_na_2026-2027_uchebnyi_god_.pdf",
    "https://sveden.utmn.ru/sveden/files/vif/Pravila_priema_na_obuchenie_v_FGAOU_VO_Tyumenskii_gosudarstvennyi_universitet_po_programmam_magistratury_na_2026-2027_uchebnyi_god(1).pdf",
    "https://sveden.utmn.ru/sveden/files/aie/Pravila_priema_SPO_26-27_(1)(1).pdf",
    "https://www.utmn.ru/upload/medialibrary/2eb/6q5jyvk9gzuxjnmqnjp5n130rfe99eop/Polozhenie-o-raspisaniyakh-SPO-Kolledzh-IIi-KM-golovnoy-vuz-02.09.2025.pdf",
    "https://www.utmn.ru/upload/medialibrary/df2/udnrhr2hk1wo2h97g02x4pg2nuo8qu7e/Polozhenie-o-raspisaniyakh-po-OP-VO-v-TyumGU-02.09.2025.pdf",
    "https://sveden.utmn.ru/sveden/files/Pologhenie_o_raspisaniyax_po_obrazovatelynym_programmam_VO_v_filialax_TyumGU.pdf",
    "https://sveden.utmn.ru/sveden/files/ric/Pologhenie_o_raspisaniyax_po_obrazovatelynym_programmam_vysshego_obrazovaniya_v_TyumGU.pdf",
    "https://sveden.utmn.ru/sveden/files/eib/Polozhenie-o-raspisaniyakh-SPO-Kolledzh-IIi-KM-golovnoy-vuz-02.09.2025.pdf",
    "https://sveden.utmn.ru/sveden/files/vim/Pologhenie_o_tekuschem_kontrole_uspevaemosti_i_promeghutochnoi_attestacii_obuchayuschixsya_TyumGU.pdf",
    "https://sveden.utmn.ru/sveden/files/Pologhenie_Perevod_SPO.pdf",
    "https://sveden.utmn.ru/sveden/files/ail/Pologhenie_o_poryadke_otchisleniya,_vosstanovleniya_obuchayuschixsya_TyumGU(1).pdf",
    "https://sveden.utmn.ru/sveden/files/vim/Poryadok_perevoda_obuchayuschixsya_po_OP_VO.pdf",
    "https://sveden.utmn.ru/sveden/files/rio/Pologhenie_o_poryadke_oformleniya_vozniknoveniya,_priostanovleniya_i_prekrascheniya_otnosheniy_meghdu_Tyumenskiy_gosudarstvennym_universitetom_i_obuchayuschimisya_i_(ili)_roditelyami_(zakonnymi_predstavitelyami)_nesovershennoletnix_obuchayusch(1).pdf",
    "https://sveden.utmn.ru/sveden/files/aiw/Reglament_otkrytiya_i_realizacii_dopolnitelynoi_obrazovatelynoi_programmy.pdf",
    "https://sveden.utmn.ru/sveden/files/ein/Poryadok_realizacii_dopolnitelynyx_professionalynyx_programm.pdf",
    "https://sveden.utmn.ru/sveden/files/aib/Poryadok_zacheta_uchebnyx_disciplin,_kursov,_modulei,_praktiti_pri_osvoenii_obuchayuschimisya_DPP.pdf",
    "https://sveden.utmn.ru/sveden/files/vix/Pologhenie_ob_itogovoi_attestacii.pdf",
    "https://sveden.utmn.ru/sveden/files/vie/Prikaz_ot_27.02.2026_No_212-1.pdf",
    "https://sveden.utmn.ru/sveden/files/eiz/Pologhenie_o_stipendialynom_obespechenii_FGAOU_VO_Tyumenskii_gosudarstvennyi_universitet_19.06.2023.pdf",
    "https://sveden.utmn.ru/sveden/files/ziv/Pologhenie_o_merax_socialynoi_podderghki_detei-sirot_FGAOU_VO_TyumGU.pdf",
    "https://sveden.utmn.ru/sveden/files/riz/Pologhenie_o_poryadke_predostavleniya_materialynoi_podderghki_obuchayuschimsya_TyumGU(1).pdf",
    "https://sveden.utmn.ru/sveden/files/rim/Prikaz_ob_ustanovlenii_razmerov_materialynoi_podderghki_obuchayuschimsya_po_obrazovatelynym_programmam_SPO_i_VO_.pdf",
    "https://sveden.utmn.ru/sveden/files/eio/Prikaz_ot_09.02.2026_No_121-1_Ob_ustanovlenii_razmerov_platy_za_proghivanie_obuchayusch,_Tyumeny.pdf",
    "https://sveden.utmn.ru/sveden/files/zin/606_1.pdf",
]

SVEDEN_HTML_PAGES: list[dict[str, Any]] = [
    {
        "url": "https://sveden.utmn.ru/sveden/managers/",
        "title": "Руководство ТюмГУ",
    },
    {
        "url": "https://sveden.utmn.ru/sveden/catering/",
        "title": "Организация питания в ТюмГУ",
    },
    {
        "url": "https://sveden.utmn.ru/sveden/struct",
        "title": "Структура и органы управления ТюмГУ",
    },
]


class SvedenParser(BaseParser):
    """Парсер для портала Сведения.

    Парсит PDF документы через OCR и HTML-страницы с таблицами.
    """

    def __init__(self) -> None:
        self._base_url = "https://sveden.utmn.ru"
        self._headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0)",
        }

    def get_source_type(self) -> str:
        return "sveden"

    async def get_documents(self, source_url: str) -> list[ParsedDocument]:
        pdf_urls = await self._find_pdf_links(source_url)
        logger.info(f"Sveden: найдено {len(pdf_urls)} PDF из whitelist")

        documents = []
        for pdf_url in pdf_urls:
            doc = await self._parse_pdf(pdf_url)
            if doc:
                documents.append(doc)

        for page_meta in SVEDEN_HTML_PAGES:
            doc = await self._parse_html_page(page_meta["url"], page_meta["title"])
            if doc:
                documents.append(doc)

        return documents

    async def get_html_documents(self) -> list[ParsedDocument]:
        documents = []
        for page_meta in SVEDEN_HTML_PAGES:
            doc = await self._parse_html_page(page_meta["url"], page_meta["title"])
            if doc:
                documents.append(doc)
        return documents

    async def get_pdf_documents(self, source_url: str) -> list[ParsedDocument]:
        pdf_urls = await self._find_pdf_links(source_url)
        logger.info(f"Sveden: найдено {len(pdf_urls)} PDF из whitelist")

        documents = []
        for pdf_url in pdf_urls:
            doc = await self._parse_pdf(pdf_url)
            if doc:
                documents.append(doc)
        return documents

    async def _find_pdf_links(self, url: str) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            pdf_urls = set()
            for link in soup.find_all("a", href=True):
                href = str(link.get("href", ""))
                if ".pdf" in href.lower():
                    full_url = urljoin(self._base_url, href)
                    if full_url in ALLOWED_SVEDEN_URLS:
                        pdf_urls.add(full_url)

            return list(pdf_urls)

        except Exception as e:
            logger.error(f"Ошибка поиска PDF ссылок на {url}: {e}")
            return []

    async def _parse_pdf(self, url: str) -> ParsedDocument | None:
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()

            pdf_bytes = BytesIO(response.content)
            text_content = await self._extract_text_ocr(pdf_bytes)
            text_content = self._clean_text(text_content)

            if not text_content.strip():
                logger.warning(f"Пустой контент в PDF: {url}")
                return None

            title = self._extract_title_from_url(url)
            logger.info(f"Распарсен PDF: {title}")

            return ParsedDocument(
                url=url,
                title=title,
                text_content=text_content,
                source_type=self.get_source_type(),
            )

        except Exception as e:
            logger.error(f"Ошибка парсинга PDF {url}: {e}")
            return None

    async def _parse_html_page(self, url: str, title: str) -> ParsedDocument | None:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            content_area = (
                soup.find("div", class_="main-content")
                or soup.find("div", class_="content")
                or soup.find("main")
                or soup.find("div", class_="container")
                or soup.body
            )
            if not content_area:
                content_area = soup

            sections = []
            for section_div in content_area.find_all("div", recursive=False):
                section_heading = section_div.find(["h2", "h3", "h4"])
                if not section_heading:
                    continue

                section_title = section_heading.get_text(strip=True)
                tables = section_div.find_all("table")
                if not tables:
                    text = section_div.get_text(strip=True)
                    if text and len(text) > 20:
                        sections.append(f"{section_title}\n{text}")
                    continue

                tables_text = []
                for table in tables:
                    table_text = self._html_table_to_text(table)
                    if table_text:
                        tables_text.append(table_text)

                if tables_text:
                    combined = "\n\n".join(tables_text)
                    sections.append(f"{section_title}\n\n{combined}")
                else:
                    text = section_div.get_text(strip=True)
                    if text and len(text) > 20:
                        sections.append(f"{section_title}\n{text}")

            if not sections:
                tables = content_area.find_all("table")
                if tables:
                    tables_text = []
                    for table in tables:
                        table_text = self._html_table_to_text(table)
                        if table_text:
                            tables_text.append(table_text)
                    if tables_text:
                        sections.append("\n\n".join(tables_text))

                paragraphs = content_area.find_all("p")
                p_texts = []
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if text and len(text) > 20:
                        p_texts.append(text)
                if p_texts:
                    sections.append("\n\n".join(p_texts))

            full_text = "\n\n".join(sections)
            full_text = re.sub(r"\n{3,}", "\n\n", full_text).strip()

            if not full_text:
                logger.warning(f"Пустой контент на HTML странице: {url}")
                return None

            logger.info(f"Распарсена HTML страница: {title}")
            return ParsedDocument(
                url=url,
                title=title,
                text_content=full_text,
                source_type=self.get_source_type(),
            )

        except Exception as e:
            logger.error(f"Ошибка парсинга HTML страницы {url}: {e}")
            return None

    def _html_table_to_text(self, table: Tag) -> str:
        headers = []
        thead = table.find("thead")
        if thead:
            header_row = thead.find("tr")
            if header_row:
                for th in header_row.find_all(["th", "td"]):
                    header_text = th.get_text(separator=" ", strip=True)
                    header_text = re.sub(r"\s+", " ", header_text)
                    headers.append(header_text)
        else:
            first_row = table.find("tr")
            if first_row:
                cells = first_row.find_all(["th", "td"])
                if cells and any(c.name == "th" for c in cells):
                    for th in first_row.find_all("th"):
                        header_text = th.get_text(separator=" ", strip=True)
                        header_text = re.sub(r"\s+", " ", header_text)
                        headers.append(header_text)

        if not headers:
            rows = table.find_all("tr")
            if not rows:
                return ""
            row_texts = []
            for row in rows:
                cells = row.find_all(["td", "th"])
                cell_texts = []
                for cell in cells:
                    cell_text = cell.get_text(separator=" ", strip=True)
                    cell_text = re.sub(r"\s+", " ", cell_text)
                    if cell_text:
                        cell_texts.append(cell_text)
                if cell_texts:
                    row_texts.append(" | ".join(cell_texts))
            return "\n".join(row_texts)

        rows_text = []
        tbody = table.find("tbody")
        if tbody:
            data_rows = tbody.find_all("tr")
        else:
            data_rows = table.find_all("tr")
            if data_rows and any(c.name == "th" for c in data_rows[0].find_all(["th", "td"])):
                data_rows = data_rows[1:]

        for row in data_rows:
            cells = row.find_all("td")
            if not cells:
                continue

            row_parts = []
            for i, cell in enumerate(cells):
                cell_text = cell.get_text(separator=" ", strip=True)
                cell_text = re.sub(r"\s+", " ", cell_text)
                if not cell_text:
                    continue
                if i < len(headers):
                    header = headers[i]
                    if header in ("№", "#", "N"):
                        continue
                    row_parts.append(f"{header}: {cell_text}")
                else:
                    row_parts.append(cell_text)

            if row_parts:
                rows_text.append("; ".join(row_parts))

        return "\n".join(rows_text)

    async def _extract_text_ocr(self, pdf_bytes: BytesIO) -> str:
        get_tesseract_version()
        ocr_config = get_ocr_config()
        pdf_bytes.seek(0)

        with pdfplumber.open(pdf_bytes) as pdf:
            pages_text = []
            for page in pdf.pages:
                page_image = page.to_image(resolution=220)
                pil_image = page_image.original
                ocr_text = pytesseract.image_to_string(
                    pil_image,
                    lang="rus+eng",
                    config=" ".join(ocr_config),
                )
                if ocr_text and ocr_text.strip():
                    pages_text.append(ocr_text.strip())

            if pages_text:
                return "\n".join(pages_text)

        return ""

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
        text = re.sub(r"([а-яёА-ЯЁa-zA-Z0-9])\s{2,}", r"\1 ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        lines = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                lines.append(line)

        return "\n".join(lines)

    def _extract_title_from_url(self, url: str) -> str:
        filename = url.split("/")[-1]
        filename = re.sub(r"\?.*$", "", filename)
        filename = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
        filename = filename.replace("-", " ").replace("_", " ")
        return filename
