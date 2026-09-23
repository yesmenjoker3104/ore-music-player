from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ore_music_player.bootstrap import build_application
from ore_music_player.ui.main_window import MainWindow


def run() -> int:
	qt_application = QApplication(sys.argv)
	with build_application() as components:
		window = MainWindow(
			components.playback_service,
			components.playlist_service,
		)
		window.show()
		return qt_application.exec()
