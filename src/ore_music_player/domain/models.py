from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from math import isfinite

MIN_PLAYBACK_SPEED = Decimal("0.50")
MAX_PLAYBACK_SPEED = Decimal("1.50")
PLAYBACK_SPEED_STEP = Decimal("0.05")
DEFAULT_PLAYBACK_SPEED = Decimal("1.00")


def validate_playback_speed(
    value: Decimal | float | int | str,
) -> Decimal:
    try:
        speed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"再生速度は数値で指定してください: {value}") from error

    if not speed.is_finite():
        raise ValueError(f"再生速度には有限の値を指定してください: {value}")

    if not (MIN_PLAYBACK_SPEED <= speed <= MAX_PLAYBACK_SPEED):
        raise ValueError(
            f"再生速度は {MIN_PLAYBACK_SPEED} から {MAX_PLAYBACK_SPEED} の間で"
            f"指定してください: {value}"
        )

    if (speed - MIN_PLAYBACK_SPEED) % PLAYBACK_SPEED_STEP != 0:
        raise ValueError(
            f"再生速度は {PLAYBACK_SPEED_STEP} 刻みで指定してください"
        )

    return speed.quantize(PLAYBACK_SPEED_STEP)


def validate_position_seconds(
    value: float | int,
    field_name: str = "position_seconds",
) -> float:
    try:
        position = float(value)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{field_name}は数値で指定してください") from error

    if not isfinite(position) or position < 0:
        raise ValueError(f"{field_name}には有限の0以上の値を指定してください")

    return position


@dataclass(frozen=True, slots=True)
class Track:
    track_id: str
    path: str
    title: str
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        if not self.track_id.strip():
            raise ValueError("track_idは空にできません")

        if not self.path.strip():
            raise ValueError("pathは空にできません")

        if not self.title.strip():
            raise ValueError("titleは空にできません")

        if self.duration_seconds is not None:
            object.__setattr__(
                self,
                "duration_seconds",
                validate_position_seconds(
                    value=self.duration_seconds,
                    field_name="duration_seconds",
                ),
            )


@dataclass(frozen=True, slots=True)
class LoopRegion:
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        start = validate_position_seconds(
            value=self.start_seconds,
            field_name="start_seconds",
        )
        end = validate_position_seconds(
            value=self.end_seconds,
            field_name="end_seconds",
        )

        if start >= end:
            raise ValueError("start_secondsはend_secondsより小さくなければなりません")

        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)


@dataclass(frozen=True, slots=True)
class PlaybackSettings:
    speed: Decimal = DEFAULT_PLAYBACK_SPEED

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "speed",
            validate_playback_speed(self.speed),
        )

    def with_speed(
        self,
        value: Decimal | float | int | str,
    ) -> PlaybackSettings:
        return replace(
            self,
            speed=validate_playback_speed(value),
        )