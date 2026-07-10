"""Детектор типа PDF для выбора подходящего парсера."""

import logging

import pdfplumber

logger = logging.getLogger(__name__)

PDFType = str
PDF_NATIVE = "native"
PDF_SCANNED = "scanned"


def detect_pdf_type(
    pdf_path: str,
    coverage_threshold: float = 0.85,
    min_text_length: int = 30,
) -> PDFType:
    """Определяет тип PDF по наличию текста и изображений.

    Args:
        pdf_path: Путь к PDF файлу
        coverage_threshold: Порог покрытия страницы изображением (по умолчанию 85%)
        min_text_length: Минимальная длина текста для определения как native (по умолчанию 30)

    Returns:
        PDF_NATIVE — текстовый PDF
        PDF_SCANNED — сканированный PDF

    """
    score = 0
    reasons = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_text_length = 0
            for i, page in enumerate(pdf.pages):
                images = page.images
                text = page.extract_text()

                if text:
                    total_text_length += len(text)

                # Image coverage check (с повышенным threshold)
                if images:
                    page_area = page.width * page.height
                    max_coverage = max(
                        (img["width"] * img["height"]) / page_area for img in images
                    )
                    if max_coverage > coverage_threshold:
                        score += 3
                        reasons.append(f"Page {i}: image covers {max_coverage:.0%}")

                # No text check (если совсем нет текста)
                if not text or not text.strip():
                    score += 3
                    reasons.append(f"Page {i}: no extractable text")

            # Проверка по общей длине текста (force native если есть текст)
            if total_text_length >= min_text_length:
                logger.debug(
                    f"PDF {pdf_path} detected as NATIVE (text length: {total_text_length})"
                )
                return PDF_NATIVE

            if score >= 5:
                logger.debug(f"PDF {pdf_path} detected as SCANNED. Reasons: {reasons}")
                return PDF_SCANNED
            else:
                logger.debug(f"PDF {pdf_path} detected as NATIVE (default)")
                return PDF_NATIVE

    except Exception as e:
        logger.error(f"Error detecting PDF type for {pdf_path}: {e}")
        return PDF_NATIVE
