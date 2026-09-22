from __future__ import annotations

from typing import Protocol

from ore_music_player.domain.models import Playlist, Track


class PlaybackBackend(Protocol):
    def load(self, track: Track) -> None:
        ...

    def play(self) -> None:
        ...

    def pause(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def seek(self, position: float) -> None:
        ...

    def set_speed(self, speed: float) -> None:
        ...

    def set_loop(
        self,
        start_seconds: float | None,
        end_seconds: float | None,
    ) -> None:
        ...

class PlaylistRepository(Protocol):
    def get(self, playlist_id: str) -> Playlist | None:
        ...

    def list_all(self) -> tuple[Playlist, ...]:
        ...

    def save(self, playlist: Playlist) -> None:
        ...

    def delete(self, playlist_id: str) -> None:
        ...