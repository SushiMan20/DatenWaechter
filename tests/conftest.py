import pytest


@pytest.fixture(autouse=True)
def eigene_einstellungen(tmp_path, monkeypatch):
    """Jeder Test bekommt eine leere Einstellungsdatei und keinen zwischengespeicherten KI-Server."""
    from datenwaechter import llm
    monkeypatch.setenv("DATENWAECHTER_EINSTELLUNGEN", str(tmp_path / "einstellungen.json"))
    monkeypatch.setenv("DATENWAECHTER_KEIN_SCHLUESSELBUND", "1")
    for var in ("DATENWAECHTER_LLM_URL", "DATENWAECHTER_LLM_TOKEN", "DATENWAECHTER_LLM_MODELL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(llm, "OLLAMA_URL", "http://127.0.0.1:9")  # kein echtes Ollama im Test
    llm._cache.clear()
    yield
    llm._cache.clear()
