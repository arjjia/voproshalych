"""Парсер для портала Сведения об организации (sveden.utmn.ru).

Получает страницу https://sveden.utmn.ru/sveden/document/,
находит ссылки на PDF документы, скачивает и парсит их.

Внимание: парсит только PDF из ALLOWED_SVEDEN_URLS whitelist.
"""

import logging
import re
from io import BytesIO
from urllib.parse import urljoin

import httpx
import pdfplumber
import pytesseract
from bs4 import BeautifulSoup
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
]


class SvedenParser(BaseParser):
    """Парсер для портала Сведения.

    Получает страницу, находит ссылки на PDF, парсит каждый PDF.
    """

    def __init__(self) -> None:
        """Инициализировать парсер."""
        self._base_url = "https://sveden.utmn.ru"

    def get_source_type(self) -> str:
        """Вернуть тип источника."""
        return "sveden"

    async def get_documents(self, source_url: str) -> list[ParsedDocument]:
        """Получить PDF документы со страницы Сведения.

        Args:
            source_url: URL страницы Сведения (обычно sveden.utmn.ru/sveden/document/)

        Returns:
            Список распарсенных PDF документов
        """
        pdf_urls = await self._find_pdf_links(source_url)
        logger.info(f"Найдено {len(pdf_urls)} PDF ссылок на {source_url}")

        documents = []
        for pdf_url in pdf_urls:
            doc = await self._parse_pdf(pdf_url)
            if doc:
                documents.append(doc)

        return documents

    async def _find_pdf_links(self, url: str) -> list[str]:
        """Найти все ссылки на PDF на странице.

        Args:
            url: URL страницы для поиска

        Returns:
            Список URL PDF файлов (только из whitelist)
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0)",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
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
        """Скачать и распарсить PDF файл.

        Всегда использует Tesseract OCR для извлечения текста из любого PDF.

        Args:
            url: URL PDF файла

        Returns:
            ParsedDocument с содержимым или None при ошибке
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; VoproshalychBot/1.0)",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
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

    async def _extract_text_ocr(self, pdf_bytes: BytesIO) -> str:
        """Извлечь текст из PDF с использованием OCR (Tesseract).

        Args:
            pdf_bytes: PDF файл в памяти

        Returns:
            Текст из PDF
        """
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
        """Очистить текст от артефактов PDF.

        Args:
            text: Сырой текст из PDF

        Returns:
            Очищенный текст
        """
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
        """Извлечь название из URL PDF.

        Args:
            url: URL PDF файла

        Returns:
            Название документа
        """
        filename = url.split("/")[-1]
        filename = re.sub(r"\?.*$", "", filename)
        filename = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
        filename = filename.replace("-", " ").replace("_", " ")
        return filename
