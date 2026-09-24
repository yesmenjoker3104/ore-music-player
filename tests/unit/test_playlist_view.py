from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

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


def test_view_displays_selected_playlist_tracks_without_paths(
    qt_application: QApplication,
) -> None:
    view, repository = make_view(qt_application)
    repository.save(
        Playlist(
            playlist_id="playlist-001",
            name="Practice",
            tracks=(Track("track-001", "song.mp3", "Song", 125.0),),
        )
    )

    view.refresh()

    assert view.playlist_list.item(0).text() == "Practice (1曲)"
    assert view.track_list.rowCount() == 1
    assert view.track_list.item(0, 0).text() == "Song"
    assert view.track_list.item(0, 1).text() == "2:05"
    assert "song.mp3" not in view.track_list.item(0, 0).text()
    assert "song.mp3" not in view.track_list.item(0, 1).text()


def test_play_playlist_emits_all_tracks(qt_application: QApplication) -> None:
    view, repository = make_view(qt_application)
    track = Track("track-001", "song.mp3", "Song")
    repository.save(Playlist("playlist-001", "Practice", (track,)))
    view.refresh()
    received: list[Track] = []
    view.play_requested.connect(received.append)

    view.play_playlist()

    assert received == [(track,)]


def test_dropped_files_and_folders_are_added_to_selected_playlist(
    qt_application: QApplication,
    tmp_path: Path,
) -> None:
    view, repository = make_view(qt_application)
    practice_folder = tmp_path / "practice"
    practice_folder.mkdir()
    first_path = tmp_path / "first.wav"
    second_path = practice_folder / "second.mp3"
    ignored_path = practice_folder / "notes.txt"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    ignored_path.write_text("notes")

    view._add_dropped_paths([first_path, practice_folder])

    playlist = repository.get("playlist-001")
    assert playlist is not None
    assert [Path(track.path) for track in playlist.tracks] == [
        first_path,
        second_path,
    ]


def test_playlist_and_track_selection_are_exclusive(
    qt_application: QApplication,
) -> None:
    view, repository = make_view(qt_application)
    repository.save(
        Playlist(
            "playlist-001",
            "Practice",
            (Track("track-001", "song.mp3", "Song"),),
        )
    )
    view.refresh()

    view.track_list.selectRow(0)
    assert not view.playlist_list.selectedItems()

    view.playlist_list.setCurrentRow(0)
    assert not view.track_list.selectedItems()


def test_delete_selected_tracks_requires_confirmation_and_supports_multiple(
    qt_application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view, repository = make_view(qt_application)
    repository.save(
        Playlist(
            "playlist-001",
            "Practice",
            (
                Track("track-001", "one.mp3", "One"),
                Track("track-002", "two.mp3", "Two"),
            ),
        )
    )
    view.refresh()
    view.track_list.selectAll()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    view.delete_selected()

    playlist = repository.get("playlist-001")
    assert playlist is not None
    assert playlist.tracks == ()


def test_delete_selected_playlists_supports_multiple(
    qt_application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view, repository = make_view(qt_application)
    repository.save(Playlist("playlist-002", "Warmup"))
    view.refresh()
    view.playlist_list.selectAll()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    view.delete_selected()

    assert repository.list_all() == ()