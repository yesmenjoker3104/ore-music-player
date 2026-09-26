from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ore_music_player.application.separation_service import SeparationService
from ore_music_player.domain.models import Track


class EnvSetupWorker(QThread):
    progress = Signal(str)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, service: SeparationService) -> None:
        super().__init__()
        self._service = service

    def run(self) -> None:
        try:
            self._service.setup_env(on_progress=self.progress.emit)
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class SeparationWorker(QThread):
    progress = Signal(str)
    finished = Signal(str)
    failed = Signal(str, str)

    def __init__(self, service: SeparationService, track: Track) -> None:
        super().__init__()
        self._service = service
        self._track = track

    def run(self) -> None:
        try:
            self._service.separate(self._track, on_progress=self.progress.emit)
            self.finished.emit(self._track.track_id)
        except Exception as exc:
            self.failed.emit(self._track.track_id, str(exc))
