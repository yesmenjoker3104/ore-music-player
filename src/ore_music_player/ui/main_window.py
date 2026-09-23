from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
	QDoubleSpinBox,
	QFileDialog,
	QGridLayout,
	QHBoxLayout,
	QLabel,
	QMainWindow,
	QPushButton,
	QSlider,
	QTabWidget,
	QVBoxLayout,
	QWidget,
)

from ore_music_player.application.playback_service import PlaybackService
from ore_music_player.application.playlist_service import PlaylistService
from ore_music_player.domain.models import Track
from ore_music_player.ui.playlist_view import PlaylistView

TILE_BUTTON_SIZE = 112
TILE_GRID_SPACING = 4


class MainWindow(QMainWindow):
	def __init__(
		self,
		playback_service: PlaybackService,
		playlist_service: PlaylistService,
	) -> None:
		super().__init__()
		self.playback_service = playback_service
		self._current_track: Track | None = None
		self._queue: tuple[Track, ...] = ()
		self._queue_index = -1

		self.setWindowTitle("ore music player")
		self.resize(720, 420)

		central_widget = QWidget()
		layout = QVBoxLayout(central_widget)
		tabs = QTabWidget()
		layout.addWidget(tabs)

		player_widget = QWidget()
		player_layout = QVBoxLayout(player_widget)

		self.track_label = QLabel("曲が選択されていません")
		self.status_label = QLabel("停止中")
		player_layout.addWidget(self.track_label)
		player_layout.addWidget(self.status_label)

		button_grid = QGridLayout()
		button_grid.setHorizontalSpacing(TILE_GRID_SPACING)
		button_grid.setVerticalSpacing(TILE_GRID_SPACING)
		open_button = self._create_tile_button("音声ファイル\nを開く", self.open_files)
		button_grid.addWidget(open_button, 0, 0)

		open_folder_button = self._create_tile_button("フォルダを開く", self.open_folder)
		button_grid.addWidget(open_folder_button, 0, 1)

		play_button = self._create_tile_button("再生", self.play)
		button_grid.addWidget(play_button, 0, 2)

		pause_button = self._create_tile_button("一時停止", self.pause)
		button_grid.addWidget(pause_button, 0, 3)

		stop_button = self._create_tile_button("停止", self.stop)
		button_grid.addWidget(stop_button, 0, 4)

		previous_button = self._create_tile_button("前の曲", self.previous_track)
		button_grid.addWidget(previous_button, 1, 0)
		next_button = self._create_tile_button("次の曲", self.next_track)
		button_grid.addWidget(next_button, 1, 1)

		position_layout = QHBoxLayout()
		position_layout.addWidget(QLabel("位置(秒)"))
		self.position_spinbox = QDoubleSpinBox()
		self.position_spinbox.setRange(0, 86400)
		self.position_spinbox.setDecimals(2)
		position_layout.addWidget(self.position_spinbox)
		seek_button = QPushButton("シーク")
		seek_button.clicked.connect(self.seek)
		position_layout.addWidget(seek_button)
		player_layout.addLayout(position_layout)

		set_a_button = self._create_tile_button("A設定", self.set_a)
		button_grid.addWidget(set_a_button, 1, 2)
		set_b_button = self._create_tile_button("B設定", self.set_b)
		button_grid.addWidget(set_b_button, 1, 3)
		self.loop_button = self._create_tile_button("A/Bループ\n開始", self.toggle_loop)
		button_grid.addWidget(self.loop_button, 1, 4)
		clear_loop_button = self._create_tile_button("A/B解除", self.clear_loop)
		button_grid.addWidget(clear_loop_button, 2, 0)
		player_layout.addLayout(button_grid)

		self.speed_slider = QSlider()
		self.speed_slider.setOrientation(Qt.Orientation.Horizontal)
		self.speed_slider.setRange(0, 20)
		self.speed_slider.setValue(10)
		self.speed_slider.valueChanged.connect(self.change_speed)
		player_layout.addWidget(QLabel("再生速度"))
		player_layout.addWidget(self.speed_slider)

		playlist_view = PlaylistView(playlist_service)
		playlist_view.play_requested.connect(self.load_and_play)
		tabs.addTab(player_widget, "再生")
		tabs.addTab(playlist_view, "プレイリスト")

		self.setCentralWidget(central_widget)

	@staticmethod
	def _create_tile_button(text: str, handler) -> QPushButton:
		button = QPushButton(text)
		button.setFixedSize(TILE_BUTTON_SIZE, TILE_BUTTON_SIZE)
		button.clicked.connect(handler)
		return button

	def open_files(self) -> None:
		file_paths, _ = QFileDialog.getOpenFileNames(
			self,
			"音声ファイルを選択",
			"",
			"Audio files (*.mp3 *.wav *.flac *.m4a *.ogg);;All files (*.*)",
		)
		if file_paths:
			self.load_tracks(self._tracks_from_paths(file_paths))

	def open_folder(self) -> None:
		folder_path = QFileDialog.getExistingDirectory(self, "音声フォルダを選択")
		if not folder_path:
			return
		paths = (
			path
			for path in Path(folder_path).rglob("*")
			if path.is_file() and path.suffix.lower() in {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
		)
		self.load_tracks(self._tracks_from_paths(paths))

	def _tracks_from_paths(
		self,
		paths: tuple[str | Path, ...] | list[str] | set[Path],
	) -> tuple[Track, ...]:
		return tuple(
			Track(track_id=str(uuid4()), path=str(path), title=Path(path).stem)
			for path in paths
		)

	def load_tracks(self, tracks: tuple[Track, ...], index: int = 0) -> None:
		if not tracks or not 0 <= index < len(tracks):
			return
		self._queue = tracks
		self._queue_index = index
		self._load_current_track(autoplay=False)

	def _load_current_track(self, autoplay: bool) -> None:
		self._current_track = self._queue[self._queue_index]
		self.playback_service.load(self._current_track)
		self.track_label.setText(self._current_track.title)
		self.position_spinbox.setValue(0)
		self.status_label.setText("読み込み済み")
		if autoplay:
			self.play()

	def load_and_play(self, tracks: tuple[Track, ...] | Track) -> None:
		if isinstance(tracks, Track):
			tracks = (tracks,)
		self.load_tracks(tuple(tracks), index=0)
		self.play()

	def play(self) -> None:
		if self._current_track is None:
			return
		self.playback_service.play()
		self.status_label.setText("再生中")

	def pause(self) -> None:
		if self._current_track is None:
			return
		self.playback_service.pause()
		self.status_label.setText("一時停止")

	def stop(self) -> None:
		self.playback_service.stop()
		self.status_label.setText("停止中")

	def previous_track(self) -> None:
		if self._queue_index > 0:
			self._queue_index -= 1
			self._load_current_track(autoplay=True)

	def next_track(self) -> None:
		if self._queue_index + 1 < len(self._queue):
			self._queue_index += 1
			self._load_current_track(autoplay=True)

	def seek(self) -> None:
		if self._current_track is not None:
			self.playback_service.seek(self.position_spinbox.value())

	def set_a(self) -> None:
		if self._current_track is not None:
			self.playback_service.set_a(self.position_spinbox.value())

	def set_b(self) -> None:
		if self._current_track is not None:
			self.playback_service.set_b(self.position_spinbox.value())

	def toggle_loop(self) -> None:
		if self._current_track is None:
			return
		if self.playback_service.state.loop_enabled:
			self.playback_service.disable_loop()
			self.loop_button.setText("A/Bループ開始")
		else:
			self.playback_service.enable_loop()
			self.loop_button.setText("A/Bループ停止")

	def clear_loop(self) -> None:
		if self._current_track is not None:
			self.playback_service.clear_loop()
			self.loop_button.setText("A/Bループ開始")

	def change_speed(self, slider_value: int) -> None:
		speed = round(0.5 + slider_value * 0.05, 2)
		self.playback_service.set_speed(speed)
