"""Генерация «трудного» датасета для RAG-бенчмарков.

6 категорий запросов:
1. Кросс-документные (25-30%) — вопрос требует 2+ документов
2. Навигационные по институтам (15-20%) — конкретный институт/кафедра
3. Условные/составные (15-20%) — 2+ условия, каждое = отдельная сущность
4. По конкретным дисциплинам (10-15%) — названа дисциплина/регламент
5. Плохо сформулированные (10-15%) — опечатки, сленг, сокращения
6. Прямые контрольные (15-20%) — обычные вопросы (baseline)

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


class QuestionDedup:
    def __init__(self, similarity_threshold: float = 0.7):
        self._questions: List[str] = []
        self._words_sets: List[Set[str]] = []
        self._threshold = similarity_threshold

    @staticmethod
    def _normalize(text: str) -> Set[str]:
        words = re.findall(r"[а-яёa-z0-9]+", text.lower())
        stop = {"в", "на", "и", "с", "по", "к", "у", "о", "а", "не", "как", "то", "за", "из", "от", "до", "для", "это", "что", "есть", "быть", "мой", "мне", "меня", "я"}
        return set(w for w in words if w not in stop)

    def is_duplicate(self, question: str) -> bool:
        words = self._normalize(question)
        if len(words) < 3:
            return True
        for existing_words in self._words_sets:
            if not existing_words:
                continue
            intersection = len(words & existing_words)
            union = len(words | existing_words)
            if union > 0 and intersection / union >= self._threshold:
                return True
        return False

    def add(self, question: str):
        self._questions.append(question)
        self._words_sets.append(self._normalize(question))

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

CATEGORY_CROSS_DOC = "cross_document"
CATEGORY_NAVIGATION = "navigation"
CATEGORY_CONDITIONAL = "conditional"
CATEGORY_DISCIPLINE = "discipline"
CATEGORY_POORLY_FORMED = "poorly_formed"
CATEGORY_DIRECT = "direct"

CATEGORIES = [
    CATEGORY_CROSS_DOC,
    CATEGORY_NAVIGATION,
    CATEGORY_CONDITIONAL,
    CATEGORY_DISCIPLINE,
    CATEGORY_POORLY_FORMED,
    CATEGORY_DIRECT,
]

CATEGORY_PROMPTS = {
    CATEGORY_DIRECT: """Тебе показали фрагмент внутренней документации Тюменского государственного университета (ТюмГУ).

Сгенерируй ОДИН осмысленный вопрос в поддержку и краткий идеальный ответ.

{common_style}

Текст фрагмента:
{{chunk_text}}

Верни ТОЛЬКО JSON:
{{"question": "...", "ground_truth_answer": "..."}}""",

    CATEGORY_CROSS_DOC: """Тебе показали ДВА фрагмента из РАЗНЫХ документов Тюменского государственного университета (ТюмГУ).

Сгенерируй ОДИН вопрос, на который нельзя ответить только по одному из фрагментов — нужно соединить информацию из обоих.

{common_style}
- Вопрос должен требовать информацию из обоих фрагментов.

Фрагмент 1:
{{chunk_text_1}}

Фрагмент 2:
{{chunk_text_2}}

Верни ТОЛЬКО JSON:
{{"question": "...", "ground_truth_answer": "..."}}""",

    CATEGORY_NAVIGATION: """Тебе показали фрагмент документа Тюменского государственного университета (ТюмГУ).
Название института/подразделения: {{institute_name}}

Сгенерируй вопрос, в котором назван этот конкретный институт/подразделение.

{common_style}
- Вопрос должен содержать название института или его аббревиатуру.

Текст фрагмента:
{{chunk_text}}

Верни ТОЛЬКО JSON:
{{"question": "...", "ground_truth_answer": "..."}}""",

    CATEGORY_CONDITIONAL: """Тебе показали фрагмент документа Тюменского государственного университета (ТюмГУ).

Сгенерируй вопрос, содержащий 2+ УСЛОВИЯ (например: "бюджетник + хвосты", "заочник + академ", "платник + перевестись").

{common_style}
- Вопрос должен содержать минимум 2 конкретных условия/статуса.

Ключевые сущности из документа: {{entities}}

Текст фрагмента:
{{chunk_text}}

Верни ТОЛЬКО JSON:
{{"question": "...", "ground_truth_answer": "..."}}""",

    CATEGORY_DISCIPLINE: """Тебе показали фрагмент документа Тюменского государственного университета (ТюмГУ).

Сгенерируй вопрос, в котором названа конкретная дисциплина или специфический регламент/положение.

{common_style}
- В вопросе должна быть названа конкретная дисциплина или документ.

Название/сущность: {{entity_name}}

Текст фрагмента:
{{chunk_text}}

Верни ТОЛЬКО JSON:
{{"question": "...", "ground_truth_answer": "..."}}""",

    CATEGORY_POORLY_FORMED: """Тебе показали фрагмент документа Тюменского государственного университета (ТюмГУ).

Сгенерируй вопрос и ответ, а затем ИСПОРТИ вопрос:
- Добавь 1-3 опечатки (переставь буквы, пропусти букву)
- Убери знаки препинания
- Используй сокращения ("общага" вместо "общежитие", "стипуха" вместо "стипендия", "сесия" вместо "сессия")
- Можно написать 2-3 слова без контекста

{common_style}

Оригинальный (правильный) вопрос сохрани в поле "clean_question".

Текст фрагмента:
{{chunk_text}}

Верни ТОЛЬКО JSON:
{{"question": "... (испорченный)", "clean_question": "... (правильный)", "ground_truth_answer": "..."}}""",
}

TYPO_TEMPLATES = {
    "общежитие": "общага",
    "стипендия": "стипуха",
    "сессия": "сесия",
    "перевестись": "перевестся",
    "аттестат": "атестат",
    "зачётка": "зачотка",
    "пересдача": "пересдоча",
    "деканат": "диконат",
    "расписание": "росписание",
}

COMMON_STYLE = """ОБЯЗАТЕЛЬНЫЙ СТИЛЬ вопроса:
- Пиши как реальный студент в чат — небрежно, быстро, строчными
- Сокращения: тюмгу (не "Тюменский государственный университет"), шкн, фэи, соцгум, ипип, биофак, инзем, инхим, фти, инбио, ифк, егш, шпи, шен, уиот
- Английские термины по-русски: лмс (не LMS), яндекс почта (не Yandex.Mail), корпоративная почта, эл журнал
- Сленг: стипуха, сессия, зачётка, хвосты, пересдача, академ, бюджетник, платник, заочник, очник, общага, деканат, проректор, отработка, курсач, дипломная
- Можно без знаков препинания, строчными буквами
- Вопрос ОБЯЗАН напрямую опираться на факты из фрагмента"""


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
    def _generate(self, system: str, user: str, temperature: float = 0.7) -> str:
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

    def generate_direct(self, chunk: Dict) -> Optional[Dict]:
        prompt = CATEGORY_PROMPTS[CATEGORY_DIRECT].format(
            chunk_text=chunk["content"][:1500], common_style=COMMON_STYLE
        )
        content = self._generate(
            "Ты формируешь synthetic dataset для RAG-бенчмарков. "
            "Каждый вопрос должен быть привязан к конкретному фрагменту, "
            "звучать как живой вопрос студента ТюмГУ. "
            "Запрещено выдумывать факты.",
            prompt,
        )
        result = _parse_json(content)
        if "question" not in result:
            return None
        time.sleep(self.request_delay)
        return result

    def generate_cross_doc(self, chunk1: Dict, chunk2: Dict) -> Optional[Dict]:
        prompt = CATEGORY_PROMPTS[CATEGORY_CROSS_DOC].format(
            chunk_text_1=chunk1["content"][:800],
            chunk_text_2=chunk2["content"][:800],
            common_style=COMMON_STYLE,
        )
        content = self._generate(
            "Ты формируешь кросс-документные вопросы для RAG-бенчмарков. "
            "Вопрос должен требовать информацию из обоих фрагментов. "
            "Стиль: студент ТюмГУ пишет в чат поддержки.",
            prompt,
        )
        result = _parse_json(content)
        if "question" not in result:
            return None
        time.sleep(self.request_delay)
        return result

    def generate_navigation(self, chunk: Dict, institute: str) -> Optional[Dict]:
        prompt = CATEGORY_PROMPTS[CATEGORY_NAVIGATION].format(
            chunk_text=chunk["content"][:1500],
            institute_name=institute,
            common_style=COMMON_STYLE,
        )
        content = self._generate(
            "Ты формируешь навигационные вопросы для RAG-бенчмарков. "
            "В вопросе обязательно должно быть название конкретного института/подразделения. "
            "Стиль: студент ТюмГУ.",
            prompt,
        )
        result = _parse_json(content)
        if "question" not in result:
            return None
        time.sleep(self.request_delay)
        return result

    def generate_conditional(self, chunk: Dict, entities: List[str]) -> Optional[Dict]:
        prompt = CATEGORY_PROMPTS[CATEGORY_CONDITIONAL].format(
            chunk_text=chunk["content"][:1500],
            entities=", ".join(entities[:5]),
            common_style=COMMON_STYLE,
        )
        content = self._generate(
            "Ты формируешь условные/составные вопросы для RAG-бенчмарков. "
            "Вопрос должен содержать минимум 2 условия/статуса студента. "
            "Стиль: студент ТюмГУ.",
            prompt,
        )
        result = _parse_json(content)
        if "question" not in result:
            return None
        time.sleep(self.request_delay)
        return result

    def generate_discipline(self, chunk: Dict, entity_name: str) -> Optional[Dict]:
        prompt = CATEGORY_PROMPTS[CATEGORY_DISCIPLINE].format(
            chunk_text=chunk["content"][:1500],
            entity_name=entity_name,
            common_style=COMMON_STYLE,
        )
        content = self._generate(
            "Ты формируешь вопросы по конкретным дисциплинам для RAG-бенчмарков. "
            "В вопросе должно быть названо конкретное название. "
            "Стиль: студент ТюмГУ.",
            prompt,
        )
        result = _parse_json(content)
        if "question" not in result:
            return None
        time.sleep(self.request_delay)
        return result

    def generate_poorly_formed(self, chunk: Dict) -> Optional[Dict]:
        prompt = CATEGORY_PROMPTS[CATEGORY_POORLY_FORMED].format(
            chunk_text=chunk["content"][:1500], common_style=COMMON_STYLE
        )
        content = self._generate(
            "Ты формируешь плохо сформулированные вопросы для RAG-бенчмарков. "
            "Сначала создай нормальный вопрос, потом ИСПОРТЬ его: "
            "опечатки, нет знаков препинания, сокращения, сленг. "
            "Сохрани правильную версию в clean_question.",
            prompt,
            temperature=0.8,
        )
        result = _parse_json(content)
        if "question" not in result:
            return None
        time.sleep(self.request_delay)
        return result


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


def generate_dataset(
    db_data: DBData,
    generator: DatasetGenerator,
    target_counts: Dict[str, int],
) -> List[Dict]:
    dataset: List[Dict] = []
    errors: List[str] = []
    dedup = QuestionDedup(similarity_threshold=0.65)

    # Build chunk_id -> confluence_url mapping
    chunk_to_url: Dict[str, str] = {}
    for chunk in db_data.chunks:
        if "file_path" in chunk and "id" in chunk:
            chunk_to_url[chunk["id"]] = chunk["file_path"]

    chunk_usage: Dict[str, int] = defaultdict(int)
    MAX_CHUNK_USAGE = 3

    chunks = db_data.chunks
    random.shuffle(chunks)

    def _available(chunks_list: List[Dict]) -> List[Dict]:
        return [c for c in chunks_list if chunk_usage[c["id"]] < MAX_CHUNK_USAGE]

    # Category 1: Cross-document
    cross_target = target_counts.get(CATEGORY_CROSS_DOC, 50)
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
                    q = result["question"].strip()
                    if dedup.is_duplicate(q):
                        logger.debug("cross-doc дубликат (попытка %d): %s", attempt + 1, q[:60])
                        continue
                    item = _make_item(
                        question=q,
                        ground_truth_answer=result.get("ground_truth_answer", ""),
                        category=CATEGORY_CROSS_DOC,
                        chunk_ids=[c1["id"], c2["id"]],
                        doc_ids=[doc1, doc2],
                        chunk_texts=[c1["content"], c2["content"]],
                        chunk_to_url=chunk_to_url,
                    )
                    dataset.append(item)
                    dedup.add(q)
                    chunk_usage[c1["id"]] += 1
                    chunk_usage[c2["id"]] += 1
                    cross_generated += 1
                    logger.info("[%d/%d] cross-doc: %s...", cross_generated, cross_target, item["question"][:50])
                    break
            except Exception as e:
                errors.append(f"cross_doc: {e}")
                logger.warning("Ошибка cross_doc: %s", e)
                break
    logger.info("Кросс-документных: %d/%d", cross_generated, cross_target)

    # Category 2: Navigation
    nav_target = target_counts.get(CATEGORY_NAVIGATION, 30)
    logger.info("=== Категория 2: Навигационные (цель: %d) ===", nav_target)
    nav_generated = 0
    nav_chunks = list(chunks)
    random.shuffle(nav_chunks)
    for chunk in nav_chunks:
        if nav_generated >= nav_target:
            break
        if chunk_usage[chunk["id"]] >= MAX_CHUNK_USAGE:
            continue
        for attempt in range(3):
            institute = random.choice(INSTITUTES)
            try:
                result = generator.generate_navigation(chunk, institute)
                if result and "question" in result:
                    q = result["question"].strip()
                    if dedup.is_duplicate(q):
                        logger.debug("navigation дубликат (попытка %d): %s", attempt + 1, q[:60])
                        continue
                    doc_id = db_data.chunk_id_to_doc[chunk["id"]]
                    item = _make_item(
                        question=q,
                        ground_truth_answer=result.get("ground_truth_answer", ""),
                        category=CATEGORY_NAVIGATION,
                        chunk_ids=[chunk["id"]],
                        doc_ids=[doc_id],
                        chunk_texts=[chunk["content"]],
                        chunk_to_url=chunk_to_url,
                    )
                    dataset.append(item)
                    dedup.add(q)
                    chunk_usage[chunk["id"]] += 1
                    nav_generated += 1
                    logger.info("[%d/%d] navigation: %s...", nav_generated, nav_target, item["question"][:50])
                    break
            except Exception as e:
                errors.append(f"navigation: {e}")
                logger.warning("Ошибка navigation: %s", e)
                break
    logger.info("Навигационных: %d/%d", nav_generated, nav_target)

    # Category 3: Conditional
    cond_target = target_counts.get(CATEGORY_CONDITIONAL, 30)
    logger.info("=== Категория 3: Условные (цель: %d) ===", cond_target)
    cond_generated = 0
    disc_entities = db_data.get_discriminative_entities(min_docs=2, max_docs=40)
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
                    q = result["question"].strip()
                    if dedup.is_duplicate(q):
                        logger.debug("conditional дубликат (попытка %d): %s", attempt + 1, q[:60])
                        continue
                    item = _make_item(
                        question=q,
                        ground_truth_answer=result.get("ground_truth_answer", ""),
                        category=CATEGORY_CONDITIONAL,
                        chunk_ids=[chunk["id"]],
                        doc_ids=[doc_id],
                        chunk_texts=[chunk["content"]],
                        chunk_to_url=chunk_to_url,
                    )
                    dataset.append(item)
                    dedup.add(q)
                    chunk_usage[chunk["id"]] += 1
                    cond_generated += 1
                    logger.info("[%d/%d] conditional: %s...", cond_generated, cond_target, item["question"][:50])
                    break
            except Exception as e:
                errors.append(f"conditional: {e}")
                logger.warning("Ошибка conditional: %s", e)
                break
    logger.info("Условных: %d/%d", cond_generated, cond_target)

    # Category 4: Discipline
    disc_target = target_counts.get(CATEGORY_DISCIPLINE, 20)
    logger.info("=== Категория 4: По дисциплинам (цель: %d) ===", disc_target)
    disc_generated = 0
    discipline_entities = [
        e for e in disc_entities
        if any(
            kw in e.lower()
            for kw in [
                "алгебр", "физик", "программ", "математик", "химия",
                "биолог", "экономик", "философ", "истори", "право",
                "лингвист", "английск", "немецк", "читан",
                "регламент", "положение о", "правила", "порядок",
            ]
        )
    ]
    random.shuffle(discipline_entities)
    for entity in discipline_entities:
        if disc_generated >= disc_target:
            break
        entity_chunks = _available(db_data.get_chunks_with_entity(entity))
        if not entity_chunks:
            continue
        chunk = random.choice(entity_chunks)
        for attempt in range(3):
            try:
                result = generator.generate_discipline(chunk, entity)
                if result and "question" in result:
                    q = result["question"].strip()
                    if dedup.is_duplicate(q):
                        logger.debug("discipline дубликат (попытка %d): %s", attempt + 1, q[:60])
                        continue
                    item = _make_item(
                        question=q,
                        ground_truth_answer=result.get("ground_truth_answer", ""),
                        category=CATEGORY_DISCIPLINE,
                        chunk_ids=[chunk["id"]],
                        doc_ids=[chunk["doc_id"]],
                        chunk_texts=[chunk["content"]],
                        chunk_to_url=chunk_to_url,
                    )
                    dataset.append(item)
                    dedup.add(q)
                    chunk_usage[chunk["id"]] += 1
                    disc_generated += 1
                    logger.info("[%d/%d] discipline: %s...", disc_generated, disc_target, item["question"][:50])
                    break
            except Exception as e:
                errors.append(f"discipline: {e}")
                logger.warning("Ошибка discipline: %s", e)
                break
    logger.info("По дисциплинам: %d/%d", disc_generated, disc_target)

    # Category 5: Poorly formed
    poor_target = target_counts.get(CATEGORY_POORLY_FORMED, 20)
    logger.info("=== Категория 5: Плохо сформулированные (цель: %d) ===", poor_target)
    poor_generated = 0
    poor_chunks = list(chunks)
    random.shuffle(poor_chunks)
    for chunk in poor_chunks:
        if poor_generated >= poor_target:
            break
        if chunk_usage[chunk["id"]] >= MAX_CHUNK_USAGE:
            continue
        for attempt in range(3):
            try:
                result = generator.generate_poorly_formed(chunk)
                if result and "question" in result:
                    q = result["question"].strip()
                    clean = result.get("clean_question", "").strip()
                    check_text = clean if clean else q
                    if dedup.is_duplicate(check_text):
                        logger.debug("poorly_formed дубликат (попытка %d): %s", attempt + 1, check_text[:60])
                        continue
                    doc_id = db_data.chunk_id_to_doc[chunk["id"]]
                    item = _make_item(
                        question=q,
                        ground_truth_answer=result.get("ground_truth_answer", ""),
                        category=CATEGORY_POORLY_FORMED,
                        chunk_ids=[chunk["id"]],
                        doc_ids=[doc_id],
                        chunk_texts=[chunk["content"]],
                        clean_question=clean,
                        chunk_to_url=chunk_to_url,
                    )
                    dataset.append(item)
                    dedup.add(check_text)
                    chunk_usage[chunk["id"]] += 1
                    poor_generated += 1
                    logger.info("[%d/%d] poorly_formed: %s...", poor_generated, poor_target, item["question"][:50])
                    break
            except Exception as e:
                errors.append(f"poorly_formed: {e}")
                logger.warning("Ошибка poorly_formed: %s", e)
                break
    logger.info("Плохо сформулированных: %d/%d", poor_generated, poor_target)

    # Category 6: Direct (control)
    direct_target = target_counts.get(CATEGORY_DIRECT, 100)
    logger.info("=== Категория 6: Прямые контрольные (цель: %d) ===", direct_target)
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
                    q = result["question"].strip()
                    if dedup.is_duplicate(q):
                        logger.debug("direct дубликат (попытка %d): %s", attempt + 1, q[:60])
                        continue
                    doc_id = db_data.chunk_id_to_doc[chunk["id"]]
                    item = _make_item(
                        question=q,
                        ground_truth_answer=result.get("ground_truth_answer", ""),
                        category=CATEGORY_DIRECT,
                        chunk_ids=[chunk["id"]],
                        doc_ids=[doc_id],
                        chunk_texts=[chunk["content"]],
                        chunk_to_url=chunk_to_url,
                    )
                    dataset.append(item)
                    dedup.add(q)
                    chunk_usage[chunk["id"]] += 1
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
        CATEGORY_CROSS_DOC: 50,
        CATEGORY_NAVIGATION: 30,
        CATEGORY_CONDITIONAL: 30,
        CATEGORY_DISCIPLINE: 20,
        CATEGORY_POORLY_FORMED: 20,
        CATEGORY_DIRECT: 100,
    }

    if args.limit:
        scale = args.limit / sum(target_counts.values())
        target_counts = {k: max(1, int(v * scale)) for k, v in target_counts.items()}

    dataset = generate_dataset(db_data, generator, target_counts)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or f"benchmarks/data/dataset/dataset_hard_{timestamp}.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"\n=== Датасет сохранён: {output_path} ===")
    print(f"Всего вопросов: {len(dataset)}")
    by_cat = defaultdict(int)
    for item in dataset:
        by_cat[item["category"]] += 1
    for cat, cnt in sorted(by_cat.items()):
        print(f"  {cat}: {cnt}")


if __name__ == "__main__":
    main()
