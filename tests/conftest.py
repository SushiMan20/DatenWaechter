import pytest


@pytest.fixture(autouse=True)
def eigene_einstellungen(tmp_path, monkeypatch):
    """Jeder Test bekommt eine leere Einstellungsdatei, keinen zwischengespeicherten KI-Server, kein KI-Modell."""
    from datenwaechter import llm
    monkeypatch.setenv("DATENWAECHTER_EINSTELLUNGEN", str(tmp_path / "einstellungen.json"))
    monkeypatch.setenv("DATENWAECHTER_KEIN_SCHLUESSELBUND", "1")
    monkeypatch.setenv("DATENWAECHTER_MODELL_ORDNER", str(tmp_path / "modell"))   # kein geladenes KI-Modell
    for var in ("DATENWAECHTER_LLM_URL", "DATENWAECHTER_LLM_TOKEN", "DATENWAECHTER_LLM_MODELL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(llm, "OLLAMA_URL", "http://127.0.0.1:9")  # kein echtes Ollama im Test
    llm._cache.clear()
    yield
    llm._cache.clear()
