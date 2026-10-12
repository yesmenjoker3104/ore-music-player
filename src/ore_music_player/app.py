from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ore_music_player.bootstrap import build_application
from ore_music_player.single_instance import (
	OpenFilesServer,
	send_paths_to_running_instance,
)
from ore_music_player.ui.main_window import SUPPORTED_AUDIO_SUFFIXES, MainWindow


def _application_icon_path() -> Path:
	return Path(__file__).resolve().parent / "assets" / "app_icon.ico"


def _set_windows_app_user_model_id() -> None:
	if sys.platform != "win32":
		return
	import ctypes

	ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
		"OreMusicPlayer.OreMusicPlayer"
	)


def _audio_paths_from_arguments(arguments: list[str]) -> list[str]:
	return [
		argument
		for argument in arguments
		if Path(argument).suffix.lower() in SUPPORTED_AUDIO_SUFFIXES
	]


def run() -> int:
	_set_windows_app_user_model_id()
	qt_application = QApplication(sys.argv)
	open_paths = _audio_paths_from_arguments(sys.argv[1:])
	if open_paths and send_paths_to_running_instance(open_paths):
		return 0
	qt_application.setWindowIcon(QIcon(str(_application_icon_path())))
	with build_application() as components:
		os.environ.setdefault(
			"ORE_MUSIC_TRACE",
			str(components.data_directory / "playback-trace.jsonl"),
		)
		window = MainWindow(
			components.playback_service,
			components.playlist_service,
			components.data_directory / "settings.ini",
			components.separation_service,
			stem_playback_backend=components.stem_playback_backend,
		)
		window.setWindowIcon(qt_application.windowIcon())
		open_files_server = OpenFilesServer(parent=window)
		open_files_server.paths_received.connect(window.open_external_paths)
		qt_application.aboutToQuit.connect(window._save_left_pane_settings)
		window.show()
		window.open_external_paths(open_paths)
		open_files_server.start()
		return qt_application.exec()
