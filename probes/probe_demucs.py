"""
Probe ①: Demucs で音源分離できるか確認する。

事前準備:
    pip install demucs

実行:
    python probes/probe_demucs.py                    # 内部生成サイン波で確認
    python probes/probe_demucs.py path/to/audio.mp3  # 実音声ファイルで確認

確認項目:
    - Demucs のインポートと htdemucs モデルのロード
    - 4ステム（vocals / drums / bass / other）への分離
    - 処理時間
    - 出力ファイルの形式とサイズ
"""
from __future__ import annotations

import math
import struct
import sys
import time
import wave
from pathlib import Path

PROBE_DIR = Path(__file__).parent
PROBE_AUDIO = PROBE_DIR / "probe_audio.wav"
PROBE_OUTPUT = PROBE_DIR / "probe_output"
EXPECTED_STEMS = {"vocals", "drums", "bass", "other"}
MODEL_NAME = "htdemucs_6s"


def generate_sine_wav(
    path: Path,
    duration_seconds: float = 5.0,
    sample_rate: int = 44100,
) -> None:
    """テスト用のサイン波 WAV（ステレオ 16bit）を生成する。"""
    frequency = 440.0
    n_samples = int(sample_rate * duration_seconds)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            value = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
            wf.writeframes(struct.pack("<hh", value, value))
    print(f"  生成: {path} ({duration_seconds:.0f}秒, {sample_rate}Hz ステレオ)")


def run_probe(audio_path: Path | None = None) -> bool:
    print("=" * 60)
    print("Probe ①: Demucs 音源分離")
    print("=" * 60)

    # 1. インポート確認
    print("\n[1] demucs インポート...")
    try:
        import demucs
        print(f"  OK: demucs {demucs.__version__}")
    except ImportError as e:
        print(f"  FAIL: {e}")
        print("  → pip install demucs を実行してください")
        return False

    # 2. 入力ファイルの準備
    print("\n[2] 入力ファイル準備...")
    if audio_path is None:
        generate_sine_wav(PROBE_AUDIO)
        audio_path = PROBE_AUDIO
    else:
        print(f"  使用: {audio_path}")
        if not audio_path.exists():
            print(f"  FAIL: ファイルが存在しません: {audio_path}")
            return False

    # 3. 分離実行
    print(f"\n[3] {MODEL_NAME} で分離中（CPU の場合は数分かかります）...")
    PROBE_OUTPUT.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    try:
        import demucs.separate
        demucs.separate.main([
            "--out", str(PROBE_OUTPUT),
            "--name", MODEL_NAME,
            str(audio_path),
        ])
    except SystemExit:
        pass  # demucs.separate.main は sys.exit(0) を呼ぶことがある
    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    elapsed = time.perf_counter() - start
    print(f"  処理時間: {elapsed:.1f}秒")

    # 4. 出力確認
    print("\n[4] 出力ステム確認...")
    stem_files = sorted(PROBE_OUTPUT.rglob("*.wav")) + sorted(PROBE_OUTPUT.rglob("*.mp3"))
    if not stem_files:
        print("  FAIL: ステムファイルが見つかりません")
        return False

    found_stems: set[str] = set()
    for stem_file in stem_files:
        size_kb = stem_file.stat().st_size // 1024
        print(f"  {stem_file.name:20s}  {size_kb:6d} KB  ({stem_file.parent.name})")
        found_stems.add(stem_file.stem)

    missing = EXPECTED_STEMS - found_stems
    extra = found_stems - EXPECTED_STEMS
    if missing:
        print(f"  WARN: 期待するステムがありません: {missing}")
    if extra:
        print(f"  INFO: 追加ステム: {extra}")

    # 5. まとめ
    print("\n[結果]")
    print(f"  ステム数   : {len(found_stems)}")
    print(f"  ステム名   : {sorted(found_stems)}")
    print(f"  処理時間   : {elapsed:.1f}秒")
    print(f"  期待通り   : {'YES' if not missing else 'NO (一部欠損)'}")
    return not missing


if __name__ == "__main__":
    audio_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    success = run_probe(audio_path)
    sys.exit(0 if success else 1)
