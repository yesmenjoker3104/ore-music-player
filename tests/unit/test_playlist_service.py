from dataclasses import dataclass, field

import pytest

from ore_music_player.application.playlist_service import PlaylistService
from ore_music_player.domain.models import Playlist, Track


@dataclass
class FakePlaylistRepository:
    playlists: dict[str, Playlist] = field(default_factory=dict)
    deleted_ids: list[str] = field(default_factory=list)

    def get(self, playlist_id: str) -> Playlist | None:
        return self.playlists.get(playlist_id)

    def list_all(self) -> tuple[Playlist, ...]:
        return tuple(self.playlists.values())

    def save(self, playlist: Playlist) -> None:
        self.playlists[playlist.playlist_id] = playlist

    def delete(self, playlist_id: str) -> None:
        self.deleted_ids.append(playlist_id)
        del self.playlists[playlist_id]


def make_track(track_id: str) -> Track:
    return Track(
        track_id=track_id,
        path=f"{track_id}.mp3",
        title=track_id,
    )


def make_playlist(playlist_id: str = "playlist-001") -> Playlist:
    return Playlist(
        playlist_id=playlist_id,
        name="Practice",
    )


def make_service() -> tuple[PlaylistService, FakePlaylistRepository]:
    repository = FakePlaylistRepository()
    return PlaylistService(repository), repository


def test_create_saves_and_returns_playlist() -> None:
    service, repository = make_service()

    result = service.create("playlist-001", "Practice")

    assert result == make_playlist()
    assert repository.playlists == {"playlist-001": result}


def test_create_rejects_existing_playlist() -> None:
    service, repository = make_service()
    repository.save(make_playlist())

    with pytest.raises(ValueError, match="既に存在"):
        service.create("playlist-001", "Another")


def test_get_and_list_all_return_saved_playlists() -> None:
    service, repository = make_service()
    first = make_playlist("playlist-001")
    second = make_playlist("playlist-002")
    repository.save(first)
    repository.save(second)

    assert service.get("playlist-001") == first
    assert service.list_all() == (first, second)


def test_get_rejects_missing_playlist() -> None:
    service, _ = make_service()

    with pytest.raises(ValueError, match="存在しません"):
        service.get("missing")


def test_update_operations_save_updated_playlist() -> None:
    service, repository = make_service()
    repository.save(make_playlist())
    first = make_track("track-001")
    second = make_track("track-002")

    service.rename("playlist-001", "Warmup")
    service.add_track("playlist-001", first)
    service.add_track("playlist-001", second)
    service.move_track("playlist-001", 0, 1)
    result = service.remove_track("playlist-001", "track-002")

    assert result.name == "Warmup"
    assert result.tracks == (first,)
    assert repository.playlists["playlist-001"] == result


def test_delete_removes_existing_playlist_by_id() -> None:
    service, repository = make_service()
    repository.save(make_playlist())

    result = service.delete("playlist-001")

    assert result is None
    assert repository.deleted_ids == ["playlist-001"]
    assert repository.playlists == {}


def test_delete_rejects_missing_playlist() -> None:
    service, repository = make_service()

    with pytest.raises(ValueError, match="存在しません"):
        service.delete("missing")

    assert repository.deleted_ids == []
