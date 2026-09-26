"""
Probe ② テスト: StemMixer ロジックの検証。

sounddevice が未インストールの場合はすべてスキップする。
音声デバイスを使わずにミキシング・シーク・A/B ループのロジックを検証する。

実行:
    python -m pytest tests/probes/test_sounddevice_mixing.py -v -s
"""
from __future__ import annotations

import sys

import numpy as np
import pytest

sounddevice = pytest.importorskip("sounddevice", reason="sounddevice not installed")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2] / "probes"))
from probe_sounddevice import CHANNELS, SAMPLE_RATE, StemMixer  # noqa: E402

# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------

@pytest.fixture
def short_stems() -> dict[str, np.ndarray]:
    """1秒のサイン波ステムを返す。"""
    n = SAMPLE_RATE  # 1秒
    t = np.linspace(0, 1.0, n, dtype=np.float32)
    stems = {}
    for i, freq in enumerate([440.0, 220.0, 110.0, 330.0]):
        mono = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        stems[("vocals", "drums", "bass", "other")[i]] = np.column_stack([mono, mono])
    return stems


@pytest.fixture
def mixer(short_stems) -> StemMixer:
    return StemMixer(short_stems, SAMPLE_RATE)


# ---------------------------------------------------------------------------
# 基本動作
# ---------------------------------------------------------------------------

def test_sounddevice_importable() -> None:
    import sounddevice  # noqa: F401


def test_mix_chunk_returns_correct_shape(mixer: StemMixer) -> None:
    chunk = mixer.mix_chunk(512)
    assert chunk.shape == (512, CHANNELS)
    assert chunk.dtype == np.float32


def test_mix_chunk_advances_position(mixer: StemMixer) -> None:
    mixer.mix_chunk(1024)
    assert mixer.position == 1024


def test_mix_chunk_values_are_clamped(mixer: StemMixer) -> None:
    """全ステム音量 1.0 でミックスしても [-1, 1] に収まること。"""
    chunk = mixer.mix_chunk(SAMPLE_RATE)
    assert chunk.max() <= 1.0
    assert chunk.min() >= -1.0


def test_mix_chunk_silence_when_all_volumes_zero(mixer: StemMixer) -> None:
    for name in mixer.volumes:
        mixer.volumes[name] = 0.0
    chunk = mixer.mix_chunk(512)
    assert np.all(chunk == 0.0)


def test_mix_chunk_half_volume_reduces_amplitude(mixer: StemMixer) -> None:
    mixer.volumes["vocals"] = 1.0
    for name in ("drums", "bass", "other"):
        mixer.volumes[name] = 0.0

    chunk_full = mixer.mix_chunk(512)
    mixer.seek(0)
    mixer.volumes["vocals"] = 0.5
    chunk_half = mixer.mix_chunk(512)

    np.testing.assert_allclose(chunk_half, chunk_full * 0.5, atol=1e-6)


# ---------------------------------------------------------------------------
# シーク
# ---------------------------------------------------------------------------

def test_seek_sets_position(mixer: StemMixer) -> None:
    mixer.seek(0.5)
    assert mixer.position == SAMPLE_RATE // 2


def test_seek_clamps_to_zero(mixer: StemMixer) -> None:
    mixer.seek(-10.0)
    assert mixer.position == 0


def test_seek_clamps_to_length(mixer: StemMixer) -> None:
    mixer.seek(9999.0)
    assert mixer.position == mixer.length


def test_seek_clears_finished_flag(mixer: StemMixer) -> None:
    mixer.mix_chunk(mixer.length + 100)
    assert mixer.finished
    mixer.seek(0)
    assert not mixer.finished


# ---------------------------------------------------------------------------
# A/B ループ
# ---------------------------------------------------------------------------

def test_ab_loop_resets_position_at_b_point(mixer: StemMixer) -> None:
    mixer.set_a(0.2)
    mixer.set_b(0.5)
    mixer.loop_enabled = True
    mixer.seek(0.49)

    mixer.mix_chunk(BLOCK_SIZE := 1024)
    assert mixer.position <= int(0.5 * SAMPLE_RATE) + BLOCK_SIZE


def test_ab_loop_disabled_does_not_reset(mixer: StemMixer) -> None:
    mixer.set_a(0.2)
    mixer.set_b(0.4)
    mixer.loop_enabled = False
    mixer.seek(0.45)
    mixer.mix_chunk(512)
    assert mixer.position > int(0.4 * SAMPLE_RATE)


def test_ab_loop_requires_b_greater_than_a(mixer: StemMixer) -> None:
    """A ≥ B のときはループしない（無限ループ防止）。"""
    mixer.set_a(0.5)
    mixer.set_b(0.3)
    mixer.loop_enabled = True
    mixer.seek(0.35)
    mixer.mix_chunk(512)
    assert mixer.position > int(0.3 * SAMPLE_RATE)


# ---------------------------------------------------------------------------
# 端末処理
# ---------------------------------------------------------------------------

def test_finished_flag_set_at_end(mixer: StemMixer) -> None:
    mixer.mix_chunk(mixer.length + 100)
    assert mixer.finished


def test_mix_chunk_returns_silence_after_finished(mixer: StemMixer) -> None:
    mixer.mix_chunk(mixer.length + 100)
    silence = mixer.mix_chunk(512)
    assert np.all(silence == 0.0)


# ---------------------------------------------------------------------------
# 速度変更（pyrubberband）
# ---------------------------------------------------------------------------

def test_pyrubberband_time_stretch_preserves_length_ratio() -> None:
    import shutil

    pytest.importorskip("pyrubberband", reason="pyrubberband not installed")
    if shutil.which("rubberband") is None:
        pytest.skip("rubberband CLI not in PATH")
    import pyrubberband as rb

    n = SAMPLE_RATE * 2  # 2秒
    mono = np.sin(2 * np.pi * 440 * np.linspace(0, 2, n)).astype(np.float32)
    speed = 1.25
    stretched = rb.time_stretch(mono, SAMPLE_RATE, speed)

    expected_len = n / speed
    assert abs(len(stretched) - expected_len) < SAMPLE_RATE * 0.05, (
        f"伸縮後の長さ {len(stretched)} が期待値 {expected_len:.0f} と乖離しています"
    )
    ratio = len(stretched) / SAMPLE_RATE
    expected_ratio = expected_len / SAMPLE_RATE
    print(f"\n  2秒 × 速度{speed} → {ratio:.2f}秒（期待: {expected_ratio:.2f}秒）")
