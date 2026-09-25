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


def test_speed_accepts_values_calculated_by_slider():
    slider_value = 4
    speed = round(0.5 + slider_value * 0.05, 2)

    assert PlaybackState().set_speed(speed).speed == Decimal("0.70")


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


@pytest.mark.parametrize("value", [-1, 100.1, "not-a-number"])
def test_volume_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        PlaybackState().set_volume(value)


def test_volume_accepts_valid_values():
    assert PlaybackState().set_volume("42").volume == Decimal("42")


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


def test_ab_loop_region_is_preserved_when_enabled():
    state = PlaybackState()
    state = state.load_track("track-001")
    state = state.set_a(30.0)
    state = state.set_b(45.0)
    state = state.set_loop_enabled(True)

    assert state.loop_region == LoopRegion(30.0, 45.0)


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
