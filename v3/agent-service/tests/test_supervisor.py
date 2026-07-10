"""Тесты supervisor-классификатора."""

import pytest

from src.models import AgentState, Intent, Complexity


class TestSupervisorRouter:
    """Тесты маршрутизации на основе интента."""

    @pytest.mark.parametrize(
        "intent,expected_node",
        [
            (Intent.KB_QA, "kb_workflow"),
            (Intent.META, "meta"),
            (Intent.TOOL_REQUIRED, "react"),
            (Intent.CLARIFY, "clarify"),
        ],
    )
    def test_router_routes_correctly(self, intent: Intent, expected_node: str):
        """Проверяет, что роутер направляет в правильный узел."""
        from src.graph import router

        state = AgentState(messages=[], intent=intent)
        result = router(state)
        assert result == expected_node

    def test_router_off_topic_goes_to_end(self):
        """Off-topic запросы идут в END."""
        from src.graph import router

        state = AgentState(messages=[], intent=Intent.OFF_TOPIC)
        result = router(state)
        assert result == "end"

    def test_router_none_intent_goes_to_end(self):
        """Если интент не определён — END."""
        from src.graph import router

        state = AgentState(messages=[], intent=None)
        result = router(state)
        assert result == "end"


class TestAgentState:
    """Тесты состояния агента."""

    def test_init(self):
        state = AgentState(messages=[{"role": "user", "content": "привет"}])
        assert state.messages[0]["content"] == "привет"
        assert state.intent is None
        assert state.final_answer is None

    def test_intent_assignment(self):
        state = AgentState(messages=[])
        state.intent = Intent.KB_QA
        state.complexity = Complexity.SIMPLE
        assert state.intent == Intent.KB_QA
        assert state.complexity == Complexity.SIMPLE

    def test_answer_assignment(self):
        state = AgentState(messages=[])
        state.final_answer = "Тестовый ответ"
        state.sources = [{"title": "Тест", "url": "https://example.com"}]
        assert state.final_answer == "Тестовый ответ"
        assert len(state.sources) == 1


class TestGraphBuild:
    """Тесты сборки графа."""

    def test_build_graph_returns_compiled_graph(self):
        from src.graph import build_graph

        g = build_graph()
        assert g is not None

    def test_graph_has_correct_nodes(self):
        from src.graph import build_graph

        g = build_graph()
        nodes = {name for name, _ in g.nodes.items()}
        required = {"clarify", "kb_workflow", "meta", "react", "supervisor"}
        assert required.issubset(nodes), f"Missing nodes: {required - nodes}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
