from __future__ import annotations

import numpy as np
import pytest

from ore_music_player.infrastructure.audio import stretched_stems as module
from ore_music_player.infrastructure.audio.stem_mixer import SAMPLE_RATE
from ore_music_player.infrastructure.audio.stretched_stems import (
    StretchedStems,
    next_chunk_to_compute,
)

SR = SAMPLE_RATE


def _identity(audio: np.ndarray, rate: float) -> np.ndarray:
    return audio


def _ramp_stems(seconds: int) -> dict[str, np.ndarray]:
    n = SR * seconds
    ramp = np.arange(n, dtype=np.float32).reshape(n, 1) * np.ones((1, 2), np.float32)
    return {"vocals": ramp}


@pytest.fixture
def small_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "CHUNK_SECONDS", 1.0)
    monkeypatch.setattr(module, "CONTEXT_SECONDS", 0.25)


def _compute_all(stretched: StretchedStems) -> None:
    for index in range(stretched.chunk_count):
        assert stretched.compute_chunk(index, lambda: False)


def test_identity_stretch_reads_original_across_chunk_boundaries(small_chunks):
    originals = _ramp_stems(3)
    stretched = StretchedStems(originals, 1.0, _identity)
    _compute_all(stretched)

    start, end = SR // 2, SR * 2 + SR // 4
    read = stretched.read(start, end)["vocals"]

    np.testing.assert_allclose(read, originals["vocals"][start:end], rtol=1e-6)


def test_length_follows_speed(small_chunks):
    stretched = StretchedStems(_ramp_stems(4), 2.0, _identity)

    assert stretched.length == 2 * SR


def test_read_returns_silence_for_uncomputed_chunks(small_chunks):
    stretched = StretchedStems(_ramp_stems(3), 1.0, _identity)
    assert stretched.compute_chunk(0, lambda: False)

    fade = int(module.FADE_SECONDS * SR)
    read = stretched.read(SR + fade, SR * 2)["vocals"]

    assert not read.any()


def test_compute_chunk_stops_when_cancelled(small_chunks):
    stretched = StretchedStems(_ramp_stems(2), 1.0, _identity)

    assert stretched.compute_chunk(0, lambda: True) is False
    assert not stretched.has_chunk(0)


def test_next_chunk_respects_lookahead_and_wraps(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(module, "CHUNK_SECONDS", 10.0)
    monkeypatch.setattr(module, "LOOKAHEAD_SECONDS", 15.0)
    stretched = StretchedStems(_ramp_stems(40), 1.0, _identity)
    assert stretched.chunk_count == 4

    assert next_chunk_to_compute(stretched, 0) == 0
    stretched.compute_chunk(0, lambda: False)
    assert next_chunk_to_compute(stretched, 0) == 1
    stretched.compute_chunk(1, lambda: False)
    assert next_chunk_to_compute(stretched, 0) is None
    assert next_chunk_to_compute(stretched, 3) == 3
