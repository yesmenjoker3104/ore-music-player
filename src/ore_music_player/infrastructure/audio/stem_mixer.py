from __future__ import annotations

from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
CHANNELS = 2
BLOCK_SIZE = 1024


class StemMixer:
    """複数ステムのリアルタイムミックスエンジン。

    sounddevice コールバックから呼ばれる mix_chunk() が本体。
    GIL に頼った軽量なロック方針（probe と同様）。
    """

    def __init__(self, stems: dict[str, np.ndarray], sample_rate: int = SAMPLE_RATE) -> None:
        self.stems = stems
        self.sample_rate = sample_rate
        self.volumes: dict[str, float] = {name: 1.0 for name in stems}
        self._master_volume: float = 1.0
        self.position: int = 0
        self.length: int = max(len(v) for v in stems.values()) if stems else 0
        self.a_point: int | None = None
        self.b_point: int | None = None
        self.loop_enabled: bool = False
        self._finished: bool = False

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
        self.position = max(0, min(int(seconds * self.sample_rate), self.length))
        self._finished = False

    def set_a(self, seconds: float) -> None:
        self.a_point = max(0, int(seconds * self.sample_rate))

    def set_b(self, seconds: float) -> None:
        self.b_point = max(0, int(seconds * self.sample_rate))

    def mix_chunk(self, frames: int) -> np.ndarray:
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
        for name, audio in self.stems.items():
            vol = self.volumes.get(name, 1.0) * self._master_volume
            if vol > 0 and actual > 0:
                chunk = audio[start:end]
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
