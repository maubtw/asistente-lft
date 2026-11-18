from pathlib import Path

from eval.rewrite_cache import CachedRewriter, cache_key, load_cache
from rag.config import Settings
from rag.query_rewrite import build_rewrite_messages

SETTINGS = Settings(_env_file=None, use_query_rewrite=True)


def test_cache_avoids_second_call(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    def fake_llm(settings):
        def complete(messages):
            calls.append(messages[-1]["content"])
            return "rescisión sin causa justificada"

        return complete

    monkeypatch.setattr("eval.rewrite_cache.openai_rewriter", fake_llm)
    path = tmp_path / "rewrites.json"
    rewriter = CachedRewriter(SETTINGS, path)
    messages = build_rewrite_messages("Me corrieron")
    assert rewriter(messages) == "rescisión sin causa justificada"
    assert rewriter(messages) == "rescisión sin causa justificada"
    assert calls == ["Me corrieron"]
    assert (rewriter.hits, rewriter.calls) == (1, 1)
    # persiste en disco: otra instancia no llama al LLM
    assert CachedRewriter(SETTINGS, path)(messages) == "rescisión sin causa justificada"
    assert len(calls) == 1
    assert cache_key("Me corrieron", SETTINGS) in load_cache(path)


def test_key_changes_with_model() -> None:
    other = Settings(_env_file=None, rewrite_model="gpt-4.1-mini")
    assert cache_key("x", SETTINGS) != cache_key("x", other)
