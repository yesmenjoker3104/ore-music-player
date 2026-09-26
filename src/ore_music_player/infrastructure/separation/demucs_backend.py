from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

MODEL_NAME = "htdemucs_6s"
STEM_NAMES: tuple[str, ...] = ("vocals", "drums", "bass", "guitar", "piano", "other")


def separate(
    track_path: Path,
    env_dir: Path,
    output_dir: Path,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Path]:
    python_exe = env_dir / "python.exe"
    if not python_exe.is_file():
        raise RuntimeError(f"demucs 環境が見つかりません: {env_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    if on_progress:
        on_progress(f"{track_path.name} を分離中...")

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                str(python_exe), "-m", "demucs.separate",
                "--out", tmp,
                "--name", MODEL_NAME,
                str(track_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"demucs 分離に失敗しました:\n{result.stderr[-2000:]}")

        stem_source = Path(tmp) / MODEL_NAME / track_path.stem
        stems: dict[str, Path] = {}
        for wav in stem_source.glob("*.wav"):
            dest = output_dir / wav.name
            wav.rename(dest)
            stems[wav.stem] = dest

    return stems
