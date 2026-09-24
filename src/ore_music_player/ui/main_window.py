from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import (
	QAbstractProxyModel,
	QByteArray,
	QDir,
	QModelIndex,
	QPointF,
	QRectF,
	QSettings,
	Qt,
	QTimer,
)
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
	QAbstractItemView,
	QComboBox,
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
		normalized_paths = {Path(path).resolve() for path in paths}
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

	def _create_path_index(self, row: int, column: int, path: str) -> QModelIndex:
		path = str(Path(path).resolve())
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
		item_path = Path(self.sourceModel().filePath(source_index)).resolve()
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
			)
		return self._create_path_index(
			source_index.row(),
			source_index.column(),
			str(item_path),
		)

	def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
		if role == Qt.ItemDataRole.ForegroundRole:
			path = self.filePath(index)
			if self._playing_path and Path(path).resolve() == Path(
				self._playing_path
			).resolve():
				return QColor("#d1495b")
		return self.sourceModel().data(self.mapToSource(index), role)

	def set_playing_path(self, path: str | Path | None) -> None:
		previous_path = self._playing_path
		self._playing_path = str(Path(path).resolve()) if path else None
		for changed_path in (previous_path, self._playing_path):
			if not changed_path:
				continue
			index = self.index_for_path(changed_path)
			if index.isValid():
				self.dataChanged.emit(
					index,
					index.siblingAtColumn(self.columnCount() - 1),
					[Qt.ItemDataRole.ForegroundRole],
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

	def set_duration(self, path: str, duration: float) -> None:
		self.sourceModel().set_duration(path, duration)

	def setRootPath(self, path: str) -> QModelIndex:
		return self.sourceModel().setRootPath(path)

	def rootPath(self) -> str:
		return self.sourceModel().rootPath()


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
	_SPLITTER_LAYOUT_VERSION_KEY = "leftPane/splitterLayoutVersion"
	_FILE_TREE_HEADER_STATE_KEY = "leftPane/fileTreeHeaderState"
	_FILE_TREE_ROOT_KEY = "leftPane/rootPath"
	_REGISTERED_PATHS_KEY = "leftPane/registeredPaths"
	_REGISTERED_FOLDERS_KEY = "leftPane/registeredFolders"
	_DRIVE_ROOTS_GROUP = "leftPane/driveRoots"

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
		self._registered_paths: set[Path] = set()
		self._registered_folders: set[Path] = self._load_registered_folders()
		self._drive_roots = self._load_drive_roots()
		self._splitter_migration_pending = self._settings.value(
			self._SPLITTER_LAYOUT_VERSION_KEY,
			0,
			type=int,
		) < 12

		self.setWindowTitle("Ore Music Player")
		icon_path = Path(__file__).resolve().parents[1] / "assets" / "app_icon.ico"
		self.setWindowIcon(QIcon(str(icon_path)))
		self.resize(960, 800)
		self._create_file_menu()

		central_widget = QWidget()
		layout = QVBoxLayout(central_widget)
		layout.setContentsMargins(0, 0, 0, 0)
		splitter = QSplitter(Qt.Orientation.Horizontal)
		self.main_splitter = splitter
		splitter.splitterMoved.connect(self._save_left_pane_settings)
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
		self._source_file_system_model = AudioFileSystemModel(self)
		self._source_file_system_model.setFilter(
			QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot
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
		self.file_tree.setRootIndex(QModelIndex())
		self._restore_left_pane_settings()
		self.file_tree.setColumnWidth(0, 240)
		self.file_tree.setColumnWidth(1, 65)
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
		splitter.addWidget(right_splitter)
		splitter.setStretchFactor(0, 1)
		splitter.setStretchFactor(1, 2)
		splitter.setSizes([170, 790])

		player_widget = QWidget()
		player_layout = QVBoxLayout(player_widget)
		player_layout.setContentsMargins(0, 0, 0, 0)
		player_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

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
		right_splitter.addWidget(player_widget)
		right_splitter.addWidget(playlist_view)
		right_splitter.setStretchFactor(0, 2)
		right_splitter.setStretchFactor(1, 1)
		right_splitter.setSizes([430, 350])

		self.setCentralWidget(central_widget)
		self._restore_splitter_state()

	def showEvent(self, event) -> None:
		super().showEvent(event)
		if self._splitter_migration_pending:
			self._splitter_migration_pending = False
			QTimer.singleShot(100, self._move_splitter_right)

	def _move_splitter_right(self) -> None:
		sizes = self.main_splitter.sizes()
		if len(sizes) == 2 and sizes[1] > 20:
			self.main_splitter.setSizes([sizes[0] + 20, sizes[1] - 20])
			self._settings.setValue(self._SPLITTER_LAYOUT_VERSION_KEY, 12)

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

	def _save_left_pane_settings(self, *_args) -> None:
		self._settings.setValue(
			self._SPLITTER_STATE_KEY,
			self.main_splitter.saveState(),
		)
		self._settings.setValue(self._SPLITTER_LAYOUT_VERSION_KEY, 12)
		self._settings.setValue(
			self._FILE_TREE_HEADER_STATE_KEY,
			self.file_tree.header().saveState(),
		)
		self._settings.setValue(
			self._FILE_TREE_ROOT_KEY,
			self.file_root_label.text(),
		)
		self._save_registered_paths()
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
			self._registered_folders.add(Path(file_paths[0]).parent.resolve())
			self._save_registered_folders()
			self._sync_file_tree_roots()
			self._set_file_tree_root(Path(file_paths[0]).parent)
			self._append_tracks(self._tracks_from_paths(file_paths))
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
		self._append_tracks(self._tracks_from_paths(paths))
		self._update_file_tree_visibility()

	def _load_file_from_tree(self, index: QModelIndex) -> None:
		if self.file_system_model.isDir(index):
			return
		path = Path(self.file_system_model.filePath(index))
		if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
			return
		self._select_file_from_tree(index, autoplay=True)

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

	def _update_file_tree_visibility(self, loaded_path: str | None = None) -> None:
		registered_paths = set(self._registered_paths)
		registered_folders = set(self._registered_folders)
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
			self.file_tree.setRowHidden(row, parent_index, not is_visible)

	def _hide_paths_from_file_tree(self, paths: list[Path] | tuple[Path, ...]) -> None:
		for path in paths:
			index = self.file_system_model.index(str(path))
			if index.isValid():
				self.file_tree.setRowHidden(index.row(), index.parent(), True)

	@staticmethod
	def _normalize_path(path: str | Path) -> Path:
		return Path(path).resolve()

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
		saved_paths = self._settings.value(self._REGISTERED_FOLDERS_KEY, [])
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
		saved_paths = self._settings.value(self._REGISTERED_PATHS_KEY, [])
		if isinstance(saved_paths, str):
			saved_paths = [saved_paths]
		self._registered_paths = {
			self._normalize_path(path) for path in saved_paths if str(path).strip()
		}
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

		self._queue = self._tracks_from_paths(existing_paths)
		self._queue_index = 0
		self._update_file_tree_visibility()

	def _register_tracks(self, tracks: tuple[Track, ...]) -> None:
		self._registered_paths.update(self._normalize_path(track.path) for track in tracks)
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
			self.file_tree.setCurrentIndex(index)
			self.file_tree.scrollTo(index)

	def _update_file_tree_path(
		self,
		current: QModelIndex,
		_previous: QModelIndex,
	) -> None:
		if not current.isValid():
			return
		selected_path = Path(self.file_system_model.filePath(current))
		folder_path = (
			selected_path if self.file_system_model.isDir(current) else selected_path.parent
		)
		self.file_root_label.setText(str(folder_path))
		if (
			self.file_system_model.isDir(current)
			or selected_path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES
		):
			return
		self._select_file_from_tree(current, autoplay=False)

	def _select_file_from_tree(self, index: QModelIndex, autoplay: bool) -> None:
		path = self._normalize_path(self.file_system_model.filePath(index))
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
		elif (
			self._current_track is not None
			and self._normalize_path(self._current_track.path) == path
			and not autoplay
		):
			return

		self._queue_index = track_index
		self._load_current_track(autoplay=autoplay)

	def _load_current_track(self, autoplay: bool) -> None:
		self._current_track = self._queue[self._queue_index]
		self.file_system_model.set_playing_path(self._current_track.path)
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
