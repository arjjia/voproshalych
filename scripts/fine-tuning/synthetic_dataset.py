import asyncio
import json
import os
import re

import aiohttp
from dotenv import load_dotenv
from tqdm.asyncio import tqdm

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise ValueError("Нет ключа OPENROUTER_API_KEY в .env")

MODEL = "openai/gpt-4o-mini"
IN_FILE = "chunks_result.txt"
OUT_FILE = "qa_dataset.jsonl"
LIMIT = 10

PROMPT_TEMPLATE = """
Твоя задача — придумать вопросы для базы знаний студенческого ассистента ТюмГУ.
Вот кусок текста:
---
{text}
---

Правила:
1. Задавай вопросы как обычный студент в телеграме (например: "как перевестись на бюджет?", "где взять справку?").
2. Если в тексте только вода, подписи, ФИО ректора или номера приказов — возвращай пустой список.
3. Вопрос должен иметь прямой ответ в тексте.

Формат ответа — только JSON:
{{"questions": ["вопрос 1", "вопрос 2"]}}
Если текст бесполезный: {{"questions": []}}
"""

async def fetch_qa(session, sem, text, chunk_id):
    async with sem:
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": PROMPT_TEMPLATE.format(text=text)}],
            "response_format": {"type": "json_object"}
        }
        
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        for attempt in range(3):
            try:
                async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    
                    resp.raise_for_status()
                    data = await resp.json()
                    
                    if not data.get('choices'):
                        return []
                        
                    content = data['choices'][0]['message']['content']

                    try:
                        parsed = json.loads(content)
                    except json.JSONDecodeError:
                        continue

                    qs = parsed.get("questions", [])
                    if not qs and parsed:
                        val = list(parsed.values())[0]
                        qs = val if isinstance(val, list) else [val] if isinstance(val, str) else []

                    result = []
                    for q in qs:
                        if isinstance(q, str) and len(q.strip()) > 10:
                            result.append({
                                "anchor": q.strip(),
                                "positive": text,
                                "source_id": str(chunk_id)
                            })
                    
                    if result:
                        return result
                    
            except Exception:
                await asyncio.sleep(1)
                
        return []

def get_chunks(path):
    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read().split("<<<DELIMITER>>>")
    
    chunks = []
    for i, c in enumerate(raw):
        text = c.split("|SOURCE_URL|")[0].strip()
        if len(re.sub(r'\s+', '', text)) > 50:
            chunks.append((str(i), text))
            
    return chunks

async def generate_dataset():
    chunks = get_chunks(IN_FILE)
    print(f"Найдено рабочих чанков: {len(chunks)}")
    if not chunks:
        return

    sem = asyncio.Semaphore(LIMIT)
    dataset = []

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_qa(session, sem, text, c_id) for c_id, text in chunks]
        
        for res in await tqdm.gather(*tasks, desc="Генерация вопросов"):
            if res:
                dataset.extend(res)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for row in dataset:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            
    print(f"Собрано пар: {len(dataset)}. Файл сохранен как {OUT_FILE}")

if __name__ == "__main__":
    asyncio.run(generate_dataset())
