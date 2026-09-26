from __future__ import annotations

import os
import subprocess
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

PYTHON_VERSION = "3.11.9"
_PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}"
    f"/python-{PYTHON_VERSION}-embed-amd64.zip"
)
_GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def find_env_dir(project_root: Path) -> Path:
    vendor_dir = project_root / "vendor"
    if vendor_dir.is_dir():
        return vendor_dir / "demucs-env"
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "OreMusicPlayer" / "demucs-env"


def is_env_ready(env_dir: Path) -> bool:
    python_exe = env_dir / "python.exe"
    if not python_exe.is_file():
        return False
    try:
        result = subprocess.run(
            [str(python_exe), "-c", "import demucs"],
            capture_output=True,
        )
        return result.returncode == 0
    except OSError:
        return False


def _enable_site_imports(pth_file: Path) -> None:
    content = pth_file.read_text(encoding="utf-8")
    if "#import site" in content:
        pth_file.write_text(content.replace("#import site", "import site"), encoding="utf-8")


def setup_env(
    env_dir: Path,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    def _progress(msg: str) -> None:
        if on_progress is not None:
            on_progress(msg)

    if is_env_ready(env_dir):
        return

    env_dir.mkdir(parents=True, exist_ok=True)
    python_exe = env_dir / "python.exe"

    if not python_exe.is_file():
        _progress("Python 環境をダウンロード中...")
        zip_path = env_dir / "_python-embed.zip"
        urllib.request.urlretrieve(_PYTHON_EMBED_URL, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(env_dir)
        zip_path.unlink()

        for pth_file in env_dir.glob("python*._pth"):
            _enable_site_imports(pth_file)

        _progress("pip をセットアップ中...")
        get_pip = env_dir / "_get-pip.py"
        urllib.request.urlretrieve(_GET_PIP_URL, get_pip)
        subprocess.check_call([str(python_exe), str(get_pip)], cwd=str(env_dir))
        get_pip.unlink()

    _progress("demucs をインストール中（数分かかります）...")
    subprocess.check_call([
        str(python_exe), "-m", "pip", "install",
        "--no-warn-script-location", "demucs",
    ])
