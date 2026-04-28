from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts import corpus_metrics


def test_show_metrics_handles_empty_database(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "dharmagpt.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE corpus_records (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            source_type TEXT NOT NULL,
            language TEXT DEFAULT 'en',
            text TEXT NOT NULL,
            text_te TEXT,
            text_en_model TEXT,
            topics TEXT,
            embedded BOOLEAN DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(corpus_metrics, "db_path", Path(db_path))

    corpus_metrics.show_metrics()

    captured = capsys.readouterr().out
    assert "Total records: 0" in captured
    assert "No corpus records found yet." in captured
