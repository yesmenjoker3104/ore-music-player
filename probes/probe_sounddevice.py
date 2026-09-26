"""
Probe ②: sounddevice でリアルタイムミックス・シーク・A/B ループ・速度変更を確認する。

事前準備:
    pip install sounddevice soundfile pyrubberband

実行:
    python probes/probe_sounddevice.py                       # サイン波ステムで確認
    python probes/probe_sounddevice.py path/to/stem_dir/     # 分離済みステムディレクトリで確認

stem_dir には vocals.wav / drums.wav / bass.wav / other.wav を置く。

確認項目:
    - 4ステムを同時再生してミックスできるか
    - 音量スライダーで各ステムの音量をリアルタイムに変えられるか
    - シークが即座に効くか
    - A/B ループが区間を外れずにループするか
    - pyrubberband でピッチを保ったまま速度変更できるか
"""
from __future__ import annotations

import math
import struct
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
CHANNELS = 2
BLOCK_SIZE = 1024
STEM_NAMES = ("vocals", "drums", "bass", "other")


# ---------------------------------------------------------------------------
# ミキシングエンジン（テスト可能な純粋ロジック）
# ---------------------------------------------------------------------------

class StemMixer:
    """複数ステムのリアルタイムミックスエンジン。

    sounddevice のコールバックから呼ばれる mix_chunk() が本体。
    ロック不使用 ─ position/volumes の更新は GIL に頼る（probe 用途）。
    """

    def __init__(
        self,
        stems: dict[str, np.ndarray],
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        self.stems = stems
        self.sample_rate = sample_rate
        self.volumes: dict[str, float] = {name: 1.0 for name in stems}
        self.position: int = 0
        self.length: int = max(len(v) for v in stems.values()) if stems else 0
        self.a_point: int | None = None
        self.b_point: int | None = None
        self.loop_enabled: bool = False
        self._finished = False

    @property
    def position_seconds(self) -> float:
        return self.position / self.sample_rate

    @property
    def length_seconds(self) -> float:
        return self.length / self.sample_rate

    @property
    def finished(self) -> bool:
        return self._finished

    def seek(self, seconds: float) -> None:
        self.position = max(0, min(int(seconds * self.sample_rate), self.length))
        self._finished = False

    def set_a(self, seconds: float) -> None:
        self.a_point = max(0, int(seconds * self.sample_rate))

    def set_b(self, seconds: float) -> None:
        self.b_point = max(0, int(seconds * self.sample_rate))

    def mix_chunk(self, frames: int) -> np.ndarray:
        """frames サンプル分をミックスして (frames, 2) の float32 配列を返す。"""
        if self._finished:
            return np.zeros((frames, CHANNELS), dtype=np.float32)

        # A/B ループ
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
            vol = self.volumes.get(name, 1.0)
            if vol > 0 and actual > 0:
                chunk = audio[start:end]
                if chunk.ndim == 1:
                    chunk = np.column_stack([chunk, chunk])
                result[:actual] += (chunk * vol).astype(np.float32)

        self.position = end
        if self.position >= self.length:
            self._finished = True

        return np.clip(result, -1.0, 1.0)


# ---------------------------------------------------------------------------
# 速度変更（pyrubberband、オフライン処理）
# ---------------------------------------------------------------------------

def stretch_stems(
    stems: dict[str, np.ndarray],
    sample_rate: int,
    speed: float,
) -> dict[str, np.ndarray]:
    """pyrubberband でピッチを維持しながら速度変更した新しい stems を返す。"""
    try:
        import pyrubberband as rb
    except ImportError:
        print("  pyrubberband が見つかりません。速度変更は確認できません。")
        return stems

    stretched: dict[str, np.ndarray] = {}
    for name, audio in stems.items():
        mono = audio[:, 0] if audio.ndim == 2 else audio
        out = rb.time_stretch(mono, sample_rate, speed)
        stretched[name] = np.column_stack([out, out]).astype(np.float32)
    return stretched


# ---------------------------------------------------------------------------
# ステム生成（テスト用サイン波）
# ---------------------------------------------------------------------------

def generate_sine_stems(duration_seconds: float = 10.0) -> dict[str, np.ndarray]:
    """4ステム分のサイン波を生成する。"""
    n = int(SAMPLE_RATE * duration_seconds)
    t = np.linspace(0, duration_seconds, n, dtype=np.float32)
    freqs = {"vocals": 440.0, "drums": 220.0, "bass": 110.0, "other": 330.0}
    stems = {}
    for name, freq in freqs.items():
        mono = (0.25 * np.sin(2 * math.pi * freq * t)).astype(np.float32)
        stems[name] = np.column_stack([mono, mono])
    return stems


def load_stems_from_dir(stem_dir: Path) -> dict[str, np.ndarray]:
    """ディレクトリから stems を読み込む。"""
    import soundfile as sf

    stems: dict[str, np.ndarray] = {}
    for name in STEM_NAMES:
        for suffix in (".wav", ".mp3"):
            path = stem_dir / f"{name}{suffix}"
            if path.exists():
                data, sr = sf.read(str(path), dtype="float32", always_2d=True)
                if sr != SAMPLE_RATE:
                    print(f"  警告: {path.name} のサンプルレートが {sr}Hz です（{SAMPLE_RATE}Hz 期待）")
                stems[name] = data
                break
    return stems


# ---------------------------------------------------------------------------
# 対話プローブ本体
# ---------------------------------------------------------------------------

def run_probe(stem_dir: Path | None = None) -> None:
    try:
        import sounddevice as sd
    except ImportError:
        print("sounddevice が見つかりません: pip install sounddevice")
        sys.exit(1)

    print("=" * 60)
    print("Probe ②: sounddevice リアルタイムミックス")
    print("=" * 60)

    print("\n[1] ステム読み込み...")
    if stem_dir is not None:
        stems = load_stems_from_dir(stem_dir)
        if not stems:
            print(f"  WAV が見つかりません: {stem_dir}")
            sys.exit(1)
        print(f"  読み込み済み: {list(stems.keys())}")
    else:
        stems = generate_sine_stems()
        print("  サイン波ステムを生成しました（vocals=440Hz, drums=220Hz, bass=110Hz, other=330Hz）")

    mixer = StemMixer(stems, SAMPLE_RATE)
    original_stems = stems
    is_playing = False
    stream: sd.OutputStream | None = None

    def audio_callback(outdata, frames, time_info, status):
        outdata[:] = mixer.mix_chunk(frames)
        if mixer.finished:
            raise sd.CallbackStop

    def start_stream():
        nonlocal stream, is_playing
        if stream is not None:
            stream.close()
        stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=audio_callback,
        )
        stream.start()
        is_playing = True

    def stop_stream():
        nonlocal stream, is_playing
        if stream is not None:
            stream.stop()
            stream.close()
            stream = None
        is_playing = False

    print("\n[2] sounddevice 確認...")
    print(f"  デバイス: {sd.query_devices(kind='output')['name']}")

    print("""
コマンド一覧:
  p       再生 / 一時停止
  s       停止（先頭に戻る）
  f/b     5秒 進む / 戻る
  a/b     A 点 / B 点を現在位置に設定
  l       A/B ループ ON/OFF
  1~4     ステム音量 0.0 / 0.5 / 1.0 をトグル（1=vocals 2=drums 3=bass 4=other）
  +/-     速度 +0.1 / -0.1（pyrubberband で前処理）
  i       現在の状態を表示
  q       終了
""")

    current_speed = 1.0

    while True:
        cmd = input("> ").strip().lower()

        if cmd == "q":
            stop_stream()
            break

        elif cmd == "p":
            if is_playing:
                stop_stream()
                print("  一時停止")
            else:
                if mixer.finished:
                    mixer.seek(0)
                start_stream()
                print(f"  再生中 ({mixer.position_seconds:.1f}s / {mixer.length_seconds:.1f}s)")

        elif cmd == "s":
            stop_stream()
            mixer.seek(0)
            print("  停止")

        elif cmd == "f":
            mixer.seek(mixer.position_seconds + 5.0)
            print(f"  → {mixer.position_seconds:.1f}s")

        elif cmd == "b":
            mixer.seek(max(0, mixer.position_seconds - 5.0))
            print(f"  → {mixer.position_seconds:.1f}s")

        elif cmd == "a":
            mixer.set_a(mixer.position_seconds)
            print(f"  A点 = {mixer.position_seconds:.1f}s")

        elif cmd == "b":
            mixer.set_b(mixer.position_seconds)
            print(f"  B点 = {mixer.position_seconds:.1f}s")

        elif cmd == "l":
            if mixer.a_point is None or mixer.b_point is None:
                print("  A点とB点を先に設定してください")
            else:
                mixer.loop_enabled = not mixer.loop_enabled
                print(f"  ループ {'ON' if mixer.loop_enabled else 'OFF'}")

        elif cmd in ("1", "2", "3", "4"):
            idx = int(cmd) - 1
            name = STEM_NAMES[idx]
            vols = [0.0, 0.5, 1.0]
            cur = mixer.volumes.get(name, 1.0)
            next_vol = vols[(vols.index(min(vols, key=lambda v: abs(v - cur))) + 1) % len(vols)]
            mixer.volumes[name] = next_vol
            print(f"  {name} 音量 → {next_vol}")

        elif cmd in ("+", "-"):
            current_speed = max(0.5, min(1.5, current_speed + (0.1 if cmd == "+" else -0.1)))
            was_playing = is_playing
            stop_stream()
            print(f"  速度変更 → {current_speed:.1f}x (pyrubberband で処理中...)")
            new_stems = stretch_stems(original_stems, SAMPLE_RATE, current_speed)
            pos_sec = mixer.position_seconds
            mixer = StemMixer(new_stems, SAMPLE_RATE)
            mixer.seek(pos_sec)
            if was_playing:
                start_stream()

        elif cmd == "i":
            a = f"{mixer.a_point / SAMPLE_RATE:.1f}s" if mixer.a_point else "未設定"
            b = f"{mixer.b_point / SAMPLE_RATE:.1f}s" if mixer.b_point else "未設定"
            print(f"  位置: {mixer.position_seconds:.1f}s / {mixer.length_seconds:.1f}s")
            print(f"  速度: {current_speed:.1f}x  ループ: {'ON' if mixer.loop_enabled else 'OFF'}")
            print(f"  A={a}  B={b}")
            print(f"  音量: { {k: v for k, v in mixer.volumes.items()} }")

        else:
            print("  不明なコマンドです")

    print("\n完了")


if __name__ == "__main__":
    stem_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    run_probe(stem_dir)
