from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from math import isfinite

MIN_PLAYBACK_SPEED = Decimal("0.50")
MAX_PLAYBACK_SPEED = Decimal("1.50")
PLAYBACK_SPEED_STEP = Decimal("0.05")
DEFAULT_PLAYBACK_SPEED = Decimal("1.00")
MIN_VOLUME = Decimal("0")
MAX_VOLUME = Decimal("100")
DEFAULT_VOLUME = Decimal("100")


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


def validate_volume(value: Decimal | float | int | str) -> Decimal:
    try:
        volume = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"音量は数値で指定してください: {value}") from error

    if not volume.is_finite():
        raise ValueError(f"音量には有限の値を指定してください: {value}")

    if not MIN_VOLUME <= volume <= MAX_VOLUME:
        raise ValueError(
            f"音量は {MIN_VOLUME} から {MAX_VOLUME} の間で指定してください: {value}"
        )

    return volume


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
    volume: Decimal = DEFAULT_VOLUME

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "speed",
            validate_playback_speed(self.speed),
        )
        object.__setattr__(self, "volume", validate_volume(self.volume))

    def with_speed(
        self,
        value: Decimal | float | int | str,
    ) -> PlaybackSettings:
        return replace(
            self,
            speed=validate_playback_speed(value),
        )

    def with_volume(
        self,
        value: Decimal | float | int | str,
    ) -> PlaybackSettings:
        return replace(
            self,
            volume=validate_volume(value),
        )

@dataclass(frozen=True, slots=True)
class Playlist:
    playlist_id: str
    name: str
    tracks: tuple[Track, ...] = ()

    def __post_init__(self) -> None:
        if not self.playlist_id.strip():
            raise ValueError("playlist_idは空にできません")

        if not self.name.strip():
            raise ValueError("nameは空にできません")

        track_ids = [track.track_id for track in self.tracks]
        if len(track_ids) != len(set(track_ids)):
            raise ValueError("tracksには重複するtrack_idを含めることはできません")

    def rename(self, new_name: str) -> Playlist:
        if not new_name.strip():
            raise ValueError("nameは空にできません")
        return replace(self, name=new_name)

    def add_track(self, track: Track) -> Playlist:
        if any(t.track_id == track.track_id for t in self.tracks):
            raise ValueError("tracksには重複するtrack_idを含めることはできません")
        return replace(self, tracks=(*self.tracks, track))

    def remove_track(self, track_id: str) -> Playlist:
        if not track_id.strip():
            raise ValueError("track_idは空にできません")

        if not any(t.track_id == track_id for t in self.tracks):
            raise ValueError(f"指定されたtrack_idは存在しません: {track_id}")
        return replace(self, tracks=tuple(t for t in self.tracks if t.track_id != track_id))

    def move_track(self, current_index: int, new_index: int) -> Playlist:
        track_count = len(self.tracks)
        if not 0 <= current_index < track_count:
            raise ValueError("current_indexが範囲外です")
        if not 0 <= new_index < track_count:
            raise ValueError("new_indexが範囲外です")

        tracks = list(self.tracks)
        track = tracks.pop(current_index)
        tracks.insert(new_index, track)
        return replace(self, tracks=tuple(tracks))

    def reorder_tracks(self, ordered_track_ids: Sequence[str]) -> Playlist:
        ordered_ids = tuple(ordered_track_ids)
        current_ids = {track.track_id for track in self.tracks}
        if len(ordered_ids) != len(self.tracks) or set(ordered_ids) != current_ids:
            raise ValueError(
                "ordered_track_idsは現在のtrack_idを過不足なく含む必要があります"
            )

        tracks_by_id = {track.track_id: track for track in self.tracks}
        return replace(
            self,
            tracks=tuple(tracks_by_id[track_id] for track_id in ordered_ids),
        )