from __future__ import annotations

import numpy as np

from ore_music_player.infrastructure.audio.stem_mixer import (
    CHANNELS,
    SAMPLE_RATE,
    StemMixer,
)


def _make_stems(length_frames: int = 4096) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(0)
    return {
        "vocals": rng.uniform(-0.5, 0.5, (length_frames, CHANNELS)).astype(np.float32),
        "drums": rng.uniform(-0.5, 0.5, (length_frames, CHANNELS)).astype(np.float32),
    }


def test_mix_chunk_shape():
    mixer = StemMixer(_make_stems(), SAMPLE_RATE)
    chunk = mixer.mix_chunk(512)
    assert chunk.shape == (512, CHANNELS)
    assert chunk.dtype == np.float32


def test_mix_chunk_advances_position():
    mixer = StemMixer(_make_stems(4096), SAMPLE_RATE)
    mixer.mix_chunk(1024)
    assert mixer.position == 1024


def test_mix_chunk_clamps_to_one():
    loud = {
        "a": np.full((1024, CHANNELS), 0.8, dtype=np.float32),
        "b": np.full((1024, CHANNELS), 0.8, dtype=np.float32),
    }
    mixer = StemMixer(loud, SAMPLE_RATE)
    chunk = mixer.mix_chunk(1024)
    assert np.all(chunk <= 1.0)
    assert np.all(chunk >= -1.0)


def test_finished_after_end():
    mixer = StemMixer(_make_stems(512), SAMPLE_RATE)
    mixer.mix_chunk(512)
    assert mixer.finished
    silence = mixer.mix_chunk(512)
    assert np.all(silence == 0.0)


def test_seek_resets_finished():
    mixer = StemMixer(_make_stems(512), SAMPLE_RATE)
    mixer.mix_chunk(512)
    assert mixer.finished
    mixer.seek(0.0)
    assert not mixer.finished
    assert mixer.position == 0


def test_ab_loop_wraps_position():
    length = SAMPLE_RATE * 4  # 4 seconds
    stems = {"a": np.zeros((length, CHANNELS), dtype=np.float32)}
    mixer = StemMixer(stems, SAMPLE_RATE)
    mixer.set_a(1.0)
    mixer.set_b(2.0)
    mixer.loop_enabled = True
    # seek to exactly B point so next mix_chunk triggers wrap at start
    mixer.seek(2.0)
    mixer.mix_chunk(512)
    # position should be A + 512 after wrapping
    assert mixer.position == int(1.0 * SAMPLE_RATE) + 512


def test_stem_volume_zero_silences_stem():
    stems = {
        "vocals": np.full((1024, CHANNELS), 0.5, dtype=np.float32),
        "drums": np.full((1024, CHANNELS), 0.5, dtype=np.float32),
    }
    mixer = StemMixer(stems, SAMPLE_RATE)
    mixer.volumes["vocals"] = 0.0
    mixer.volumes["drums"] = 0.0
    chunk = mixer.mix_chunk(1024)
    assert np.all(chunk == 0.0)
