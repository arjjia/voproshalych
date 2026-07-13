from src.models import AgentState, Profile, Intent, Complexity


class TestProfile:
    def test_defaults(self):
        p = Profile()
        assert p.user_id == "anonymous"
        assert p.role == "guest"

    def test_custom_values(self):
        p = Profile(user_id="user-1", role="student")
        assert p.user_id == "user-1"
        assert p.role == "student"


class TestAgentState:
    def test_default_profile(self):
        state = AgentState(messages=[])
        assert state.profile.user_id == "anonymous"
        assert state.profile.role == "guest"
        assert state.request_id == ""

    def test_custom_profile(self):
        profile = Profile(user_id="user-1", role="admin")
        state = AgentState(messages=[], profile=profile, request_id="req-123")
        assert state.profile.user_id == "user-1"
        assert state.request_id == "req-123"

    def test_existing_fields_unchanged(self):
        state = AgentState(
            messages=[{"role": "user", "content": "hi"}],
            intent=Intent.KB_QA,
            complexity=Complexity.SIMPLE,
        )
        assert state.intent == Intent.KB_QA
        assert state.complexity == Complexity.SIMPLE
        assert state.final_answer is None
