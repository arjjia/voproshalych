# Модельный пул Voproshalych v3

> Дата: 2026-07-16
> Все модели доступны через единый LiteLLM-прокси на порту 4000

---

## Структура пула

Пул состоит из трёх групп моделей, упорядоченных по приоритету:

### 1. OpenCode ZEN — Free (бесплатные)

Провайдер: `https://opencode.ai/zen/v1`  
API-ключ: `ZEN_API_KEY` (в .env)

| ID в пуле | Реальная модель | Разработчик | Параметры | Контекст |
|---|---|---|---|---|
| `nemotron-ultra-free` | Nemotron 3 Ultra | Nvidia | **550B** | 128K |
| `deepseek-v4-flash-free` | DeepSeek V4 Flash | DeepSeek | ? | 128K |
| `hy3-free` | HY3 | Tencent | ? | 128K |
| `mimo-free` | MiMo v2.5 | Xiaomi | ? | 128K |
| `code-free` | North Mini Code | North AI | ? | 128K |
| `pickle-free` | Big Pickle | OpenCode | ? | 128K |

> **Примечание:** Все модели в группе — полностью бесплатные (ZEN free).
> `glm-5.2` (Zhipu GLM 5.2) **удалён из пула** — требует платного метода оплаты на ZEN (401 AuthError / "No payment method").

### 2. OpenRouter — Free (бесплатные)

Провайдер: OpenRouter  
API-ключ: `OPENROUTER_API_KEY` (в .env)

| ID в пуле | Реальная модель | Разработчик | Параметры | Контекст |
|---|---|---|---|---|
| `nemotron-super-or` | Nemotron 3 Super 120B | Nvidia | 120B | 1M |
| `gpt-oss-or` | GPT-OSS 120B | OpenAI | 120B | 128K |
| `llama-70b-or` | Llama 3.3 70B Instruct | Meta | 70B | 128K |
| `qwen-coder-or` | Qwen3 Coder | Alibaba (Qwen) | 33B | 1M |
| `gemma-31b-or` | Gemma 4 31B IT | Google | 31B | 128K |

### 3. Mistral API — Paid (платные, дешёвые)

Провайдер: `https://api.mistral.ai`  
API-ключ: `MISTRAL_API_KEY` (в .env)

| ID в пуле | Реальная модель | Параметры | Цена (I/O за 1M токенов) |
|---|---|---|---|
| `mistral-nemo` | open-mistral-nemo | 12B | $0.16 / $0.16 |
| `mistral-classifier` | open-mistral-nemo (то же) | 12B | $0.16 / $0.16 |

> **Важно:** `mistral-classifier` и `mistral-nemo` — одна и та же модель `open-mistral-nemo`.
> В конфиге LiteLLM у `mistral-classifier` жёстко проставлены `temperature: 0.1`, `max_tokens: 512`.
> Для v3 решили отказаться от выделенной «классификационной» модели — и для классификации, и для
> генерации используется первая доступная модель из приоритетного списка.

---

## Приоритет моделей (от наиболее приоритетной к наименее)

```
  1. nemotron-ultra-free   — Nvidia Nemotron 3 Ultra 550B [ZEN free]       ← самый мощный
  2. nemotron-super-or     — Nvidia Nemotron 3 Super 120B (1M ctx) [OR free]
  3. gpt-oss-or            — OpenAI GPT-OSS 120B [OR free]
  4. deepseek-v4-flash-free — DeepSeek V4 Flash [ZEN free]                 ← доверие к бренду
  5. llama-70b-or          — Llama 3.3 70B Instruct [OR free]
  6. qwen-coder-or         — Qwen3 Coder (1M ctx) [OR free]
  7. gemma-31b-or          — Gemma 4 31B IT [OR free]
  8. hy3-free              — Tencent HY3 [ZEN free]                        ← неизвестное качество
  9. mimo-free             — Xiaomi MiMo v2.5 [ZEN free]                   ← неизвестное качество
 10. mistral-nemo          — Mistral Nemo 12B [Mistral paid]
 11. code-free             — North Mini Code [ZEN free]                    ← экспериментальная
 12. pickle-free           — Big Pickle [ZEN free]                         ← экспериментальная
 ```

Приоритет построен по принципу:
- **Мощь / число параметров** — главный критерий: чем больше параметров, тем выше приоритет
- **Бесплатные** — выше платных (при прочих равных)
- **Проверенные модели** — выше экспериментальных (`code-free`, `pickle-free` — в самом низу)
- **Mistral Nemo (12B)** — современная модель 2025 года, объективно сильнее экспериментальных `code-free` и `pickle-free`

---

## Модель для эмбеддингов

| Роль | Модель | Размерность | Где запускается |
|---|---|---|---|---|
| Эмбеддинги | `deepvk/USER-bge-m3` (локально, SentenceTransformer) | 1024 | kb-service (in-process) |

---

## Fallback-цепи (LiteLLM config.yaml)

Если первая модель падает, LiteLLM автоматически переключается по цепочке:

```
nemotron-ultra-free      → deepseek-v4-flash-free, nemotron-super-or, gpt-oss-or
nemotron-super-or        → nemotron-ultra-free, gpt-oss-or, deepseek-v4-flash-free
gpt-oss-or               → nemotron-super-or, deepseek-v4-flash-free, llama-70b-or
deepseek-v4-flash-free   → nemotron-ultra-free, hy3-free, llama-70b-or
llama-70b-or             → deepseek-v4-flash-free, nemotron-super-or, gpt-oss-or
qwen-coder-or            → deepseek-v4-flash-free, nemotron-ultra-free, gemma-31b-or
gemma-31b-or             → deepseek-v4-flash-free, hy3-free, mistral-nemo
hy3-free                 → deepseek-v4-flash-free, nemotron-ultra-free, llama-70b-or
mimo-free                → deepseek-v4-flash-free, hy3-free, gemma-31b-or
mistral-nemo             → deepseek-v4-flash-free, nemotron-ultra-free
code-free                → qwen-coder-or, deepseek-v4-flash-free, nemotron-ultra-free
pickle-free              → deepseek-v4-flash-free, nemotron-ultra-free
```

---

## Конфигурация в коде

`model_priority` задаётся в `Settings` каждого сервиса:

```python
model_priority: list[str] = [
    "nemotron-ultra-free",
    "nemotron-super-or",
    "gpt-oss-or",
    "deepseek-v4-flash-free",
    "llama-70b-or",
    "qwen-coder-or",
    "gemma-31b-or",
    "hy3-free",
    "mimo-free",
    "mistral-nemo",
    "code-free",
    "pickle-free",
]
```

При каждом LLM-вызове используется `model_priority[0]` (первая доступная).  
LiteLLM fallback-цепи обрабатывают отказ вышестоящих моделей автоматически.
