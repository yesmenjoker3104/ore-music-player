from __future__ import annotations

import sqlite3
from pathlib import Path

from ore_music_player.domain.models import Playlist, Track


class SQLitePlaylistRepository:
    def __init__(self, database_path: str | Path) -> None:
        self._connection = sqlite3.connect(database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS playlists (
                playlist_id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tracks (
                track_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                title TEXT NOT NULL,
                duration_seconds REAL
            );
            CREATE TABLE IF NOT EXISTS playlist_tracks (
                playlist_id TEXT NOT NULL,
                track_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                PRIMARY KEY (playlist_id, track_id),
                FOREIGN KEY (playlist_id) 
                REFERENCES playlists (playlist_id) 
                ON DELETE CASCADE,
                FOREIGN KEY (track_id) 
                REFERENCES tracks (track_id) 
                ON DELETE CASCADE
            );
            """
        )
        self._connection.commit()

    def get(self, playlist_id: str) -> Playlist | None:
        playlist_row = self._connection.execute(
            """
            SELECT playlist_id, name 
            FROM playlists 
            WHERE playlist_id = ?
            """,
            (playlist_id,)
        ).fetchone()

        if playlist_row is None:
            return None

        tracks_rows = self._connection.execute(
            """
            SELECT 
                t.track_id,
                t.path,
                t.title,
                t.duration_seconds
            FROM tracks AS t
            INNER JOIN playlist_tracks AS pt
            ON t.track_id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
            """,
            (playlist_id,)
        ).fetchall()

        tracks = tuple(
            Track(
                track_id=row["track_id"],
                path=row["path"],
                title=row["title"],
                duration_seconds=row["duration_seconds"]
            )
            for row in tracks_rows
        )

        return Playlist(
            playlist_id=playlist_row["playlist_id"],
            name=playlist_row["name"],
            tracks=tracks,
        )

    def list_all(self) -> tuple[Playlist, ...]:
        rows = self._connection.execute(
            """
            SELECT
                p.playlist_id,
                p.name,
                t.track_id,
                t.path,
                t.title,
                t.duration_seconds
            FROM playlists AS p
            LEFT JOIN playlist_tracks AS pt
                ON p.playlist_id = pt.playlist_id
            LEFT JOIN tracks AS t
                ON pt.track_id = t.track_id
            ORDER BY p.rowid, pt.position
            """
        ).fetchall()

        playlist_data: dict[str, tuple[str, list[Track]]] = {}
        for row in rows:
            playlist_id = row["playlist_id"]
            name, tracks = playlist_data.setdefault(
                playlist_id,
                (row["name"], []),
            )
            if row["track_id"] is not None:
                tracks.append(
                    Track(
                        track_id=row["track_id"],
                        path=row["path"],
                        title=row["title"],
                        duration_seconds=row["duration_seconds"],
                    )
                )

        return tuple(
            Playlist(
                playlist_id=playlist_id,
                name=name,
                tracks=tuple(tracks),
            )
            for playlist_id, (name, tracks) in playlist_data.items()
        )

    def save(self, playlist: Playlist) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO playlists (playlist_id, name)
                VALUES (?, ?)
                ON CONFLICT(playlist_id) 
                DO UPDATE SET
                    name = excluded.name
                """,
                (playlist.playlist_id, playlist.name),
            )

            self._connection.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ?",
                (playlist.playlist_id,)
            )

            for position, track in enumerate(playlist.tracks):
                self._connection.execute(
                    """
                    INSERT INTO tracks (
                    track_id,
                    path,
                    title,
                    duration_seconds
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(track_id) 
                    DO UPDATE SET
                        path = excluded.path,
                        title = excluded.title,
                        duration_seconds = excluded.duration_seconds
                    """,
                    (
                        track.track_id, 
                        track.path, 
                        track.title, 
                        track.duration_seconds
                     ),
                )
                self._connection.execute(
                    """
                    INSERT INTO playlist_tracks (
                    playlist_id,
                    track_id,
                    position
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        playlist.playlist_id,
                        track.track_id,
                        position,
                    ),
                )

    def delete(self, playlist_id: str) -> None:
        with self._connection:
            self._connection.execute(
                """
                DELETE FROM playlists
                WHERE playlist_id = ?
                """,
                (playlist_id,),
            )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
