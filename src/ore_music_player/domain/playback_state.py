from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum

from .models import (
    LoopRegion,
    PlaybackSettings,
    validate_position_seconds,
)


class PlaybackStatus(StrEnum):
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class PlaybackState:
    status: PlaybackStatus = PlaybackStatus.STOPPED
    track_id: str | None = None
    position_seconds: float = 0.0
    settings: PlaybackSettings = field(
        default_factory=PlaybackSettings,
    )
    a_point_seconds: float | None = None
    b_point_seconds: float | None = None
    loop_enabled: bool = False

    def __post_init__(self) -> None:
        if self.track_id is not None and not self.track_id.strip():
            raise ValueError("track_idは空にできません")

        if not isinstance(self.settings, PlaybackSettings):
            raise TypeError("settingsにはPlaybackSettingsを指定してください")

        object.__setattr__(
            self,
            "position_seconds",
            validate_position_seconds(self.position_seconds),
        )

        if self.a_point_seconds is not None:
            object.__setattr__(
                self,
                "a_point_seconds",
                validate_position_seconds(
                    self.a_point_seconds,
                    "a_point_seconds",
                ),
            )

        if self.b_point_seconds is not None:
            object.__setattr__(
                self,
                "b_point_seconds",
                validate_position_seconds(
                    self.b_point_seconds,
                    "b_point_seconds",
                ),
            )

        if (
            self.a_point_seconds is not None
            and self.b_point_seconds is not None
            and self.a_point_seconds >= self.b_point_seconds
        ):
            raise ValueError("A地点はB地点より前である必要があります")

        if self.loop_enabled and self.loop_region is None:
            raise ValueError("A/B地点を設定してからループを有効にしてください")

    @property
    def speed(self) -> Decimal:
        return self.settings.speed

    @property
    def loop_region(self) -> LoopRegion | None:
        if self.a_point_seconds is None or self.b_point_seconds is None:
            return None

        return LoopRegion(
            start_seconds=self.a_point_seconds,
            end_seconds=self.b_point_seconds,
        )

    def load_track(self, track_id: str) -> PlaybackState:
        if not track_id.strip():
            raise ValueError("track_idは空にできません")

        return replace(
            self,
            status=PlaybackStatus.STOPPED,
            track_id=track_id,
            position_seconds=0.0,
            a_point_seconds=None,
            b_point_seconds=None,
            loop_enabled=False,
        )

    def play(self) -> PlaybackState:
        if self.track_id is None:
            raise RuntimeError("曲を読み込んでから再生してください")

        return replace(
            self,
            status=PlaybackStatus.PLAYING,
        )

    def pause(self) -> PlaybackState:
        if self.status is PlaybackStatus.STOPPED:
            return self

        return replace(
            self,
            status=PlaybackStatus.PAUSED,
        )

    def stop(self) -> PlaybackState:
        return replace(
            self,
            status=PlaybackStatus.STOPPED,
            position_seconds=0.0,
        )

    def set_position(self, position_seconds: float) -> PlaybackState:
        return replace(
            self,
            position_seconds=validate_position_seconds(position_seconds),
        )

    def set_speed(
        self,
        value: Decimal | float | int | str,
    ) -> PlaybackState:
        return replace(
            self,
            settings=self.settings.with_speed(value),
        )

    def set_a(self, position_seconds: float) -> PlaybackState:
        position = validate_position_seconds(
            position_seconds,
            "a_point_seconds",
        )

        if (
            self.b_point_seconds is not None
            and position >= self.b_point_seconds
        ):
            raise ValueError("A地点はB地点より前である必要があります")

        return replace(
            self,
            a_point_seconds=position,
            loop_enabled=False,
        )

    def set_b(self, position_seconds: float) -> PlaybackState:
        if self.a_point_seconds is None:
            raise ValueError("先にA地点を設定してください")

        position = validate_position_seconds(
            position_seconds,
            "b_point_seconds",
        )

        if position <= self.a_point_seconds:
            raise ValueError("B地点はA地点より後である必要があります")

        return replace(
            self,
            b_point_seconds=position,
            loop_enabled=False,
        )

    def clear_loop_points(self) -> PlaybackState:
        return replace(
            self,
            a_point_seconds=None,
            b_point_seconds=None,
            loop_enabled=False,
        )

    def set_loop_enabled(self, enabled: bool) -> PlaybackState:
        if enabled and self.loop_region is None:
            raise ValueError("A/B地点を設定してからループを有効にしてください")

        return replace(
            self,
            loop_enabled=enabled,
        )

    def loop_seek_target(
        self,
        position_seconds: float,
    ) -> float | None:
        position = validate_position_seconds(position_seconds)
        region = self.loop_region

        if not self.loop_enabled or region is None:
            return None

        if position >= region.end_seconds:
            return region.start_seconds

        return None