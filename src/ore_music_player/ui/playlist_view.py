from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
	QAbstractItemView,
	QGridLayout,
	QHeaderView,
	QInputDialog,
	QLabel,
	QListWidget,
	QMessageBox,
	QPushButton,
	QSplitter,
	QTableWidget,
	QTableWidgetItem,
	QVBoxLayout,
	QWidget,
)

from ore_music_player.application.playlist_service import PlaylistService
from ore_music_player.domain.models import Playlist, Track
from ore_music_player.infrastructure.audio.metadata import read_duration_seconds
from ore_music_player.ui.utils import format_duration

TILE_BUTTON_SIZE = 96
TILE_GRID_SPACING = 4
SUPPORTED_AUDIO_SUFFIXES = (".mp3", ".wav", ".flac", ".m4a", ".ogg")
LIST_HEADER_HEIGHT = 28
PLAYING_BACKGROUND_COLOR = "#b8d8e8"
PLAYING_FOREGROUND_COLOR = "#102a43"


@dataclass(frozen=True, slots=True)
class PlaylistTrackSelection:
	tracks: tuple[Track, ...]
	index: int
	playlist_id: str | None = None


class PlaylistListWidget(QListWidget):
	paths_dropped = Signal(object)

	def dragEnterEvent(self, event) -> None:
		if event.mimeData().hasUrls():
			event.acceptProposedAction()
			return
		super().dragEnterEvent(event)

	def dragMoveEvent(self, event) -> None:
		if event.mimeData().hasUrls():
			item = self.itemAt(event.position().toPoint())
			if item is not None:
				self.setCurrentItem(item)
			event.acceptProposedAction()
			return
		super().dragMoveEvent(event)

	def dropEvent(self, event) -> None:
		if event.mimeData().hasUrls():
			self.paths_dropped.emit(
				[Path(url.toLocalFile()) for url in event.mimeData().urls()]
			)
			event.acceptProposedAction()
			return
		super().dropEvent(event)


class TrackTableWidget(QTableWidget):
	_NAME_COLUMN_RATIO = 0.8
	paths_dropped = Signal(object)
	rows_reordered = Signal()

	def __init__(self, rows: int, columns: int) -> None:
		super().__init__(rows, columns)
		self.setAcceptDrops(True)
		self.setDropIndicatorShown(False)
		self.setDragEnabled(True)
		self.setDefaultDropAction(Qt.DropAction.MoveAction)
		self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

	def dragEnterEvent(self, event) -> None:
		if event.mimeData().hasUrls():
			event.acceptProposedAction()
			return
		super().dragEnterEvent(event)

	def dragMoveEvent(self, event) -> None:
		if event.mimeData().hasUrls():
			event.acceptProposedAction()
			return
		super().dragMoveEvent(event)

	def dropEvent(self, event) -> None:
		if event.mimeData().hasUrls():
			self.paths_dropped.emit(
				[Path(url.toLocalFile()) for url in event.mimeData().urls()]
			)
			event.acceptProposedAction()
			return
		super().dropEvent(event)
		for row in range(self.rowCount() - 1, -1, -1):
			if self.item(row, 0) is None:
				self.removeRow(row)
		self.rows_reordered.emit()

	_STEM_COLUMN_WIDTH = 28

	def resizeEvent(self, event) -> None:
		super().resizeEvent(event)
		header = self.horizontalHeader()
		available_width = header.viewport().width()
		if available_width <= 0:
			return
		remaining = max(0, available_width - self._STEM_COLUMN_WIDTH)
		name_width = int(remaining * self._NAME_COLUMN_RATIO)
		duration_width = remaining - name_width
		header.resizeSection(0, name_width)
		header.resizeSection(1, duration_width)
		header.resizeSection(2, self._STEM_COLUMN_WIDTH)


class PlaylistView(QWidget):
	play_requested = Signal(object)
	track_selected = Signal(object)

	def __init__(
		self,
		playlist_service: PlaylistService,
		has_stems_fn: Callable[[str], bool] | None = None,
	) -> None:
		super().__init__()
		self.playlist_service = playlist_service
		self._has_stems_fn = has_stems_fn
		self._playlists: tuple[Playlist, ...] = ()
		self._active_playlist_id: str | None = None
		self._playing_playlist_id: str | None = None
		self._playing_track_id: str | None = None

		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)

		splitter = QSplitter()
		layout.addWidget(splitter)

		playlist_panel = QWidget()
		playlist_layout = QVBoxLayout(playlist_panel)
		playlist_layout.setContentsMargins(0, 0, 0, 0)
		playlist_title = QLabel("プレイリスト")
		playlist_title.setFixedHeight(LIST_HEADER_HEIGHT)
		playlist_layout.addWidget(playlist_title)

		self.playlist_list = PlaylistListWidget()
		self.playlist_list.setAcceptDrops(True)
		self.playlist_list.setDropIndicatorShown(False)
		self.playlist_list.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
		self.playlist_list.setSelectionMode(
			QAbstractItemView.SelectionMode.ExtendedSelection
		)
		self.playlist_list.currentRowChanged.connect(self._select_playlist)
		self.playlist_list.itemSelectionChanged.connect(
			self._playlist_selection_changed
		)
		self.playlist_list.paths_dropped.connect(self._add_dropped_paths)
		playlist_layout.addWidget(self.playlist_list, 1)

		playlist_buttons = QGridLayout()
		playlist_buttons.setHorizontalSpacing(TILE_GRID_SPACING)
		playlist_buttons.setVerticalSpacing(TILE_GRID_SPACING)
		create_button = self._create_tile_button("新規作成", self.create_playlist)
		playlist_buttons.addWidget(create_button, 0, 0)
		rename_button = self._create_tile_button("名前変更", self.rename_playlist)
		playlist_buttons.addWidget(rename_button, 0, 1)
		delete_button = self._create_tile_button("削除", self.delete_selected)
		playlist_buttons.addWidget(delete_button, 0, 2)
		playlist_layout.addLayout(playlist_buttons)

		self.track_list = TrackTableWidget(0, 3)
		self.track_list.setHorizontalHeaderLabels(["曲名", "再生時間", "♫"])
		self.track_list.horizontalHeader().setSectionResizeMode(
			QHeaderView.ResizeMode.Fixed
		)
		self.track_list.setSelectionBehavior(
			QAbstractItemView.SelectionBehavior.SelectRows
		)
		self.track_list.setSelectionMode(
			QAbstractItemView.SelectionMode.ExtendedSelection
		)
		self.track_list.setEditTriggers(
			QAbstractItemView.EditTrigger.NoEditTriggers
		)
		self.track_list.verticalHeader().setVisible(False)
		self.track_list.itemSelectionChanged.connect(
			self._track_selection_changed
		)
		self.track_list.itemDoubleClicked.connect(self._play_selected_track)
		self.track_list.paths_dropped.connect(self._add_dropped_paths)
		self.track_list.rows_reordered.connect(self._reorder_tracks)

		track_panel = QWidget()
		track_layout = QVBoxLayout(track_panel)
		track_layout.setContentsMargins(0, 0, 0, 0)
		track_layout.addSpacing(LIST_HEADER_HEIGHT + track_layout.spacing())
		track_layout.addWidget(self.track_list, 1)

		splitter.addWidget(playlist_panel)
		splitter.addWidget(track_panel)
		splitter.setStretchFactor(0, 1)
		splitter.setStretchFactor(1, 2)
		splitter.setSizes([280, 560])

		self.refresh()

	@staticmethod
	def _create_tile_button(text: str, handler) -> QPushButton:
		button = QPushButton(text)
		button.setFixedSize(TILE_BUTTON_SIZE, TILE_BUTTON_SIZE)
		button.clicked.connect(handler)
		return button

	def refresh(self) -> None:
		selected_id = self.selected_playlist_id()
		self._playlists = self.playlist_service.list_all()
		self.playlist_list.blockSignals(True)
		self.playlist_list.clear()
		for playlist in self._playlists:
			self.playlist_list.addItem(
				f"{playlist.name} ({len(playlist.tracks)}曲)"
			)
		self.playlist_list.blockSignals(False)

		if self._playlists:
			row = next(
				(
					index
					for index, playlist in enumerate(self._playlists)
					if playlist.playlist_id == selected_id
				),
				0,
			)
			self.playlist_list.setCurrentRow(row)
		else:
			self.playlist_list.clearSelection()
		self._select_playlist(self.playlist_list.currentRow())
		self._update_playing_highlights()

	def selected_playlist_id(self) -> str | None:
		row = self.playlist_list.currentRow()
		if 0 <= row < len(self._playlists):
			return self._playlists[row].playlist_id
		return self._active_playlist_id

	def selected_playlist(self) -> Playlist | None:
		playlist_id = self.selected_playlist_id()
		if playlist_id is None:
			return None
		return self.playlist_service.get(playlist_id)

	def selected_track_selection(self) -> PlaylistTrackSelection | None:
		if not self.track_list.selectedItems():
			return None
		playlist = self.selected_playlist()
		row = self.track_list.currentRow()
		if playlist is None or not 0 <= row < len(playlist.tracks):
			return None
		return PlaylistTrackSelection(
			tuple(playlist.tracks),
			row,
			playlist.playlist_id,
		)

	def set_playing_track(
		self,
		playlist_id: str | None,
		track_id: str | None,
	) -> None:
		self._playing_playlist_id = playlist_id
		self._playing_track_id = track_id
		self._update_playing_highlights()

	def _update_playing_highlights(self) -> None:
		playing_background = QColor(PLAYING_BACKGROUND_COLOR)
		playing_foreground = QColor(PLAYING_FOREGROUND_COLOR)
		for row, playlist in enumerate(self._playlists):
			item = self.playlist_list.item(row)
			if item is None:
				continue
			item.setData(
				Qt.ItemDataRole.BackgroundRole,
				playing_background
				if playlist.playlist_id == self._playing_playlist_id
				else None,
			)
			item.setData(
				Qt.ItemDataRole.ForegroundRole,
				playing_foreground
				if playlist.playlist_id == self._playing_playlist_id
				else None,
			)

		for row in range(self.track_list.rowCount()):
			for column in range(self.track_list.columnCount()):
				item = self.track_list.item(row, column)
				if item is None:
					continue
				track_item = self.track_list.item(row, 0)
				is_playing = (
					self._active_playlist_id == self._playing_playlist_id
					and track_item is not None
					and track_item.data(Qt.ItemDataRole.UserRole)
					== self._playing_track_id
				)
				item.setData(
					Qt.ItemDataRole.BackgroundRole,
					playing_background if is_playing else None,
				)
				item.setData(
					Qt.ItemDataRole.ForegroundRole,
					playing_foreground if is_playing else None,
				)

	def update_stem_status(self, track_id: str, has_stems: bool) -> None:
		for row in range(self.track_list.rowCount()):
			item = self.track_list.item(row, 0)
			if item is not None and item.data(Qt.ItemDataRole.UserRole) == track_id:
				stem_item = self.track_list.item(row, 2)
				if stem_item is None:
					stem_item = QTableWidgetItem()
					self.track_list.setItem(row, 2, stem_item)
				stem_item.setText("♫" if has_stems else "")
				stem_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
				break

	def _select_playlist(self, row: int) -> None:
		self.track_selected.emit(None)
		self.track_list.setRowCount(0)
		if not 0 <= row < len(self._playlists):
			self._active_playlist_id = None
			self._update_playing_highlights()
			return
		self._active_playlist_id = self._playlists[row].playlist_id
		self.track_list.blockSignals(True)
		self.track_list.clearSelection()
		self.track_list.blockSignals(False)
		for track in self._playlists[row].tracks:
			track_row = self.track_list.rowCount()
			self.track_list.insertRow(track_row)
			duration_seconds = track.duration_seconds
			if duration_seconds is None:
				duration_seconds = read_duration_seconds(track.path)
			title_item = QTableWidgetItem(track.title)
			title_item.setData(Qt.ItemDataRole.UserRole, track.track_id)
			self.track_list.setItem(track_row, 0, title_item)
			self.track_list.setItem(
				track_row,
				1,
				QTableWidgetItem(format_duration(duration_seconds)),
			)
			has = self._has_stems_fn is not None and self._has_stems_fn(track.track_id)
			stem_item = QTableWidgetItem("♫" if has else "")
			stem_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
			stem_item.setFlags(stem_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
			self.track_list.setItem(track_row, 2, stem_item)
		self._update_playing_highlights()

	def _playlist_selection_changed(self) -> None:
		if not self.playlist_list.selectedItems():
			return
		self.track_selected.emit(None)
		self.track_list.blockSignals(True)
		self.track_list.clearSelection()
		self.track_list.blockSignals(False)
		self.playlist_list.setFocus()

	def _track_selection_changed(self) -> None:
		if not self.track_list.selectedItems():
			return
		self.track_selected.emit(self.selected_track_selection())
		self.playlist_list.blockSignals(True)
		self.playlist_list.clearSelection()
		self.playlist_list.blockSignals(False)
		self.track_list.setFocus()

	def create_playlist(self) -> None:
		name, accepted = QInputDialog.getText(self, "新規プレイリスト", "名前")
		if accepted and name.strip():
			self.playlist_service.create(str(uuid4()), name.strip())
			self.refresh()

	def rename_playlist(self) -> None:
		playlist = self.selected_playlist()
		if playlist is None:
			return
		name, accepted = QInputDialog.getText(
			self,
			"プレイリスト名を変更",
			"名前",
			text=playlist.name,
		)
		if accepted and name.strip():
			self.playlist_service.rename(playlist.playlist_id, name.strip())
			self.refresh()

	def delete_selected(self) -> None:
		if self.track_list.selectedItems():
			self._delete_selected_tracks()
		elif self.playlist_list.selectedItems():
			self._delete_selected_playlists()

	def _delete_selected_playlists(self) -> None:
		playlist_ids = [
			self._playlists[self.playlist_list.row(item)].playlist_id
			for item in self.playlist_list.selectedItems()
		]
		if not playlist_ids:
			return
		answer = QMessageBox.question(
			self,
			"プレイリストを削除",
			f"プレイリストを{len(playlist_ids)}件削除しますか？",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
			QMessageBox.StandardButton.No,
		)
		if answer != QMessageBox.StandardButton.Yes:
			return
		for playlist_id in playlist_ids:
			self.playlist_service.delete(playlist_id)
		self._active_playlist_id = None
		self.refresh()

	def delete_playlist(self) -> None:
		self._delete_selected_playlists()

	def _add_dropped_paths(self, paths: list[Path]) -> None:
		playlist_id = self.selected_playlist_id()
		if playlist_id is None:
			return
		for dropped_path in paths:
			file_paths = (
				[dropped_path]
				if dropped_path.is_file()
				else (
					path
					for path in dropped_path.rglob("*")
					if path.is_file()
				)
			)
			for path in file_paths:
				if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
					continue
				track = Track(
					track_id=str(uuid4()),
					path=str(path),
					title=path.stem,
					duration_seconds=read_duration_seconds(path),
				)
				self.playlist_service.add_track(playlist_id, track)
		self.refresh()

	def _delete_selected_tracks(self) -> None:
		playlist = self.selected_playlist()
		track_rows = sorted(
			{index.row() for index in self.track_list.selectionModel().selectedRows()},
			reverse=True,
		)
		if playlist is None or not track_rows:
			return
		answer = QMessageBox.question(
			self,
			"曲を削除",
			f"曲を{len(track_rows)}件削除しますか？",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
			QMessageBox.StandardButton.No,
		)
		if answer != QMessageBox.StandardButton.Yes:
			return
		for track_row in track_rows:
			if 0 <= track_row < len(playlist.tracks):
				self.playlist_service.remove_track(
					playlist.playlist_id,
					playlist.tracks[track_row].track_id,
				)
		self.refresh()

	def remove_track(self) -> None:
		self._delete_selected_tracks()

	def _reorder_tracks(self) -> None:
		playlist = self.selected_playlist()
		if playlist is None:
			return
		ordered_track_ids = [
			item.data(Qt.ItemDataRole.UserRole)
			for row in range(self.track_list.rowCount())
			if (item := self.track_list.item(row, 0)) is not None
		]
		if set(ordered_track_ids) != {track.track_id for track in playlist.tracks}:
			self.refresh()
			return

		self.playlist_service.reorder_tracks(
			playlist.playlist_id,
			ordered_track_ids,
		)
		self.refresh()

	def _play_selected_track(self, item: QTableWidgetItem) -> None:
		playlist = self.selected_playlist()
		row = item.row()
		if playlist is not None and 0 <= row < len(playlist.tracks):
			self.play_requested.emit(
				PlaylistTrackSelection(
					tuple(playlist.tracks),
					row,
					playlist.playlist_id,
				)
			)
