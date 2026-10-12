import threading
import time
import uuid

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from ore_music_player.single_instance import (
    OpenFilesServer,
    send_paths_to_running_instance,
)


@pytest.fixture
def qt_application() -> QApplication:
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


def test_paths_sent_to_running_instance_are_received_by_server(
    qt_application: QApplication,
) -> None:
    server_name = f"OreMusicPlayer.Test.{uuid.uuid4().hex}"
    server = OpenFilesServer(server_name)
    received: list[list[str]] = []
    server.paths_received.connect(received.append)
    assert server.start()

    paths = ["C:/music/a.mp3", "C:/music/b.wav"]
    results: list[bool] = []
    sender = threading.Thread(
        target=lambda: results.append(
            send_paths_to_running_instance(paths, server_name=server_name)
        )
    )
    sender.start()
    for _ in range(500):
        QCoreApplication.processEvents()
        if received:
            break
        time.sleep(0.01)
    sender.join(timeout=5)

    assert results == [True]
    assert received == [paths]


def test_send_returns_false_when_no_instance_is_running(
    qt_application: QApplication,
) -> None:
    server_name = f"OreMusicPlayer.Test.{uuid.uuid4().hex}"

    assert send_paths_to_running_instance(["C:/music/a.mp3"], server_name=server_name) is False
