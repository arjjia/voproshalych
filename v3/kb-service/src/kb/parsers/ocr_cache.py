"""Кэш OCR для оптимизации инициализации Tesseract."""

import logging
import subprocess

logger = logging.getLogger(__name__)

_tesseract_version: str | None = None


def get_tesseract_version() -> str:
    """Проверить версию Tesseract и доступность русского языка."""
    global _tesseract_version

    if _tesseract_version is not None:
        return _tesseract_version

    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.split("\n")[0]
        _tesseract_version = version
        logger.info(f"Tesseract: {version}")

        lang_check = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if "rus" in lang_check.stdout:
            logger.info("Русский язык (rus) доступен")
        else:
            logger.warning("Русский язык (rus) НЕ доступен в Tesseract")

        return version

    except Exception as e:
        logger.error(f"Ошибка проверки Tesseract: {e}")
        _tesseract_version = "unknown"
        return "unknown"


def get_ocr_config() -> list[str]:
    """Вернуть оптимальные параметры Tesseract для русских PDF."""
    return [
        "--oem",
        "3",
        "--psm",
        "1",
    ]
