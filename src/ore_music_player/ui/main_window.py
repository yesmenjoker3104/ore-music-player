from __future__ import annotations

import json
import random
import shutil
import sys
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import (
	QAbstractProxyModel,
	QByteArray,
	QDir,
	QItemSelectionModel,
	QModelIndex,
	QPointF,
	QRectF,
	Qt,
	QThread,
	QTimer,
	Signal,
)
from PySide6.QtGui import (
	QAction,
	QColor,
	QIcon,
	QKeySequence,
	QPainter,
	QPen,
	QPolygonF,
	QShortcut,
)
from PySide6.QtWidgets import (
	QAbstractItemView,
	QComboBox,
	QFileDialog,
	QFileSystemModel,
	QGridLayout,
	QHBoxLayout,
	QLabel,
	QLineEdit,
	QMainWindow,
	QMenu,
	QMessageBox,
	QProgressDialog,
	QPushButton,
	QSizePolicy,
	QSlider,
	QSplitter,
	QStyle,
	QStyleOptionSlider,
	QTreeView,
	QVBoxLayout,
	QWidget,
)

from ore_music_player.application.playback_service import PlaybackService
from ore_music_player.application.playlist_service import PlaylistService
from ore_music_player.application.ports import PlaybackBackendError
from ore_music_player.application.separation_service import SeparationService
from ore_music_player.domain.models import (
	DEFAULT_PLAYBACK_SPEED,
	MAX_PLAYBACK_SPEED,
	MIN_PLAYBACK_SPEED,
	PLAYBACK_SPEED_STEP,
	Track,
)
from ore_music_player.infrastructure.audio.metadata import read_duration_seconds
from ore_music_player.infrastructure.playback_trace import trace_playback_event
from ore_music_player.infrastructure.settings import load_settings
from ore_music_player.infrastructure.update_service import (
	ReleaseInfo,
	download_release,
	fetch_latest_release,
	make_update_workspace,
	prepare_update,
	start_update_process,
	update_script_path,
)
from ore_music_player.ui.playlist_view import (
	PlaylistTrackSelection,
	PlaylistView,
)
from ore_music_player.ui.separation_worker import EnvSetupWorker, SeparationWorker
from ore_music_player.ui.utils import format_duration

TILE_BUTTON_SIZE = 112
TILE_GRID_SPACING = 4
SPEED_SLIDER_WIDTH = 160
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


class PlaybackMode(StrEnum):
	REPEAT_ALL = "repeat_all"
	SHUFFLE = "shuffle"
	REPEAT_ONE = "repeat_one"


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
	duration_loaded = Signal(str, object)

	def __init__(
		self,
		parent: QWidget | None = None,
		duration_cache: dict[str, float | None] | None = None,
	) -> None:
		super().__init__(parent)
		self._duration_cache = dict(duration_cache or {})

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
			path = str(Path(self.filePath(index)).absolute())
			if path not in self._duration_cache:
				duration = read_duration_seconds(path)
				self._duration_cache[path] = duration
				self.duration_loaded.emit(path, duration)
			return format_duration(self._duration_cache.get(path))
		return super().data(index, role)

	def set_duration(self, path: str, duration: float | None) -> None:
		normalized_path = str(Path(path).absolute())
		self._duration_cache[normalized_path] = duration
		self.duration_loaded.emit(normalized_path, duration)
		index = self.index(path)
		if index.isValid():
			duration_index = index.siblingAtColumn(1)
			self.dataChanged.emit(
				duration_index,
				duration_index,
				[Qt.ItemDataRole.DisplayRole],
			)


class RegisteredFoldersModel(QAbstractProxyModel):
	def __init__(self, source_model: AudioFileSystemModel, parent: QWidget | None = None) -> None:
		super().__init__(parent)
		self.setSourceModel(source_model)
		self._root_paths: tuple[Path, ...] = ()
		self._path_ids: dict[str, int] = {}
		self._id_paths: dict[int, str] = {}
		self._next_path_id = 1
		self._playing_path: str | None = None

	def set_root_paths(self, paths: set[Path]) -> None:
		self.beginResetModel()
		normalized_paths = {Path(path).absolute() for path in paths}
		self._root_paths = tuple(
			sorted(
				(
					path
					for path in normalized_paths
					if not any(
						path != other and other in path.parents
						for other in normalized_paths
					)
				),
				key=lambda path: str(path).casefold(),
			)
		)
		self._path_ids.clear()
		self._id_paths.clear()
		self._next_path_id = 1
		self.endResetModel()

	def _create_path_index(
		self,
		row: int,
		column: int,
		path: str,
		source_index: QModelIndex,
	) -> QModelIndex:
		path = str(Path(path).absolute())
		path_id = self._path_ids.get(path)
		if path_id is None:
			path_id = self._next_path_id
			self._next_path_id += 1
			self._path_ids[path] = path_id
			self._id_paths[path_id] = path
		return self.createIndex(row, column, path_id)

	def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
		return self.sourceModel().columnCount()

	def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
		if not parent.isValid():
			return len(self._root_paths)
		return self.sourceModel().rowCount(self.mapToSource(parent))

	def index(self, row, column=None, parent=QModelIndex()) -> QModelIndex:
		if isinstance(row, (str, Path)) and column is None:
			return self.index_for_path(row)
		if column is None:
			return QModelIndex()
		if row < 0 or column < 0:
			return QModelIndex()
		if not parent.isValid():
			if row >= len(self._root_paths):
				return QModelIndex()
			source_index = self.sourceModel().index(str(self._root_paths[row]))
		else:
			source_parent = self.mapToSource(parent)
			source_index = self.sourceModel().index(row, column, source_parent)
		if not source_index.isValid():
			return QModelIndex()
		return self._create_path_index(
			row,
			column,
			self.sourceModel().filePath(source_index),
			source_index,
		)

	def parent(self, child: QModelIndex) -> QModelIndex:
		if not child.isValid():
			return QModelIndex()
		source_index = self.mapToSource(child)
		source_parent = self.sourceModel().parent(source_index)
		if not source_parent.isValid():
			return QModelIndex()
		return self.mapFromSource(source_parent)

	def mapToSource(self, proxy_index: QModelIndex) -> QModelIndex:
		if not proxy_index.isValid():
			return QModelIndex()
		path = self._id_paths.get(proxy_index.internalId())
		if path is None:
			return QModelIndex()
		source_index = self.sourceModel().index(path)
		return source_index.siblingAtColumn(proxy_index.column())

	def mapFromSource(self, source_index: QModelIndex) -> QModelIndex:
		if not source_index.isValid():
			return QModelIndex()
		item_path = Path(self.sourceModel().filePath(source_index)).absolute()
		root = next(
			(
				root_path
				for root_path in self._root_paths
				if root_path == item_path or root_path in item_path.parents
			),
			None,
		)
		if root is None:
			return QModelIndex()
		if item_path == root:
			return self._create_path_index(
				self._root_paths.index(root),
				source_index.column(),
				str(item_path),
				source_index,
			)
		return self._create_path_index(
			source_index.row(),
			source_index.column(),
			str(item_path),
			source_index,
		)

	def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
		if role == Qt.ItemDataRole.BackgroundRole:
			path = self.filePath(index)
			if self._playing_path and Path(path).absolute() == Path(
				self._playing_path
			).absolute():
				return QColor("#b8d8e8")
		if role == Qt.ItemDataRole.ForegroundRole:
			path = self.filePath(index)
			if self._playing_path and Path(path).absolute() == Path(
				self._playing_path
			).absolute():
				return QColor("#102a43")
		return self.sourceModel().data(self.mapToSource(index), role)

	def set_playing_path(self, path: str | Path | None) -> None:
		previous_path = self._playing_path
		self._playing_path = str(Path(path).absolute()) if path else None
		for changed_path in (previous_path, self._playing_path):
			if not changed_path:
				continue
			index = self.index_for_path(changed_path)
			if index.isValid():
				self.dataChanged.emit(
					index,
					index.siblingAtColumn(self.columnCount() - 1),
					[Qt.ItemDataRole.BackgroundRole],
				)

	def flags(self, index: QModelIndex):
		return self.sourceModel().flags(self.mapToSource(index))

	def headerData(
		self,
		section: int,
		orientation: Qt.Orientation,
		role: int = Qt.ItemDataRole.DisplayRole,
	):
		return self.sourceModel().headerData(section, orientation, role)

	def filePath(self, index: QModelIndex) -> str:
		return self.sourceModel().filePath(self.mapToSource(index))

	def fileName(self, index: QModelIndex) -> str:
		return self.sourceModel().fileName(self.mapToSource(index))

	def mimeData(self, indexes: list[QModelIndex]):
		source_indexes = [
			self.mapToSource(index)
			for index in indexes
			if index.isValid() and index.column() == 0
		]
		return self.sourceModel().mimeData(source_indexes)

	def isDir(self, index: QModelIndex) -> bool:
		return self.sourceModel().isDir(self.mapToSource(index))

	def index_for_path(self, path: str | Path) -> QModelIndex:
		return self.mapFromSource(self.sourceModel().index(str(path)))

	def set_duration(self, path: str, duration: float | None) -> None:
		self.sourceModel().set_duration(path, duration)

	def setRootPath(self, path: str) -> QModelIndex:
		return self.sourceModel().setRootPath(path)

	def rootPath(self) -> str:
		return self.sourceModel().rootPath()


class UpdateWorker(QThread):
	no_update = Signal()
	update_ready = Signal(object)
	failed = Signal(str)

	def run(self) -> None:
		workspace: Path | None = None
		try:
			release = fetch_latest_release()
			if release is None:
				self.no_update.emit()
				return
			workspace = make_update_workspace()
			archive_path = download_release(
				release,
				workspace / "update.zip",
			)
			staged_application = prepare_update(
				archive_path,
				workspace / "staged",
			)
			self.update_ready.emit((release, staged_application))
		except Exception as error:
			if workspace is not None:
				shutil.rmtree(workspace, ignore_errors=True)
			self.failed.emit(str(error))


class MainWindow(QMainWindow):
	_SPLITTER_STATE_KEY = "leftPane/splitterState"
	_RIGHT_SPLITTER_STATE_KEY = "rightPane/splitterState"
	_SPLITTER_LAYOUT_VERSION_KEY = "leftPane/splitterLayoutVersion"
	_FILE_TREE_HEADER_STATE_KEY = "leftPane/fileTreeHeaderState"
	_WINDOW_GEOMETRY_KEY = "window/geometry"
	_FILE_TREE_ROOT_KEY = "leftPane/rootPath"
	_REGISTERED_PATHS_KEY = "leftPane/registeredPaths"
	_REGISTERED_FOLDERS_KEY = "leftPane/registeredFolders"
	_DURATION_CACHE_KEY = "metadata/durations"
	_DRIVE_ROOTS_GROUP = "leftPane/driveRoots"
	_VOLUME_KEY = "playback/volume"
	_RECENT_TRACKS_KEY = "playback/recentTracks"

	def __init__(
		self,
		playback_service: PlaybackService,
		playlist_service: PlaylistService,
		settings_path: str | Path | None = None,
		separation_service: SeparationService | None = None,
	) -> None:
		super().__init__()
		self.playback_service = playback_service
		self.playlist_service = playlist_service
		self._separation_service = separation_service
		self._separation_worker: SeparationWorker | None = None
		self._env_setup_worker: EnvSetupWorker | None = None
		self._settings = load_settings(
			settings_path or Path.cwd() / "data" / "settings.ini"
		)
		self._current_track: Track | None = None
		self._playback_playlist_id: str | None = None
		self._selected_playlist_track: PlaylistTrackSelection | None = None
		self._playback_mode = PlaybackMode.REPEAT_ALL
		self._queue: tuple[Track, ...] = ()
		self._queue_index = -1
		self._is_seeking = False
		self._is_playing = False
		self._duration_seconds = 0.0
		self._pending_restore_position: float | None = None
		self._shortcuts: list[QShortcut] = []
		self._update_worker: UpdateWorker | None = None
		self._layout_restored_after_show = False
		self._settings_save_timer = QTimer(self)
		self._settings_save_timer.setSingleShot(True)
		self._settings_save_timer.timeout.connect(self._save_left_pane_settings)
		self._hidden_file_paths: set[Path] = set()
		self._registered_paths: set[Path] = set()
		self._registered_folders: set[Path] = self._load_registered_folders()
		self._duration_cache_records = self._load_duration_cache_records()
		self._drive_roots = self._load_drive_roots()
		self._recent_paths = self._load_recent_paths()
		self._file_tree_filter = ""
		splitter_layout_version = self._settings.value(
			self._SPLITTER_LAYOUT_VERSION_KEY,
			0,
			type=int,
		)
		splitter_state = self._settings.value(
			self._SPLITTER_STATE_KEY,
			QByteArray(),
		)
		has_saved_splitter_state = (
			isinstance(splitter_state, QByteArray)
			and not splitter_state.isEmpty()
		)
		self._splitter_migration_pending = (
			has_saved_splitter_state and splitter_layout_version < 17
		)
		self._splitter_migration_delta = (
			100
			if splitter_layout_version >= 16
			else 75
			if splitter_layout_version >= 15
			else 50
			if splitter_layout_version >= 14
			else 100
			if splitter_layout_version >= 13
			else 170
		)

		self.setWindowTitle("Ore Music Player")
		icon_path = Path(__file__).resolve().parents[1] / "assets" / "app_icon.ico"
		self.setWindowIcon(QIcon(str(icon_path)))
		self.resize(1209, 770)
		self._create_file_menu()

		central_widget = QWidget()
		layout = QVBoxLayout(central_widget)
		layout.setContentsMargins(0, 0, 0, 0)
		splitter = QSplitter(Qt.Orientation.Horizontal)
		self.main_splitter = splitter
		splitter.splitterMoved.connect(self._schedule_left_pane_settings_save)
		layout.addWidget(splitter)

		file_panel = QWidget()
		file_panel.setMinimumWidth(0)
		file_layout = QVBoxLayout(file_panel)
		file_layout.setContentsMargins(0, 0, 0, 0)
		self.file_root_label = QLabel()
		self.file_root_label.setSizePolicy(
			QSizePolicy.Policy.Ignored,
			QSizePolicy.Policy.Fixed,
		)
		self.file_root_label.setTextInteractionFlags(
			Qt.TextInteractionFlag.TextSelectableByMouse
		)
		self.drive_selector = QComboBox(self)
		self.drive_selector.setPlaceholderText("登録ドライブ")
		self.drive_selector.currentTextChanged.connect(self._switch_drive)
		self.drive_selector.setVisible(False)
		file_layout.addWidget(self.drive_selector)
		self.file_filter_edit = QLineEdit()
		self.file_filter_edit.setPlaceholderText("ファイルを検索")
		self.file_filter_edit.setClearButtonEnabled(True)
		self.file_filter_edit.textChanged.connect(self._filter_file_tree)
		file_layout.addWidget(self.file_filter_edit)
		self._source_file_system_model = AudioFileSystemModel(
			self,
			duration_cache=self._valid_duration_cache(),
		)
		self._source_file_system_model.duration_loaded.connect(
			self._remember_duration
		)
		self._source_file_system_model.setFilter(
			QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.Dirs
		)
		self._source_file_system_model.setNameFilters(SUPPORTED_AUDIO_NAME_FILTERS)
		self._source_file_system_model.setNameFilterDisables(False)
		self.file_system_model = RegisteredFoldersModel(
			self._source_file_system_model,
			self,
		)
		self._sync_file_tree_roots()
		default_root_path = Path(QDir.currentPath()).anchor or QDir.rootPath()
		root_path = self._settings.value(
			self._FILE_TREE_ROOT_KEY,
			default_root_path,
			type=str,
		)
		self._source_file_system_model.setRootPath(root_path)
		self.file_root_label.setText(root_path)
		self.file_tree = QTreeView()
		self.file_tree.setSizePolicy(
			QSizePolicy.Policy.Ignored,
			QSizePolicy.Policy.Expanding,
		)
		self.file_tree.setMinimumSize(0, 0)
		self.file_tree.setModel(self.file_system_model)
		self.file_tree.setSelectionMode(
			QAbstractItemView.SelectionMode.ExtendedSelection
		)
		self.file_tree.setSelectionBehavior(
			QAbstractItemView.SelectionBehavior.SelectRows
		)
		self.file_tree.setDragEnabled(True)
		self.file_tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
		self.file_tree.setUniformRowHeights(True)
		self.file_tree.setRootIndex(QModelIndex())
		self.file_tree.header().setStretchLastSection(False)
		self.file_tree.setColumnWidth(0, 250)
		self.file_tree.setColumnWidth(1, 65)
		self._restore_left_pane_settings()
		self.file_tree.doubleClicked.connect(self._load_file_from_tree)
		self.file_tree.selectionModel().selectionChanged.connect(
			self._update_delete_button_state
		)
		self.file_tree.selectionModel().currentChanged.connect(
			self._update_file_tree_path
		)
		self._source_file_system_model.directoryLoaded.connect(
			self._update_file_tree_visibility
		)
		file_layout.addWidget(self.file_tree)
		self._restore_registered_tracks()
		splitter.addWidget(file_panel)
		self.delete_file_button = QPushButton("削除")
		self.delete_file_button.setEnabled(False)
		self.delete_file_button.clicked.connect(self.delete_selected_files)
		file_layout.addWidget(self.delete_file_button)

		right_splitter = QSplitter(Qt.Orientation.Vertical)
		self.right_splitter = right_splitter
		right_splitter.splitterMoved.connect(self._schedule_left_pane_settings_save)
		splitter.addWidget(right_splitter)
		splitter.setStretchFactor(0, 1)
		splitter.setStretchFactor(1, 2)
		splitter.setSizes([345, 615])

		player_widget = QWidget()
		player_layout = QVBoxLayout(player_widget)
		player_layout.setContentsMargins(0, 0, 0, 0)
		player_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

		self.track_label = QLabel("曲が選択されていません")
		self.status_label = QLabel("停止中")
		label_size_policy = QSizePolicy(
			QSizePolicy.Policy.Ignored,
			QSizePolicy.Policy.Fixed,
		)
		self.track_label.setSizePolicy(label_size_policy)
		self.status_label.setSizePolicy(label_size_policy)
		track_status_layout = QHBoxLayout()
		track_status_layout.setContentsMargins(0, 0, 0, 0)
		track_status_layout.setSpacing(0)
		track_status_layout.addWidget(self.track_label, 1)
		player_layout.addLayout(track_status_layout)

		button_grid = QGridLayout()
		button_grid.setHorizontalSpacing(TILE_GRID_SPACING)
		button_grid.setVerticalSpacing(TILE_GRID_SPACING)

		control_button_size = 96
		self.previous_button = self._create_tile_button(
			"前の曲",
			self.previous_track,
			control_button_size,
		)
		button_grid.addWidget(self.previous_button, 0, 0)

		self.play_pause_button = self._create_tile_button(
			"再生",
			self.toggle_play_pause,
			control_button_size,
		)

		button_grid.addWidget(self.play_pause_button, 0, 1)

		self.stop_button = self._create_tile_button(
			"停止",
			self.stop,
			control_button_size,
		)
		button_grid.addWidget(self.stop_button, 0, 2)

		self.next_button = self._create_tile_button(
			"次の曲",
			self.next_track,
			control_button_size,
		)
		button_grid.addWidget(self.next_button, 0, 3)

		self.set_a_button = self._create_tile_button(
			"A設定",
			self.set_a,
			control_button_size,
		)
		button_grid.addWidget(self.set_a_button, 0, 4)
		self.set_b_button = self._create_tile_button(
			"B設定",
			self.set_b,
			control_button_size,
		)
		button_grid.addWidget(self.set_b_button, 0, 5)
		self.loop_button = self._create_tile_button(
			"A/Bループ\n開始",
			self.toggle_loop,
			control_button_size,
		)
		self.loop_button.setEnabled(False)
		button_grid.addWidget(self.loop_button, 0, 6)
		self.playback_mode_button = self._create_tile_button(
			self._playback_mode_text(self._playback_mode),
			self.toggle_playback_mode,
			control_button_size,
		)
		button_grid.addWidget(self.playback_mode_button, 0, 7)
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

		self.speed_label = QLabel("再生速度")
		self.speed_label.setSizePolicy(
			QSizePolicy.Policy.Fixed,
			QSizePolicy.Policy.Fixed,
		)
		min_speed_label = QLabel(f"{MIN_PLAYBACK_SPEED:.2f}x")
		min_speed_label.setSizePolicy(
			QSizePolicy.Policy.Fixed,
			QSizePolicy.Policy.Fixed,
		)
		self.speed_slider = QSlider()
		self._configure_slider(self.speed_slider)
		self.speed_slider.setFixedWidth(SPEED_SLIDER_WIDTH)
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
		self.speed_min_label = min_speed_label
		self.speed_current_label = QLabel()
		self.speed_current_label.setSizePolicy(
			QSizePolicy.Policy.Fixed,
			QSizePolicy.Policy.Fixed,
		)
		speed_row_layout = QHBoxLayout()
		speed_row_layout.setContentsMargins(0, 0, 0, 0)
		speed_row_layout.setSpacing(8)
		speed_row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
		speed_row_layout.addWidget(self.speed_label)
		speed_row_layout.addWidget(min_speed_label)
		speed_row_layout.addWidget(self.speed_slider)
		speed_row_layout.addWidget(self.speed_current_label)

		self.volume_label = QLabel("音量")
		self.volume_label.setAlignment(
			Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
		)
		self.volume_label.setSizePolicy(
			QSizePolicy.Policy.Fixed,
			QSizePolicy.Policy.Fixed,
		)
		self.volume_min_label = QLabel("0")
		self.volume_min_label.setSizePolicy(
			QSizePolicy.Policy.Fixed,
			QSizePolicy.Policy.Fixed,
		)
		self.volume_value_label = QLabel()
		self.volume_value_label.setSizePolicy(
			QSizePolicy.Policy.Fixed,
			QSizePolicy.Policy.Fixed,
		)
		self.volume_slider = QSlider(Qt.Orientation.Horizontal)
		self._configure_slider(self.volume_slider)
		self.volume_slider.setRange(0, 100)
		saved_volume = self._settings.value(self._VOLUME_KEY, 100, type=int)
		self.volume_slider.setValue(max(0, min(100, saved_volume)))
		self.volume_slider.setFixedWidth(SPEED_SLIDER_WIDTH)
		self.volume_slider.setToolTip("音量")
		self.volume_slider.valueChanged.connect(self.change_volume)
		volume_layout = QHBoxLayout()
		volume_layout.setContentsMargins(0, 0, 0, 0)
		volume_layout.setSpacing(8)
		volume_layout.addWidget(self.volume_label)
		volume_layout.addWidget(self.volume_min_label)
		volume_layout.addWidget(self.volume_slider)
		volume_layout.addWidget(self.volume_value_label)
		self.change_volume(self.volume_slider.value())
		speed_row_layout.addLayout(volume_layout)
		speed_row_layout.addStretch(1)
		bars_layout.addLayout(speed_row_layout, 1, 0, 1, 4)

		player_layout.addLayout(bars_layout)
		self._update_speed_label(self.speed_slider.value())

		self._position_timer = QTimer(self)
		self._position_timer.setInterval(250)
		self._position_timer.timeout.connect(self._update_position)
		self._position_timer.start()

		playlist_view = PlaylistView(playlist_service)
		self.playlist_view = playlist_view
		playlist_view.play_requested.connect(self.load_playlist_track_selection)
		playlist_view.track_selected.connect(self._set_selected_playlist_track)
		playlist_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
		playlist_view.customContextMenuRequested.connect(self._show_playlist_context_menu)
		player_widget.setMaximumHeight(player_widget.sizeHint().height())
		right_splitter.addWidget(player_widget)
		right_splitter.addWidget(playlist_view)
		right_splitter.setStretchFactor(0, 0)
		right_splitter.setStretchFactor(1, 1)
		right_splitter.setSizes([player_widget.sizeHint().height(), 430])
		self._restore_right_splitter_state()

		self.setCentralWidget(central_widget)
		self._restore_window_geometry()
		self._create_shortcuts()
		self._restore_splitter_state()

	def showEvent(self, event) -> None:
		super().showEvent(event)
		if not self._layout_restored_after_show:
			self._layout_restored_after_show = True
			self._restore_splitter_state()
			self._restore_right_splitter_state()
		if self._splitter_migration_pending:
			self._splitter_migration_pending = False
			QTimer.singleShot(100, self._move_splitter_right)

	def _move_splitter_right(self) -> None:
		sizes = self.main_splitter.sizes()
		delta = self._splitter_migration_delta
		if len(sizes) == 2 and sizes[1] > delta:
			self.main_splitter.setSizes([sizes[0] + delta, sizes[1] - delta])
			self._settings.setValue(self._SPLITTER_LAYOUT_VERSION_KEY, 17)

	def _restore_left_pane_settings(self) -> None:
		header_state = self._settings.value(
			self._FILE_TREE_HEADER_STATE_KEY,
			QByteArray(),
		)
		if isinstance(header_state, QByteArray) and not header_state.isEmpty():
			self.file_tree.header().restoreState(header_state)

	def _restore_right_splitter_state(self) -> bool:
		splitter_state = self._settings.value(
			self._RIGHT_SPLITTER_STATE_KEY,
			QByteArray(),
		)
		return (
			isinstance(splitter_state, QByteArray)
			and not splitter_state.isEmpty()
			and self.right_splitter.restoreState(splitter_state)
		)

	def _restore_window_geometry(self) -> bool:
		geometry = self._settings.value(
			self._WINDOW_GEOMETRY_KEY,
			QByteArray(),
		)
		return (
			isinstance(geometry, QByteArray)
			and not geometry.isEmpty()
			and self.restoreGeometry(geometry)
		)

	def _restore_splitter_state(self) -> bool:
		splitter_state = self._settings.value(
			self._SPLITTER_STATE_KEY,
			QByteArray(),
		)
		restored = (
			isinstance(splitter_state, QByteArray)
			and not splitter_state.isEmpty()
			and self.main_splitter.restoreState(splitter_state)
		)
		if restored and self._settings.value(
			self._SPLITTER_LAYOUT_VERSION_KEY,
			0,
			type=int,
		) < 2:
			sizes = self.main_splitter.sizes()
			if len(sizes) == 2:
				self.main_splitter.setSizes([170, max(1, sum(sizes) - 170)])
			self._settings.setValue(self._SPLITTER_LAYOUT_VERSION_KEY, 2)
		return restored

	def _schedule_left_pane_settings_save(self, *_args) -> None:
		self._settings_save_timer.start(150)

	def _save_left_pane_settings(self, *_args) -> None:
		self._settings_save_timer.stop()
		self._settings.setValue(
			self._SPLITTER_STATE_KEY,
			self.main_splitter.saveState(),
		)
		self._settings.setValue(
			self._RIGHT_SPLITTER_STATE_KEY,
			self.right_splitter.saveState(),
		)
		self._settings.setValue(
			self._WINDOW_GEOMETRY_KEY,
			self.saveGeometry(),
		)
		self._settings.setValue(self._SPLITTER_LAYOUT_VERSION_KEY, 17)
		self._settings.setValue(
			self._FILE_TREE_HEADER_STATE_KEY,
			self.file_tree.header().saveState(),
		)
		self._settings.setValue(
			self._FILE_TREE_ROOT_KEY,
			self.file_root_label.text(),
		)
		self._settings.setValue(self._VOLUME_KEY, self.volume_slider.value())
		self._save_registered_paths()
		self._settings.sync()

	def closeEvent(self, event) -> None:
		self._position_timer.stop()
		self._save_left_pane_settings()
		super().closeEvent(event)

	@staticmethod
	def _create_tile_button(
		text: str,
		handler,
		size: int = TILE_BUTTON_SIZE,
	) -> QPushButton:
		button = QPushButton(text)
		button.setFixedSize(size, size)
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

		self.check_update_action = QAction("更新を確認", self)
		self.check_update_action.triggered.connect(self.check_for_updates)
		file_menu.addAction(self.check_update_action)

		self.recent_menu = self.menuBar().addMenu("最近再生")
		self._refresh_recent_menu()

	def check_for_updates(self) -> None:
		if not getattr(sys, "frozen", False):
			QMessageBox.information(
				self,
				"更新確認",
				"更新確認はExe版で起動したときに利用できます。",
			)
			return
		if self._update_worker is not None and self._update_worker.isRunning():
			return
		self.check_update_action.setEnabled(False)
		self._update_worker = UpdateWorker(self)
		self._update_worker.no_update.connect(self._show_no_update)
		self._update_worker.update_ready.connect(self._confirm_update)
		self._update_worker.failed.connect(self._show_update_error)
		self._update_worker.finished.connect(self._update_finished)
		self._update_worker.start()

	def _show_no_update(self) -> None:
		QMessageBox.information(self, "更新確認", "現在のバージョンは最新版です。")

	def _confirm_update(self, payload: object) -> None:
		release, staged_application = payload
		if not isinstance(release, ReleaseInfo) or not isinstance(staged_application, Path):
			self._show_update_error("更新データの形式が不正です")
			return
		answer = QMessageBox.question(
			self,
			"更新があります",
			f"バージョン {release.version} に更新します。アプリを再起動しますか？",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
			QMessageBox.StandardButton.Yes,
		)
		if answer != QMessageBox.StandardButton.Yes:
			return
		try:
			start_update_process(
				staged_application,
				Path(sys.executable).resolve().parent,
				update_script_path(),
			)
			self.close()
		except Exception as error:
			self._show_update_error(str(error))

	def _show_update_error(self, message: str) -> None:
		QMessageBox.critical(self, "更新失敗", f"更新を確認できませんでした。\n{message}")

	def _update_finished(self) -> None:
		self.check_update_action.setEnabled(True)
		self._update_worker = None

	def _refresh_recent_menu(self) -> None:
		self.recent_menu.clear()
		if not self._recent_paths:
			empty_action = QAction("履歴なし", self)
			empty_action.setEnabled(False)
			self.recent_menu.addAction(empty_action)
			return

		for path in self._recent_paths:
			action = QAction(path.name, self)
			action.setToolTip(str(path))
			action.triggered.connect(
				lambda _checked=False, selected_path=path: self._play_recent_path(
					selected_path
				)
			)
			self.recent_menu.addAction(action)

	def _load_recent_paths(self) -> list[Path]:
		saved_paths = self._settings.value(self._RECENT_TRACKS_KEY, []) or []
		if isinstance(saved_paths, str):
			saved_paths = [saved_paths]
		return [
			Path(path)
			for path in saved_paths
			if str(path).strip() and Path(path).is_file()
		][:10]

	def _record_recent_path(self, path: str | Path) -> None:
		normalized_path = self._normalize_path(path)
		self._recent_paths = [
			normalized_path,
			*(recent_path for recent_path in self._recent_paths if recent_path != normalized_path),
		][:10]
		self._settings.setValue(
			self._RECENT_TRACKS_KEY,
			[str(recent_path) for recent_path in self._recent_paths],
		)
		self._settings.sync()
		self._refresh_recent_menu()

	def _play_recent_path(self, path: Path) -> None:
		if (
			not path.is_file()
			or path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES
		):
			self._recent_paths = [
				recent_path
				for recent_path in self._recent_paths
				if recent_path != path
			]
			self._settings.setValue(
				self._RECENT_TRACKS_KEY,
				[str(recent_path) for recent_path in self._recent_paths],
			)
			self._refresh_recent_menu()
			return
		track = Track(
			track_id=str(uuid4()),
			path=str(path),
			title=path.stem,
			duration_seconds=read_duration_seconds(path),
		)
		self.load_tracks((track,))

	def _create_shortcuts(self) -> None:
		shortcut_handlers = (
			("Space", self.toggle_play_pause),
			("A", self.set_a),
			("B", self.set_b),
			("S", self.toggle_loop),
			("Left", self.seek_backward),
			("Right", self.seek_forward),
			("Ctrl+Left", self.previous_track),
			("Ctrl+Right", self.next_track),
		)
		for sequence, handler in shortcut_handlers:
			shortcut = QShortcut(QKeySequence(sequence), self)
			shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
			shortcut.activated.connect(handler)
			self._shortcuts.append(shortcut)

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
			self._registered_folders.add(Path(file_paths[0]).parent.resolve())
			self._save_registered_folders()
			self._sync_file_tree_roots()
			self._set_file_tree_root(Path(file_paths[0]).parent)
			self._append_tracks(self._tracks_from_paths(file_paths, read_durations=False))
			self._update_file_tree_visibility()

	def open_folder(self) -> None:
		folder_path = QFileDialog.getExistingDirectory(self, "音声フォルダを選択")
		if not folder_path:
			return
		self._registered_folders.add(Path(folder_path).resolve())
		self._save_registered_folders()
		self._sync_file_tree_roots()
		self._set_file_tree_root(folder_path)
		paths = (
			path
			for path in Path(folder_path).rglob("*")
			if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES
		)
		self._append_tracks(self._tracks_from_paths(paths, read_durations=False))
		self._update_file_tree_visibility()

	def _load_file_from_tree(self, index: QModelIndex) -> None:
		trace_playback_event(
			"tree_double_clicked",
			index_valid=index.isValid(),
			index_path=(self.file_system_model.filePath(index) if index.isValid() else None),
			current_path=(self._current_track.path if self._current_track else None),
			queue_index=self._queue_index,
		)
		if not index.isValid() or self.file_system_model.isDir(index):
			return
		path = Path(self.file_system_model.filePath(index))
		if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
			return
		self._select_file_path(path, autoplay=True)

	def _selected_unregister_paths(self) -> tuple[Path, ...]:
		return tuple(
			Path(self.file_system_model.filePath(index))
			for index in self.file_tree.selectionModel().selectedRows(0)
			if index.isValid()
			and (
				self.file_system_model.isDir(index)
				or (
					Path(self.file_system_model.filePath(index)).is_file()
					and Path(self.file_system_model.filePath(index)).suffix.lower()
					in SUPPORTED_AUDIO_SUFFIXES
				)
			)
		)

	def _selected_audio_paths(self) -> tuple[Path, ...]:
		return tuple(
			path
			for path in self._selected_unregister_paths()
			if path.is_file()
		)

	def _update_delete_button_state(self, *_args) -> None:
		self.delete_file_button.setEnabled(bool(self._selected_unregister_paths()))

	def _filter_file_tree(self, text: str) -> None:
		self._file_tree_filter = text.strip().casefold()
		self._update_file_tree_visibility()

	def delete_selected_files(self) -> None:
		selected_paths = self._selected_unregister_paths()
		if not selected_paths:
			return

		file_list = "\n".join(f"・{path.name}" for path in selected_paths)
		answer = QMessageBox.warning(
			self,
			"左ペインから登録解除",
			f"選択した{len(selected_paths)}個の項目を左ペインから登録解除します。\n"
			f"{file_list}",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
			QMessageBox.StandardButton.No,
		)
		if answer != QMessageBox.StandardButton.Yes:
			return

		normalized_paths = tuple(self._normalize_path(path) for path in selected_paths)
		removed_audio_paths = tuple(
			path
			for path in self._registered_paths
			if any(path == selected or selected in path.parents for selected in normalized_paths)
		)
		self._hidden_file_paths.update(normalized_paths)
		self._registered_paths.difference_update(removed_audio_paths)
		self._registered_folders = {
			folder
			for folder in self._registered_folders
			if not any(
				folder == selected or selected in folder.parents
				for selected in normalized_paths
			)
		}
		self._sync_file_tree_roots()
		self._remove_unregistered_tracks(removed_audio_paths)
		self._save_registered_paths()
		self._save_registered_folders()
		self._update_file_tree_visibility()
		self._hide_paths_from_file_tree(selected_paths)
		self.file_tree.clearSelection()
		self._update_delete_button_state()

	def _update_file_tree_visibility(
		self,
		loaded_path: str | None = None,
		parent_index: QModelIndex | None = None,
	) -> None:
		registered_paths = set(self._registered_paths)
		registered_folders = set(self._registered_folders)
		filter_text = self._file_tree_filter
		if parent_index is None:
			parent_index = self.file_tree.rootIndex()
			if loaded_path:
				loaded_index = self.file_system_model.index(loaded_path)
				if loaded_index.isValid():
					parent_index = loaded_index

		for row in range(self.file_system_model.rowCount(parent_index)):
			index = self.file_system_model.index(row, 0, parent_index)
			path = self._normalize_path(self.file_system_model.filePath(index))
			if path in self._hidden_file_paths:
				is_visible = False
			elif self.file_system_model.isDir(index):
				is_visible = any(
					registered_path == path or path in registered_path.parents
					for registered_path in registered_paths | registered_folders
				)
			else:
				is_visible = path in registered_paths
			if is_visible and filter_text:
				if self.file_system_model.isDir(index):
					is_visible = any(
						filter_text in registered_path.name.casefold()
						and (
							registered_path == path
							or path in registered_path.parents
						)
						for registered_path in registered_paths
					)
				else:
					is_visible = filter_text in path.name.casefold()
			self.file_tree.setRowHidden(row, parent_index, not is_visible)
			if self.file_system_model.isDir(index):
				self._update_file_tree_visibility(parent_index=index)

	def _hide_paths_from_file_tree(self, paths: list[Path] | tuple[Path, ...]) -> None:
		for path in paths:
			index = self.file_system_model.index(str(path))
			if index.isValid():
				self.file_tree.setRowHidden(index.row(), index.parent(), True)

	@staticmethod
	def _normalize_path(path: str | Path) -> Path:
		return Path(path).absolute()

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
			self._playback_playlist_id = None
			self.file_system_model.set_playing_path(None)
			self.playlist_view.set_playing_track(None, None)
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
		path_object = Path(root_path).resolve()
		path = str(path_object)
		source_root = path_object.anchor or path
		self._source_file_system_model.setRootPath(source_root)
		self._sync_file_tree_roots()
		self.file_tree.setRootIndex(QModelIndex())
		self.file_root_label.setText(path)
		if path_object.anchor:
			self._drive_roots[path_object.anchor] = path_object
			self._save_drive_roots()
		self._select_drive_for_path(path)
		self._settings.setValue(self._FILE_TREE_ROOT_KEY, path)
		self._settings.sync()

	def _switch_drive(self, drive_root: str) -> None:
		if drive_root:
			root_path = self._drive_root_path(drive_root)
			self._set_file_tree_root(root_path)

	def _drive_root_path(self, drive_root: str) -> Path:
		for folder in sorted(
			self._registered_folders,
			key=lambda value: str(value).casefold(),
		):
			if folder.anchor.casefold() == drive_root.casefold():
				return folder
		for anchor, path in self._drive_roots.items():
			if anchor.casefold() == drive_root.casefold() and path.is_dir():
				return path
		for path in sorted(
			self._registered_paths,
			key=lambda value: str(value).casefold(),
		):
			if path.anchor.casefold() == drive_root.casefold():
				return path.parent
		return Path(drive_root)

	def _load_registered_folders(self) -> set[Path]:
		saved_paths = self._settings.value(self._REGISTERED_FOLDERS_KEY, []) or []
		if isinstance(saved_paths, str):
			saved_paths = [saved_paths]
		return {Path(path).resolve() for path in saved_paths if str(path).strip()}

	def _save_registered_folders(self) -> None:
		self._settings.setValue(
			self._REGISTERED_FOLDERS_KEY,
			[
				str(path)
				for path in sorted(
					self._registered_folders,
					key=lambda value: str(value).casefold(),
				)
			],
		)
		self._settings.sync()

	@staticmethod
	def _common_root(first_path: str | Path, second_path: str | Path) -> Path:
		common_root = Path(first_path).resolve()
		other_path = Path(second_path).resolve()
		while (
			common_root != other_path
			and common_root not in other_path.parents
			and common_root != common_root.parent
		):
			common_root = common_root.parent
		return common_root

	def _load_drive_roots(self) -> dict[str, Path]:
		self._settings.beginGroup(self._DRIVE_ROOTS_GROUP)
		roots = {
			key: Path(value)
			for key in self._settings.childKeys()
			if (value := self._settings.value(key, "", type=str)).strip()
		}
		self._settings.endGroup()
		return roots

	def _save_drive_roots(self) -> None:
		self._settings.beginGroup(self._DRIVE_ROOTS_GROUP)
		self._settings.remove("")
		for anchor, path in self._drive_roots.items():
			self._settings.setValue(anchor, str(path))
		self._settings.endGroup()
		self._settings.sync()

	def _refresh_drive_selector(self) -> None:
		drive_roots = sorted(
			{
				path.anchor
				for path in self._registered_paths
				if path.anchor
			},
			key=str.casefold,
		)
		current_root = self.drive_selector.currentText()
		self.drive_selector.blockSignals(True)
		self.drive_selector.clear()
		self.drive_selector.addItems(drive_roots)
		self.drive_selector.blockSignals(False)
		self.drive_selector.setVisible(len(drive_roots) > 1)
		if current_root in drive_roots:
			self.drive_selector.setCurrentText(current_root)
		elif drive_roots:
			self._select_drive_for_path(self.file_root_label.text())

	def _select_drive_for_path(self, path: str | Path) -> None:
		drive_root = Path(path).anchor
		if drive_root and self.drive_selector.findText(drive_root) >= 0:
			self.drive_selector.blockSignals(True)
			self.drive_selector.setCurrentText(drive_root)
			self.drive_selector.blockSignals(False)

	def _load_duration_cache_records(self) -> dict[str, tuple[int, float | None]]:
		raw_value = self._settings.value(self._DURATION_CACHE_KEY, "", type=str)
		if not raw_value:
			return {}
		try:
			raw_records = json.loads(raw_value)
		except (TypeError, ValueError):
			return {}
		if not isinstance(raw_records, dict):
			return {}

		records: dict[str, tuple[int, float | None]] = {}
		for path, record in raw_records.items():
			if not isinstance(path, str) or not isinstance(record, list):
				continue
			if len(record) != 2 or not isinstance(record[0], int):
				continue
			duration = record[1]
			if duration is not None and not isinstance(duration, (int, float)):
				continue
			records[path] = (record[0], duration)
		return records

	def _valid_duration_cache(self) -> dict[str, float | None]:
		cache: dict[str, float | None] = {}
		for path, (modified_ns, duration) in self._duration_cache_records.items():
			try:
				if Path(path).stat().st_mtime_ns == modified_ns:
					cache[path] = duration
			except OSError:
				continue
		return cache

	def _remember_duration(self, path: str, duration: object) -> None:
		try:
			modified_ns = Path(path).stat().st_mtime_ns
		except OSError:
			return
		if duration is not None and not isinstance(duration, (int, float)):
			return
		self._duration_cache_records[path] = (modified_ns, duration)
		serialized = {
			cached_path: [record[0], record[1]]
			for cached_path, record in self._duration_cache_records.items()
		}
		self._settings.setValue(
			self._DURATION_CACHE_KEY,
			json.dumps(serialized),
		)

	def _save_registered_paths(self) -> None:
		self._settings.setValue(
			self._REGISTERED_PATHS_KEY,
			[
				str(path)
				for path in sorted(
					self._registered_paths,
					key=lambda value: str(value).casefold(),
				)
			],
		)

	def _restore_registered_tracks(self) -> None:
		saved_paths = self._settings.value(self._REGISTERED_PATHS_KEY, []) or []
		if isinstance(saved_paths, str):
			saved_paths = [saved_paths]
		playlist_paths = [
			track.path
			for playlist in self.playlist_service.list_all()
			for track in playlist.tracks
		]
		self._registered_paths = {
			self._normalize_path(path) for path in saved_paths if str(path).strip()
		}
		self._registered_paths.update(
			self._normalize_path(path)
			for path in playlist_paths
			if str(path).strip()
		)
		existing_paths = {
			path
			for path in self._registered_paths
			if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES
		}
		self._registered_paths = existing_paths
		self._registered_folders = {
			folder
			for folder in self._registered_folders
			if any(folder == path or folder in path.parents for path in existing_paths)
		}
		self._sync_file_tree_roots()
		self._save_registered_paths()
		self._save_registered_folders()
		self._settings.remove(self._FILE_TREE_ROOT_KEY)
		if self._registered_folders:
			self._set_file_tree_root(next(iter(self._registered_folders)))
		self._refresh_drive_selector()
		existing_paths = tuple(existing_paths)
		if not existing_paths:
			return

		self._queue = self._tracks_from_paths(existing_paths, read_durations=False)
		self._queue_index = 0
		self._update_file_tree_visibility()

	def _register_tracks(self, tracks: tuple[Track, ...]) -> None:
		self._registered_paths.update(self._normalize_path(track.path) for track in tracks)
		for track in tracks:
			if track.duration_seconds is not None:
				self.file_system_model.set_duration(
					track.path,
					track.duration_seconds,
				)
		self._sync_file_tree_roots()
		self._refresh_drive_selector()
		self._save_registered_paths()

	def _sync_file_tree_roots(self) -> None:
		expanded_paths = self._expanded_file_tree_paths()
		file_roots = {
			path.parent
			for path in self._registered_paths
			if path.is_file()
		}
		self.file_system_model.set_root_paths(self._registered_folders | file_roots)
		if expanded_paths and hasattr(self, "file_tree"):
			QTimer.singleShot(
				0,
				lambda: self._restore_expanded_file_tree_paths(expanded_paths),
			)

	def _expanded_file_tree_paths(self) -> set[Path]:
		if not hasattr(self, "file_tree"):
			return set()

		expanded_paths: set[Path] = set()

		def collect(parent: QModelIndex = QModelIndex()) -> None:
			for row in range(self.file_system_model.rowCount(parent)):
				index = self.file_system_model.index(row, 0, parent)
				if not index.isValid() or not self.file_system_model.isDir(index):
					continue
				if self.file_tree.isExpanded(index):
					expanded_paths.add(
						Path(self.file_system_model.filePath(index)).resolve()
					)
					collect(index)

		collect()
		return expanded_paths

	def _restore_expanded_file_tree_paths(self, paths: set[Path]) -> None:
		for path in paths:
			index = self.file_system_model.index(str(path))
			if index.isValid():
				self.file_tree.expand(index)

	def _tracks_from_paths(
		self,
		paths: tuple[str | Path, ...] | list[str] | set[Path],
		read_durations: bool = True,
	) -> tuple[Track, ...]:
		sorted_paths = sorted(paths, key=lambda path: str(path).casefold())
		return tuple(
			Track(
				track_id=str(uuid4()),
				path=str(path),
				title=Path(path).stem,
				duration_seconds=read_duration_seconds(path)
				if read_durations
				else None,
			)
			for path in sorted_paths
		)

	def load_tracks(
		self,
		tracks: tuple[Track, ...],
		index: int = 0,
		playlist_id: str | None = None,
	) -> None:
		if not tracks or not 0 <= index < len(tracks):
			return
		self._playback_playlist_id = playlist_id
		self._queue = tracks
		self._queue_index = index
		self._register_tracks(tracks)
		self._update_file_tree_visibility()
		self._load_current_track(autoplay=True)

	def _append_tracks(self, tracks: tuple[Track, ...]) -> None:
		if not tracks:
			return

		existing_paths = {Path(track.path) for track in self._queue}
		new_tracks = tuple(
			track for track in tracks if Path(track.path) not in existing_paths
		)
		if not new_tracks:
			return

		if not self._queue:
			self.load_tracks(new_tracks)
			return

		self._queue = self._queue + new_tracks
		self._register_tracks(new_tracks)
		self._update_file_tree_visibility()

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
			selection_model = self.file_tree.selectionModel()
			selection_model.clearSelection()
			selection_model.select(
				index,
				QItemSelectionModel.SelectionFlag.ClearAndSelect
				| QItemSelectionModel.SelectionFlag.Rows,
			)
			selection_model.setCurrentIndex(
				index,
				QItemSelectionModel.SelectionFlag.NoUpdate,
			)
			self.file_tree.scrollTo(index)

	def _update_file_tree_path(
		self,
		current: QModelIndex,
		_previous: QModelIndex,
	) -> None:
		if not current.isValid():
			return
		selected_path = Path(self.file_system_model.filePath(current))
		trace_playback_event(
			"tree_current_changed",
			path=str(selected_path),
			is_dir=self.file_system_model.isDir(current),
			current_path=(self._current_track.path if self._current_track else None),
			queue_index=self._queue_index,
		)
		folder_path = (
			selected_path if self.file_system_model.isDir(current) else selected_path.parent
		)
		self.file_root_label.setText(str(folder_path))
		if (
			self.file_system_model.isDir(current)
			or selected_path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES
		):
			return

	def _select_file_from_tree(self, index: QModelIndex, autoplay: bool) -> None:
		path = self._normalize_path(self.file_system_model.filePath(index))
		self._select_file_path(path, autoplay)

	def _select_file_path(self, path: str | Path, autoplay: bool) -> None:
		path = self._normalize_path(path)
		trace_playback_event(
			"select_file_path",
			path=str(path),
			autoplay=autoplay,
			current_path=(self._current_track.path if self._current_track else None),
			queue_index=self._queue_index,
		)
		if (
			autoplay
			and self._is_playing
			and self._current_track is not None
			and self._normalize_path(self._current_track.path) == path
		):
			return
		track_index = next(
			(
				queue_index
				for queue_index, track in enumerate(self._queue)
				if self._normalize_path(track.path) == path
			),
			None,
		)
		if track_index is None:
			track = Track(
				track_id=str(uuid4()),
				path=str(path),
				title=path.stem,
			)
			self._queue = self._queue + (track,)
			self._register_tracks((track,))
			track_index = len(self._queue) - 1
		else:
			track = self._queue[track_index]
			if track.duration_seconds is None:
				track = replace(
					track,
					duration_seconds=read_duration_seconds(track.path),
				)
				self._queue = (
					*self._queue[:track_index],
					track,
					*self._queue[track_index + 1 :],
				)
				self.file_system_model.set_duration(
					track.path,
					track.duration_seconds,
				)
		if (
			self._current_track is not None
			and self._normalize_path(self._current_track.path) == path
			and not autoplay
		):
			return

		self._playback_playlist_id = None
		self._queue_index = track_index
		self._load_current_track(autoplay=autoplay)

	def _load_current_track(self, autoplay: bool) -> None:
		self._current_track = self._queue[self._queue_index]
		trace_playback_event(
			"load_current_track",
			path=self._current_track.path,
			autoplay=autoplay,
			queue_index=self._queue_index,
			track_id=self._current_track.track_id,
		)
		self._record_recent_path(self._current_track.path)
		self.file_system_model.set_playing_path(self._current_track.path)
		self.playlist_view.set_playing_track(
			self._playback_playlist_id,
			self._current_track.track_id,
		)
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

	def load_and_play(self, tracks: tuple[Track, ...]) -> None:
		self._selected_playlist_track = None
		self.load_tracks(tuple(tracks), index=0)

	def load_playlist_track_selection(
		self,
		selection: PlaylistTrackSelection,
	) -> None:
		self._selected_playlist_track = None
		self.load_tracks(
			selection.tracks,
			index=selection.index,
			playlist_id=selection.playlist_id,
		)

	def _set_selected_playlist_track(
		self,
		selection: PlaylistTrackSelection | None,
	) -> None:
		self._selected_playlist_track = selection

	@staticmethod
	def _playback_mode_text(mode: PlaybackMode) -> str:
		labels = {
			PlaybackMode.REPEAT_ALL: "再生方法\n全曲ループ",
			PlaybackMode.SHUFFLE: "再生方法\nランダム",
			PlaybackMode.REPEAT_ONE: "再生方法\n1曲ループ",
		}
		return labels[mode]

	def toggle_playback_mode(self) -> None:
		modes = tuple(PlaybackMode)
		mode_index = modes.index(self._playback_mode)
		self._playback_mode = modes[(mode_index + 1) % len(modes)]
		self.playback_mode_button.setText(
			self._playback_mode_text(self._playback_mode)
		)

	def _set_playback_status(self, label: str, is_playing: bool) -> None:
		self._is_playing = is_playing
		self.status_label.setText(label)
		self.play_pause_button.setText("一時停止" if is_playing else "再生")

	def toggle_play_pause(self) -> None:
		if self._selected_playlist_track is not None:
			selected_track = self._selected_playlist_track
			self._selected_playlist_track = None
			self.load_playlist_track_selection(selected_track)
			return
		if self._is_playing:
			self.pause()
		else:
			self.play()

	def play(self) -> None:
		trace_playback_event(
			"ui_play_requested",
			selected_paths=[
				self.file_system_model.filePath(index)
				for index in self.file_tree.selectionModel().selectedRows(0)
			],
			current_path=(self._current_track.path if self._current_track else None),
			queue_index=self._queue_index,
		)
		selected_rows = self.file_tree.selectionModel().selectedRows(0)
		if selected_rows:
			selected_path = Path(self.file_system_model.filePath(selected_rows[0]))
			if (
				selected_path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES
				and (
					self._current_track is None
					or self._normalize_path(self._current_track.path)
					!= self._normalize_path(selected_path)
				)
			):
				self._select_file_path(selected_path, autoplay=False)
		if self._current_track is None:
			return
		backend_track = getattr(self.playback_service.backend, "current_track", None)
		if (
			backend_track is None
			or self._normalize_path(backend_track.path)
			!= self._normalize_path(self._current_track.path)
		):
			restore_position = self._pending_restore_position
			self._load_current_track(autoplay=False)
			if restore_position is not None:
				self.playback_service.seek(restore_position)
			self._pending_restore_position = None
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

	def seek_backward(self) -> None:
		self._seek_relative(-5.0)

	def seek_forward(self) -> None:
		self._seek_relative(5.0)

	def _seek_relative(self, offset_seconds: float) -> None:
		if self._current_track is None:
			return
		position = max(0.0, self.playback_service.position_seconds + offset_seconds)
		if self._duration_seconds > 0:
			position = min(position, self._duration_seconds)
		if self._try_seek(position):
			self.position_slider.setValue(round(position * SEEK_SCALE))
			self.position_label.setText(self._format_time(position))

	def _try_seek(self, position: float) -> bool:
		was_playing = self._is_playing
		try:
			self.playback_service.seek(position)
		except PlaybackBackendError:
			return False
		if was_playing:
			self.play()
		return True

	def previous_track(self) -> None:
		if self._queue_index > 0:
			self._queue_index -= 1
			self._load_current_track(autoplay=True)

	def next_track(self) -> None:
		self._advance_track(automatic=False)

	def _advance_track(self, automatic: bool) -> None:
		if not self._queue:
			return

		if automatic and self._playback_mode is PlaybackMode.REPEAT_ONE:
			self._restart_current_track()
			return

		if self._playback_mode is PlaybackMode.SHUFFLE:
			if len(self._queue) == 1:
				next_index = self._queue_index
			else:
				candidate_indices = [
					index
					for index in range(len(self._queue))
					if index != self._queue_index
				]
				next_index = random.choice(candidate_indices)
		elif self._queue_index + 1 < len(self._queue):
			next_index = self._queue_index + 1
		elif self._playback_mode is PlaybackMode.REPEAT_ALL:
			next_index = 0
		else:
			return

		self._queue_index = next_index
		self._load_current_track(autoplay=True)

	def _restart_current_track(self) -> None:
		if self._current_track is None:
			return
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
		if self._try_seek(position):
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
		if (
			self._is_playing
			and not self.playback_service.state.loop_enabled
			and self._duration_seconds > 0
			and position >= max(0.0, self._duration_seconds - 0.05)
		):
			self._advance_track(automatic=True)
			return
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
		return format_duration(seconds)

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

	def change_volume(self, slider_value: int) -> None:
		self.volume_value_label.setText(str(slider_value))
		self.playback_service.set_volume(float(slider_value))

	# ------------------------------------------------------------------
	# 音源分離
	# ------------------------------------------------------------------

	def _show_playlist_context_menu(self, pos) -> None:
		if self._separation_service is None:
			return
		selection = self.playlist_view.selected_track_selection()
		if selection is None:
			return
		track = selection.tracks[selection.index]

		has_stems = self._separation_service.has_stems(track.track_id)
		menu = QMenu(self)
		separate_action = menu.addAction("音源を分離")
		separate_action.setEnabled(not has_stems)
		delete_action = menu.addAction("分離キャッシュを削除")
		delete_action.setEnabled(has_stems)

		action = menu.exec(self.playlist_view.mapToGlobal(pos))
		if action == separate_action:
			self._request_separation(track)
		elif action == delete_action:
			self._separation_service.delete_stems(track.track_id)
			QMessageBox.information(
				self, "削除完了", f"{track.title} の分離キャッシュを削除しました。"
			)

	def _request_separation(self, track) -> None:
		if self._separation_service is None:
			return
		if not self._separation_service.is_env_ready():
			reply = QMessageBox.question(
				self,
				"Demucs 環境のセットアップ",
				"音源分離には Demucs 環境が必要です（約600MBのダウンロード）。\n"
				"セットアップしますか？",
				QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
			)
			if reply != QMessageBox.StandardButton.Yes:
				return
			self._start_env_setup(lambda: self._start_separation(track))
		else:
			self._start_separation(track)

	def _start_env_setup(self, on_done) -> None:
		if self._separation_service is None:
			return
		dlg = QProgressDialog("Demucs 環境を構築中...", None, 0, 0, self)
		dlg.setWindowTitle("セットアップ中")
		dlg.setWindowModality(Qt.WindowModality.WindowModal)
		dlg.setCancelButton(None)
		dlg.show()

		worker = EnvSetupWorker(self._separation_service)
		self._env_setup_worker = worker

		def _on_finished():
			dlg.close()
			on_done()

		def _on_failed(msg: str):
			dlg.close()
			QMessageBox.critical(
				self, "セットアップ失敗", f"Demucs 環境の構築に失敗しました:\n{msg}"
			)

		worker.progress.connect(dlg.setLabelText)
		worker.finished.connect(_on_finished)
		worker.failed.connect(_on_failed)
		worker.start()

	def _start_separation(self, track) -> None:
		if self._separation_service is None:
			return
		dlg = QProgressDialog(f"{track.title} を分離中...", None, 0, 0, self)
		dlg.setWindowTitle("音源分離中")
		dlg.setWindowModality(Qt.WindowModality.WindowModal)
		dlg.setCancelButton(None)
		dlg.show()

		worker = SeparationWorker(self._separation_service, track)
		self._separation_worker = worker

		def _on_finished(track_id: str):
			dlg.close()
			QMessageBox.information(self, "分離完了", f"{track.title} の音源分離が完了しました。")

		def _on_failed(track_id: str, msg: str):
			dlg.close()
			QMessageBox.critical(self, "分離失敗", f"音源分離に失敗しました:\n{msg}")

		worker.progress.connect(dlg.setLabelText)
		worker.finished.connect(_on_finished)
		worker.failed.connect(_on_failed)
		worker.start()
