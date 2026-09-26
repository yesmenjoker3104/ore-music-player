from __future__ import annotations

import threading

from ore_music_player.domain.models import Track
from ore_music_player.infrastructure.audio.stem_mixer import (
    BLOCK_SIZE,
    CHANNELS,
    SAMPLE_RATE,
    StemMixer,
    load_stems,
)
from ore_music_player.infrastructure.separation.stem_repository import StemRepository


class StemPlaybackBackend:
    """sounddevice + StemMixer による PlaybackBackend 実装。"""

    def __init__(self, stem_repository: StemRepository) -> None:
        self._repo = stem_repository
        self._mixer: StemMixer | None = None
        self._stream = None
        self._is_playing: bool = False
        self._lock = threading.Lock()

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
            self._mixer = StemMixer(stems, SAMPLE_RATE)

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
        if self._mixer is not None:
            self._mixer.seek(position)

    def set_speed(self, speed: float) -> None:
        pass  # 将来: pyrubberband で前処理

    def set_volume(self, volume: float) -> None:
        if self._mixer is not None:
            self._mixer.set_master_volume(volume / 100.0)

    def set_loop(
        self,
        start_seconds: float | None,
        end_seconds: float | None,
    ) -> None:
        if self._mixer is None:
            return
        if start_seconds is not None:
            self._mixer.set_a(start_seconds)
        if end_seconds is not None:
            self._mixer.set_b(end_seconds)
        self._mixer.loop_enabled = (
            start_seconds is not None and end_seconds is not None
        )

    @property
    def position_seconds(self) -> float:
        if self._mixer is None:
            return 0.0
        return self._mixer.position_seconds

    @property
    def duration_seconds(self) -> float | None:
        if self._mixer is None:
            return None
        return self._mixer.length_seconds

    # ------------------------------------------------------------------
    # ステム音量制御（UI から呼ばれる）
    # ------------------------------------------------------------------

    def set_stem_volume(self, stem_name: str, volume: float) -> None:
        if self._mixer is not None:
            self._mixer.volumes[stem_name] = max(0.0, min(1.0, volume))

    def stem_names(self) -> list[str]:
        if self._mixer is None:
            return []
        return list(self._mixer.stems.keys())

    def close(self) -> None:
        self.stop()
