from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

from ore_music_player.application.playback_service import PlaybackService
from ore_music_player.application.playlist_service import PlaylistService
from ore_music_player.infrastructure.audio.playback_backend import (
    LibMpvPlaybackBackend,
)
from ore_music_player.infrastructure.persistence.sqlite_repository import (
    SQLitePlaylistRepository,
)


@dataclass
class ApplicationComponents:
    playback_backend: LibMpvPlaybackBackend
    playback_service: PlaybackService
    playlist_repository: SQLitePlaylistRepository
    playlist_service: PlaylistService
    _mpv_dll_directory: Any = None

    def close(self) -> None:
        try:
            self.playback_backend.close()
        finally:
            self.playlist_repository.close()
            if self._mpv_dll_directory is not None:
                self._mpv_dll_directory.close()

    def __enter__(self) -> ApplicationComponents:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _configure_mpv_runtime(project_root: Path) -> Any:
    dll_names = ("libmpv-2.dll", "mpv-2.dll", "mpv-1.dll")
    mpv_directories = [project_root / "vendor" / "mpv"]
    if getattr(sys, "frozen", False):
        meipass_directory = Path(getattr(sys, "_MEIPASS", project_root))
        mpv_directories.insert(0, meipass_directory / "vendor" / "mpv")
    mpv_directory = next(
        (
            directory
            for directory in mpv_directories
            if directory.is_dir()
            and any((directory / name).is_file() for name in dll_names)
        ),
        None,
    )
    if mpv_directory is None:
        raise FileNotFoundError(
            f"mpv共有DLLが見つかりません: {', '.join(str(path) for path in mpv_directories)}"
        )

    os.environ["PATH"] = str(mpv_directory) + os.pathsep + os.environ.get("PATH", "")

    if os.name == "nt":
        return os.add_dll_directory(str(mpv_directory))

    return None


def build_application(
    data_directory: str | Path | None = None,
    project_root: str | Path | None = None,
) -> ApplicationComponents:
    resolved_root = (
        Path(project_root)
        if project_root is not None
        else Path(__file__).resolve().parents[2]
    )
    mpv_dll_directory = _configure_mpv_runtime(resolved_root)

    resolved_data_directory = (
        Path(data_directory)
        if data_directory is not None
        else resolved_root / "data"
    )
    resolved_data_directory.mkdir(parents=True, exist_ok=True)

    playback_backend = LibMpvPlaybackBackend()
    playback_service = PlaybackService(playback_backend)
    playlist_repository = SQLitePlaylistRepository(
        resolved_data_directory / "ore_music_player.sqlite3"
    )
    playlist_service = PlaylistService(playlist_repository)

    return ApplicationComponents(
        playback_backend=playback_backend,
        playback_service=playback_service,
        playlist_repository=playlist_repository,
        playlist_service=playlist_service,
        _mpv_dll_directory=mpv_dll_directory,
    )