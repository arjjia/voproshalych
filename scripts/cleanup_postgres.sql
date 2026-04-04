-- 1. Удалить лишние схемы из Docker-образа
DROP SCHEMA IF EXISTS sample_graph CASCADE;
DROP SCHEMA IF EXISTS tiger CASCADE;
DROP SCHEMA IF EXISTS tiger_data CASCADE;
DROP SCHEMA IF EXISTS topology CASCADE;

-- 2. Очистить таблицы LightRAG (мусорные данные)
TRUNCATE TABLE lightrag_vdb_entity_deepvk_user_bge_m3_1024d CASCADE;
TRUNCATE TABLE lightrag_vdb_relation_deepvk_user_bge_m3_1024d CASCADE;
TRUNCATE TABLE lightrag_vdb_chunks_deepvk_user_bge_m3_1024d CASCADE;
TRUNCATE TABLE lightrag_full_entities CASCADE;
TRUNCATE TABLE lightrag_full_relations CASCADE;
TRUNCATE TABLE lightrag_entity_chunks CASCADE;
TRUNCATE TABLE lightrag_relation_chunks CASCADE;
TRUNCATE TABLE lightrag_doc_chunks CASCADE;
TRUNCATE TABLE lightrag_doc_full CASCADE;
TRUNCATE TABLE lightrag_doc_status CASCADE;
TRUNCATE TABLE lightrag_llm_cache CASCADE;
TRUNCATE TABLE lightrag_index_versions CASCADE;
TRUNCATE TABLE lightrag_doc_registry CASCADE;

-- 3. Удалить демо-граф из AGE
SELECT ag_catalog.drop_graph('sample_graph', true);

-- 4. Создать новый граф для LightRAG
SELECT ag_catalog.create_graph('voproshalych_graph');
