# PostgreSQL with pgvector and Apache AGE

Кастомный Docker образ PostgreSQL 17 с предустановленными расширениями pgvector и Apache AGE.

## Версии

| Компонент | Версия |
|-----------|--------|
| PostgreSQL | 17.9 |
| pgvector | 0.8.1 |
| Apache AGE | 1.6.0 |

## Возможности

- **pgvector** — векторная similarity search для RAG и semantic search
- **Apache AGE** — graph database с поддержкой openCypher запросов
- **ARM64** — работает на Mac Apple Silicon
- **Чистая БД** — без демо-данных (tiger, topology, sample_graph)

## Использование

### Запуск через docker-compose

```bash
cd Submodules/voproshalych_v2
docker compose up -d postgres
```

### Подключение к БД

```bash
# Через docker-compose exec
docker compose exec postgres psql -U voproshalych -d voproshalych

# Напрямую (порт 5433)
psql -h localhost -p 5433 -U voproshalych -d voproshalych
```

### Проверка установленных расширений

```sql
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'age');
```

Результат:
```
 extname | extversion 
---------+------------
 vector  | 0.8.1
 age     | 1.6.0
```

## Примеры использования

### pgvector (векторный поиск)

```sql
-- Создание таблицы с векторами
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding vector(1536)
);

-- Вставка данных
INSERT INTO documents (content, embedding)
VALUES ('Hello world', '[0.1, 0.2, 0.3]');

-- Поиск похожих документов
SELECT * FROM documents
ORDER BY embedding <=> '[0.1, 0.2, 0.3]'
LIMIT 5;
```

### Apache AGE (graph queries)

```sql
-- Включение расширения (обычно уже включено)
CREATE EXTENSION age;

-- Создание графа
SELECT create_graph('my_graph');

-- Создание узлов и связей через Cypher
SELECT * FROM cypher('my_graph', $$
    CREATE (p:Person {name: 'Alice'}),
           (b:Book {title: 'Graph Databases'}),
           (p)-[:READS]->(b)
$$) AS (n agtype);

-- Запрос к графу
SELECT * FROM cypher('my_graph', $$
    MATCH (p:Person)-[:READS]->(b:Book)
    RETURN p.name, b.title
$$) AS (name agtype, title agtype);
```

## Переменные окружения

| Переменная | Значение по умолчанию |
|------------|----------------------|
| POSTGRES_DB | voproshalych |
| POSTGRES_USER | voproshalych |
| POSTGRES_PASSWORD | voproshalych |
| PGDATA | /var/lib/postgresql/data/pgdata |

## Структура файлов

```
db/postgres/
├── Dockerfile              # Сборка образа
└── init-extensions.sql     # Автоматическое создание расширений
```

## Пересборка образа

```bash
cd Submodules/voproshalych_v2
docker compose build postgres
docker compose up -d postgres
```

## Удаление и пересоздание БД

Для полного сброса данных:

```bash
docker compose down -v  # Удаляет volume с данными
docker compose up -d    # Создает чистую БД
```