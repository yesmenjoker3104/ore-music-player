from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
	QFileDialog,
	QGridLayout,
	QInputDialog,
	QLabel,
	QListWidget,
	QPushButton,
	QVBoxLayout,
	QWidget,
)

from ore_music_player.application.playlist_service import PlaylistService
from ore_music_player.domain.models import Playlist, Track

TILE_BUTTON_SIZE = 112
TILE_GRID_SPACING = 4


class PlaylistView(QWidget):
	play_requested = Signal(object)

	def __init__(self, playlist_service: PlaylistService) -> None:
		super().__init__()
		self.playlist_service = playlist_service
		self._playlists: tuple[Playlist, ...] = ()

		layout = QVBoxLayout(self)
		layout.addWidget(QLabel("プレイリスト"))

		self.playlist_list = QListWidget()
		self.playlist_list.currentRowChanged.connect(self._select_playlist)
		layout.addWidget(self.playlist_list)

		playlist_buttons = QGridLayout()
		playlist_buttons.setHorizontalSpacing(TILE_GRID_SPACING)
		playlist_buttons.setVerticalSpacing(TILE_GRID_SPACING)
		create_button = self._create_tile_button("新規作成", self.create_playlist)
		playlist_buttons.addWidget(create_button, 0, 0)
		rename_button = self._create_tile_button("名前変更", self.rename_playlist)
		playlist_buttons.addWidget(rename_button, 0, 1)
		delete_button = self._create_tile_button("削除", self.delete_playlist)
		playlist_buttons.addWidget(delete_button, 0, 2)
		layout.addLayout(playlist_buttons)

		self.track_list = QListWidget()
		layout.addWidget(QLabel("曲"))
		layout.addWidget(self.track_list)

		track_buttons = QGridLayout()
		track_buttons.setHorizontalSpacing(TILE_GRID_SPACING)
		track_buttons.setVerticalSpacing(TILE_GRID_SPACING)
		add_button = self._create_tile_button("曲を追加", self.add_track)
		track_buttons.addWidget(add_button, 0, 0)
		remove_button = self._create_tile_button("曲を削除", self.remove_track)
		track_buttons.addWidget(remove_button, 0, 1)
		play_button = self._create_tile_button("プレイリスト\nを再生", self.play_playlist)
		track_buttons.addWidget(play_button, 0, 2)
		layout.addLayout(track_buttons)

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
		self.playlist_list.addItems(playlist.name for playlist in self._playlists)
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
			self.track_list.clear()

	def selected_playlist_id(self) -> str | None:
		row = self.playlist_list.currentRow()
		if 0 <= row < len(self._playlists):
			return self._playlists[row].playlist_id
		return None

	def selected_playlist(self) -> Playlist | None:
		playlist_id = self.selected_playlist_id()
		if playlist_id is None:
			return None
		return self.playlist_service.get(playlist_id)

	def _select_playlist(self, row: int) -> None:
		self.track_list.clear()
		if not 0 <= row < len(self._playlists):
			return
		self.track_list.addItems(track.title for track in self._playlists[row].tracks)

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

	def delete_playlist(self) -> None:
		playlist_id = self.selected_playlist_id()
		if playlist_id is not None:
			self.playlist_service.delete(playlist_id)
			self.refresh()

	def add_track(self) -> None:
		playlist_id = self.selected_playlist_id()
		if playlist_id is None:
			return
		file_paths, _ = QFileDialog.getOpenFileNames(
			self,
			"プレイリストへ追加する音声ファイルを選択",
			"",
			"Audio files (*.mp3 *.wav *.flac *.m4a *.ogg);;All files (*.*)",
		)
		if not file_paths:
			return

		for file_path in file_paths:
			path = Path(file_path)
			track = Track(track_id=str(uuid4()), path=str(path), title=path.stem)
			self.playlist_service.add_track(playlist_id, track)
		self.refresh()

	def remove_track(self) -> None:
		playlist = self.selected_playlist()
		track_row = self.track_list.currentRow()
		if playlist is None or not 0 <= track_row < len(playlist.tracks):
			return
		self.playlist_service.remove_track(
			playlist.playlist_id,
			playlist.tracks[track_row].track_id,
		)
		self.refresh()

	def play_playlist(self) -> None:
		playlist = self.selected_playlist()
		if playlist is not None and playlist.tracks:
			self.play_requested.emit(playlist.tracks)
