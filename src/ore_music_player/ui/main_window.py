from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import (
	QByteArray,
	QDir,
	QModelIndex,
	QPointF,
	QRectF,
	QSettings,
	Qt,
	QTimer,
)
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
	QAbstractItemView,
	QFileDialog,
	QFileSystemModel,
	QGridLayout,
	QLabel,
	QMainWindow,
	QMessageBox,
	QPushButton,
	QSizePolicy,
	QSlider,
	QSplitter,
	QStyle,
	QStyleOptionSlider,
	QTabWidget,
	QTreeView,
	QVBoxLayout,
	QWidget,
)

from ore_music_player.application.playback_service import PlaybackService
from ore_music_player.application.playlist_service import PlaylistService
from ore_music_player.domain.models import (
	DEFAULT_PLAYBACK_SPEED,
	MAX_PLAYBACK_SPEED,
	MIN_PLAYBACK_SPEED,
	PLAYBACK_SPEED_STEP,
	Track,
)
from ore_music_player.infrastructure.audio.metadata import read_duration_seconds
from ore_music_player.ui.playlist_view import PlaylistView

TILE_BUTTON_SIZE = 112
TILE_GRID_SPACING = 4
SUPPORTED_AUDIO_SUFFIXES = (".mp3", ".wav", ".flac", ".m4a", ".ogg")
SUPPORTED_AUDIO_NAME_FILTERS = [f"*{suffix}" for suffix in SUPPORTED_AUDIO_SUFFIXES]
SEEK_SCALE = 1000
SLIDER_GROOVE_HEIGHT = 18
SLIDER_HANDLE_SIZE = 28
SLIDER_MINIMUM_HEIGHT = 44
SLIDER_STYLE = f"""
QSlider {{
	min-height: {SLIDER_MINIMUM_HEIGHT}px;
}}
QSlider::groove:horizontal {{
	height: {SLIDER_GROOVE_HEIGHT}px;
	background: #d7dde5;
	border: 1px solid #9aa4b2;
	border-radius: 9px;
}}
QSlider::sub-page:horizontal {{
	background: #2f6fed;
	border-radius: 9px;
}}
QSlider::add-page:horizontal {{
	background: #d7dde5;
	border-radius: 9px;
}}
QSlider::handle:horizontal {{
	width: {SLIDER_HANDLE_SIZE}px;
	height: {SLIDER_HANDLE_SIZE}px;
	margin: -5px 0;
	background: #ffffff;
	border: 2px solid #2f6fed;
	border-radius: 14px;
}}
QSlider::groove:horizontal:disabled {{
	background: #e5e7eb;
	border-color: #c5cad3;
}}
QSlider::sub-page:horizontal:disabled {{
	background: #c5cad3;
}}
QSlider::handle:horizontal:disabled {{
	background: #f3f4f6;
	border-color: #aeb5c0;
}}
"""


class PositionSlider(QSlider):
	def __init__(self) -> None:
		super().__init__(Qt.Orientation.Horizontal)
		self._a_marker_seconds: float | None = None
		self._b_marker_seconds: float | None = None
		self._marker_duration_seconds = 0.0

	def set_markers(
		self,
		a_seconds: float | None,
		b_seconds: float | None,
		duration_seconds: float,
	) -> None:
		self._a_marker_seconds = a_seconds
		self._b_marker_seconds = b_seconds
		self._marker_duration_seconds = max(0.0, duration_seconds)
		self.update()

	def paintEvent(self, event) -> None:
		super().paintEvent(event)
		if self._marker_duration_seconds <= 0:
			return

		option = QStyleOptionSlider()
		self.initStyleOption(option)
		groove = self.style().subControlRect(
			QStyle.ComplexControl.CC_Slider,
			option,
			QStyle.SubControl.SC_SliderGroove,
			self,
		)
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		markers = (
			("A", self._a_marker_seconds, QColor("#1f8a70")),
			("B", self._b_marker_seconds, QColor("#d1495b")),
		)

		for label, seconds, color in markers:
			if seconds is None or not 0 <= seconds <= self._marker_duration_seconds:
				continue
			x = groove.left() + groove.width() * (
				seconds / self._marker_duration_seconds
			)
			painter.setPen(QPen(color, 2))
			painter.drawLine(
				QPointF(x, groove.top() - 3),
				QPointF(x, groove.bottom() + 3),
			)
			painter.setPen(Qt.PenStyle.NoPen)
			painter.setBrush(color)
			painter.drawPolygon(
				QPolygonF(
					[
						QPointF(x - 5, groove.top() - 5),
						QPointF(x + 5, groove.top() - 5),
						QPointF(x, groove.top()),
					]
				)
			)
			painter.setPen(color)
			painter.drawText(
				QRectF(x - 10, 0, 20, groove.top() - 5),
				Qt.AlignmentFlag.AlignCenter,
				label,
			)

		painter.end()


class AudioFileSystemModel(QFileSystemModel):
	def __init__(self, parent: QWidget | None = None) -> None:
		super().__init__(parent)
		self._duration_cache: dict[str, float | None] = {}

	def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
		return 2

	def headerData(
		self,
		section: int,
		orientation: Qt.Orientation,
		role: int = Qt.ItemDataRole.DisplayRole,
	):
		if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
			return ("ファイル名", "再生時間")[section]
		return super().headerData(section, orientation, role)

	def data(
		self,
		index: QModelIndex,
		role: int = Qt.ItemDataRole.DisplayRole,
	):
		if index.column() == 1 and role == Qt.ItemDataRole.DisplayRole:
			if self.isDir(index):
				return ""
			path = self.filePath(index)
			if path not in self._duration_cache:
				self._duration_cache[path] = read_duration_seconds(path)
			return _format_duration(self._duration_cache[path])
		return super().data(index, role)

	def set_duration(self, path: str, duration: float) -> None:
		self._duration_cache[path] = duration
		index = self.index(path)
		if index.isValid():
			duration_index = index.siblingAtColumn(1)
			self.dataChanged.emit(
				duration_index,
				duration_index,
				[Qt.ItemDataRole.DisplayRole],
			)


def _format_duration(seconds: float | None) -> str:
	if seconds is None:
		return "--:--"

	total_seconds = max(0, int(seconds))
	minutes, remainder = divmod(total_seconds, 60)
	hours, minutes = divmod(minutes, 60)
	if hours:
		return f"{hours}:{minutes:02d}:{remainder:02d}"
	return f"{minutes}:{remainder:02d}"


class MainWindow(QMainWindow):
	_SETTINGS_ORGANIZATION = "OreMusicPlayer"
	_SETTINGS_APPLICATION = "OreMusicPlayer"
	_SPLITTER_STATE_KEY = "leftPane/splitterState"
	_FILE_TREE_HEADER_STATE_KEY = "leftPane/fileTreeHeaderState"
	_FILE_TREE_ROOT_KEY = "leftPane/rootPath"

	def __init__(
		self,
		playback_service: PlaybackService,
		playlist_service: PlaylistService,
	) -> None:
		super().__init__()
		self.playback_service = playback_service
		self._settings = QSettings(
			self._SETTINGS_ORGANIZATION,
			self._SETTINGS_APPLICATION,
		)
		self._current_track: Track | None = None
		self._queue: tuple[Track, ...] = ()
		self._queue_index = -1
		self._is_seeking = False
		self._is_playing = False
		self._duration_seconds = 0.0
		self._hidden_file_paths: set[Path] = set()

		self.setWindowTitle("Ore Music Player")
		self.resize(960, 620)
		self._create_file_menu()

		central_widget = QWidget()
		layout = QVBoxLayout(central_widget)
		splitter = QSplitter(Qt.Orientation.Horizontal)
		self.main_splitter = splitter
		splitter.splitterMoved.connect(self._save_left_pane_settings)
		layout.addWidget(splitter)

		file_panel = QWidget()
		file_layout = QVBoxLayout(file_panel)
		file_layout.addWidget(QLabel("ファイル一覧"))
		self.file_root_label = QLabel()
		file_layout.addWidget(self.file_root_label)
		self.delete_file_button = QPushButton("削除")
		self.delete_file_button.setEnabled(False)
		self.delete_file_button.clicked.connect(self.delete_selected_files)
		file_layout.addWidget(self.delete_file_button)
		self.file_system_model = AudioFileSystemModel(self)
		self.file_system_model.setFilter(
			QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot
		)
		self.file_system_model.setNameFilters(SUPPORTED_AUDIO_NAME_FILTERS)
		self.file_system_model.setNameFilterDisables(False)
		default_root_path = Path(QDir.currentPath()).anchor or QDir.rootPath()
		root_path = self._settings.value(
			self._FILE_TREE_ROOT_KEY,
			default_root_path,
			type=str,
		)
		if not Path(root_path).is_dir():
			root_path = default_root_path
		self.file_system_model.setRootPath(root_path)
		self.file_root_label.setText(root_path)
		self.file_tree = QTreeView()
		self.file_tree.setModel(self.file_system_model)
		self.file_tree.setSelectionMode(
			QAbstractItemView.SelectionMode.ExtendedSelection
		)
		self.file_tree.setSelectionBehavior(
			QAbstractItemView.SelectionBehavior.SelectRows
		)
		self.file_tree.setRootIndex(self.file_system_model.index(root_path))
		self.file_tree.setColumnWidth(0, 280)
		self.file_tree.setColumnWidth(1, 90)
		self._restore_left_pane_settings()
		self.file_tree.doubleClicked.connect(self._load_file_from_tree)
		self.file_tree.selectionModel().selectionChanged.connect(
			self._update_delete_button_state
		)
		self.file_system_model.directoryLoaded.connect(
			self._hide_hidden_file_tree_rows
		)
		file_layout.addWidget(self.file_tree)
		splitter.addWidget(file_panel)

		tabs = QTabWidget()
		splitter.addWidget(tabs)
		splitter.setStretchFactor(0, 1)
		splitter.setStretchFactor(1, 2)
		splitter.setSizes([320, 640])

		player_widget = QWidget()
		player_layout = QVBoxLayout(player_widget)

		self.track_label = QLabel("曲が選択されていません")
		self.status_label = QLabel("停止中")
		label_size_policy = QSizePolicy(
			QSizePolicy.Policy.Preferred,
			QSizePolicy.Policy.Fixed,
		)
		self.track_label.setSizePolicy(label_size_policy)
		self.status_label.setSizePolicy(label_size_policy)
		track_status_layout = QVBoxLayout()
		track_status_layout.setContentsMargins(0, 0, 0, 0)
		track_status_layout.setSpacing(0)
		track_status_layout.addWidget(self.track_label)
		track_status_layout.addWidget(self.status_label)
		player_layout.addLayout(track_status_layout)

		button_grid = QGridLayout()
		button_grid.setHorizontalSpacing(TILE_GRID_SPACING)
		button_grid.setVerticalSpacing(TILE_GRID_SPACING)

		previous_button = self._create_tile_button("前の曲", self.previous_track)
		button_grid.addWidget(previous_button, 0, 1)

		self.play_pause_button = self._create_tile_button(
			"再生",
			self.toggle_play_pause,
		)

		button_grid.addWidget(self.play_pause_button, 0, 2)

		stop_button = self._create_tile_button("停止", self.stop)
		button_grid.addWidget(stop_button, 0, 3)


		next_button = self._create_tile_button("次の曲", self.next_track)
		button_grid.addWidget(next_button, 0, 4)

		self.set_a_button = self._create_tile_button("A設定", self.set_a)
		button_grid.addWidget(self.set_a_button, 1, 1)
		self.set_b_button = self._create_tile_button("B設定", self.set_b)
		button_grid.addWidget(self.set_b_button, 1, 2)
		self.loop_button = self._create_tile_button("A/Bループ\n開始", self.toggle_loop)
		self.loop_button.setEnabled(False)
		button_grid.addWidget(self.loop_button, 1, 3)
		player_layout.addLayout(button_grid)
		player_layout.setAlignment(button_grid, Qt.AlignmentFlag.AlignLeft)

		bars_layout = QGridLayout()
		bars_layout.setHorizontalSpacing(8)
		bars_layout.setColumnStretch(2, 1)

		self.position_label = QLabel("0:00")
		self.duration_label = QLabel("--:--")
		self.position_slider = PositionSlider()
		self._configure_slider(self.position_slider)
		self.position_slider.setRange(0, 0)
		self.position_slider.setEnabled(False)
		self.position_slider.setTracking(True)
		self.position_slider.sliderPressed.connect(self._start_seeking)
		self.position_slider.sliderMoved.connect(self._preview_seek)
		self.position_slider.sliderReleased.connect(self._finish_seeking)
		bars_layout.addWidget(QLabel("再生位置"), 0, 0)
		bars_layout.addWidget(self.position_label, 0, 1)
		bars_layout.addWidget(self.position_slider, 0, 2)
		bars_layout.addWidget(self.duration_label, 0, 3)

		min_speed_label = QLabel(f"{MIN_PLAYBACK_SPEED:.2f}x")
		self.speed_slider = QSlider()
		self._configure_slider(self.speed_slider)
		speed_steps = int(
			(MAX_PLAYBACK_SPEED - MIN_PLAYBACK_SPEED)
			/ PLAYBACK_SPEED_STEP
		)
		self.speed_slider.setRange(
			0,
			speed_steps,
		)
		self.speed_slider.setValue(
			int(
				(DEFAULT_PLAYBACK_SPEED - MIN_PLAYBACK_SPEED)
				/ PLAYBACK_SPEED_STEP
			)
		)
		self.speed_slider.valueChanged.connect(self.change_speed)
		self.speed_current_label = QLabel()
		bars_layout.addWidget(QLabel("再生速度"), 1, 0)
		bars_layout.addWidget(min_speed_label, 1, 1)
		bars_layout.addWidget(self.speed_slider, 1, 2)
		bars_layout.addWidget(self.speed_current_label, 1, 3)

		player_layout.addLayout(bars_layout)
		self._update_speed_label(self.speed_slider.value())

		self._position_timer = QTimer(self)
		self._position_timer.setInterval(250)
		self._position_timer.timeout.connect(self._update_position)
		self._position_timer.start()

		playlist_view = PlaylistView(playlist_service)
		playlist_view.play_requested.connect(self.load_and_play)
		tabs.addTab(player_widget, "再生")
		tabs.addTab(playlist_view, "プレイリスト")

		self.setCentralWidget(central_widget)
		self._restore_splitter_state()

	def _restore_left_pane_settings(self) -> None:
		header_state = self._settings.value(
			self._FILE_TREE_HEADER_STATE_KEY,
			QByteArray(),
		)
		if isinstance(header_state, QByteArray) and not header_state.isEmpty():
			self.file_tree.header().restoreState(header_state)

	def _restore_splitter_state(self) -> bool:
		splitter_state = self._settings.value(
			self._SPLITTER_STATE_KEY,
			QByteArray(),
		)
		return (
			isinstance(splitter_state, QByteArray)
			and not splitter_state.isEmpty()
			and self.main_splitter.restoreState(splitter_state)
		)

	def _save_left_pane_settings(self, *_args) -> None:
		self._settings.setValue(
			self._SPLITTER_STATE_KEY,
			self.main_splitter.saveState(),
		)
		self._settings.setValue(
			self._FILE_TREE_HEADER_STATE_KEY,
			self.file_tree.header().saveState(),
		)
		self._settings.setValue(
			self._FILE_TREE_ROOT_KEY,
			self.file_root_label.text(),
		)
		self._settings.sync()

	def closeEvent(self, event) -> None:
		self._save_left_pane_settings()
		super().closeEvent(event)

	@staticmethod
	def _create_tile_button(text: str, handler) -> QPushButton:
		button = QPushButton(text)
		button.setFixedSize(TILE_BUTTON_SIZE, TILE_BUTTON_SIZE)
		button.clicked.connect(handler)
		return button

	def _create_file_menu(self) -> None:
		file_menu = self.menuBar().addMenu("ファイル")
		open_files_action = QAction("音声ファイルを開く", self)
		open_files_action.triggered.connect(self.open_files)
		file_menu.addAction(open_files_action)

		open_folder_action = QAction("フォルダを開く", self)
		open_folder_action.triggered.connect(self.open_folder)
		file_menu.addAction(open_folder_action)

	@staticmethod
	def _configure_slider(slider: QSlider) -> None:
		slider.setOrientation(Qt.Orientation.Horizontal)
		slider.setMinimumHeight(SLIDER_MINIMUM_HEIGHT)
		slider.setStyleSheet(SLIDER_STYLE)

	def open_files(self) -> None:
		file_paths, _ = QFileDialog.getOpenFileNames(
			self,
			"音声ファイルを選択",
			"",
			"Audio files (*.mp3 *.wav *.flac *.m4a *.ogg);;All files (*.*)",
		)
		if file_paths:
			self._set_file_tree_root(Path(file_paths[0]).parent)
			self.load_tracks(self._tracks_from_paths(file_paths))

	def open_folder(self) -> None:
		folder_path = QFileDialog.getExistingDirectory(self, "音声フォルダを選択")
		if not folder_path:
			return
		self._set_file_tree_root(folder_path)
		paths = (
			path
			for path in Path(folder_path).rglob("*")
			if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES
		)
		self.load_tracks(self._tracks_from_paths(paths))

	def _load_file_from_tree(self, index: QModelIndex) -> None:
		if self.file_system_model.isDir(index):
			return
		path = Path(self.file_system_model.filePath(index))
		if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
			return
		track = Track(track_id=str(uuid4()), path=str(path), title=path.stem)
		self.load_tracks((track,))

	def _selected_audio_paths(self) -> tuple[Path, ...]:
		return tuple(
			Path(self.file_system_model.filePath(index))
			for index in self.file_tree.selectionModel().selectedRows(0)
			if index.isValid()
			and not self.file_system_model.isDir(index)
			and Path(self.file_system_model.filePath(index)).is_file()
			and Path(self.file_system_model.filePath(index)).suffix.lower()
			in SUPPORTED_AUDIO_SUFFIXES
		)

	def _update_delete_button_state(self, *_args) -> None:
		self.delete_file_button.setEnabled(bool(self._selected_audio_paths()))

	def delete_selected_files(self) -> None:
		selected_paths = self._selected_audio_paths()
		if not selected_paths:
			return

		file_list = "\n".join(f"・{path.name}" for path in selected_paths)
		answer = QMessageBox.warning(
			self,
			"左ペインから登録解除",
			f"選択した{len(selected_paths)}個のファイルを左ペインから登録解除します。\n"
			f"{file_list}",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
			QMessageBox.StandardButton.No,
		)
		if answer != QMessageBox.StandardButton.Yes:
			return

		self._hidden_file_paths.update(selected_paths)
		self._hide_hidden_file_tree_rows()
		self._remove_unregistered_tracks(selected_paths)
		self.file_tree.clearSelection()
		self._update_delete_button_state()

	def _hide_hidden_file_tree_rows(self, *_args) -> None:
		for path in self._hidden_file_paths:
			index = self.file_system_model.index(str(path))
			if index.isValid():
				self.file_tree.setRowHidden(index.row(), index.parent(), True)

	def _remove_unregistered_tracks(self, unregistered_paths: list[Path]) -> None:
		unregistered_path_set = set(unregistered_paths)
		remaining_tracks = tuple(
			track
			for track in self._queue
			if Path(track.path) not in unregistered_path_set
		)
		if len(remaining_tracks) == len(self._queue):
			return

		current_path = (
			Path(self._current_track.path)
			if self._current_track is not None
			else None
		)
		current_was_deleted = (
			current_path is not None and current_path in unregistered_path_set
		)
		deleted_before_current = sum(
			1
			for index, track in enumerate(self._queue)
			if index < self._queue_index
			and Path(track.path) in unregistered_path_set
		)
		self._queue = remaining_tracks
		if not self._queue:
			self.playback_service.stop()
			self.playback_service.clear_loop()
			self._current_track = None
			self._queue_index = -1
			self._duration_seconds = 0.0
			self.track_label.setText("曲が選択されていません")
			self._set_playback_status("停止中", is_playing=False)
			self.position_slider.setRange(0, 0)
			self.position_slider.setValue(0)
			self.position_slider.setEnabled(False)
			self.position_label.setText("0:00")
			self.duration_label.setText("--:--")
			self._update_ab_button_labels()
			self._update_loop_button()
			return

		if current_was_deleted:
			self.playback_service.stop()
			self._queue_index = min(self._queue_index, len(self._queue) - 1)
			self._load_current_track(autoplay=False)
		else:
			self._queue_index = min(
				self._queue_index - deleted_before_current,
				len(self._queue) - 1,
			)

	def _set_file_tree_root(self, root_path: str | Path) -> None:
		path = str(Path(root_path))
		self.file_system_model.setRootPath(path)
		self.file_tree.setRootIndex(self.file_system_model.index(path))
		self.file_root_label.setText(path)
		self._settings.setValue(self._FILE_TREE_ROOT_KEY, path)
		self._settings.sync()

	def _tracks_from_paths(
		self,
		paths: tuple[str | Path, ...] | list[str] | set[Path],
	) -> tuple[Track, ...]:
		sorted_paths = sorted(paths, key=lambda path: str(path).casefold())
		return tuple(
			Track(
				track_id=str(uuid4()),
				path=str(path),
				title=Path(path).stem,
				duration_seconds=read_duration_seconds(path),
			)
			for path in sorted_paths
		)

	def load_tracks(self, tracks: tuple[Track, ...], index: int = 0) -> None:
		if not tracks or not 0 <= index < len(tracks):
			return
		self._queue = tracks
		self._queue_index = index
		self._expand_file_tree_for_tracks()
		self._load_current_track(autoplay=True)

	def _expand_file_tree_for_tracks(self) -> None:
		for track in self._queue:
			parent_index = self.file_system_model.index(str(Path(track.path).parent))
			if parent_index.isValid():
				self.file_tree.expand(parent_index)

	def _update_file_tree_selection(self) -> None:
		if self._current_track is None:
			return
		index = self.file_system_model.index(self._current_track.path)
		if index.isValid():
			self.file_tree.setCurrentIndex(index)
			self.file_tree.scrollTo(index)

	def _load_current_track(self, autoplay: bool) -> None:
		self._current_track = self._queue[self._queue_index]
		self._update_file_tree_selection()
		self.playback_service.load(self._current_track)
		self.track_label.setText(self._current_track.title)
		self._update_ab_button_labels()
		self._update_loop_button()
		self._set_playback_status("読み込み済み", is_playing=False)
		self._is_seeking = False
		self._duration_seconds = 0.0
		self.position_slider.setRange(0, 0)
		self.position_slider.setValue(0)
		self.position_slider.setEnabled(False)
		self.position_label.setText("0:00")
		self.duration_label.setText("--:--")
		if autoplay:
			self.play()

	def load_and_play(self, tracks: tuple[Track, ...] | Track) -> None:
		if isinstance(tracks, Track):
			tracks = (tracks,)
		self.load_tracks(tuple(tracks), index=0)

	def _set_playback_status(self, label: str, is_playing: bool) -> None:
		self._is_playing = is_playing
		self.status_label.setText(label)
		self.play_pause_button.setText("一時停止" if is_playing else "再生")

	def toggle_play_pause(self) -> None:
		if self._is_playing:
			self.pause()
		else:
			self.play()

	def play(self) -> None:
		if self._current_track is None:
			return
		self.playback_service.play()
		self._set_playback_status("再生中", is_playing=True)

	def pause(self) -> None:
		if self._current_track is None:
			return
		self.playback_service.pause()
		self._set_playback_status("一時停止", is_playing=False)

	def stop(self) -> None:
		self.playback_service.stop()
		self._set_playback_status("停止中", is_playing=False)

	def previous_track(self) -> None:
		if self._queue_index > 0:
			self._queue_index -= 1
			self._load_current_track(autoplay=True)

	def next_track(self) -> None:
		if self._queue_index + 1 < len(self._queue):
			self._queue_index += 1
			self._load_current_track(autoplay=True)

	def _start_seeking(self) -> None:
		self._is_seeking = True

	def _preview_seek(self, slider_value: int) -> None:
		position = slider_value / SEEK_SCALE
		self.position_label.setText(self._format_time(position))

	def _finish_seeking(self) -> None:
		self._is_seeking = False
		if self._current_track is None:
			return

		position = self.position_slider.sliderPosition() / SEEK_SCALE
		self.playback_service.seek(position)
		self.position_label.setText(self._format_time(position))

	def _current_position_for_action(self) -> float:
		if self._is_seeking:
			return self.position_slider.value() / SEEK_SCALE

		return self.playback_service.position_seconds

	@staticmethod
	def _ab_button_text(label: str, position: float | None) -> str:
		if position is None:
			return label
		return f"{label}\n{MainWindow._format_time(position)}"

	def _update_position_markers(self) -> None:
		state = self.playback_service.state
		self.position_slider.set_markers(
			state.a_point_seconds,
			state.b_point_seconds,
			self._duration_seconds,
		)

	def _update_ab_button_labels(self) -> None:
		state = self.playback_service.state
		self.set_a_button.setText(
			self._ab_button_text("A設定", state.a_point_seconds)
		)
		self.set_b_button.setText(
			self._ab_button_text("B設定", state.b_point_seconds)
		)
		self._update_position_markers()

	def _update_loop_button(self) -> None:
		state = self.playback_service.state
		has_loop_points = (
			state.a_point_seconds is not None
			and state.b_point_seconds is not None
		)
		self.loop_button.setEnabled(has_loop_points)
		if state.loop_enabled:
			self.loop_button.setText("A/B解除")
		else:
			self.loop_button.setText("A/Bループ\n開始")

	def set_a(self) -> None:
		if self._current_track is not None:
			self.playback_service.set_a(self._current_position_for_action())
			self._update_ab_button_labels()
			self._update_loop_button()

	def set_b(self) -> None:
		if self._current_track is not None:
			self.playback_service.set_b(self._current_position_for_action())
			self._update_ab_button_labels()
			self._update_loop_button()

	def _update_position(self) -> None:
		if self._current_track is None:
			return

		duration = self.playback_service.duration_seconds
		if duration is not None and duration > 0:
			self._set_duration(duration)

		if self._is_seeking:
			return

		position = self.playback_service.position_seconds
		if self._duration_seconds > 0:
			position = min(position, self._duration_seconds)

		self.position_slider.blockSignals(True)
		self.position_slider.setValue(round(position * SEEK_SCALE))
		self.position_slider.blockSignals(False)
		self.position_label.setText(self._format_time(position))

	def _set_duration(self, duration_seconds: float) -> None:
		self._duration_seconds = max(0.0, duration_seconds)
		self._update_current_track_duration(self._duration_seconds)
		maximum = round(self._duration_seconds * SEEK_SCALE)

		if self.position_slider.maximum() != maximum:
			self.position_slider.setRange(0, maximum)

		self.position_slider.setEnabled(maximum > 0)
		self.duration_label.setText(self._format_time(self._duration_seconds))
		self._update_position_markers()

	def _update_current_track_duration(self, duration_seconds: float) -> None:
		if self._current_track is None or self._current_track.duration_seconds == duration_seconds:
			return

		self._current_track = replace(
			self._current_track,
			duration_seconds=duration_seconds,
		)
		tracks = list(self._queue)
		if 0 <= self._queue_index < len(tracks):
			tracks[self._queue_index] = self._current_track
			self._queue = tuple(tracks)
		self.file_system_model.set_duration(
			self._current_track.path,
			duration_seconds,
		)

	@staticmethod
	def _format_time(seconds: float | None) -> str:
		return _format_duration(seconds)

	def toggle_loop(self) -> None:
		if self._current_track is None:
			return
		if self.playback_service.state.loop_enabled:
			self.clear_loop()
		else:
			self.playback_service.enable_loop()
			self._update_loop_button()

	def clear_loop(self) -> None:
		if self._current_track is not None:
			self.playback_service.clear_loop()
			self._update_ab_button_labels()
			self._update_loop_button()

	def _speed_from_slider(self, slider_value: int):
		return MIN_PLAYBACK_SPEED + PLAYBACK_SPEED_STEP * slider_value

	def _update_speed_label(self, slider_value: int) -> None:
		speed = self._speed_from_slider(slider_value)
		self.speed_current_label.setText(f"{speed:.2f}x")

	def change_speed(self, slider_value: int) -> None:
		speed = self._speed_from_slider(slider_value)
		self._update_speed_label(slider_value)
		self.playback_service.set_speed(speed)
