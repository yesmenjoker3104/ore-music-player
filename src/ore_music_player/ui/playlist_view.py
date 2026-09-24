from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
	QAbstractItemView,
	QGridLayout,
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

TILE_BUTTON_SIZE = 112
TILE_GRID_SPACING = 4
SUPPORTED_AUDIO_SUFFIXES = (".mp3", ".wav", ".flac", ".m4a", ".ogg")


def _format_duration(seconds: float | None) -> str:
	if seconds is None:
		return "--:--"

	total_seconds = max(0, int(seconds))
	minutes, remainder = divmod(total_seconds, 60)
	hours, minutes = divmod(minutes, 60)
	if hours:
		return f"{hours}:{minutes:02d}:{remainder:02d}"
	return f"{minutes}:{remainder:02d}"


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


class PlaylistView(QWidget):
	play_requested = Signal(object)

	def __init__(self, playlist_service: PlaylistService) -> None:
		super().__init__()
		self.playlist_service = playlist_service
		self._playlists: tuple[Playlist, ...] = ()
		self._active_playlist_id: str | None = None

		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)

		splitter = QSplitter()
		layout.addWidget(splitter)

		playlist_panel = QWidget()
		playlist_layout = QVBoxLayout(playlist_panel)
		playlist_layout.setContentsMargins(0, 0, 0, 0)
		playlist_layout.addWidget(QLabel("プレイリスト"))

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
		playlist_layout.addWidget(self.playlist_list)

		playlist_buttons = QGridLayout()
		playlist_buttons.setHorizontalSpacing(TILE_GRID_SPACING)
		playlist_buttons.setVerticalSpacing(TILE_GRID_SPACING)
		create_button = self._create_tile_button("新規作成", self.create_playlist)
		playlist_buttons.addWidget(create_button, 0, 0)
		rename_button = self._create_tile_button("名前変更", self.rename_playlist)
		playlist_buttons.addWidget(rename_button, 0, 1)
		delete_button = self._create_tile_button("削除", self.delete_selected)
		playlist_buttons.addWidget(delete_button, 0, 2)

		play_button = self._create_tile_button("プレイリスト\nを再生", self.play_playlist)
		playlist_buttons.addWidget(play_button, 0, 3)
		playlist_layout.addLayout(playlist_buttons)

		self.track_list = QTableWidget(0, 2)
		self.track_list.setHorizontalHeaderLabels(["曲名", "再生時間"])
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
		self.track_list.horizontalHeader().setStretchLastSection(True)
		self.track_list.itemSelectionChanged.connect(
			self._track_selection_changed
		)

		splitter.addWidget(playlist_panel)
		splitter.addWidget(self.track_list)
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

	def _select_playlist(self, row: int) -> None:
		self.track_list.setRowCount(0)
		if not 0 <= row < len(self._playlists):
			return
		self._active_playlist_id = self._playlists[row].playlist_id
		self.track_list.blockSignals(True)
		self.track_list.clearSelection()
		self.track_list.blockSignals(False)
		for track in self._playlists[row].tracks:
			track_row = self.track_list.rowCount()
			self.track_list.insertRow(track_row)
			self.track_list.setItem(track_row, 0, QTableWidgetItem(track.title))
			self.track_list.setItem(
				track_row,
				1,
				QTableWidgetItem(_format_duration(track.duration_seconds)),
			)

	def _playlist_selection_changed(self) -> None:
		if not self.playlist_list.selectedItems():
			return
		self.track_list.blockSignals(True)
		self.track_list.clearSelection()
		self.track_list.blockSignals(False)
		self.playlist_list.setFocus()

	def _track_selection_changed(self) -> None:
		if not self.track_list.selectedItems():
			return
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
				track = Track(track_id=str(uuid4()), path=str(path), title=path.stem)
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

	def play_playlist(self) -> None:
		playlist = self.selected_playlist()
		if playlist is not None and playlist.tracks:
			self.play_requested.emit(playlist.tracks)
