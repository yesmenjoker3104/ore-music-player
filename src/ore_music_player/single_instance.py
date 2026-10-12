from __future__ import annotations

import json
from functools import partial

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

OPEN_FILES_SERVER_NAME = "OreMusicPlayer.OpenFiles"
CONNECT_TIMEOUT_MS = 500
WRITE_TIMEOUT_MS = 2000


def send_paths_to_running_instance(
	paths: list[str],
	server_name: str = OPEN_FILES_SERVER_NAME,
) -> bool:
	socket = QLocalSocket()
	socket.connectToServer(server_name)
	if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
		return False
	payload = json.dumps(paths).encode("utf-8") + b"\n"
	written = 0
	loop = QEventLoop()

	def on_bytes_written(count: int) -> None:
		nonlocal written
		written += count
		if written >= len(payload):
			loop.quit()

	socket.bytesWritten.connect(on_bytes_written)
	socket.write(payload)
	QTimer.singleShot(WRITE_TIMEOUT_MS, loop.quit)
	loop.exec()
	socket.disconnectFromServer()
	return written >= len(payload)


class OpenFilesServer(QObject):
	paths_received = Signal(list)

	def __init__(
		self,
		server_name: str = OPEN_FILES_SERVER_NAME,
		parent: QObject | None = None,
	) -> None:
		super().__init__(parent)
		self._server_name = server_name
		self._server = QLocalServer(self)
		self._server.newConnection.connect(self._accept_connections)

	def start(self) -> bool:
		if self._server.listen(self._server_name):
			return True
		QLocalServer.removeServer(self._server_name)
		return self._server.listen(self._server_name)

	def _accept_connections(self) -> None:
		while self._server.hasPendingConnections():
			connection = self._server.nextPendingConnection()
			connection.setParent(self)
			connection.readyRead.connect(
				partial(self._read_paths, connection, bytearray())
			)
			connection.disconnected.connect(connection.deleteLater)

	def _read_paths(self, connection, buffer: bytearray) -> None:
		buffer.extend(connection.readAll().data())
		message, newline, _ = bytes(buffer).partition(b"\n")
		if not newline:
			return
		buffer.clear()
		try:
			paths = json.loads(message.decode("utf-8"))
		except (UnicodeDecodeError, json.JSONDecodeError):
			return
		if isinstance(paths, list) and all(isinstance(path, str) for path in paths):
			self.paths_received.emit(paths)
