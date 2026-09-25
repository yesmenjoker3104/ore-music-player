from __future__ import annotations

from pathlib import Path
from typing import Any

from ore_music_player.application.ports import PlaybackBackendError
from ore_music_player.domain.models import Track


class LibMpvPlaybackBackend:
    def __init__(self) -> None:
        import mpv

        self._player: Any = mpv.MPV(
            video=False,
            audio_pitch_correction=True,
            keep_open=True,
        )
        self._current_track: Track | None = None
        self._is_stopped = True
        self._closed = False
        self._last_position_seconds = 0.0
        self._last_duration_seconds: float | None = None
        self._has_observed_position = False

    def load(self, track: Track) -> None:
        path = Path(track.path)
        if not path.is_file():
            raise FileNotFoundError(f"音声ファイルが存在しません: {path}")
        self._current_track = track
        self._player.stop()
        self._player.play(str(path))
        self._player.pause = True
        self._is_stopped = False
        self._last_position_seconds = 0.0
        self._last_duration_seconds = track.duration_seconds
        self._has_observed_position = False

    def play(self) -> None:
        if self._current_track is None:
            return
        if self._is_stopped:
            self._player.play(self._current_track.path)
            self._is_stopped = False
        self._player.pause = False

    def pause(self) -> None:
        self._player.pause = True

    def stop(self) -> None:
        self._player.stop()
        self._is_stopped = True
        self._last_position_seconds = 0.0
        self._has_observed_position = False

    def seek(self, position: float) -> None:
        if position < 0:
            raise ValueError("再生位置は0以上で指定してください")
        try:
            self._player.seek(position, reference="absolute")
        except SystemError as error:
            if self._current_track is None:
                raise PlaybackBackendError(
                    "libmpvが再生位置の変更を受け付けませんでした"
                ) from error
            try:
                self.load(self._current_track)
                wait_until_playing = getattr(
                    self._player,
                    "wait_until_playing",
                    None,
                )
                if wait_until_playing is not None:
                    self._player.pause = False
                    wait_until_playing(timeout=1.0)
                    self._player.pause = True
                self._player.seek(position, reference="absolute")
            except (AttributeError, RuntimeError, SystemError, TimeoutError) as retry_error:
                raise PlaybackBackendError(
                    "libmpvが再生位置の変更を受け付けませんでした"
                ) from retry_error
        self._last_position_seconds = position
        self._has_observed_position = True

    def set_speed(self, speed: float) -> None:
        if not 0.5 <= speed <= 1.5:
            raise ValueError("再生速度は0.5以上1.5以下で指定してください")
        self._player.speed = speed

    def set_volume(self, volume: float) -> None:
        if not 0.0 <= volume <= 100.0:
            raise ValueError("音量は0以上100以下で指定してください")
        self._player.volume = volume

    def set_loop(
        self,
        start_seconds: float | None,
        end_seconds: float | None,
    ) -> None:
        if start_seconds is None or end_seconds is None:
            self._player.ab_loop_a = "no"
            self._player.ab_loop_b = "no"
            return
        if start_seconds >= end_seconds:
            raise ValueError("ループの開始位置は終了位置より前で指定してください")
        self._player.ab_loop_a = start_seconds
        self._player.ab_loop_b = end_seconds
        if self.position_seconds >= end_seconds:
            self.seek(start_seconds)

    def _is_eof_reached(self) -> bool:
        try:
            return bool(self._player.eof_reached)
        except (AttributeError, RuntimeError, SystemError):
            return False

    @property
    def position_seconds(self) -> float:
        if self._is_eof_reached():
            duration = self.duration_seconds
            if duration is not None:
                self._last_position_seconds = duration
                return duration
        try:
            value = self._player.time_pos
        except (AttributeError, RuntimeError, SystemError):
            return self._last_position_seconds
        if value is None:
            if self._has_observed_position:
                duration = self.duration_seconds
                if duration is not None:
                    self._last_position_seconds = duration
                    return duration
            return self._last_position_seconds
        try:
            position = float(value)
        except (TypeError, ValueError):
            return self._last_position_seconds
        self._last_position_seconds = position
        self._has_observed_position = True
        return position

    @property
    def duration_seconds(self) -> float | None:
        try:
            value = self._player.duration
        except (AttributeError, RuntimeError, SystemError):
            return self._last_duration_seconds
        if value is None:
            return self._last_duration_seconds
        try:
            duration = float(value)
        except (TypeError, ValueError):
            return self._last_duration_seconds
        self._last_duration_seconds = duration
        return duration

    @property
    def current_track(self) -> Track | None:
        return self._current_track

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._player.terminate()

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        self.close()