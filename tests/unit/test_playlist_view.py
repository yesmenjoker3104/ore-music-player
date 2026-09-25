import wave
from pathlib import Path

import pytest
from conftest import FakePlaylistRepository
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
)

from ore_music_player.application.playlist_service import PlaylistService
from ore_music_player.domain.models import Playlist, Track
from ore_music_player.ui.playlist_view import (
    PlaylistTrackSelection,
    PlaylistView,
)


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


def test_view_resolves_missing_track_duration_from_audio_file(
    qt_application: QApplication,
    tmp_path: Path,
) -> None:
    view, repository = make_view(qt_application)
    audio_path = tmp_path / "tone.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(100)
        audio.writeframes(b"\0\0" * 100)

    repository.save(
        Playlist(
            "playlist-001",
            "Practice",
            (Track("track-001", str(audio_path), "Tone"),),
        )
    )
    view.refresh()

    assert view.track_list.item(0, 1).text() == "0:01"


def test_track_table_starts_at_top_without_track_title(
    qt_application: QApplication,
) -> None:
    view, _ = make_view(qt_application)
    view.show()
    qt_application.processEvents()

    assert "曲一覧" not in [
        label.text() for label in view.findChildren(QLabel)
    ]
    assert view.playlist_list.geometry().top() == view.track_list.geometry().top()
    assert view.playlist_list.height() > 0
    assert view.track_list.height() > 0
    view.close()


def test_track_table_columns_use_eight_to_two_ratio(
    qt_application: QApplication,
) -> None:
    view, _ = make_view(qt_application)
    view.show()
    qt_application.processEvents()

    column_total = (
        view.track_list.columnWidth(0) + view.track_list.columnWidth(1)
    )
    assert view.track_list.columnWidth(0) == pytest.approx(
        column_total * 0.8,
        abs=2,
    )
    assert view.track_list.columnWidth(1) == pytest.approx(
        column_total * 0.2,
        abs=2,
    )
    view.close()


def test_double_clicking_track_emits_selected_track(
    qt_application: QApplication,
) -> None:
    view, repository = make_view(qt_application)
    track = Track("track-001", "song.mp3", "Song")
    repository.save(Playlist("playlist-001", "Practice", (track,)))
    view.refresh()
    received: list[Track] = []
    view.play_requested.connect(received.append)

    item = view.track_list.item(0, 0)
    assert item is not None
    view.track_list.itemDoubleClicked.emit(item)

    assert received == [PlaylistTrackSelection((track,), 0, "playlist-001")]


def test_playing_playlist_and_track_use_background_highlights(
    qt_application: QApplication,
) -> None:
    view, repository = make_view(qt_application)
    track = Track("track-001", "song.mp3", "Song")
    repository.save(Playlist("playlist-001", "Practice", (track,)))
    view.refresh()

    view.set_playing_track("playlist-001", "track-001")

    playlist_item = view.playlist_list.item(0)
    track_item = view.track_list.item(0, 0)
    assert playlist_item is not None
    assert track_item is not None
    assert playlist_item.background().color().name() == "#dcecff"
    assert track_item.background().color().name() == "#dcecff"


def test_playlist_action_buttons_match_transport_size(
    qt_application: QApplication,
) -> None:
    view, _ = make_view(qt_application)

    buttons = view.findChildren(QPushButton)

    assert len(buttons) == 3
    assert all(button.width() == 96 and button.height() == 96 for button in buttons)
    assert all(button.text() != "プレイリスト\nを再生" for button in buttons)


def test_track_table_reorders_tracks_and_persists_order(
    qt_application: QApplication,
) -> None:
    view, repository = make_view(qt_application)
    tracks = tuple(
        Track(f"track-00{index}", f"song-{index}.mp3", f"Song {index}")
        for index in range(1, 4)
    )
    repository.save(Playlist("playlist-001", "Practice", tracks))
    view.refresh()

    assert view.track_list.dragDropMode() is QAbstractItemView.DragDropMode.InternalMove
    first_title = view.track_list.takeItem(0, 0)
    first_duration = view.track_list.takeItem(0, 1)
    second_title = view.track_list.takeItem(1, 0)
    second_duration = view.track_list.takeItem(1, 1)
    assert first_title is not None
    assert first_duration is not None
    assert second_title is not None
    assert second_duration is not None
    view.track_list.setItem(0, 0, second_title)
    view.track_list.setItem(0, 1, second_duration)
    view.track_list.setItem(1, 0, first_title)
    view.track_list.setItem(1, 1, first_duration)

    view._reorder_tracks()

    playlist = repository.get("playlist-001")
    assert playlist is not None
    assert playlist.tracks == (tracks[1], tracks[0], tracks[2])


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


def test_track_table_accepts_dropped_files_and_folders(
    qt_application: QApplication,
    tmp_path: Path,
) -> None:
    view, repository = make_view(qt_application)
    practice_folder = tmp_path / "practice"
    practice_folder.mkdir()
    first_path = tmp_path / "first.wav"
    second_path = practice_folder / "second.mp3"
    with wave.open(str(first_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(100)
        audio.writeframes(b"\0\0" * 100)
    second_path.write_bytes(b"second")

    view.track_list.paths_dropped.emit([first_path, practice_folder])

    playlist = repository.get("playlist-001")
    assert playlist is not None
    assert view.track_list.acceptDrops()
    assert [Path(track.path) for track in playlist.tracks] == [
        first_path,
        second_path,
    ]
    assert playlist.tracks[0].duration_seconds == pytest.approx(1.0)
    assert view.track_list.item(0, 1).text() == "0:01"


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