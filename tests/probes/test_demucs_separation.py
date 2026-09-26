"""
Probe ① テスト: Demucs 音源分離の検証。

demucs が未インストールの場合はすべてのテストを自動スキップする。
重い分離テスト（test_separation_*）は通常の CI では除外し、
probe 確認時だけ実行する。

実行方法:
    # demucs インポートだけ確認（高速）
    python -m pytest tests/probes/ -q -k "not separation"

    # 分離まで含めて全確認（数分かかる）
    python -m pytest tests/probes/ -q -s
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import pytest

demucs = pytest.importorskip("demucs", reason="demucs not installed; run: pip install demucs")

EXPECTED_STEMS = {"vocals", "drums", "bass", "other"}
MODEL_NAME = "htdemucs"


def _generate_sine_wav(path: Path, duration_seconds: float = 3.0, sample_rate: int = 44100) -> None:
    """テスト用サイン波 WAV（ステレオ 16bit）を生成する。"""
    n_samples = int(sample_rate * duration_seconds)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            value = int(32767 * math.sin(2 * math.pi * 440.0 * i / sample_rate))
            wf.writeframes(struct.pack("<hh", value, value))


def test_demucs_is_importable() -> None:
    import demucs  # noqa: F401
    assert hasattr(demucs, "__version__")


def test_demucs_version_is_available() -> None:
    import demucs
    version = demucs.__version__
    parts = version.split(".")
    assert len(parts) >= 2, f"バージョン形式が想定外: {version}"
    print(f"\n  demucs version: {version}")


def test_demucs_separate_module_importable() -> None:
    import demucs.separate  # noqa: F401


def test_htdemucs_stem_names_are_as_expected() -> None:
    """htdemucs が 4ステムを持つことを確認する（初回のみモデルダウンロードが発生する）。"""
    from demucs.api import Separator
    sep = Separator(MODEL_NAME)
    sources = list(sep.model.sources)
    assert set(sources) == EXPECTED_STEMS, (
        f"ステム名が変わっています: {sources}"
    )
    print(f"\n  htdemucs stems: {sources}")


def test_separation_produces_expected_stems(tmp_path: Path) -> None:
    """実際に分離して 4ステムが生成されることを確認する（数分かかる）。"""
    import time

    import demucs.separate

    audio_path = tmp_path / "test_audio.wav"
    _generate_sine_wav(audio_path, duration_seconds=3.0)

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    print(f"\n  入力: {audio_path} (3秒)")
    print(f"  モデル: {MODEL_NAME}")
    print("  分離中...")

    start = time.perf_counter()
    try:
        demucs.separate.main([
            "--out", str(output_dir),
            "--name", MODEL_NAME,
            str(audio_path),
        ])
    except SystemExit:
        pass
    elapsed = time.perf_counter() - start

    print(f"  処理時間: {elapsed:.1f}秒")

    stem_files = sorted(output_dir.rglob("*.wav")) + sorted(output_dir.rglob("*.mp3"))
    assert stem_files, "ステムファイルが1つも生成されませんでした"

    found_stems = {f.stem for f in stem_files}
    print(f"  生成ステム: {sorted(found_stems)}")
    for stem_file in stem_files:
        size_kb = stem_file.stat().st_size // 1024
        print(f"    {stem_file.name}: {size_kb} KB")

    assert EXPECTED_STEMS <= found_stems, (
        f"期待するステムが不足しています。\n"
        f"  期待: {EXPECTED_STEMS}\n"
        f"  実際: {found_stems}"
    )
