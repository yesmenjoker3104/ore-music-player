from __future__ import annotations

from pathlib import Path
from typing import Any

from ore_music_player.domain.models import Track


class LibMpvPlaybackBackend:
    def __init__(self) -> None:
        import mpv

        self._player: Any = mpv.MPV(
            video=False,
            audio_pitch_correction=True,
        )
        self._current_track: Track | None = None

    def load(self, track: Track) -> None:
        path = Path(track.path)
        if not path.is_file():
            raise FileNotFoundError(f"音声ファイルが存在しません: {path}")
        self._current_track = track
        self._player.stop()
        self._player.play(str(path))

    def play(self) -> None:
        self._player.pause = False

    def pause(self) -> None:
        self._player.pause = True

    def stop(self) -> None:
        self._player.stop()
        self._current_track = None

    def seek(self, position: float) -> None:
        if position < 0 :
            raise ValueError("再生位置は0以上で指定してください")
        self._player.seek(position, reference='absolute')

    def set_speed(self, speed: float) -> None:
        if not 0.5 <= speed <= 1.5:
            raise ValueError("再生速度は0.5以上1.5以下で指定してください")
        self._player.speed = speed

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

    @property
    def current_track(self) -> Track | None:
        return self._current_track

    def close(self) -> None:
        self._player.terminate()

    def __enter__(self):
        return self

    def __exit__(self, *args:object):
        self.close()