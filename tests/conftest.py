from dataclasses import dataclass, field

from ore_music_player.domain.models import Playlist


@dataclass
class FakePlaylistRepository:
	playlists: dict[str, Playlist] = field(default_factory=dict)
	deleted_ids: list[str] = field(default_factory=list)
	save_calls: int = 0

	def get(self, playlist_id: str) -> Playlist | None:
		return self.playlists.get(playlist_id)

	def list_all(self) -> tuple[Playlist, ...]:
		return tuple(self.playlists.values())

	def reorder_playlists(self, ordered_playlist_ids: tuple[str, ...]) -> None:
		if set(ordered_playlist_ids) != set(self.playlists):
			raise ValueError("invalid playlist order")
		self.playlists = {
			playlist_id: self.playlists[playlist_id]
			for playlist_id in ordered_playlist_ids
		}

	def save(self, playlist: Playlist) -> None:
		self.save_calls += 1
		self.playlists[playlist.playlist_id] = playlist

	def delete(self, playlist_id: str) -> None:
		self.deleted_ids.append(playlist_id)
		del self.playlists[playlist_id]