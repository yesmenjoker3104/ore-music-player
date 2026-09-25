import wave
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from conftest import FakePlaylistRepository
from PySide6.QtCore import QItemSelectionModel, QSettings, Qt
from PySide6.QtGui import QIcon, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
    QPushButton,
    QSlider,
)

from ore_music_player.application.playback_service import PlaybackService
from ore_music_player.application.playlist_service import PlaylistService
from ore_music_player.application.ports import PlaybackBackendError
from ore_music_player.domain.models import Track
from ore_music_player.ui.main_window import (
    SLIDER_GROOVE_HEIGHT,
    MainWindow,
    PlaybackMode,
)


@dataclass
class FakePlaybackBackend:
    speed_calls: list[float] = field(default_factory=list)
    volume_calls: list[float] = field(default_factory=list)
    seek_calls: list[float] = field(default_factory=list)
    loop_calls: list[tuple[float | None, float | None]] = field(
        default_factory=list
    )
    play_calls: int = 0
    pause_calls: int = 0
    stop_calls: int = 0
    position_seconds: float = 0.0
    duration_seconds: float | None = None
    fail_seek: bool = False

    def load(self, track) -> None:
        pass

    def play(self) -> None:
        self.play_calls += 1

    def pause(self) -> None:
        self.pause_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def seek(self, position: float) -> None:
        if self.fail_seek:
            raise PlaybackBackendError("seek failed")
        self.seek_calls.append(position)
        self.position_seconds = position

    def set_speed(self, speed: float) -> None:
        self.speed_calls.append(speed)

    def set_volume(self, volume: float) -> None:
        self.volume_calls.append(volume)

    def set_loop(
        self,
        start_seconds: float | None,
        end_seconds: float | None,
    ) -> None:
        self.loop_calls.append((start_seconds, end_seconds))


@pytest.fixture(scope="session")
def qt_application() -> QApplication:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


def make_window(
    qt_application: QApplication,
) -> tuple[MainWindow, FakePlaybackBackend]:
    backend = FakePlaybackBackend()
    repository = FakePlaylistRepository()
    window = MainWindow(
        PlaybackService(backend),
        PlaylistService(repository),
    )
    return window, backend


def test_file_operations_are_in_file_menu_not_tile_buttons(
    qt_application: QApplication,
) -> None:
    window, _ = make_window(qt_application)

    file_menu_action = next(
        action for action in window.menuBar().actions() if action.text() == "ファイル"
    )
    file_menu = file_menu_action.menu()
    assert file_menu is not None
    assert [action.text() for action in file_menu.actions()] == [
        "音声ファイルを開く",
        "フォルダを開く",
        "更新を確認",
    ]

    button_texts = {
        button.text() for button in window.findChildren(QPushButton)
    }
    assert "音声ファイル\nを開く" not in button_texts
    assert "フォルダを開く" not in button_texts

    window.close()


def test_application_icon_is_configured(
    qt_application: QApplication,
) -> None:
    from ore_music_player.app import _application_icon_path

    icon_path = _application_icon_path()
    assert icon_path.is_file()
    qt_application.setWindowIcon(QIcon(str(icon_path)))
    assert not qt_application.windowIcon().isNull()


def test_file_tree_uses_filesystem_hierarchy_and_duration_column(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    music_folder = tmp_path / "music"
    nested_folder = music_folder / "practice"
    nested_folder.mkdir(parents=True)
    audio_path = nested_folder / "second.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(100)
        audio.writeframes(b"\0\0" * 100)

    window.load_tracks(
        (Track("track-001", str(audio_path), "Second", duration_seconds=1.0),)
    )
    QTest.qWait(100)

    assert window.file_system_model.columnCount() == 2
    assert [
        window.file_system_model.headerData(
            column,
            Qt.Orientation.Horizontal,
        )
        for column in range(window.file_system_model.columnCount())
    ] == ["ファイル名", "再生時間"]
    index = window.file_system_model.index(str(audio_path))
    assert index.isValid()
    assert window.file_system_model.fileName(index) == "second.wav"
    assert (
        window.file_system_model.data(
            index.siblingAtColumn(1),
            Qt.ItemDataRole.DisplayRole,
        )
        == "0:01"
    )

    window.close()


def test_file_tree_filter_hides_non_matching_audio_files(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    window._settings.clear()
    first_path = tmp_path / "first.wav"
    second_path = tmp_path / "second.wav"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    window._set_file_tree_root(tmp_path)
    window.load_tracks(window._tracks_from_paths((first_path, second_path)))
    QTest.qWait(100)

    window.file_filter_edit.setText("first")
    QTest.qWait(100)
    first_index = window.file_system_model.index(str(first_path))
    second_index = window.file_system_model.index(str(second_path))

    assert not window.file_tree.isRowHidden(first_index.row(), first_index.parent())
    assert window.file_tree.isRowHidden(second_index.row(), second_index.parent())
    window.close()


def test_playing_file_tree_row_uses_background_highlight(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    audio_path = tmp_path / "playing.wav"
    audio_path.write_bytes(b"audio")
    window._settings.clear()
    window._set_file_tree_root(tmp_path)
    window.load_tracks(
        (Track("track-001", str(audio_path), "Playing"),)
    )
    QTest.qWait(100)

    index = window.file_system_model.index(str(audio_path))
    background = window.file_system_model.data(
        index,
        Qt.ItemDataRole.BackgroundRole,
    )

    assert background is not None
    assert background.name() == "#b8d8e8"
    foreground = window.file_system_model.data(
        index,
        Qt.ItemDataRole.ForegroundRole,
    )
    assert foreground is not None
    assert foreground.name() == "#102a43"
    window.close()


def test_loading_track_updates_recent_menu(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    window._settings.clear()
    audio_path = tmp_path / "recent.wav"
    audio_path.write_bytes(b"audio")

    window.load_tracks(window._tracks_from_paths((audio_path,)))

    assert window._recent_paths[0] == audio_path.resolve()
    assert window.recent_menu.actions()[0].text() == audio_path.name
    window.close()


def test_last_playback_state_is_restored(
    qt_application: QApplication,
    tmp_path,
) -> None:
    audio_path = tmp_path / "resume.wav"
    audio_path.write_bytes(b"audio")
    window, _ = make_window(qt_application)
    window._settings.clear()
    window._registered_paths.clear()
    window.load_tracks(window._tracks_from_paths((audio_path,)))
    window.playback_service.set_speed("0.75")
    window.playback_service.seek(12.0)
    window.playback_service.set_a(3.0)
    window.playback_service.set_b(8.0)
    window._save_left_pane_settings()
    window.close()

    restored_window, restored_backend = make_window(qt_application)
    try:
        qt_application.processEvents()
        assert restored_window._current_track is not None
        assert Path(restored_window._current_track.path) == audio_path.resolve()
        assert restored_window.playback_service.state.speed == 0.75
        assert restored_window.playback_service.state.a_point_seconds == 3.0
        assert restored_window.playback_service.state.b_point_seconds == 8.0
        assert restored_backend.seek_calls[-1] == 12.0
    finally:
        settings = restored_window._settings
        restored_window.close()
        settings.clear()
        settings.sync()


def test_open_folders_keep_both_folders_visible(
    qt_application: QApplication,
    monkeypatch,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    window._settings.clear()
    window._registered_paths.clear()
    window._registered_folders.clear()
    window._queue = ()
    window._drive_roots.clear()
    window.drive_selector.clear()
    parent_folder = tmp_path / "band-practice"
    first_folder = parent_folder / "first-band"
    second_folder = parent_folder / "second-band"
    first_folder.mkdir(parents=True)
    second_folder.mkdir()
    first_path = first_folder / "first.wav"
    second_path = second_folder / "second.wav"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args: str(first_folder),
    )
    window.open_folder()
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args: str(second_folder),
    )
    window.open_folder()

    assert Path(window.file_root_label.text()) == first_folder
    assert {Path(track.path) for track in window._queue} == {
        first_path,
        second_path,
    }
    window.close()


def test_registered_folder_roots_merge_nested_folder_under_parent(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    window._settings.clear()
    window._registered_paths.clear()
    window._registered_folders.clear()
    pc_folder = tmp_path / "04_PC"
    music_folder = tmp_path / "05_MUSIC"
    nested_folder = music_folder / "band" / "OT"
    pc_folder.mkdir()
    nested_folder.mkdir(parents=True)

    window._registered_folders.update({pc_folder, music_folder, nested_folder})
    window._registered_paths.update(
        {
            pc_folder / "pc.wav",
            nested_folder / "ot.wav",
        }
    )
    window.file_system_model.set_root_paths(window._registered_folders)

    assert window.file_system_model._root_paths == (pc_folder, music_folder)
    window.close()


def test_delete_button_unregisters_multiple_selected_audio_files(
    qt_application: QApplication,
    monkeypatch,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    first_path = tmp_path / "first.wav"
    second_path = tmp_path / "second.mp3"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    window._set_file_tree_root(tmp_path)
    window.load_tracks(
        (
            Track("track-001", str(first_path), "First"),
            Track("track-002", str(second_path), "Second"),
        )
    )
    QTest.qWait(100)

    selection_model = window.file_tree.selectionModel()
    select_rows = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    selection_model.select(window.file_system_model.index(str(first_path)), select_rows)
    selection_model.select(window.file_system_model.index(str(second_path)), select_rows)

    assert window.delete_file_button.isEnabled()
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    window.delete_selected_files()

    assert first_path.exists()
    assert second_path.exists()
    assert not window.file_system_model.index(str(first_path)).isValid()
    assert not window.file_system_model.index(str(second_path)).isValid()
    assert window._queue == ()
    assert window._current_track is None
    assert not window.delete_file_button.isEnabled()
    window.close()


def test_delete_button_supports_folders_and_cancel_keeps_file(
    qt_application: QApplication,
    monkeypatch,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    window._settings.clear()
    window._registered_paths.clear()
    window._registered_folders.clear()
    folder_path = tmp_path / "practice"
    folder_path.mkdir()
    audio_path = tmp_path / "practice.wav"
    audio_path.write_bytes(b"audio")
    window._set_file_tree_root(tmp_path)
    window._registered_folders.add(folder_path.resolve())
    window._update_file_tree_visibility()
    QTest.qWait(100)
    window._update_file_tree_visibility()

    selection_model = window.file_tree.selectionModel()
    select_rows = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    selection_model.select(window.file_system_model.index(str(folder_path)), select_rows)
    qt_application.processEvents()
    monkeypatch.setattr(
        window,
        "_selected_unregister_paths",
        lambda: (folder_path,),
    )
    window._update_delete_button_state()
    assert window.delete_file_button.isEnabled()

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    window.delete_selected_files()
    assert folder_path.exists()
    assert not window.file_tree.isRowHidden(
        window.file_system_model.index(str(folder_path)).row(),
        window.file_system_model.index(str(folder_path)).parent(),
    )

    selection_model.clearSelection()
    selection_model.select(window.file_system_model.index(str(audio_path)), select_rows)
    assert window.delete_file_button.isEnabled()
    window.delete_selected_files()

    assert audio_path.exists()
    window.close()


def test_delete_button_unregisters_folder_without_deleting_it(
    qt_application: QApplication,
    monkeypatch,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    folder_path = tmp_path / "practice"
    folder_path.mkdir()
    audio_path = folder_path / "song.wav"
    audio_path.write_bytes(b"audio")
    window._set_file_tree_root(tmp_path)
    window._registered_folders.add(folder_path.resolve())
    window.load_tracks(window._tracks_from_paths((audio_path,)))
    QTest.qWait(100)

    selection_model = window.file_tree.selectionModel()
    select_rows = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    selection_model.select(window.file_system_model.index(str(folder_path)), select_rows)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    window.delete_selected_files()

    assert folder_path.exists()
    assert audio_path.exists()
    assert window._queue == ()
    assert audio_path.resolve() not in window._registered_paths
    window.close()


def test_left_pane_settings_are_saved_and_restored(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    try:
        window._settings.clear()
        window._registered_paths.clear()
        window.show()
        qt_application.processEvents()
        window._set_file_tree_root(tmp_path)
        window.resize(700, 520)
        window.main_splitter.setSizes([180, 500])
        window.right_splitter.setSizes([150, 300])
        window.file_tree.setColumnWidth(0, 320)
        window.file_tree.setColumnWidth(1, 95)
        window._save_left_pane_settings()
        saved_left_width = window.main_splitter.sizes()[0]
        saved_right_sizes = window.right_splitter.sizes()
        saved_window_size = window.size()
        saved_file_columns = (
            window.file_tree.columnWidth(0),
            window.file_tree.columnWidth(1),
        )
    finally:
        window.close()

    restored_window, _ = make_window(qt_application)
    try:
        qt_application.processEvents()
        assert Path(restored_window.file_system_model.rootPath()) == tmp_path
        assert not restored_window.file_tree.rootIndex().isValid()
        assert restored_window.main_splitter.sizes()[0] == saved_left_width
        assert restored_window.right_splitter.sizes()[0] == saved_right_sizes[0]
        assert restored_window.height() == saved_window_size.height()
        assert restored_window.width() >= 700
        assert (
            restored_window.file_tree.columnWidth(0),
            restored_window.file_tree.columnWidth(1),
        ) == saved_file_columns
    finally:
        settings = restored_window._settings
        restored_window.close()
        settings.clear()
        settings.sync()


def test_saved_left_pane_layout_is_migrated_by_75_pixels(
    qt_application: QApplication,
) -> None:
    settings = QSettings("OreMusicPlayer", "OreMusicPlayer")
    settings.clear()
    window, _ = make_window(qt_application)
    window.show()
    qt_application.processEvents()
    window.main_splitter.setSizes([245, 715])
    splitter_state = window.main_splitter.saveState()
    window.close()
    settings.setValue(window._SPLITTER_STATE_KEY, splitter_state)
    settings.setValue(window._SPLITTER_LAYOUT_VERSION_KEY, 16)
    settings.remove(window._WINDOW_GEOMETRY_KEY)
    settings.sync()

    migrated_window, _ = make_window(qt_application)
    try:
        migrated_window.show()
        qt_application.processEvents()
        before_width = migrated_window.main_splitter.sizes()[0]
        migrated_window._move_splitter_right()

        assert migrated_window.main_splitter.sizes()[0] == before_width + 100
        assert (
            settings.value(
                migrated_window._SPLITTER_LAYOUT_VERSION_KEY,
                0,
                type=int,
            )
            == 17
        )
    finally:
        migrated_window.close()
        settings.clear()
        settings.sync()


def test_registered_tracks_are_restored_after_root_changes(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    window._settings.clear()
    window._registered_paths.clear()
    first_folder = tmp_path / "first-drive"
    second_folder = tmp_path / "second-drive"
    first_folder.mkdir()
    second_folder.mkdir()
    first_path = first_folder / "first.wav"
    second_path = second_folder / "second.wav"
    first_path.write_bytes(b"audio")
    second_path.write_bytes(b"audio")

    window._set_file_tree_root(first_folder)
    window._append_tracks(window._tracks_from_paths((first_path,)))
    window._set_file_tree_root(second_folder)
    window._append_tracks(window._tracks_from_paths((second_path,)))
    window.close()

    restored_window, _ = make_window(qt_application)
    try:
        QTest.qWait(250)
        assert restored_window._registered_paths == {
            first_path.resolve(),
            second_path.resolve(),
        }
        assert {
            Path(track.path).resolve() for track in restored_window._queue
        } == restored_window._registered_paths
        for path in (first_path, second_path):
            index = restored_window.file_system_model.index(str(path))
            assert index.isValid()
            assert not restored_window.file_tree.isRowHidden(
                index.row(),
                index.parent(),
            )
    finally:
        settings = restored_window._settings
        restored_window.close()
        settings.clear()
        settings.sync()


def test_playlist_tracks_are_registered_for_left_pane_on_restore(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    audio_path = tmp_path / "playlist-track.wav"
    audio_path.write_bytes(b"audio")
    playlist_service = window.playlist_view.playlist_service
    playlist_service.create("playlist-001", "Practice")
    playlist_service.add_track(
        "playlist-001",
        Track("playlist-track-001", str(audio_path), "Playlist Track"),
    )
    window._settings.clear()
    window._registered_paths.clear()
    window._registered_folders.clear()
    window._restore_registered_tracks()

    try:
        QTest.qWait(250)
        assert audio_path.resolve() in window._registered_paths
        index = window.file_system_model.index(str(audio_path))
        assert index.isValid()
        assert not window.file_tree.isRowHidden(index.row(), index.parent())
    finally:
        settings = window._settings
        window.close()
        settings.clear()
        settings.sync()


def test_tracks_from_paths_reads_audio_duration(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    audio_path = tmp_path / "tone.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(100)
        audio.writeframes(b"\0\0" * 100)

    track = window._tracks_from_paths((audio_path,))[0]

    assert track.duration_seconds == pytest.approx(1.0)
    window.close()


def test_open_folder_loads_all_audio_files(
    qt_application: QApplication,
    monkeypatch,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    window._settings.clear()
    window._registered_paths.clear()
    window._queue = ()
    music_folder = tmp_path / "music"
    music_folder.mkdir()
    nested_folder = music_folder / "practice"
    nested_folder.mkdir()
    for path in (
        music_folder / "first.wav",
        nested_folder / "second.wav",
        nested_folder / "third.wav",
    ):
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(100)
            audio.writeframes(b"\0\0" * 100)
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args: str(music_folder),
    )

    window.open_folder()

    assert [Path(track.path).name for track in window._queue] == [
        "first.wav",
        "second.wav",
        "third.wav",
    ]
    qt_application.processEvents()
    nested_index = window.file_system_model.index(str(nested_folder))
    assert not window.file_tree.isExpanded(nested_index)
    assert not window.file_tree.isRowHidden(
        window.file_system_model.index(str(music_folder / "first.wav")).row(),
        window.file_system_model.index(str(music_folder / "first.wav")).parent(),
    )
    window.close()


def test_file_tree_hides_unregistered_audio_files(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    music_folder = tmp_path / "music"
    music_folder.mkdir()
    registered_path = music_folder / "registered.wav"
    unregistered_path = music_folder / "unregistered.wav"
    for path in (registered_path, unregistered_path):
        path.write_bytes(b"audio")

    window._set_file_tree_root(music_folder)
    window.load_tracks(window._tracks_from_paths((registered_path,)))
    QTest.qWait(100)

    registered_index = window.file_system_model.index(str(registered_path))
    unregistered_index = window.file_system_model.index(str(unregistered_path))
    assert not window.file_tree.isRowHidden(
        registered_index.row(), registered_index.parent()
    )
    assert window.file_tree.isRowHidden(
        unregistered_index.row(), unregistered_index.parent()
    )
    window.close()


def test_registered_audio_remains_visible_after_loading_another_track(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    first_path = tmp_path / "first.wav"
    second_path = tmp_path / "second.wav"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    window._set_file_tree_root(tmp_path)

    window.load_tracks(window._tracks_from_paths((first_path,)))
    window.load_tracks(window._tracks_from_paths((second_path,)))
    QTest.qWait(100)

    first_index = window.file_system_model.index(str(first_path))
    second_index = window.file_system_model.index(str(second_path))
    assert not window.file_tree.isRowHidden(first_index.row(), first_index.parent())
    assert not window.file_tree.isRowHidden(second_index.row(), second_index.parent())
    window.close()


def test_drive_selector_is_available_for_multiple_registered_drives(
    qt_application: QApplication,
) -> None:
    window, _ = make_window(qt_application)
    window._registered_paths = {
        Path("C:/Music/song.wav"),
        Path("D:/Practice/song.wav"),
    }
    window._refresh_drive_selector()

    assert not window.drive_selector.isHidden()
    assert {
        window.drive_selector.itemText(index)
        for index in range(window.drive_selector.count())
    } == {str(Path("C:/")), str(Path("D:/"))}
    window.drive_selector.setCurrentText(str(Path("D:/")))
    assert window._drive_root_path(str(Path("D:/"))) == Path(
        "D:/Practice"
    )
    window.close()


def test_open_folder_appends_to_existing_queue(
    qt_application: QApplication,
    monkeypatch,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    first_path = tmp_path / "first.wav"
    second_folder = tmp_path / "second"
    second_folder.mkdir()
    second_path = second_folder / "second.wav"
    for path in (first_path, second_path):
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(100)
            audio.writeframes(b"\0\0" * 100)

    window.load_tracks(window._tracks_from_paths((first_path,)))
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args: str(second_folder),
    )

    window.open_folder()

    assert [Path(track.path).name for track in window._queue] == [
        "first.wav",
        "second.wav",
    ]
    window.close()


def test_open_folder_does_not_duplicate_existing_tracks(
    qt_application: QApplication,
    monkeypatch,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    music_folder = tmp_path / "music"
    music_folder.mkdir()
    audio_path = music_folder / "song.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(100)
        audio.writeframes(b"\0\0" * 100)

    window.load_tracks(window._tracks_from_paths((audio_path,)))
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args: str(music_folder),
    )

    window.open_folder()

    assert [Path(track.path).name for track in window._queue] == ["song.wav"]
    window.close()


def test_play_pause_uses_one_toggle_button(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    window.load_tracks((Track("track-001", "song.mp3", "Song"),))

    playback_buttons = [
        button
        for button in window.findChildren(QPushButton)
        if button.text() in {"再生", "一時停止"}
    ]
    assert playback_buttons == [window.play_pause_button]
    assert backend.play_calls == 1
    assert window.status_label.text() == "再生中"
    assert window.play_pause_button.text() == "一時停止"

    window.play_pause_button.click()
    assert backend.pause_calls == 1
    assert window.status_label.text() == "一時停止"
    assert window.play_pause_button.text() == "再生"

    window.play()
    window.stop()
    assert backend.stop_calls == 1
    assert window.status_label.text() == "停止中"
    assert window.play_pause_button.text() == "再生"

    window.play_pause_button.click()
    assert backend.play_calls == 3
    assert window.status_label.text() == "再生中"
    assert window.play_pause_button.text() == "一時停止"

    window.close()


def test_selecting_file_then_pressing_play_starts_that_file(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, backend = make_window(qt_application)
    first_path = tmp_path / "first.wav"
    second_path = tmp_path / "second.wav"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")

    window._set_file_tree_root(tmp_path)
    window.load_tracks((Track("track-001", str(first_path), "First"),))
    second_index = window.file_system_model.index(str(second_path))
    window.file_tree.setCurrentIndex(second_index)
    window.stop()

    window.play_pause_button.click()

    assert window._current_track is not None
    assert Path(window._current_track.path) == second_path
    assert backend.play_calls == 2
    window.close()


def test_double_clicking_existing_queued_file_starts_it(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, backend = make_window(qt_application)
    first_path = tmp_path / "first.wav"
    second_path = tmp_path / "second.wav"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")

    window._set_file_tree_root(tmp_path)
    window.load_tracks(
        (
            Track("track-001", str(first_path), "First"),
            Track("track-002", str(second_path), "Second"),
        )
    )
    second_index = window.file_system_model.index(str(second_path))
    window._load_file_from_tree(second_index)

    assert window._queue_index == 1
    assert window._current_track is not None
    assert Path(window._current_track.path) == second_path
    assert backend.play_calls == 2
    window.close()


def test_selecting_playlist_track_then_pressing_play_starts_that_track(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    track = Track("playlist-track-001", "playlist-song.mp3", "Playlist Song")
    playlist_service = window.playlist_view.playlist_service
    playlist_service.create("playlist-001", "Practice")
    playlist_service.add_track("playlist-001", track)
    window.playlist_view.refresh()
    window.playlist_view.track_list.selectRow(0)
    window.stop()

    window.play_pause_button.click()

    assert window._current_track == track
    assert backend.play_calls == 1
    window.close()


def test_double_clicking_playlist_track_starts_that_track(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    track = Track("playlist-track-001", "playlist-song.mp3", "Playlist Song")
    playlist_service = window.playlist_view.playlist_service
    playlist_service.create("playlist-001", "Practice")
    playlist_service.add_track("playlist-001", track)
    window.playlist_view.refresh()
    item = window.playlist_view.track_list.item(0, 0)
    assert item is not None

    window.playlist_view.track_list.itemDoubleClicked.emit(item)

    assert window._current_track == track
    assert backend.play_calls == 1
    playlist_item = window.playlist_view.playlist_list.item(0)
    assert playlist_item is not None
    assert playlist_item.background().color().name() == "#b8d8e8"
    assert item.background().color().name() == "#b8d8e8"

    window.load_tracks((Track("catalog-track-001", "catalog-song.mp3", "Catalog"),))
    assert playlist_item.background().style() == Qt.BrushStyle.NoBrush
    assert item.background().style() == Qt.BrushStyle.NoBrush
    window.close()


def test_transport_and_ab_buttons_share_one_row(
    qt_application: QApplication,
) -> None:
    window, _ = make_window(qt_application)
    window.show()
    qt_application.processEvents()

    control_buttons = (
        window.previous_button,
        window.play_pause_button,
        window.stop_button,
        window.next_button,
        window.set_a_button,
        window.set_b_button,
        window.loop_button,
        window.playback_mode_button,
    )
    assert all(button.height() == 96 for button in control_buttons)
    assert len({button.geometry().top() for button in control_buttons}) == 1
    window.close()


def test_playback_mode_button_cycles_through_three_modes(
    qt_application: QApplication,
) -> None:
    window, _ = make_window(qt_application)

    assert window._playback_mode is PlaybackMode.REPEAT_ALL
    assert "全曲ループ" in window.playback_mode_button.text()

    window.playback_mode_button.click()
    assert window._playback_mode is PlaybackMode.SHUFFLE
    assert "ランダム" in window.playback_mode_button.text()

    window.playback_mode_button.click()
    assert window._playback_mode is PlaybackMode.REPEAT_ONE
    assert "1曲ループ" in window.playback_mode_button.text()

    window.playback_mode_button.click()
    assert window._playback_mode is PlaybackMode.REPEAT_ALL
    window.close()


def test_repeat_one_restarts_current_track_at_end(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    window.load_tracks((Track("track-001", "song.mp3", "Song"),))
    window._playback_mode = PlaybackMode.REPEAT_ONE
    window._set_duration(120.0)
    backend.position_seconds = 120.0

    window._update_position()

    assert window._queue_index == 0
    assert backend.seek_calls == []
    assert backend.play_calls == 2
    window.close()


def test_repeat_one_reloads_track_when_end_seek_fails(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    window.load_tracks((Track("track-001", "song.mp3", "Song"),))
    window._playback_mode = PlaybackMode.REPEAT_ONE
    window._set_duration(120.0)
    backend.position_seconds = 120.0
    backend.fail_seek = True

    window._update_position()

    assert window._queue_index == 0
    assert backend.seek_calls == []
    assert backend.play_calls == 2
    window.close()


def test_repeat_all_wraps_to_first_track_at_end(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    tracks = (
        Track("track-001", "first.mp3", "First"),
        Track("track-002", "second.mp3", "Second"),
    )
    window.load_tracks(tracks, index=1)
    window._playback_mode = PlaybackMode.REPEAT_ALL
    window._set_duration(120.0)
    backend.position_seconds = 120.0

    window._update_position()

    assert window._queue_index == 0
    assert window._current_track == tracks[0]
    window.close()


def test_shuffle_advances_to_a_different_track(
    qt_application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, _ = make_window(qt_application)
    tracks = (
        Track("track-001", "first.mp3", "First"),
        Track("track-002", "second.mp3", "Second"),
    )
    window.load_tracks(tracks)
    window._playback_mode = PlaybackMode.SHUFFLE
    monkeypatch.setattr(
        "ore_music_player.ui.main_window.random.choice",
        lambda choices: choices[0],
    )

    window._advance_track(automatic=True)

    assert window._queue_index == 1
    window.close()


def test_loaded_tracks_keep_current_index_when_navigating(
    qt_application: QApplication,
) -> None:
    window, _ = make_window(qt_application)
    tracks = (
        Track("track-001", "first.mp3", "First song"),
        Track("track-002", "second.mp3", "Second song"),
    )

    window.load_tracks(tracks, index=1)

    assert window._queue_index == 1

    window.previous_track()
    assert window._queue_index == 0
    window.next_track()
    assert window._queue_index == 1

    window.close()


def test_ab_buttons_show_positions_and_toggle_loop_button(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    window.load_tracks((Track("track-001", "song.mp3", "Song"),))
    window._set_duration(120.0)

    assert window.set_a_button.text() == "A設定"
    assert window.set_b_button.text() == "B設定"
    assert window.loop_button.text() == "A/Bループ\n開始"
    assert not window.loop_button.isEnabled()

    backend.position_seconds = 12.4
    window.set_a()
    assert window.set_a_button.text() == "A設定\n0:12"
    assert window.position_slider._a_marker_seconds == 12.4
    assert window.position_slider._b_marker_seconds is None
    assert not window.loop_button.isEnabled()

    backend.position_seconds = 65.9
    window.set_b()
    assert window.set_b_button.text() == "B設定\n1:05"
    assert window.position_slider._b_marker_seconds == 65.9
    assert window.loop_button.isEnabled()

    window.loop_button.click()
    assert window.playback_service.state.loop_enabled
    assert window.loop_button.text() == "A/B解除"
    assert backend.loop_calls[-1] == (12.4, 65.9)

    window.loop_button.click()
    assert not window.playback_service.state.loop_enabled
    assert window.loop_button.text() == "A/Bループ\n開始"
    assert window.set_a_button.text() == "A設定"
    assert window.set_b_button.text() == "B設定"
    assert not window.loop_button.isEnabled()
    assert window.position_slider._a_marker_seconds is None
    assert window.position_slider._b_marker_seconds is None
    assert backend.loop_calls[-1] == (None, None)

    window.close()


def test_ab_shortcuts_set_points_and_toggle_loop(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    window.load_tracks((Track("track-001", "song.mp3", "Song"),))
    window._set_duration(120.0)
    shortcuts = {
        shortcut.key().toString(): shortcut
        for shortcut in window._shortcuts
    }

    backend.position_seconds = 12.0
    shortcuts["A"].activated.emit()
    backend.position_seconds = 60.0
    shortcuts["B"].activated.emit()
    shortcuts["S"].activated.emit()

    state = window.playback_service.state
    assert state.a_point_seconds == 12.0
    assert state.b_point_seconds == 60.0
    assert state.loop_enabled
    assert backend.loop_calls[-1] == (12.0, 60.0)

    window.close()


def test_speed_slider_starts_at_default_speed(
    qt_application: QApplication,
) -> None:
    window, _ = make_window(qt_application)

    assert window.speed_slider.minimum() == 0
    assert window.speed_slider.maximum() == 20
    assert window.speed_slider.value() == 10
    assert window.speed_current_label.text() == "1.00x"

    window.close()


def test_speed_slider_updates_current_speed_and_backend(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)

    window.speed_slider.setValue(0)
    assert window.speed_current_label.text() == "0.50x"
    assert backend.speed_calls[-1] == 0.5

    window.speed_slider.setValue(20)
    assert window.speed_current_label.text() == "1.50x"
    assert backend.speed_calls[-1] == 1.5

    window.close()


def test_volume_slider_is_small_and_updates_backend(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    window.show()
    qt_application.processEvents()

    assert window.volume_slider.value() == 100
    assert window.volume_slider.width() == 160
    assert window.volume_value_label.text() == "100"
    assert window.volume_slider.height() == window.speed_slider.height()
    assert window.volume_slider.minimumHeight() == window.speed_slider.minimumHeight()
    assert window.volume_slider.styleSheet() == window.speed_slider.styleSheet()
    window.volume_slider.setValue(42)

    assert backend.volume_calls[-1] == 42.0
    assert window.volume_value_label.text() == "42"
    window.close()


def test_volume_setting_is_saved_and_restored(
    qt_application: QApplication,
) -> None:
    window, _ = make_window(qt_application)
    try:
        window._settings.clear()
        window.volume_slider.setValue(42)
        window._save_left_pane_settings()
    finally:
        window.close()

    restored_window, _ = make_window(qt_application)
    try:
        assert restored_window.volume_slider.value() == 42
        assert restored_window.playback_service.state.volume == 42
    finally:
        settings = restored_window._settings
        restored_window.close()
        settings.clear()
        settings.sync()


def test_keyboard_seek_moves_by_five_seconds(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    window.load_tracks((Track("track-001", "song.mp3", "Song"),))
    window._duration_seconds = 60.0
    backend.position_seconds = 10.0

    window.seek_forward()
    window.seek_backward()

    assert backend.seek_calls[-2:] == [15.0, 10.0]
    window.close()


def test_position_slider_seeks_only_when_released(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    window.load_tracks((Track("track-001", "song.mp3", "Song"),))
    window.position_slider.setRange(0, 120_000)

    assert window.position_slider.hasTracking()

    window._start_seeking()
    window.position_slider.setSliderPosition(60_000)
    window._preview_seek(window.position_slider.sliderPosition())

    assert backend.seek_calls == []
    assert window.position_label.text() == "1:00"

    window._finish_seeking()

    assert backend.seek_calls == [60.0]
    assert backend.play_calls == 2
    assert window.position_label.text() == "1:00"

    window.close()


def test_position_slider_ignores_transient_backend_seek_error(
    qt_application: QApplication,
) -> None:
    window, backend = make_window(qt_application)
    window.load_tracks((Track("track-001", "song.mp3", "Song"),))
    window.position_slider.setRange(0, 120_000)
    window._start_seeking()
    window.position_slider.setSliderPosition(60_000)
    backend.fail_seek = True

    window._finish_seeking()

    assert window.playback_service.state.position_seconds == 0.0
    window.close()


def test_seek_and_speed_sliders_share_width_and_thickness(
    qt_application: QApplication,
) -> None:
    window, _ = make_window(qt_application)
    window.show()
    qt_application.processEvents()

    assert window.speed_slider.width() == 160
    assert window.speed_slider.width() >= 160
    assert window.right_splitter.sizes()[0] <= 350
    assert (
        window.position_slider.minimumHeight()
        == window.speed_slider.minimumHeight()
    )
    assert window.position_slider.styleSheet() == window.speed_slider.styleSheet()
    assert "height: 18px" in window.position_slider.styleSheet()

    window.close()


def test_playlist_starts_immediately_below_speed_slider(
    qt_application: QApplication,
) -> None:
    window, _ = make_window(qt_application)
    window.show()
    qt_application.processEvents()

    playlist_view = window.right_splitter.widget(1)
    assert playlist_view is not None
    row_bottom = max(
        window.speed_slider.geometry().bottom(),
        window.volume_slider.geometry().bottom(),
    )
    assert playlist_view.geometry().top() <= row_bottom + 6

    window.close()


def test_slider_renders_a_thick_track(
    qt_application: QApplication,
) -> None:
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(25)
    MainWindow._configure_slider(slider)
    slider.resize(240, 44)
    slider.show()
    qt_application.processEvents()

    image = slider.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    background = image.pixelColor(20, 0)
    painted_rows = [
        row
        for row in range(image.height())
        if image.pixelColor(20, row) != background
    ]

    assert painted_rows
    assert max(painted_rows) - min(painted_rows) + 1 >= SLIDER_GROOVE_HEIGHT

    slider.close()