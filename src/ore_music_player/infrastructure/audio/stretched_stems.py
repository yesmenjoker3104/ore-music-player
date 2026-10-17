from __future__ import annotations

import os
import threading
from bisect import bisect_right
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from math import ceil

import numpy as np

from ore_music_player.infrastructure.audio.stem_mixer import SAMPLE_RATE

CHUNK_SECONDS = 10.0
CONTEXT_SECONDS = 1.0
FADE_SECONDS = 0.05
LOOKAHEAD_SECONDS = 30.0


def _fit(stretched: np.ndarray, head: int, length: int) -> np.ndarray:
    part = stretched[head : head + length]
    if len(part) == length:
        return part.astype(np.float32, copy=False)
    out = np.zeros((length,) + part.shape[1:], dtype=np.float32)
    out[: len(part)] = part
    return out


def _broadcast(gains: np.ndarray, audio: np.ndarray) -> np.ndarray:
    return gains.reshape(gains.shape + (1,) * (audio.ndim - 1))


class StretchedStems:
    """伸縮後のステムを区間単位で保持する StemSource 実装。

    元の時間軸を CHUNK_SECONDS ごとに区切り、区間ごとに前後 CONTEXT_SECONDS の
    余白を付けて伸縮してから余白を取り除く。区間境界は前後 FADE_SECONDS で
    線形にクロスフェードして、伸縮の位相ずれによる音の途切れを抑える。
    まだ作っていない区間は read() で無音として返す。
    """

    def __init__(
        self,
        originals: dict[str, np.ndarray],
        speed: float,
        stretch_fn: Callable[[np.ndarray, float], np.ndarray],
    ) -> None:
        self.names = list(originals)
        self._originals = originals
        self._speed = speed
        self._stretch_fn = stretch_fn
        self._tails = {name: audio.shape[1:] for name, audio in originals.items()}
        original_length = max((len(v) for v in originals.values()), default=0)
        self._original_length = original_length
        self._chunk_samples = max(1, int(CHUNK_SECONDS * SAMPLE_RATE))
        self._context_samples = int(CONTEXT_SECONDS * SAMPLE_RATE)
        self._fade = min(int(FADE_SECONDS * SAMPLE_RATE), self._chunk_samples // 4)
        self.chunk_count = ceil(original_length / self._chunk_samples)
        self._bounds = [
            round(min(k * self._chunk_samples, original_length) / speed)
            for k in range(self.chunk_count + 1)
        ]
        # 値は (伸縮後の時間軸での開始位置, ステムごとの音声, 区間の重み)
        self._chunks: dict[int, tuple[int, dict[str, np.ndarray], np.ndarray]] = {}
        self._lock = threading.Lock()

    @property
    def length(self) -> int:
        return self._bounds[-1]

    def chunk_of_original(self, seconds: float) -> int:
        index = int(seconds * SAMPLE_RATE) // self._chunk_samples
        return min(max(index, 0), max(self.chunk_count - 1, 0))

    def has_chunk(self, index: int) -> bool:
        with self._lock:
            return index in self._chunks

    def is_complete(self) -> bool:
        with self._lock:
            return len(self._chunks) == self.chunk_count

    def compute_chunk(self, index: int, is_cancelled: Callable[[], bool]) -> bool:
        """区間 index を伸縮して保存する。途中で is_cancelled() が True になると False を返す。"""
        start = index * self._chunk_samples
        end = min(start + self._chunk_samples, self._original_length)
        context_start = max(0, start - self._context_samples)
        context_end = min(self._original_length, end + self._context_samples)
        fade_head = self._fade if index > 0 else 0
        fade_tail = self._fade if index < self.chunk_count - 1 else 0
        core = self._bounds[index + 1] - self._bounds[index]
        length = fade_head + core + fade_tail
        first = round((start - context_start) / self._speed) - fade_head

        def stretch_one(name: str) -> np.ndarray | None:
            if is_cancelled():
                return None
            segment = self._originals[name][context_start:context_end]
            return _fit(self._stretch_fn(segment, self._speed), first, length)

        workers = max(1, min(len(self.names), os.cpu_count() or 1))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {name: executor.submit(stretch_one, name) for name in self.names}
            parts = {name: future.result() for name, future in futures.items()}
        if any(part is None for part in parts.values()):
            return False
        begin = self._bounds[index] - fade_head
        gains = self._gains(length, fade_head, fade_tail)
        with self._lock:
            self._chunks[index] = (begin, parts, gains)
        return True

    def _gains(self, length: int, fade_head: int, fade_tail: int) -> np.ndarray:
        gains = np.ones(length, dtype=np.float32)
        width = 2 * self._fade
        if width == 0:
            return gains
        if fade_head:
            gains[:width] = (np.arange(width) + 0.5) / width
        if fade_tail:
            gains[length - width :] = 1 - (np.arange(width) + 0.5) / width
        return gains

    def read(self, start: int, end: int) -> dict[str, np.ndarray]:
        end = min(end, self.length)
        count = max(0, end - start)
        result = {
            name: np.zeros((count,) + self._tails[name], dtype=np.float32)
            for name in self.names
        }
        if count == 0:
            return result
        with self._lock:
            chunks = dict(self._chunks)
        first = max(0, self._chunk_of_stretched(start) - 1)
        last = min(self.chunk_count - 1, self._chunk_of_stretched(end - 1) + 1)
        for index in range(first, last + 1):
            entry = chunks.get(index)
            if entry is None:
                continue
            begin, parts, gains = entry
            lo = max(start, begin)
            hi = min(end, begin + len(gains))
            if hi <= lo:
                continue
            gain = gains[lo - begin : hi - begin]
            for name in self.names:
                piece = parts[name][lo - begin : hi - begin]
                result[name][lo - start : hi - start] += piece * _broadcast(gain, piece)
        return result

    def _chunk_of_stretched(self, position: int) -> int:
        index = bisect_right(self._bounds, position) - 1
        return min(max(index, 0), max(self.chunk_count - 1, 0))


def next_chunk_to_compute(stretched: StretchedStems, playhead_chunk: int) -> int | None:
    """再生位置の区間から先読み範囲内で、まだ作っていない最初の区間を返す。"""
    for distance in range(stretched.chunk_count):
        if distance * CHUNK_SECONDS > LOOKAHEAD_SECONDS:
            break
        index = (playhead_chunk + distance) % stretched.chunk_count
        if not stretched.has_chunk(index):
            return index
    return None
