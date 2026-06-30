import json
import os

import torch
from torch.utils.data import DataLoader
from sentence_transformers import SentenceTransformer, InputExample, losses

INPUT_FILE = "qa_dataset_semantic_clean.jsonl"
MODEL_NAME = "deepvk/USER-bge-m3"
OUTPUT_DIR = "finetuned_bge_m3_v1"

BATCH_SIZE = 8
NUM_EPOCHS = 3
WARMUP_RATIO = 0.1


def load_dataset(file_path: str) -> list[InputExample]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл датасета не найден: {file_path}")

    examples = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            examples.append(InputExample(texts=[data["anchor"], data["positive"]]))
            
    return examples


def run_training():
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    print(f"Загрузка обучающей выборки из {INPUT_FILE}...")
    train_examples = load_dataset(INPUT_FILE)
    print(f"Размер выборки: {len(train_examples)} пар.")

    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=BATCH_SIZE)

    print(f"Инициализация SentenceTransformer ({MODEL_NAME})...")
    model = SentenceTransformer(MODEL_NAME)
    train_loss = losses.MultipleNegativesRankingLoss(model=model)

    warmup_steps = int(len(train_dataloader) * NUM_EPOCHS * WARMUP_RATIO)

    print(f"Старт обучения (эпох: {NUM_EPOCHS}, размер батча: {BATCH_SIZE})...")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=NUM_EPOCHS,
        warmup_steps=warmup_steps,
        output_path=OUTPUT_DIR,
        show_progress_bar=True,
        save_best_model=True
    )
    
    print(f"Обучение завершено. Веса сохранены в {OUTPUT_DIR}/")


if __name__ == "__main__":
    run_training()
