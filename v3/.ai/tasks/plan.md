# Plan

## Статус: Step 6/7 ✅ (LobeChat fork — все Docker образы собраны)

### Завершено

**kb-service:**
- `src/kb/embedding.py` — локальная deepvk/USER-bge-m3 (не mistral-embed)
- `src/kb/parsers/utmn_news.py` — новый парсер utmn.ru/news/stories и /events
- `src/kb/tools.py` — crawl_utmn_news, crawl_utmn_events
- `Dockerfile` — переписан (python:3.12-slim-bookworm, без tesseract для MVP)
- Docker image: **voproshalych-v3-kb-service** (11.5GB, включает torch + deepvk/USER-bge-m3)

**mcp-news улучшен + mcp-fetch создан (Step 4):**
- `src/public/news_server.py` — _extract_items, _fetch_page, _fallback_to_rss
- `src/public/fetch_server.py` — fetch_url (fetch_url, очистка HTML)
- `src/public/server.py` — добавлен fetch dispatch
- docker-compose: mcp-fetch (порт 9015)
- agent-service: mcp_fetch_url в config, react.py, main.py (/mcp/tools)
- Docker images: **voproshalych-v3-mcp-{news,contacts,library,sveden,kb,fetch}**

**agent-service — X-User-Id + agent_traces (Step 5):**
- `src/middleware.py` — UserIdentityMiddleware (X-User-Id, X-User-Role, X-Request-Id)
- `src/trace_logger.py` — JSON Lines trace logger (по request_id)
- `src/models.py` — Profile + request_id в AgentState
- Все 6 узлов графа пишут трассировки
- GET /trace — получение трассировок
- Docker image: **voproshalych-v3-agent-service**

**LobeChat fork — auth + branding + consent (Step 6/7):**
- `custom.js` — #00aeef brand color, скрытие лишних UI элементов
- `consent.html` — экран согласия на обработку данных
- `assets/` — pixel cat логотип (logo.svg, logo-icon.svg), иконки обновлены
- `Dockerfile` — COPY custom.js + consent.html в public/
- docker-compose: AUTH_SECRET, DATABASE_URL, KEY_VAULTS_SECRET, CUSTOM_JS_URL
- Docker image: **voproshalych-v3-lobe-chat**

### Тесты (63)
| Модуль | Тесты | Статус |
|---|---|---|
| kb-service | 17 | ✅ (в т.ч. в Docker контейнере) |
| mcp-servers | 17 | ✅ |
| agent-service | 29 | ✅ |

### Docker образы (10)
| Образ | Размер | Статус |
|---|---|---|
| voproshalych-v3-kb-service | 11.5 GB | ✅ |
| voproshalych-v3-lobe-chat | 1.18 GB | ✅ |
| voproshalych-v3-postgres | 648 MB | ✅ |
| voproshalych-v3-agent-service | 481 MB | ✅ |
| voproshalych-v3-mcp-* (6шт) | 444 MB each | ✅ |

### Как запустить
```bash
cd Submodules/voproshalych_v2/v3
docker compose up -d
# LobeChat: http://localhost:3210
# Agent API: http://localhost:8001
# KB API: http://localhost:8005
```
