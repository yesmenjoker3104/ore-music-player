from pathlib import Path

from ore_music_player.domain.models import Playlist, Track
from ore_music_player.infrastructure.persistence.sqlite_repository import (
	SQLitePlaylistRepository,
)


def make_track(track_id: str, duration_seconds: float | None = None) -> Track:
	return Track(
		track_id=track_id,
		path=f"{track_id}.mp3",
		title=f"Title {track_id}",
		duration_seconds=duration_seconds,
	)


def make_playlist() -> Playlist:
	return Playlist(
		playlist_id="playlist-001",
		name="Practice",
		tracks=(
			make_track("track-001", 120.5),
			make_track("track-002"),
		),
	)


def test_save_and_get_preserve_playlist_and_track_order(tmp_path: Path) -> None:
	database_path = tmp_path / "music.sqlite3"
	playlist = make_playlist()

	with SQLitePlaylistRepository(database_path) as repository:
		repository.save(playlist)

		assert repository.get("playlist-001") == playlist


def test_saved_playlist_can_be_restored_by_a_new_repository(
	tmp_path: Path,
) -> None:
	database_path = tmp_path / "music.sqlite3"
	playlist = make_playlist()

	with SQLitePlaylistRepository(database_path) as repository:
		repository.save(playlist)

	with SQLitePlaylistRepository(database_path) as repository:
		assert repository.get("playlist-001") == playlist
		assert repository.list_all() == (playlist,)


def test_save_updates_playlist_name_and_tracks(tmp_path: Path) -> None:
	database_path = tmp_path / "music.sqlite3"
	original = make_playlist()
	updated = Playlist(
		playlist_id=original.playlist_id,
		name="Warmup",
		tracks=(original.tracks[1],),
	)

	with SQLitePlaylistRepository(database_path) as repository:
		repository.save(original)
		repository.save(updated)

		assert repository.get(original.playlist_id) == updated


def test_delete_removes_playlist(tmp_path: Path) -> None:
	database_path = tmp_path / "music.sqlite3"

	with SQLitePlaylistRepository(database_path) as repository:
		repository.save(make_playlist())
		repository.delete("playlist-001")

		assert repository.get("playlist-001") is None
		assert repository.list_all() == ()
