from __future__ import annotations

from ore_music_player.application.ports import PlaylistRepository
from ore_music_player.domain.models import Playlist, Track


class PlaylistService:
    def __init__(self, repository: PlaylistRepository) -> None:
        self.repository = repository

    def create(self, playlist_id: str, name: str) -> Playlist:
        if self.repository.get(playlist_id) is not None:
            raise ValueError(f"プレイリストは既に存在します: {playlist_id}")

        playlist = Playlist(playlist_id=playlist_id, name=name)
        self.repository.save(playlist)
        return playlist

    def get(self, playlist_id: str) -> Playlist:
        playlist = self.repository.get(playlist_id)
        if playlist is None:
            raise ValueError(f"プレイリストは存在しません: {playlist_id}")
        return playlist

    def list_all(self) -> tuple[Playlist, ...]:
        return self.repository.list_all()

    def rename(self, playlist_id: str, new_name: str) -> Playlist:
        playlist = self.get(playlist_id)
        update_playlist = playlist.rename(new_name)
        self.repository.save(update_playlist)
        return update_playlist

    def add_track(
        self,
        playlist_id: str,
        track: Track,
    ) -> Playlist:
        playlist = self.get(playlist_id)
        updated_playlist = playlist.add_track(track)
        self.repository.save(updated_playlist)
        return updated_playlist

    def remove_track(
        self,
        playlist_id: str,
        track_id: str,
    ) -> Playlist:
        playlist = self.get(playlist_id)
        updated_playlist = playlist.remove_track(track_id)
        self.repository.save(updated_playlist)
        return updated_playlist

    def move_track(
        self,
        playlist_id: str,
        current_index: int,
        new_index: int,
    ) -> Playlist:
        playlist = self.get(playlist_id)
        updated_playlist = playlist.move_track(
            current_index=current_index,
            new_index=new_index
        )
        self.repository.save(updated_playlist)
        return updated_playlist

    def delete(self, playlist_id: str) -> None:
        self.get(playlist_id)
        self.repository.delete(playlist_id=playlist_id)