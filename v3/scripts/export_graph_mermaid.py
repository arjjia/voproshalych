"""Генерация Mermaid-диаграммы по текущему графу LangGraph.

Запуск (из корня v3):
    uv run --package agent-service python scripts/export_graph_mermaid.py

или (из директории agent-service):
    cd agent-service && uv run python ../scripts/export_graph_mermaid.py

Результат — файл docs/AGENT_GRAPH.mmd в корне v3.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
V3_ROOT = os.path.dirname(SCRIPT_DIR)
AGENT_SERVICE_DIR = os.path.join(V3_ROOT, "agent-service")

sys.path.insert(0, AGENT_SERVICE_DIR)

from src.graph import build_graph


def main() -> None:
    graph = build_graph()
    mermaid_text = graph.get_graph().draw_mermaid()

    output_dir = os.path.join(V3_ROOT, "docs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "AGENT_GRAPH.mmd")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(mermaid_text)

    print(f"✓ Граф экспортирован: {output_path}")
    print(f"  Узлов: {len(graph.get_graph().nodes)}")
    print(f"  Рёбер: {len(graph.get_graph().edges)}")
    print()
    print("--- Mermaid ---")
    print(mermaid_text)


if __name__ == "__main__":
    main()
