"""Тесты модуля эмбеддингов (локальная deepvk/USER-bge-m3).

Реальная модель НЕ загружается (это ~2 ГБ): мы подменяем
SentenceTransformer фейком через monkeypatch и проверяем логику singleton,
нормализацию и async-обёртки.
"""

import asyncio

import kb.embedding as emb


class _FakeModel:
    """Фейк SentenceTransformer: детерминированный вектор из текста."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._dim = 8

    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        import numpy as np

        single = isinstance(texts, str)
        seq = [texts] if single else list(texts)
        if not seq:
            return np.empty((0, self._dim), dtype="float32")
        vecs = np.array(
            [[float(len(t) % 7) for _ in range(self._dim)] for t in seq],
            dtype="float32",
        )
        if normalize_embeddings:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            vecs = vecs / norms
        return vecs[0] if single else vecs

    def get_sentence_embedding_dimension(self) -> int:
        return self._dim


def test_get_model_is_singleton(monkeypatch):
    monkeypatch.setattr(emb, "_model", None)
    created = []

    def factory(name):
        m = _FakeModel(name)
        created.append(m)
        return m

    monkeypatch.setattr(emb, "SentenceTransformer", factory)

    m1 = emb._get_model()
    m2 = emb._get_model()
    assert m1 is m2
    assert len(created) == 1  #второй вызов не создаёт новую модель


def test_get_embedding_returns_float_list(monkeypatch):
    monkeypatch.setattr(emb, "_model", None)
    monkeypatch.setattr(emb, "SentenceTransformer", lambda name: _FakeModel(name))

    vec = asyncio.run(emb.get_embedding("привет"))
    assert isinstance(vec, list)
    assert all(isinstance(x, float) for x in vec)
    assert len(vec) == 8


def test_get_embeddings_batch_length_matches(monkeypatch):
    monkeypatch.setattr(emb, "_model", None)
    monkeypatch.setattr(emb, "SentenceTransformer", lambda name: _FakeModel(name))

    texts = ["один", "два текста", "три"]
    res = asyncio.run(emb.get_embeddings_batch(texts))
    assert isinstance(res, list)
    assert len(res) == 3
    assert all(isinstance(v, list) for v in res)


def test_get_embeddings_batch_empty(monkeypatch):
    monkeypatch.setattr(emb, "_model", None)
    monkeypatch.setattr(emb, "SentenceTransformer", lambda name: _FakeModel(name))

    res = asyncio.run(emb.get_embeddings_batch([]))
    assert res == []


def test_embedding_model_config_default():
    from kb.config import settings

    # .env в тестовом контейнере должен выставлять deepvk/USER-bge-m3
    assert settings.embedding_model == "deepvk/USER-bge-m3"
