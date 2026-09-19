from decimal import Decimal

import pytest

from ore_music_player.domain.models import LoopRegion
from ore_music_player.domain.playback_state import (
    PlaybackState,
    PlaybackStatus,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.50", Decimal("0.50")),
        (0.55, Decimal("0.55")),
        (0.75, Decimal("0.75")),
        (0.85, Decimal("0.85")),
        (1.15, Decimal("1.15")),
        ("1.00", Decimal("1.00")),
        (Decimal("1.50"), Decimal("1.50")),
    ],
)
def test_speed_accepts_valid_values(value, expected):
    state = PlaybackState().set_speed(value)

    assert state.speed == expected


@pytest.mark.parametrize(
    "value",
    [
        "0.49",
        "0.53",
        "1.51",
        "not-a-number",
    ],
)
def test_speed_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        PlaybackState().set_speed(value)


def test_playback_state_changes_status():
    state = PlaybackState().load_track("track-001")

    assert state.status is PlaybackStatus.STOPPED

    state = state.play()
    assert state.status is PlaybackStatus.PLAYING

    state = state.pause()
    assert state.status is PlaybackStatus.PAUSED

    state = state.stop()
    assert state.status is PlaybackStatus.STOPPED
    assert state.position_seconds == 0.0


def test_ab_loop_returns_to_a_when_position_reaches_b():
    state = PlaybackState()
    state = state.load_track("track-001")
    state = state.set_a(30.0)
    state = state.set_b(45.0)
    state = state.set_loop_enabled(True)

    assert state.loop_region == LoopRegion(30.0, 45.0)
    assert state.loop_seek_target(44.99) is None
    assert state.loop_seek_target(45.0) == 30.0
    assert state.loop_seek_target(50.0) == 30.0


def test_b_point_requires_a_point():
    with pytest.raises(ValueError):
        PlaybackState().set_b(20.0)


def test_loop_can_be_disabled_without_removing_points():
    state = PlaybackState()
    state = state.load_track("track-001")
    state = state.set_a(10.0)
    state = state.set_b(20.0)
    state = state.set_loop_enabled(True)
    state = state.set_loop_enabled(False)

    assert state.loop_region == LoopRegion(10.0, 20.0)
    assert state.loop_seek_target(20.0) is None