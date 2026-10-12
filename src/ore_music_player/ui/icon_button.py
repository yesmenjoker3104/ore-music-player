from __future__ import annotations

from functools import cache
from pathlib import Path

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import (
	QColor,
	QFocusEvent,
	QFont,
	QPainter,
	QPaintEvent,
	QPen,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
CAPTION_HEIGHT = 22
CAPTION_COLOR = QColor("#ffb020")
FOCUS_COLOR = QColor("#ffe9a0")
DISABLED_OPACITY = 0.4
VARIANT_SUFFIXES = {"normal": "", "hover": "_hover", "pressed": "_pressed"}
# Focus ring is shown only for keyboard navigation, not when the window activates.
KEYBOARD_FOCUS_REASONS = {
	Qt.FocusReason.TabFocusReason,
	Qt.FocusReason.BacktabFocusReason,
	Qt.FocusReason.ShortcutFocusReason,
}


@cache
def _load_renderer(name: str) -> QSvgRenderer:
	return QSvgRenderer(str(ASSETS_DIR / f"{name}.svg"))


def icon_variant(is_hovered: bool, is_pressed: bool) -> str:
	if is_pressed:
		return "pressed"
	if is_hovered:
		return "hover"
	return "normal"


class IconButton(QPushButton):
	def __init__(self, size: int, label: str, art: str) -> None:
		super().__init__()
		self._base_size = size
		self._art = art
		self._caption = ""
		self._focus_ring_visible = False
		self.setFixedSize(size, size)
		self.setCursor(Qt.CursorShape.PointingHandCursor)
		self.set_label(label)
		self.pressed.connect(self.update)
		self.released.connect(self.update)

	def set_scale(self, scale: float) -> None:
		side = round(self._base_size * scale)
		self.setFixedSize(side, side)

	def label(self) -> str:
		return self._label

	def set_label(self, label: str) -> None:
		self._label = label
		self.setToolTip(label.replace("\n", " "))
		self.setAccessibleName(label.replace("\n", " "))

	def caption(self) -> str:
		return self._caption

	def set_caption(self, caption: str) -> None:
		self._caption = caption
		self.update()

	def art(self) -> str:
		return self._art

	def set_art(self, art: str) -> None:
		self._art = art
		self.update()

	def is_focus_ring_visible(self) -> bool:
		return self._focus_ring_visible

	def focusInEvent(self, event: QFocusEvent) -> None:
		super().focusInEvent(event)
		self._focus_ring_visible = event.reason() in KEYBOARD_FOCUS_REASONS
		self.update()

	def focusOutEvent(self, event: QFocusEvent) -> None:
		super().focusOutEvent(event)
		self._focus_ring_visible = False
		self.update()

	def enterEvent(self, event: QEvent) -> None:
		super().enterEvent(event)
		self.update()

	def leaveEvent(self, event: QEvent) -> None:
		super().leaveEvent(event)
		self.update()

	def paintEvent(self, event: QPaintEvent) -> None:
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		if not self.isEnabled():
			painter.setOpacity(DISABLED_OPACITY)

		variant = icon_variant(self.underMouse(), self.isDown())
		renderer = _load_renderer(self._art + VARIANT_SUFFIXES[variant])
		icon_side = self.width() - (CAPTION_HEIGHT if self._caption else 0)
		icon_rect = QRectF((self.width() - icon_side) / 2, 0, icon_side, icon_side)
		renderer.render(painter, icon_rect)

		if self._caption:
			font = QFont(self.font())
			font.setPointSize(9)
			font.setBold(True)
			painter.setFont(font)
			painter.setPen(CAPTION_COLOR)
			painter.drawText(
				QRectF(0, self.height() - CAPTION_HEIGHT, self.width(), CAPTION_HEIGHT),
				Qt.AlignmentFlag.AlignCenter,
				self._caption,
			)

		if self.hasFocus() and self._focus_ring_visible:
			painter.setOpacity(1.0)
			painter.setBrush(Qt.BrushStyle.NoBrush)
			painter.setPen(QPen(FOCUS_COLOR, 1, Qt.PenStyle.DotLine))
			painter.drawRect(QRectF(2, 2, self.width() - 5, self.height() - 5))
		painter.end()
