# Модельный пул Voproshalych v3

> Дата: 2026-07-14
> Все модели доступны через единый LiteLLM-прокси на порту 4000

---

## Структура пула

Пул состоит из трёх групп моделей, упорядоченных по приоритету использования:

### 1. OpenCode ZEN — Free (бесплатные)

Провайдер: `https://opencode.ai/zen/v1`  
API-ключ: `ZEN_API_KEY` (в .env)

| ID в пуле | Реальная модель | Разработчик | Контекст | Примечание |
|---|---|---|---|---|
| `deepseek-v4-flash-free` | DeepSeek V4 Flash | DeepSeek | 128K | Быстрый универсал, ≈ GPT-4o mini |
| `nemotron-ultra-free` | Nemotron 3 Ultra | Nvidia | 128K | 550B параметров, сильный reasoning |
| `hy3-free` | HY3 | Tencent | 128K | Анализ, многоязычность |
| `mimo-free` | MiMo v2.5 | Xiaomi | 128K | Общего назначения |
| `code-free` | North Mini Code | North AI | 128K | Специализация: код |
| `pickle-free` | Big Pickle | OpenCode | 128K | Экспериментальная |
| `glm-5.2` | GLM 5.2 | Zhipu AI | 128K | **Условно-бесплатный** (дешёвый) |

### 2. OpenRouter — Free (бесплатные)

Провайдер: OpenRouter  
API-ключ: `OPENROUTER_API_KEY` (в .env)

| ID в пуле | Реальная модель | Разработчик | Параметры | Контекст |
|---|---|---|---|---|
| `nemotron-super-or` | Nemotron 3 Super 120B | Nvidia | 120B | 1M |
| `llama-70b-or` | Llama 3.3 70B Instruct | Meta | 70B | 128K |
| `gpt-oss-or` | GPT-OSS 120B | OpenAI | 120B | 128K |
| `qwen-coder-or` | Qwen3 Coder | Alibaba (Qwen) | 33B | 1M |
| `gemma-31b-or` | Gemma 4 31B IT | Google | 31B | 128K |

### 3. Mistral API — Paid (платные, дешёвые)

Провайдер: `https://api.mistral.ai`  
API-ключ: `MISTRAL_API_KEY` (в .env)

| ID в пуле | Реальная модель | Параметры | Цена (I/O за 1M токенов) |
|---|---|---|---|
| `mistral-nemo` | open-mistral-nemo | 12B | $0.16 / $0.16 |
| `mistral-classifier` | open-mistral-nemo (то же) | 12B | $0.16 / $0.16 |
| `mistral-embed` | mistral-embed | 1024d | $0.04 / $0.04 |

> **Важно:** `mistral-classifier` и `mistral-nemo` — одна и та же модель `open-mistral-nemo`.
> В конфиге LiteLLM у `mistral-classifier` жёстко проставлены `temperature: 0.1`, `max_tokens: 512`.
> Для v3 решили отказаться от выделенной «классификационной» модели — и для классификации, и для
> генерации используется первая доступная модель из приоритетного списка.

---

## Приоритет моделей (от наиболее приоритетной к наименее)

```
1. nemotron-super-or     — Nvidia Nemotron 3 Super 120B (1M ctx) [OpenRouter free]
2. nemotron-ultra-free   — Nvidia Nemotron 3 Ultra 550B [ZEN free]
3. gpt-oss-or            — OpenAI GPT-OSS 120B [OpenRouter free]
4. deepseek-v4-flash-free — DeepSeek V4 Flash [ZEN free]
5. llama-70b-or          — Llama 3.3 70B Instruct [OpenRouter free]
6. qwen-coder-or         — Qwen3 Coder (1M ctx) [OpenRouter free]
7. gemma-31b-or          — Gemma 4 31B IT [OpenRouter free]
8. hy3-free              — Tencent HY3 [ZEN free]
9. mimo-free             — Xiaomi MiMo v2.5 [ZEN free]
10. code-free            — North Mini Code [ZEN free]
11. pickle-free          — Big Pickle [ZEN free]
12. glm-5.2              — Zhipu GLM 5.2 [ZEN paid cheap]
13. mistral-nemo         — Mistral Nemo 12B [Mistral paid cheap]
```

Приоритет построен по принципу:
- **Reasoning/мощь** (большие модели с сильным reasoning) — выше
- **Бесплатные** — выше платных
- **Специализированные** (code-free, pickle-free) — ниже универсальных

---

## Модель для эмбеддингов

| Роль | Модель | Размерность | Где запускается |
|---|---|---|---|
| Эмбеддинги БЗ | `deepvk/USER-bge-m3` (локально, SentenceTransformer) | 1024 | kb-service (in-process) |
| Эмбеддинги через API | `mistral-embed` (через LiteLLM → Mistral API) | 1024 | agent-service (прокси) |

---

## Fallback-цепи (LiteLLM config.yaml)

Если первая модель падает, LiteLLM автоматически переключается по цепочке:

```
deepseek-v4-flash-free      → nemotron-ultra-free, hy3-free, llama-70b-or
nemotron-ultra-free         → deepseek-v4-flash-free, nemotron-super-or, gpt-oss-or
hy3-free                    → deepseek-v4-flash-free, nemotron-ultra-free, llama-70b-or
mimo-free                   → deepseek-v4-flash-free, hy3-free, gemma-31b-or
code-free                   → qwen-coder-or, deepseek-v4-flash-free, nemotron-ultra-free
pickle-free                 → deepseek-v4-flash-free, nemotron-ultra-free
glm-5.2                     → deepseek-v4-flash-free, mistral-nemo, nemotron-ultra-free
mistral-nemo                → deepseek-v4-flash-free, glm-5.2, nemotron-ultra-free
```

---

## Конфигурация в коде

`model_priority` задаётся в `Settings` каждого сервиса:

```python
model_priority: list[str] = [
    "nemotron-super-or",
    "nemotron-ultra-free",
    "gpt-oss-or",
    "deepseek-v4-flash-free",
    "llama-70b-or",
    "qwen-coder-or",
    "gemma-31b-or",
    "hy3-free",
    "mimo-free",
    "code-free",
    "pickle-free",
    "glm-5.2",
    "mistral-nemo",
]
```

При каждом LLM-вызове используется `model_priority[0]` (первая доступная).  
LiteLLM fallback-цепи обрабатывают отказ вышестоящих моделей автоматически.
