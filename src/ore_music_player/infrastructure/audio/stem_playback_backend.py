from __future__ import annotations

import logging
import threading

import numpy as np
import pyrubberband as rb

from ore_music_player.domain.models import Track
from ore_music_player.infrastructure.audio.stem_mixer import (
    BLOCK_SIZE,
    CHANNELS,
    SAMPLE_RATE,
    StemMixer,
    load_stems,
)
from ore_music_player.infrastructure.separation.stem_repository import StemRepository

logger = logging.getLogger(__name__)


def _stretch_stems(stems: dict[str, np.ndarray], speed: float) -> dict[str, np.ndarray]:
    """ピッチを保ったまま時間伸縮する。speed > 1 で短くなる。"""
    return {
        name: rb.time_stretch(audio, SAMPLE_RATE, speed).astype(np.float32)
        for name, audio in stems.items()
    }


class StemPlaybackBackend:
    """sounddevice + StemMixer による PlaybackBackend 実装。

    再生位置・シーク・ループ点は元の曲の時間軸（秒）で扱う。
    速度変更時は元音源を伸縮したステムをバックグラウンドで作り、
    再生中のミキサーへ差し替える。
    """

    def __init__(self, stem_repository: StemRepository) -> None:
        self._repo = stem_repository
        self._mixer: StemMixer | None = None
        self._stream = None
        self._is_playing: bool = False
        self._lock = threading.Lock()
        self._current_track: Track | None = None
        self._original_stems: dict[str, np.ndarray] | None = None
        self._applied_speed: float = 1.0
        self._target_speed: float = 1.0
        self._stretch_generation: int = 0
        self._master_volume: float = 1.0
        self._stem_volumes: dict[str, float] = {}
        self._loop_start: float | None = None
        self._loop_end: float | None = None
        self._loop_enabled: bool = False

    @property
    def current_track(self) -> Track | None:
        return self._current_track

    # ------------------------------------------------------------------
    # PlaybackBackend protocol
    # ------------------------------------------------------------------

    def load(self, track: Track) -> None:
        self.stop()
        stem_paths = self._repo.find(track.track_id)
        if not stem_paths:
            raise RuntimeError(f"ステムが見つかりません: {track.track_id}")
        stems = load_stems(stem_paths)
        with self._lock:
            self._current_track = track
            self._original_stems = stems
            self._applied_speed = 1.0
            self._stretch_generation += 1
            mixer = StemMixer(stems, SAMPLE_RATE)
            mixer.set_master_volume(self._master_volume)
            for name, volume in self._stem_volumes.items():
                if name in mixer.volumes:
                    mixer.volumes[name] = volume
            self._mixer = mixer
            self._apply_loop_locked()
        self._request_stretch()

    def play(self) -> None:
        import sounddevice as sd

        if self._mixer is None:
            return
        with self._lock:
            if self._is_playing:
                return

            mixer = self._mixer

            def callback(outdata, frames, time_info, status):
                chunk = mixer.mix_chunk(frames)
                outdata[:] = chunk
                if mixer.finished:
                    raise sd.CallbackStop

            self._stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                callback=callback,
            )
            self._stream.start()
            self._is_playing = True

    def pause(self) -> None:
        with self._lock:
            if self._stream is not None:
                self._stream.stop()
            self._is_playing = False

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            self._is_playing = False
            if self._mixer is not None:
                self._mixer.seek(0)

    def seek(self, position: float) -> None:
        with self._lock:
            if self._mixer is not None:
                self._mixer.seek(position / self._applied_speed)

    def set_speed(self, speed: float) -> None:
        with self._lock:
            self._target_speed = float(speed)
        self._request_stretch()

    def set_volume(self, volume: float) -> None:
        self._master_volume = max(0.0, min(1.0, volume / 100.0))
        if self._mixer is not None:
            self._mixer.set_master_volume(self._master_volume)

    def set_loop(
        self,
        start_seconds: float | None,
        end_seconds: float | None,
    ) -> None:
        with self._lock:
            if start_seconds is not None:
                self._loop_start = start_seconds
            if end_seconds is not None:
                self._loop_end = end_seconds
            self._loop_enabled = (
                start_seconds is not None and end_seconds is not None
            )
            self._apply_loop_locked()

    @property
    def position_seconds(self) -> float:
        if self._mixer is None:
            return 0.0
        return self._mixer.position_seconds * self._applied_speed

    @property
    def duration_seconds(self) -> float | None:
        if self._mixer is None:
            return None
        return self._mixer.length_seconds * self._applied_speed

    # ------------------------------------------------------------------
    # 速度変更（時間伸縮）
    # ------------------------------------------------------------------

    def _apply_loop_locked(self) -> None:
        if self._mixer is None:
            return
        speed = self._applied_speed
        if self._loop_start is not None:
            self._mixer.set_a(self._loop_start / speed)
        if self._loop_end is not None:
            self._mixer.set_b(self._loop_end / speed)
        self._mixer.loop_enabled = self._loop_enabled

    def _install_stems_locked(self, stems: dict[str, np.ndarray], speed: float) -> None:
        """現在位置（元の時間軸）を保ったまま、伸縮済みステムに切り替える。"""
        assert self._mixer is not None
        position_original = self._mixer.position_seconds * self._applied_speed
        self._mixer.replace_stems(stems, position_original / speed)
        self._applied_speed = speed
        self._apply_loop_locked()

    def _request_stretch(self) -> None:
        with self._lock:
            self._stretch_generation += 1
            generation = self._stretch_generation
            target = self._target_speed
            originals = self._original_stems
            if originals is None or self._mixer is None:
                return
            if target == self._applied_speed:
                return
            if target == 1.0:
                self._install_stems_locked(originals, 1.0)
                return
        threading.Thread(
            target=self._stretch_worker,
            args=(generation, target, originals),
            daemon=True,
        ).start()

    def _stretch_worker(
        self,
        generation: int,
        speed: float,
        originals: dict[str, np.ndarray],
    ) -> None:
        try:
            stretched = _stretch_stems(originals, speed)
        except Exception:
            logger.exception("ステムの時間伸縮に失敗しました (speed=%s)", speed)
            return
        with self._lock:
            if (
                generation != self._stretch_generation
                or originals is not self._original_stems
                or self._mixer is None
            ):
                return
            self._install_stems_locked(stretched, speed)

    # ------------------------------------------------------------------
    # ステム音量制御（UI から呼ばれる）
    # ------------------------------------------------------------------

    def set_stem_volume(self, stem_name: str, volume: float) -> None:
        clamped = max(0.0, min(1.0, volume))
        self._stem_volumes[stem_name] = clamped
        if self._mixer is not None and stem_name in self._mixer.volumes:
            self._mixer.volumes[stem_name] = clamped

    @property
    def stem_volumes(self) -> dict[str, float]:
        if self._mixer is None:
            return {}
        return dict(self._mixer.volumes)

    def stem_names(self) -> list[str]:
        if self._mixer is None:
            return []
        return list(self._mixer.stems.keys())

    def close(self) -> None:
        self.stop()
