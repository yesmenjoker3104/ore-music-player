from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ore_music_player.bootstrap import build_application
from ore_music_player.ui.main_window import MainWindow


def _application_icon_path() -> Path:
	return Path(__file__).resolve().parent / "assets" / "app_icon.ico"


def _set_windows_app_user_model_id() -> None:
	if sys.platform != "win32":
		return
	import ctypes

	ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
		"OreMusicPlayer.OreMusicPlayer"
	)


def run() -> int:
	_set_windows_app_user_model_id()
	qt_application = QApplication(sys.argv)
	qt_application.setWindowIcon(QIcon(str(_application_icon_path())))
	with build_application() as components:
		window = MainWindow(
			components.playback_service,
			components.playlist_service,
		)
		window.setWindowIcon(qt_application.windowIcon())
		qt_application.aboutToQuit.connect(window._save_left_pane_settings)
		window.show()
		return qt_application.exec()
