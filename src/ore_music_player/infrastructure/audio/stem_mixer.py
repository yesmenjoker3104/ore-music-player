from __future__ import annotations

import threading
from pathlib import Path
from typing import Protocol

import numpy as np

SAMPLE_RATE = 44100
CHANNELS = 2
BLOCK_SIZE = 1024


class StemSource(Protocol):
    """ミキサーが読み出すステム音源。read() は [start, end) のサンプルを返す。"""

    names: list[str]
    length: int

    def read(self, start: int, end: int) -> dict[str, np.ndarray]: ...


class DirectStems:
    """メモリ上のステム配列をそのまま読み出す音源。"""

    def __init__(self, stems: dict[str, np.ndarray]) -> None:
        self._stems = stems
        self.names = list(stems)
        self.length = max((len(v) for v in stems.values()), default=0)

    def read(self, start: int, end: int) -> dict[str, np.ndarray]:
        return {name: audio[start:end] for name, audio in self._stems.items()}


def _as_source(stems: dict[str, np.ndarray] | StemSource) -> StemSource:
    return DirectStems(stems) if isinstance(stems, dict) else stems


class StemMixer:
    """複数ステムのリアルタイムミックスエンジン。

    sounddevice コールバックから呼ばれる mix_chunk() が本体。
    stems の差し替え（速度変更）と mix_chunk の競合を避けるため _lock で保護する。
    """

    def __init__(
        self, stems: dict[str, np.ndarray] | StemSource, sample_rate: int = SAMPLE_RATE
    ) -> None:
        self.source = _as_source(stems)
        self.sample_rate = sample_rate
        self.volumes: dict[str, float] = {name: 1.0 for name in self.source.names}
        self._master_volume: float = 1.0
        self.position: int = 0
        self.length: int = self.source.length
        self.a_point: int | None = None
        self.b_point: int | None = None
        self.loop_enabled: bool = False
        self._finished: bool = False
        self._lock = threading.Lock()

    @property
    def stem_names(self) -> list[str]:
        return list(self.source.names)

    def replace_stems(self, stems: dict[str, np.ndarray] | StemSource, seconds: float) -> None:
        """同じ音量設定のまま、ステムを差し替えて指定位置から再生を続ける。"""
        with self._lock:
            self.source = _as_source(stems)
            self.length = self.source.length
            self.position = max(0, min(int(seconds * self.sample_rate), self.length))
            self._finished = self.position >= self.length

    @property
    def position_seconds(self) -> float:
        return self.position / self.sample_rate

    @property
    def length_seconds(self) -> float:
        return self.length / self.sample_rate

    @property
    def finished(self) -> bool:
        return self._finished

    def set_master_volume(self, volume: float) -> None:
        self._master_volume = max(0.0, min(1.0, volume))

    def seek(self, seconds: float) -> None:
        with self._lock:
            self.position = max(0, min(int(seconds * self.sample_rate), self.length))
            self._finished = False

    def set_a(self, seconds: float) -> None:
        self.a_point = max(0, int(seconds * self.sample_rate))

    def set_b(self, seconds: float) -> None:
        self.b_point = max(0, int(seconds * self.sample_rate))

    def mix_chunk(self, frames: int) -> np.ndarray:
        with self._lock:
            return self._mix(frames)

    def _mix(self, frames: int) -> np.ndarray:
        if self._finished:
            return np.zeros((frames, CHANNELS), dtype=np.float32)

        if (
            self.loop_enabled
            and self.a_point is not None
            and self.b_point is not None
            and self.b_point > self.a_point
            and self.position >= self.b_point
        ):
            self.position = self.a_point

        start = self.position
        end = min(start + frames, self.length)
        actual = end - start

        result = np.zeros((frames, CHANNELS), dtype=np.float32)
        if actual > 0:
            for name, chunk in self.source.read(start, end).items():
                vol = self.volumes.get(name, 1.0) * self._master_volume
                if vol <= 0:
                    continue
                if chunk.ndim == 1:
                    chunk = np.column_stack([chunk, chunk])
                result[:actual] += (chunk * vol).astype(np.float32)

        self.position = end
        if self.position >= self.length:
            self._finished = True

        return np.clip(result, -1.0, 1.0)


def load_stems(
    stem_paths: dict[str, Path], sample_rate: int = SAMPLE_RATE
) -> dict[str, np.ndarray]:
    """soundfile でステム WAV ファイルを読み込む。"""
    import soundfile as sf

    stems: dict[str, np.ndarray] = {}
    for name, path in stem_paths.items():
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        if sr != sample_rate:
            raise RuntimeError(
                f"{path.name}: サンプルレート {sr}Hz（期待: {sample_rate}Hz）"
            )
        stems[name] = data
    return stems
