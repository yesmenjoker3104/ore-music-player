from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ore_music_player.application.playlist_service import PlaylistService
from ore_music_player.domain.models import Playlist, Track
from ore_music_player.ui.playlist_view import PlaylistView


@dataclass
class FakePlaylistRepository:
    playlists: dict[str, Playlist] = field(default_factory=dict)

    def get(self, playlist_id: str) -> Playlist | None:
        return self.playlists.get(playlist_id)

    def list_all(self) -> tuple[Playlist, ...]:
        return tuple(self.playlists.values())

    def save(self, playlist: Playlist) -> None:
        self.playlists[playlist.playlist_id] = playlist

    def delete(self, playlist_id: str) -> None:
        del self.playlists[playlist_id]


@pytest.fixture(scope="session")
def qt_application() -> QApplication:
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


def make_view(qt_application: QApplication) -> tuple[PlaylistView, FakePlaylistRepository]:
    repository = FakePlaylistRepository()
    repository.save(Playlist(playlist_id="playlist-001", name="Practice"))
    view = PlaylistView(PlaylistService(repository))
    return view, repository


def test_view_displays_saved_playlists_and_tracks(qt_application: QApplication) -> None:
    view, repository = make_view(qt_application)
    repository.save(
        Playlist(
            playlist_id="playlist-001",
            name="Practice",
            tracks=(Track("track-001", "song.mp3", "Song"),),
        )
    )

    view.refresh()

    assert view.playlist_list.item(0).text() == "Practice"
    assert view.track_list.item(0).text() == "Song"


def test_add_track_uses_selected_playlist(
    qt_application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view, repository = make_view(qt_application)
    monkeypatch.setattr(
        "ore_music_player.ui.playlist_view.QFileDialog.getOpenFileNames",
        lambda *args: (["C:/Music/song.mp3"], ""),
    )

    view.add_track()

    playlist = repository.get("playlist-001")
    assert playlist is not None
    assert playlist.tracks[0].path == str(Path("C:/Music/song.mp3"))


def test_remove_track_updates_selected_playlist(qt_application: QApplication) -> None:
    view, repository = make_view(qt_application)
    repository.save(
        Playlist(
            playlist_id="playlist-001",
            name="Practice",
            tracks=(Track("track-001", "song.mp3", "Song"),),
        )
    )
    view.refresh()
    view.track_list.setCurrentRow(0)

    view.remove_track()

    playlist = repository.get("playlist-001")
    assert playlist is not None
    assert playlist.tracks == ()


def test_play_playlist_emits_all_tracks(qt_application: QApplication) -> None:
    view, repository = make_view(qt_application)
    track = Track("track-001", "song.mp3", "Song")
    repository.save(Playlist("playlist-001", "Practice", (track,)))
    view.refresh()
    received: list[Track] = []
    view.play_requested.connect(received.append)

    view.play_playlist()

    assert received == [(track,)]