import json
import os

import torch
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, util

load_dotenv()

INPUT_FILE = "qa_dataset.jsonl"
OUTPUT_FILE = "qa_dataset_semantic_clean.jsonl"
MODEL_NAME = "deepvk/USER-bge-m3"
THRESHOLD = 0.85

def run_deduplication():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Инициализация SentenceTransformer ({MODEL_NAME}) на {device}...")
    model = SentenceTransformer(MODEL_NAME, device=device)
    
    records = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    if not records:
        print("Ошибка: входной датасет пуст.")
        return

    print(f"Загружено записей: {len(records)}")
    questions = [rec["anchor"] for rec in records]
    
    print("Вычисление эмбеддингов...")
    embeddings = model.encode(questions, convert_to_tensor=True, show_progress_bar=True)
    
    print("Поиск дубликатов...")
    cosine_scores = util.cos_sim(embeddings, embeddings)
    
    keep_indices = []
    dropped_count = 0
    
    for i in range(len(records)):
        is_duplicate = False
        
        for j in keep_indices:
            if cosine_scores[i][j].item() > THRESHOLD:
                is_duplicate = True
                break
        
        if not is_duplicate:
            keep_indices.append(i)
        else:
            dropped_count += 1
            
    print("Сохранение результатов...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_f:
        for idx in keep_indices:
            out_f.write(json.dumps(records[idx], ensure_ascii=False) + '\n')
            
    print(f"Дедупликация завершена. Уникальных пар: {len(keep_indices)} (удалено: {dropped_count})")

if __name__ == "__main__":
    run_deduplication()
