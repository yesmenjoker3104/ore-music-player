from __future__ import annotations

import sqlite3
from pathlib import Path


class StemRepository:
    def __init__(self, database_path: str | Path) -> None:
        self._conn = sqlite3.connect(
            str(database_path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS stems (
                track_id TEXT NOT NULL,
                stem_name TEXT NOT NULL,
                path TEXT NOT NULL,
                PRIMARY KEY (track_id, stem_name)
            );
        """)
        self._conn.commit()

    def save(self, track_id: str, stems: dict[str, Path]) -> None:
        self._conn.execute("DELETE FROM stems WHERE track_id = ?", (track_id,))
        self._conn.executemany(
            "INSERT INTO stems (track_id, stem_name, path) VALUES (?, ?, ?)",
            [(track_id, name, str(path)) for name, path in stems.items()],
        )
        self._conn.commit()

    def find(self, track_id: str) -> dict[str, Path] | None:
        rows = self._conn.execute(
            "SELECT stem_name, path FROM stems WHERE track_id = ?", (track_id,)
        ).fetchall()
        if not rows:
            return None
        return {row["stem_name"]: Path(row["path"]) for row in rows}

    def delete(self, track_id: str) -> None:
        self._conn.execute("DELETE FROM stems WHERE track_id = ?", (track_id,))
        self._conn.commit()

    def all_track_ids_with_stems(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT track_id FROM stems"
        ).fetchall()
        return [row["track_id"] for row in rows]
