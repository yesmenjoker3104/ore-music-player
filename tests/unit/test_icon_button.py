import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QApplication

from ore_music_player.ui.icon_button import IconButton, icon_variant


@pytest.fixture
def qt_application() -> QApplication:
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


def focus_in(button: IconButton, reason: Qt.FocusReason) -> None:
    button.focusInEvent(QFocusEvent(QEvent.Type.FocusIn, reason))


def focus_out(button: IconButton) -> None:
    button.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason))


def test_focus_ring_hidden_when_window_activation_gives_focus(
    qt_application: QApplication,
) -> None:
    button = IconButton(72, "削除", "delete")

    focus_in(button, Qt.FocusReason.ActiveWindowFocusReason)

    assert button.is_focus_ring_visible() is False


def test_focus_ring_shown_for_keyboard_tab_focus(
    qt_application: QApplication,
) -> None:
    button = IconButton(72, "削除", "delete")

    focus_in(button, Qt.FocusReason.TabFocusReason)

    assert button.is_focus_ring_visible() is True


def test_focus_ring_cleared_when_focus_leaves(
    qt_application: QApplication,
) -> None:
    button = IconButton(72, "削除", "delete")
    focus_in(button, Qt.FocusReason.TabFocusReason)

    focus_out(button)

    assert button.is_focus_ring_visible() is False


def test_icon_variant_prefers_pressed_over_hover() -> None:
    assert icon_variant(is_hovered=False, is_pressed=False) == "normal"
    assert icon_variant(is_hovered=True, is_pressed=False) == "hover"
    assert icon_variant(is_hovered=True, is_pressed=True) == "pressed"
