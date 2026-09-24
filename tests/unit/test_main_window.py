import wave
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QImage
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
from ore_music_player.domain.models import Playlist, Track
from ore_music_player.ui.main_window import (
    SLIDER_GROOVE_HEIGHT,
    MainWindow,
)


@dataclass
class FakePlaybackBackend:
    speed_calls: list[float] = field(default_factory=list)
    seek_calls: list[float] = field(default_factory=list)
    loop_calls: list[tuple[float | None, float | None]] = field(
        default_factory=list
    )
    play_calls: int = 0
    pause_calls: int = 0
    stop_calls: int = 0
    position_seconds: float = 0.0
    duration_seconds: float | None = None

    def load(self, track) -> None:
        pass

    def play(self) -> None:
        self.play_calls += 1

    def pause(self) -> None:
        self.pause_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def seek(self, position: float) -> None:
        self.seek_calls.append(position)

    def set_speed(self, speed: float) -> None:
        self.speed_calls.append(speed)

    def set_loop(
        self,
        start_seconds: float | None,
        end_seconds: float | None,
    ) -> None:
        self.loop_calls.append((start_seconds, end_seconds))


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
    ]

    button_texts = {
        button.text() for button in window.findChildren(QPushButton)
    }
    assert "音声ファイル\nを開く" not in button_texts
    assert "フォルダを開く" not in button_texts

    window.close()


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
    assert window.file_tree.isRowHidden(
        window.file_system_model.index(str(first_path)).row(),
        window.file_system_model.index(str(first_path)).parent(),
    )
    assert window.file_tree.isRowHidden(
        window.file_system_model.index(str(second_path)).row(),
        window.file_system_model.index(str(second_path)).parent(),
    )
    assert window._queue == ()
    assert window._current_track is None
    assert not window.delete_file_button.isEnabled()
    window.close()


def test_delete_button_ignores_folders_and_cancel_keeps_file(
    qt_application: QApplication,
    monkeypatch,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    folder_path = tmp_path / "practice"
    folder_path.mkdir()
    audio_path = tmp_path / "practice.wav"
    audio_path.write_bytes(b"audio")
    window._set_file_tree_root(tmp_path)
    QTest.qWait(100)

    selection_model = window.file_tree.selectionModel()
    select_rows = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    selection_model.select(window.file_system_model.index(str(folder_path)), select_rows)
    assert not window.delete_file_button.isEnabled()

    selection_model.clearSelection()
    selection_model.select(window.file_system_model.index(str(audio_path)), select_rows)
    assert window.delete_file_button.isEnabled()
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )

    window.delete_selected_files()

    assert audio_path.exists()
    window.close()


def test_left_pane_settings_are_saved_and_restored(
    qt_application: QApplication,
    tmp_path,
) -> None:
    window, _ = make_window(qt_application)
    window._settings.clear()
    window._set_file_tree_root(tmp_path)
    window.main_splitter.setSizes([240, 720])
    window._save_left_pane_settings()
    saved_left_width = window.main_splitter.sizes()[0]
    window.close()

    restored_window, _ = make_window(qt_application)
    try:
        qt_application.processEvents()
        assert Path(restored_window.file_system_model.rootPath()) == tmp_path
        assert (
            Path(
                restored_window.file_system_model.filePath(
                    restored_window.file_tree.rootIndex()
                )
            )
            == tmp_path
        )
        assert restored_window.main_splitter.sizes()[0] == saved_left_width
    finally:
        settings = restored_window._settings
        restored_window.close()
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
    assert window.file_tree.isExpanded(nested_index)
    assert window.file_system_model.rowCount(nested_index) == 2
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
    assert window.position_label.text() == "1:00"

    window.close()


def test_seek_and_speed_sliders_share_width_and_thickness(
    qt_application: QApplication,
) -> None:
    window, _ = make_window(qt_application)
    window.show()
    qt_application.processEvents()

    assert window.position_slider.width() == window.speed_slider.width()
    assert (
        window.position_slider.minimumHeight()
        == window.speed_slider.minimumHeight()
    )
    assert window.position_slider.styleSheet() == window.speed_slider.styleSheet()
    assert "height: 18px" in window.position_slider.styleSheet()

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