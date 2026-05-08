import asyncio
import aiofiles
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import fitz
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import logging

# Импорт сплиттера
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ===================== НАСТРОЙКИ (SETTINGS) =====================
# Пути к файлам и папкам
INPUT_PATH = r"C:\Users\ramil\OneDrive\Desktop\PT_start\samples"
LINKS_DATA_PATH = r"C:\Users\ramil\OneDrive\Desktop\PT_start\pdf_links.txt"
OUTPUT_PATH = r"C:\Users\ramil\OneDrive\Desktop\PT_start\chunks_result.txt"

# --- ПАРАМЕТРЫ ЧАНКИРОВАНИЯ ---
CHUNK_SIZE = 1024  # Максимальное количество токенов в чанке
CHUNK_OVERLAP = 200  # Перекрытие между чанками (токенов)

# Разделители для выходного файла
FIELD_SEP = " |SOURCE_URL| "
CHUNK_DELIMITER = "\n<<<DELIMITER>>>\n"

# Настройки Tesseract
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_LANG = 'rus'

# Производительность и качество OCR
MAX_WORKERS = 8
DPI = 300

# Параметры предобработки изображения
CONTRAST = 2.0
SHARPEN = True
THRESHOLD = 140
# ===============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def load_links_map(path: str) -> dict:
    """Парсит файл со ссылками."""
    links_map = {}
    p = Path(path)
    if not p.exists():
        logger.warning(f"Файл ссылок не найден: {path}")
        return links_map
    try:
        with open(p, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(';')
                if len(parts) >= 3:
                    links_map[parts[0].strip()] = parts[2].strip()
    except Exception as e:
        logger.error(f"Ошибка загрузки ссылок: {e}")
    return links_map


def preprocess_image(img: Image.Image) -> Image.Image:
    img = img.convert('L')
    if CONTRAST != 1.0:
        img = ImageEnhance.Contrast(img).enhance(CONTRAST)
    if SHARPEN:
        img = img.filter(ImageFilter.SHARPEN)
    img = img.point(lambda x: 0 if x < THRESHOLD else 255, '1')
    return img


def ocr_pdf(pdf_path: str) -> str:
    """OCR обработка документа."""
    try:
        doc = fitz.open(pdf_path)
        full_text = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(DPI / 72, DPI / 72))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img = preprocess_image(img)
            text = pytesseract.image_to_string(img, lang=TESSERACT_LANG)
            full_text.append(text.strip())
        doc.close()
        return "\n".join(full_text)
    except Exception as e:
        return f"ERROR_OCR: {e}"


async def process_chunks_async(text: str, url: str):
    """Асинхронное чанкирование текста."""
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )

    loop = asyncio.get_running_loop()
    # Выполняем разбиение в экзекуторе, чтобы не блокировать цикл
    chunks = await loop.run_in_executor(None, splitter.split_text, text)

    # К каждому чанку прикрепляем его URL
    return [f"{chunk}{FIELD_SEP}{url}" for chunk in chunks]


async def main():
    # Загружаем метаданные
    links_map = load_links_map(LINKS_DATA_PATH)

    source_path = Path(sys.argv[1] if len(sys.argv) > 1 else INPUT_PATH).resolve()
    target_file = Path(OUTPUT_PATH).resolve()

    if not source_path.exists():
        logger.error(f"Входной путь не найден: {source_path}")
        return

    pdf_files = [source_path] if source_path.is_file() else list(source_path.rglob("*.pdf"))
    if not pdf_files:
        logger.warning("PDF файлы не найдены.")
        return

    # 1. Запуск OCR (параллельные процессы)
    logger.info(f"Запуск OCR для {len(pdf_files)} файлов...")
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        loop = asyncio.get_running_loop()
        ocr_tasks = [loop.run_in_executor(executor, ocr_pdf, str(p)) for p in pdf_files]
        ocr_results = await asyncio.gather(*ocr_tasks)

    # 2. Чанкирование (асинхронно)
    logger.info(f"Разбиение на чанки (Size: {CHUNK_SIZE}, Overlap: {CHUNK_OVERLAP})...")
    chunk_tasks = []
    for path, text in zip(pdf_files, ocr_results):
        url = links_map.get(path.name, "URL_NOT_FOUND")
        chunk_tasks.append(process_chunks_async(text, url))

    nested_chunks = await asyncio.gather(*chunk_tasks)

    # 3. Сохранение итогового файла
    target_file.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(target_file, 'w', encoding='utf-8') as f:
        for file_chunks in nested_chunks:
            for chunk_content in file_chunks:
                # Записываем чанк и разделитель
                await f.write(chunk_content + CHUNK_DELIMITER)

    logger.info(f"Успешно! Итоговый файл: {target_file}")


if __name__ == "__main__":
    asyncio.run(main())