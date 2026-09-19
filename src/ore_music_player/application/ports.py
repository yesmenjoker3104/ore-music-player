from __future__ import annotations

from typing import Protocol

from ore_music_player.domain.models import Track


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