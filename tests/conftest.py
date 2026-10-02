import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db  # noqa: E402


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path, monkeypatch):
    """Cada teste usa um banco SQLite novo e isolado."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "teste.db")
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "APIFY_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    db.init_db()
    yield tmp_path / "teste.db"
