from pathlib import Path

from ore_music_player import bootstrap


class FakePlaybackBackend:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeDllDirectory:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_build_application_wires_components_and_uses_data_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_directory = FakeDllDirectory()
    playback_backend = FakePlaybackBackend()
    monkeypatch.setattr(
        bootstrap,
        "_configure_mpv_runtime",
        lambda project_root: dll_directory,
    )
    monkeypatch.setattr(
        bootstrap,
        "LibMpvPlaybackBackend",
        lambda: playback_backend,
    )

    application = bootstrap.build_application(data_directory=tmp_path)

    assert application.playback_backend is playback_backend
    assert application.playback_service.backend is playback_backend
    assert application.playlist_repository._connection is not None
    assert (tmp_path / "ore_music_player.sqlite3").is_file()

    application.close()

    assert playback_backend.closed is True
    assert dll_directory.closed is True


def test_build_application_context_manager_closes_components(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_directory = FakeDllDirectory()
    playback_backend = FakePlaybackBackend()
    monkeypatch.setattr(
        bootstrap,
        "_configure_mpv_runtime",
        lambda project_root: dll_directory,
    )
    monkeypatch.setattr(
        bootstrap,
        "LibMpvPlaybackBackend",
        lambda: playback_backend,
    )

    with bootstrap.build_application(data_directory=tmp_path):
        assert playback_backend.closed is False

    assert playback_backend.closed is True
    assert dll_directory.closed is True