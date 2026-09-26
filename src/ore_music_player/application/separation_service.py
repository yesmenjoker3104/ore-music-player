from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ore_music_player.domain.models import Track
from ore_music_player.infrastructure.separation.demucs_backend import separate
from ore_music_player.infrastructure.separation.demucs_env import (
    find_env_dir,
    is_env_ready,
    setup_env,
)
from ore_music_player.infrastructure.separation.stem_repository import StemRepository


class SeparationService:
    def __init__(
        self,
        stem_repository: StemRepository,
        stems_dir: Path,
        project_root: Path,
    ) -> None:
        self._repo = stem_repository
        self._stems_dir = stems_dir
        self._env_dir = find_env_dir(project_root)

    @property
    def env_dir(self) -> Path:
        return self._env_dir

    def is_env_ready(self) -> bool:
        return is_env_ready(self._env_dir)

    def setup_env(self, on_progress: Callable[[str], None] | None = None) -> None:
        setup_env(self._env_dir, on_progress=on_progress)

    def has_stems(self, track_id: str) -> bool:
        stems = self._repo.find(track_id)
        if stems is None:
            return False
        return all(p.is_file() for p in stems.values())

    def get_stems(self, track_id: str) -> dict[str, Path] | None:
        return self._repo.find(track_id)

    def separate(
        self,
        track: Track,
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, Path]:
        track_stems_dir = self._stems_dir / track.track_id
        track_stems_dir.mkdir(parents=True, exist_ok=True)
        stems = separate(
            track_path=Path(track.path),
            env_dir=self._env_dir,
            output_dir=track_stems_dir,
            on_progress=on_progress,
        )
        self._repo.save(track.track_id, stems)
        return stems

    def delete_stems(self, track_id: str) -> None:
        stems = self._repo.find(track_id)
        if stems:
            for path in stems.values():
                if path.is_file():
                    path.unlink()
            track_dir = self._stems_dir / track_id
            if track_dir.is_dir():
                try:
                    track_dir.rmdir()
                except OSError:
                    pass
        self._repo.delete(track_id)

    def all_separated_track_ids(self) -> list[str]:
        return self._repo.all_track_ids_with_stems()
