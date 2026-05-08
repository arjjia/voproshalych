"""Генерация «трудного» датасета для RAG-бенчмарков.

4 категории запросов:
1. Кросс-документные (20%) — вопрос требует 2+ документов
2. Условные/составные (15%) — 2+ условия, каждое = отдельная сущность
3. По конкретным дисциплинам (15%) — названа дисциплина/регламент
4. Прямые контрольные (50%) — обычные вопросы

ВСЕ вопросы генерируются в стиле реальных студентов:
опечатки, без запятых, сленг, строчными — как в чат поддержки.

Использует Mistral Open Nemo через OpenAI-compatible API.
Данные берёт из PostgreSQL (v2 LightRAG).
"""

import argparse
import hashlib
import json
import logging
import os
import random
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env.docker")
load_dotenv()

INSTITUTES = [
    "ШКН", "ФЭИ", "СоцГУ", "ИПиП", "Биофак", "ИНЖИН",
    "ИНХИМ", "ФТИ", "ИНБИО", "ИФК", "ЕГШ", "ШПИ",
    "ШЕН", "УИОТ", "Колледж информационных технологий",
    "Институт биологии", "Гуманитарный институт",
]

NOISE_ENTITIES = {
    "Сертификат", "Корпус 1", "Кабинет 205",
    "Кабинет 205 корпуса 1", "Институт биологии",
    "Колледж информационных технологий",
    "Тюменский государственный университет",
    "Тюмень", "ТюмГУ", "ФГАОУ ВО «Тюменский государственный университет»",
}

DISCIPLINE_DOC_IDS = {
    "c96dfa8d83b52bfa",
    "1bba857e92b48fd5",
    "dd5e86036969deb5",
    "3ab86954cf586669",
    "82d4f5304fdfda45",
    "3c59a061d32e72c4",
    "da5582f52a5a8ffb",
    "7b48fe73317dbe0a",
    "c33d378aff3a9434",
    "e77eef10e762e055",
    "a54bf1f9ef37a853",
    "d7f0003f0efac5f3",
    "bcdf537d0c62ebb0",
}

CATEGORY_CROSS_DOC = "cross_document"
CATEGORY_CONDITIONAL = "conditional"
CATEGORY_DISCIPLINE = "discipline"
CATEGORY_DIRECT = "direct"

CATEGORIES = [
    CATEGORY_CROSS_DOC,
    CATEGORY_CONDITIONAL,
    CATEGORY_DISCIPLINE,
    CATEGORY_DIRECT,
]

SPOIL_RULES = """ШАГИ:
1. Найди в тексте конкретный факт/правило/баллы/дедлайн
2. Сгенерируй вопрос + ответ — ответ ДОЛЖЕН быть в тексте
3. ПОТОМ испорти вопрос: опечатки, без запятых, сленг, строчными

ЗАПРЕЩЕНО:
- "не указано", "в тексте нет" — таких ответов НЕ должно быть
- если в тексте нет ответа — придумай ДРУГОЙ вопрос
- "когда сессия?" — слишком общие вопросы часто не имеют ответа

Оригинальный (правильный) вопрос сохрани в clean_question."""

COMMON_STYLE = """СТИЛЬ ВОПРОСА (применяется ПОСЛЕ того как вопрос сформулирован по фактам):
- Пиши как реальный студент в чат поддержки — небрежно, строчными
- Сокращения: тюмгу, шкн, фэи, соцгум, ипип, биофак, инхим, фти, инбио, ифк, шен
- Сленг: стипуха, зачётка, хвосты, академ, бюджетник, платник, заочник, общага, деканат, курсач
- Можно без знаков препинания, строчными буквами"""

CATEGORY_PROMPTS = {
    CATEGORY_DIRECT: """НИЖЕ ПРИВЕДЁН ФРАГМЕНТ ДОКУМЕНТАЦИИ ТюмГУ.

{spoil_rules}

{common_style}

Фрагмент:
```
{chunk_text}
```

Верни ТОЛЬКО JSON:
{{"question": "...", "clean_question": "...", "ground_truth_answer": "..."}}""",

    CATEGORY_CROSS_DOC: """НИЖЕ ПРИВЕДЕНЫ ДВА ФРАГМЕНТА из РАЗНЫХ документов ТюмГУ.

Твоя задача: прочитать ОБА фрагмента и сгенерировать ОДИН вопрос, ответ на который требует информацию ИЗ ОБЕИХ частей.

{spoil_rules}

{common_style}

Фрагмент 1:
```
{chunk_text_1}
```

Фрагмент 2:
```
{chunk_text_2}
```

Верни ТОЛЬКО JSON:
{{"question": "...", "clean_question": "...", "ground_truth_answer": "..."}}""",

    CATEGORY_CONDITIONAL: """НИЖЕ ПРИВЕДЁН ФРАГМЕНТ ДОКУМЕНТАЦИИ ТюмГУ.

Твоя задача: прочитать фрагмент и сгенерировать вопрос с 2+ условиями, который МОЖНО ОТВЕТИТЬ по этому фрагменту.

{spoil_rules}

Ключевые сущности: {entities}

{common_style}

Фрагмент:
```
{chunk_text}
```

Верни ТОЛЬКО JSON:
{{"question": "...", "clean_question": "...", "ground_truth_answer": "..."}}""",

    CATEGORY_DISCIPLINE: """НИЖЕ ПРИВЕДЁН ФРАГМЕНТ ДОКУМЕНТАЦИИ ТюмГУ — по конкретной дисциплине/регламенту.

Твоя задача: прочитать фрагмент и сгенерировать вопрос, который МОЖНО ОТВЕТИТЬ ТОЛЬКО по этому фрагменту.
В вопросе должно быть названо конкретное название дисциплины/регламента.

{spoil_rules}

{common_style}

Фрагмент:
```
{chunk_text}
```

Верни ТОЛЬКО JSON:
{{"question": "...", "clean_question": "...", "ground_truth_answer": "..."}}""",
}


def _parse_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip().replace("{{", "{").replace("}}", "}")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}


def _item_id(text: str, prefix: str = "v2_") -> str:
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}{h}"


class DBData:
    def __init__(self, dsn: str):
        self.conn = psycopg2.connect(dsn)
        self.chunks: List[Dict] = []
        self.entity_to_docs: Dict[str, Set[str]] = defaultdict(set)
        self.doc_to_entities: Dict[str, Set[str]] = defaultdict(set)
        self.entity_to_chunks: Dict[str, List[str]] = defaultdict(list)
        self.chunk_id_to_doc: Dict[str, str] = {}
        self.doc_id_to_chunks: Dict[str, List[Dict]] = defaultdict(list)
        self.chunk_id_to_content: Dict[str, str] = {}
        self._load()

    def _load(self):
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, full_doc_id, content, file_path FROM lightrag_doc_chunks")
            for row in cur.fetchall():
                chunk = dict(row)
                self.chunks.append(chunk)
                self.chunk_id_to_doc[chunk["id"]] = chunk["full_doc_id"]
                self.chunk_id_to_content[chunk["id"]] = chunk["content"]
                self.doc_id_to_chunks[chunk["full_doc_id"]].append(chunk)

            cur.execute("SELECT id, chunk_ids FROM lightrag_entity_chunks")
            for row in cur.fetchall():
                entity_name = row["id"]
                chunk_ids = row["chunk_ids"] or []
                if not isinstance(chunk_ids, list):
                    continue
                for cid in chunk_ids:
                    if cid in self.chunk_id_to_doc:
                        doc_id = self.chunk_id_to_doc[cid]
                        self.entity_to_docs[entity_name].add(doc_id)
                        self.doc_to_entities[doc_id].add(entity_name)
                        self.entity_to_chunks[entity_name].append(cid)

        logger.info(
            "Загружено: %d чанков, %d документов, %d сущностей",
            len(self.chunks),
            len(self.doc_id_to_chunks),
            len(self.entity_to_docs),
        )
        self.conn.close()

    def get_discriminative_entities(self, min_docs: int = 2, max_docs: int = 50) -> List[str]:
        entities = []
        for entity, docs in self.entity_to_docs.items():
            if entity in NOISE_ENTITIES:
                continue
            n = len(docs)
            if min_docs <= n <= max_docs:
                entities.append(entity)
        entities.sort(key=lambda e: len(self.entity_to_docs[e]), reverse=True)
        return entities

    def get_chunks_with_entity(self, entity: str) -> List[Dict]:
        chunk_ids = self.entity_to_chunks.get(entity, [])
        return [
            {"id": cid, "content": self.chunk_id_to_content[cid], "doc_id": self.chunk_id_to_doc[cid]}
            for cid in chunk_ids
            if cid in self.chunk_id_to_content
        ]

    def find_shared_entity_pairs(self, max_pairs: int = 100) -> List[Tuple[str, str, str]]:
        disc = self.get_discriminative_entities(min_docs=2, max_docs=30)
        pairs = []
        max_per_entity = 2
        for entity in disc:
            docs = list(self.entity_to_docs[entity])
            random.shuffle(docs)
            count = 0
            for i in range(len(docs)):
                for j in range(i + 1, len(docs)):
                    pairs.append((entity, docs[i], docs[j]))
                    count += 1
                    if count >= max_per_entity:
                        break
                if count >= max_per_entity:
                    break
            if len(pairs) >= max_pairs:
                break
        random.shuffle(pairs)
        return pairs[:max_pairs]


SYSTEM_PROMPT = (
    "Ты формируешь synthetic dataset для RAG-бенчмарков. "
    "АБСОЛЮТНЫЙ ПРИОРИТЕТ: вопрос должен быть ОТВЕТИМ по тексту фрагмента. "
    "ЗАПРЕЩЕНО задавать вопросы о том, чего нет в тексте. "
    "Стиль: студент ТюмГУ пишет в чат поддержки — небрежно, с опечатками, строчными."
)


class DatasetGenerator:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.mistral.ai/v1",
        model: str = "open-mistral-nemo",
        request_delay: float = 1.5,
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=60)
        self.model = model
        self.request_delay = request_delay

    @retry(stop=stop_after_attempt(3), wait=wait_random_exponential(min=5, max=60), reraise=True)
    def _generate(self, system: str, user: str, temperature: float = 0.8) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=600,
        )
        return (resp.choices[0].message.content or "").strip()

    def _generate_single(self, prompt: str) -> Optional[Dict]:
        content = self._generate(SYSTEM_PROMPT, prompt)
        result = _parse_json(content)
        if "question" not in result:
            return None
        time.sleep(self.request_delay)
        return result

    def generate_direct(self, chunk: Dict) -> Optional[Dict]:
        prompt = CATEGORY_PROMPTS[CATEGORY_DIRECT].format(
            chunk_text=chunk["content"][:1500],
            spoil_rules=SPOIL_RULES,
            common_style=COMMON_STYLE,
        )
        return self._generate_single(prompt)

    def generate_cross_doc(self, chunk1: Dict, chunk2: Dict) -> Optional[Dict]:
        prompt = CATEGORY_PROMPTS[CATEGORY_CROSS_DOC].format(
            chunk_text_1=chunk1["content"][:800],
            chunk_text_2=chunk2["content"][:800],
            spoil_rules=SPOIL_RULES,
            common_style=COMMON_STYLE,
        )
        return self._generate_single(prompt)

    def generate_conditional(self, chunk: Dict, entities: List[str]) -> Optional[Dict]:
        prompt = CATEGORY_PROMPTS[CATEGORY_CONDITIONAL].format(
            chunk_text=chunk["content"][:1500],
            entities=", ".join(entities[:5]),
            spoil_rules=SPOIL_RULES,
            common_style=COMMON_STYLE,
        )
        return self._generate_single(prompt)

    def generate_discipline(self, chunk: Dict) -> Optional[Dict]:
        prompt = CATEGORY_PROMPTS[CATEGORY_DISCIPLINE].format(
            chunk_text=chunk["content"][:1500],
            spoil_rules=SPOIL_RULES,
            common_style=COMMON_STYLE,
        )
        return self._generate_single(prompt)


def _make_item(
    question: str,
    ground_truth_answer: str,
    category: str,
    chunk_ids: List[str],
    doc_ids: List[str],
    chunk_texts: List[str],
    clean_question: Optional[str] = None,
    chunk_to_url: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if chunk_to_url is None:
        chunk_to_url = {}
    item = {
        "id": _item_id(question),
        "source": "synthetic_v2",
        "category": category,
        "question": question.strip(),
        "ground_truth_answer": ground_truth_answer.strip(),
        "chunk_id": chunk_ids[0] if chunk_ids else None,
        "relevant_chunk_ids": chunk_ids,
        "relevant_urls": doc_ids,
        "confluence_url": chunk_to_url.get(chunk_ids[0], "") if chunk_ids else "",
        "chunk_text": chunk_texts[0][:500] if chunk_texts else "",
    }
    if clean_question:
        item["clean_question"] = clean_question
    return item


def _save_incremental(dataset: List[Dict], output_path: str) -> None:
    if not output_path:
        return
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)


def generate_dataset(
    db_data: DBData,
    generator: DatasetGenerator,
    target_counts: Dict[str, int],
    output_path: str = "",
    save_every: int = 10,
) -> List[Dict]:
    dataset: List[Dict] = []
    errors: List[str] = []

    chunk_to_url: Dict[str, str] = {}
    for chunk in db_data.chunks:
        if "file_path" in chunk and "id" in chunk:
            chunk_to_url[chunk["id"]] = chunk["file_path"]

    chunk_usage: Dict[str, int] = defaultdict(int)
    MAX_CHUNK_USAGE = 3
    _save_counter = 0

    def _on_added():
        nonlocal _save_counter
        _save_counter += 1
        if _save_counter % save_every == 0:
            _save_incremental(dataset, output_path)
            logger.info("[CHECKPOINT] Сохранено %d вопросов в %s", len(dataset), output_path)

    def _add_item(result, category, chunk_ids, doc_ids, chunk_texts):
        q = result["question"].strip()
        clean = result.get("clean_question", "").strip()
        item = _make_item(
            question=q,
            ground_truth_answer=result.get("ground_truth_answer", ""),
            category=category,
            chunk_ids=chunk_ids,
            doc_ids=doc_ids,
            chunk_texts=chunk_texts,
            clean_question=clean or None,
            chunk_to_url=chunk_to_url,
        )
        dataset.append(item)
        _on_added()
        for cid in chunk_ids:
            chunk_usage[cid] += 1
        return item

    chunks = db_data.chunks
    random.shuffle(chunks)

    def _available(chunks_list: List[Dict]) -> List[Dict]:
        return [c for c in chunks_list if chunk_usage[c["id"]] < MAX_CHUNK_USAGE]

    # Category 1: Cross-document
    cross_target = target_counts.get(CATEGORY_CROSS_DOC, 40)
    logger.info("=== Категория 1: Кросс-документные (цель: %d) ===", cross_target)
    pairs = db_data.find_shared_entity_pairs(max_pairs=cross_target * 4)
    random.shuffle(pairs)
    cross_generated = 0
    for entity, doc1, doc2 in pairs:
        if cross_generated >= cross_target:
            break
        chunks_d1 = _available(db_data.doc_id_to_chunks[doc1])
        chunks_d2 = _available(db_data.doc_id_to_chunks[doc2])
        if not chunks_d1 or not chunks_d2:
            continue
        for attempt in range(3):
            c1 = random.choice(chunks_d1)
            c2 = random.choice(chunks_d2)
            try:
                result = generator.generate_cross_doc(c1, c2)
                if result and "question" in result:
                    item = _add_item(
                        result,
                        CATEGORY_CROSS_DOC,
                        [c1["id"], c2["id"]],
                        [doc1, doc2],
                        [c1["content"], c2["content"]],
                    )
                    cross_generated += 1
                    logger.info("[%d/%d] cross-doc: %s...", cross_generated, cross_target, item["question"][:50])
                    break
            except Exception as e:
                errors.append(f"cross_doc: {e}")
                logger.warning("Ошибка cross_doc: %s", e)
                break
    logger.info("Кросс-документных: %d/%d", cross_generated, cross_target)

    # Category 2: Discipline
    disc_target = target_counts.get(CATEGORY_DISCIPLINE, 30)
    logger.info("=== Категория 2: По дисциплинам (цель: %d) ===", disc_target)
    disc_generated = 0
    discipline_chunks = [
        c for c in chunks if db_data.chunk_id_to_doc.get(c["id"]) in DISCIPLINE_DOC_IDS
    ]
    random.shuffle(discipline_chunks)
    logger.info("  Чанков для discipline: %d", len(discipline_chunks))
    disc_doc_used: Dict[str, int] = defaultdict(int)
    for chunk in discipline_chunks:
        if disc_generated >= disc_target:
            break
        doc_id = db_data.chunk_id_to_doc[chunk["id"]]
        if disc_doc_used[doc_id] >= 3:
            continue
        if chunk_usage[chunk["id"]] >= MAX_CHUNK_USAGE:
            continue
        for attempt in range(3):
            try:
                result = generator.generate_discipline(chunk)
                if result and "question" in result:
                    item = _add_item(
                        result,
                        CATEGORY_DISCIPLINE,
                        [chunk["id"]],
                        [doc_id],
                        [chunk["content"]],
                    )
                    disc_doc_used[doc_id] += 1
                    disc_generated += 1
                    logger.info("[%d/%d] discipline: %s...", disc_generated, disc_target, item["question"][:50])
                    break
            except Exception as e:
                errors.append(f"discipline: {e}")
                logger.warning("Ошибка discipline: %s", e)
                break
    logger.info("По дисциплинам: %d/%d", disc_generated, disc_target)

    # Category 3: Conditional
    cond_target = target_counts.get(CATEGORY_CONDITIONAL, 30)
    logger.info("=== Категория 3: Условные (цель: %d) ===", cond_target)
    cond_generated = 0
    cond_chunks = list(chunks)
    random.shuffle(cond_chunks)
    for chunk in cond_chunks:
        if cond_generated >= cond_target:
            break
        if chunk_usage[chunk["id"]] >= MAX_CHUNK_USAGE:
            continue
        doc_id = db_data.chunk_id_to_doc[chunk["id"]]
        doc_entities = list(db_data.doc_to_entities.get(doc_id, set()) - NOISE_ENTITIES)
        if len(doc_entities) < 2:
            continue
        for attempt in range(3):
            try:
                result = generator.generate_conditional(chunk, doc_entities)
                if result and "question" in result:
                    item = _add_item(
                        result,
                        CATEGORY_CONDITIONAL,
                        [chunk["id"]],
                        [doc_id],
                        [chunk["content"]],
                    )
                    cond_generated += 1
                    logger.info("[%d/%d] conditional: %s...", cond_generated, cond_target, item["question"][:50])
                    break
            except Exception as e:
                errors.append(f"conditional: {e}")
                logger.warning("Ошибка conditional: %s", e)
                break
    logger.info("Условных: %d/%d", cond_generated, cond_target)

    # Category 4: Direct
    direct_target = target_counts.get(CATEGORY_DIRECT, 100)
    logger.info("=== Категория 4: Прямые контрольные (цель: %d) ===", direct_target)
    direct_generated = 0
    direct_chunks = list(chunks)
    random.shuffle(direct_chunks)
    for chunk in direct_chunks:
        if direct_generated >= direct_target:
            break
        if chunk_usage[chunk["id"]] >= MAX_CHUNK_USAGE:
            continue
        for attempt in range(3):
            try:
                result = generator.generate_direct(chunk)
                if result and "question" in result:
                    item = _add_item(
                        result,
                        CATEGORY_DIRECT,
                        [chunk["id"]],
                        [db_data.chunk_id_to_doc[chunk["id"]]],
                        [chunk["content"]],
                    )
                    direct_generated += 1
                    logger.info("[%d/%d] direct: %s...", direct_generated, direct_target, item["question"][:50])
                    break
            except Exception as e:
                errors.append(f"direct: {e}")
                logger.warning("Ошибка direct: %s", e)
                break
    logger.info("Прямых: %d/%d", direct_generated, direct_target)

    logger.info("=== ИТОГО ===")
    logger.info("Сгенерировано: %d вопросов", len(dataset))
    by_cat = defaultdict(int)
    for item in dataset:
        by_cat[item["category"]] += 1
    for cat, cnt in by_cat.items():
        logger.info("  %s: %d", cat, cnt)
    if errors:
        logger.warning("Ошибок: %d", len(errors))

    return dataset


def main():
    parser = argparse.ArgumentParser(description="Генерация «трудного» датасета для RAG-бенчмарков")
    parser.add_argument("--output", type=str, default=None, help="Путь для сохранения датасета")
    parser.add_argument("--db-host", type=str, default="localhost", help="PostgreSQL host")
    parser.add_argument("--db-port", type=int, default=5433, help="PostgreSQL port")
    parser.add_argument("--db-name", type=str, default="voproshalych", help="PostgreSQL database")
    parser.add_argument("--db-user", type=str, default="voproshalych", help="PostgreSQL user")
    parser.add_argument("--db-password", type=str, default="voproshalych", help="PostgreSQL password")
    parser.add_argument("--api-key", type=str, default=None, help="Mistral API key")
    parser.add_argument("--model", type=str, default="open-mistral-nemo", help="LLM model name")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between API calls (seconds)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--limit", type=int, default=None, help="Limit total questions (for testing)")
    args = parser.parse_args()

    random.seed(args.seed)

    api_key = args.api_key or os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY не задан. Укажите --api-key или MISTRAL_API_KEY в окружении.")

    dsn = f"postgresql://{args.db_user}:{args.db_password}@{args.db_host}:{args.db_port}/{args.db_name}"
    logger.info("Подключение к БД: %s", dsn.replace(args.db_password, "***"))

    db_data = DBData(dsn)
    generator = DatasetGenerator(api_key=api_key, model=args.model, request_delay=args.delay)

    target_counts = {
        CATEGORY_CROSS_DOC: 40,
        CATEGORY_DISCIPLINE: 30,
        CATEGORY_CONDITIONAL: 30,
        CATEGORY_DIRECT: 100,
    }

    if args.limit:
        scale = args.limit / sum(target_counts.values())
        target_counts = {k: max(1, int(v * scale)) for k, v in target_counts.items()}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "..",
        "tyumgu_2026_MIM", "Benchmarks", "benchmarks_datasets",
        f"dataset_hard_{timestamp}.json",
    )
    output_path = os.path.abspath(output_path)

    dataset = generate_dataset(db_data, generator, target_counts, output_path=output_path)

    _save_incremental(dataset, output_path)

    print(f"\n=== Датасет сохранён: {output_path} ===")
    print(f"Всего вопросов: {len(dataset)}")
    by_cat = defaultdict(int)
    for item in dataset:
        by_cat[item["category"]] += 1
    for cat, cnt in sorted(by_cat.items()):
        print(f"  {cat}: {cnt}")


if __name__ == "__main__":
    main()
