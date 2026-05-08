import asyncio
import aiohttp
import aiofiles
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ================= НАСТРОЙКИ ПУТЕЙ И ФОРМАТОВ =================
# Папка, куда будут скачиваться PDF-файлы
INPUT_PATH = r"C:\Users\ramil\OneDrive\Desktop\PT_start\samples"

# Файл, куда будут сохраняться логи скачанных PDF (формат: файл;-;url)
PDF_LOG_PATH = r"C:\Users\ramil\OneDrive\Desktop\PT_start\pdf_links.txt"

# Файл для сохранения извлеченных текстов и таблиц
TEXT_DATA_PATH = r"C:\Users\ramil\OneDrive\Desktop\PT_start\texts.txt"

# Разделитель между контентом и ссылкой
DELIMITER = "<<<DELIMITER>>>"
# ==============================================================

# Список задач для парсинга
TASKS = [
    {"type": "текст", "url": "https://sveden.utmn.ru/sveden/common/",
     "desc": "Наименование организации, адреса и график работы"},
    {"type": "текст", "url": "https://sveden.utmn.ru/redirect/struct/index.php",
     "desc": "Список институтов, школ и кафедр"},
    {"type": "пдф", "url": "https://sveden.utmn.ru/sveden/document/", "desc": "Устав ТюмГУ"},
    {"type": "пдф", "url": "https://sveden.utmn.ru/sveden/document/",
     "desc": "Правила внутреннего распорядка обучающихся"},
    {"type": "пдф", "url": "https://sveden.utmn.ru/sveden/document/", "desc": "Режим занятий обучающихся"},
    {"type": "пдф", "url": "https://sveden.utmn.ru/sveden/document/",
     "desc": "Порядок текущего контроля и промежуточной аттестации"},
    {"type": "пдф", "url": "https://sveden.utmn.ru/sveden/document/",
     "desc": "Порядок перевода, отчисления и восстановления"},
    {"type": "пдф", "url": "https://sveden.utmn.ru/sveden/document/", "desc": "Правила приема"},
    {"type": "таблица", "url": "https://sveden.utmn.ru/sveden/education/",
     "desc": "Информация о реализуемых образовательных программах"},
    {"type": "пдф", "url": "https://sveden.utmn.ru/sveden/education/", "desc": "Положение о языках образования"},
    {"type": "текст", "url": "https://sveden.utmn.ru/sveden/managers/", "desc": "Информация о ректоре и проректорах"},
    {"type": "текст", "url": "https://sveden.utmn.ru/sveden/objects/",
     "desc": "Сведения о библиотеках и объектах спорта"},
    {"type": "таблица", "url": "https://sveden.utmn.ru/redirect/vacant/index.php",
     "desc": "Количество вакантных мест для приема и перевода"},
    {"type": "таблица", "url": "https://sveden.utmn.ru/sveden/grants/",
     "desc": "Информация о размерах и видах стипендий"},
    {"type": "пдф", "url": "https://sveden.utmn.ru/sveden/grants/", "desc": "Положение о стипендиальном обеспечении"},
    {"type": "текст/таблица", "url": "https://sveden.utmn.ru/sveden/grants/",
     "desc": "Сведения об общежитиях и количестве жилых помещений"},
    {"type": "пдф", "url": "https://sveden.utmn.ru/sveden/grants/",
     "desc": "Приказ об установлении платы за проживание в общежитиях"},
]


async def fetch_html(session, url):
    try:
        async with session.get(url, timeout=15) as response:
            response.raise_for_status()
            return await response.text()
    except Exception as e:
        print(f"[Ошибка] Доступ к {url}: {e}")
        return None


async def download_pdf(session, url, save_path):
    """Скачивает PDF и возвращает True при успехе, иначе False"""
    try:
        async with session.get(url, timeout=30) as response:
            response.raise_for_status()
            async with aiofiles.open(save_path, 'wb') as f:
                while True:
                    chunk = await response.content.read(8192)
                    if not chunk: break
                    await f.write(chunk)
        print(f"[Успех] Скачан PDF: {os.path.basename(save_path)}")
        return True
    except Exception as e:
        print(f"[Ошибка] PDF {url}: {e}")
        return False


def parse_table(table_soup):
    rows = table_soup.find_all('tr')
    parsed_rows = []
    for row in rows:
        cols = row.find_all(['td', 'th'])
        cols_text = [col.get_text(strip=True).replace('\n', ' ') for col in cols]
        parsed_rows.append(" | ".join(cols_text))
    return "\n".join(parsed_rows)


async def process_task(session, task, text_lock, pdf_log_lock):
    url = task['url']
    task_type = task['type'].lower()
    desc = task['desc']

    html = await fetch_html(session, url)
    if not html: return

    soup = BeautifulSoup(html, 'lxml')
    # Очистка от скриптов, стилей и меню
    for tag in soup(['script', 'style', 'nav', 'header', 'footer']): tag.decompose()

    # 1. ПОИСК И СКАЧИВАНИЕ PDF
    if 'пдф' in task_type:
        keywords = [w.lower() for w in desc.replace(',', '').split() if len(w) > 3]
        pdf_link = None
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True).lower()
            if any(kw in text for kw in keywords) and (href.endswith('.pdf') or 'document' in href):
                pdf_link = urljoin(url, href)
                break

        if pdf_link:
            filename = re.sub(r'[\\/*?:"<>|]', "", desc) + ".pdf"
            save_path = os.path.join(INPUT_PATH, filename)
            is_downloaded = await download_pdf(session, pdf_link, save_path)

            # Если скачалось успешно, записываем в лог-файл в формате: test.pdf;-;url
            if is_downloaded:
                async with pdf_log_lock:
                    async with aiofiles.open(PDF_LOG_PATH, 'a', encoding='utf-8') as f:
                        await f.write(f"{filename};-;{pdf_link}\n")

    # 2. ИЗВЛЕЧЕНИЕ ТЕКСТА И ТАБЛИЦ
    content_parts = []
    if 'таблица' in task_type:
        for table in soup.find_all('table'):
            content_parts.append(parse_table(table))

    if 'текст' in task_type:
        main_box = soup.find('main') or soup.find('div', class_=re.compile('content|text', re.I)) or soup.body
        if main_box:
            txt = main_box.get_text(separator='\n', strip=True)
            content_parts.append(re.sub(r'\n{3,}', '\n\n', txt))

    # Если нашли текст или таблицы, склеиваем их и сохраняем с заданным разделителем
    if content_parts:
        # Соединяем все найденные куски текста/таблиц
        combined_content = "\n\n".join(content_parts).strip()

        async with text_lock:
            async with aiofiles.open(TEXT_DATA_PATH, 'a', encoding='utf-8') as f:
                # Формат: текст/таблица<<<DELIMITER>>>URL
                await f.write(f"{combined_content}{DELIMITER}{url}\n")
        print(f"[Успех] Текст сохранен для: {desc}")


async def main():
    # Создаем папки если их нет
    os.makedirs(INPUT_PATH, exist_ok=True)
    os.makedirs(os.path.dirname(PDF_LOG_PATH) or '.', exist_ok=True)
    os.makedirs(os.path.dirname(TEXT_DATA_PATH) or '.', exist_ok=True)

    # Очищаем старые файлы перед новой записью
    open(PDF_LOG_PATH, 'w', encoding='utf-8').close()
    open(TEXT_DATA_PATH, 'w', encoding='utf-8').close()

    print(
        f"Запуск... \nПапка для PDF -> {INPUT_PATH}\nФайл логов PDF -> {PDF_LOG_PATH}\nФайл текстов -> {TEXT_DATA_PATH}\n")

    # Блокировки (locks) для безопасной асинхронной записи в разные файлы
    text_lock = asyncio.Lock()
    pdf_log_lock = asyncio.Lock()

    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}) as session:
        tasks = [process_task(session, t, text_lock, pdf_log_lock) for t in TASKS]
        await asyncio.gather(*tasks)

    print("\nГотово!")


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())