"""Prueba de humo de la demo (sin navegador ni API): la página carga y es usable."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parent.parent / "app" / "streamlit_app.py")


def _run(monkeypatch) -> AppTest:
    monkeypatch.setenv("LFT_API_URL", "http://127.0.0.1:9")  # puerto cerrado: API caída
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    return app


def test_page_has_title_legal_notice_and_examples(monkeypatch) -> None:
    app = _run(monkeypatch)
    assert not app.exception
    assert app.title[0].value == "⚖️ Asistente LFT"
    assert any("No sustituye asesoría legal" in w.value for w in app.warning)
    examples = [b for b in app.button if b.key and b.key.startswith("example_")]
    assert len(examples) == 4


def test_shows_clear_error_when_api_is_down(monkeypatch) -> None:
    app = _run(monkeypatch)
    assert any("API no disponible" in e.value for e in app.sidebar.error)


def test_example_click_reports_connection_error_without_crashing(monkeypatch) -> None:
    app = _run(monkeypatch)
    next(b for b in app.button if b.key == "example_0").click().run()
    assert not app.exception
    assert any("No hay conexión con la API" in e.value for e in app.error)
