"""
Probe ③: vendor/demucs-env/ に embeddable Python + demucs 環境をオンデマンド構築する。

事前準備不要（スクリプトが自動でダウンロード・構築する）。
初回は PyTorch 含むため数百 MB・数分かかる。

実行:
    python probes/probe_demucs_env.py            # vendor/demucs-env/ に構築して確認
    python probes/probe_demucs_env.py --check    # 既存環境の確認のみ（ダウンロードしない）
    python probes/probe_demucs_env.py --target D:/path/to/dir  # 指定パスに構築

確認項目:
    - embeddable Python を ZIP からダウンロード・展開できるか
    - ._pth ファイルを修正して site-packages を有効化できるか
    - get-pip.py で pip をブートストラップできるか
    - pip install demucs が embeddable 環境に入るか
    - 構築済み環境の python.exe から demucs を呼び出せるか
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PYTHON_VERSION = "3.11.9"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}"
    f"/python-{PYTHON_VERSION}-embed-amd64.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


# ---------------------------------------------------------------------------
# パス解決
# ---------------------------------------------------------------------------

def find_default_env_dir() -> Path:
    """vendor/demucs-env/ を返す。書き込み不可なら APPDATA フォールバック。"""
    repo_root = Path(__file__).parent.parent
    vendor_dir = repo_root / "vendor"
    if vendor_dir.is_dir():
        return vendor_dir / "demucs-env"
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "OreMusicPlayer" / "demucs-env"


# ---------------------------------------------------------------------------
# 状態チェック
# ---------------------------------------------------------------------------

def is_env_ready(env_dir: Path) -> bool:
    """python.exe が存在し、demucs を import できれば True。"""
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


# ---------------------------------------------------------------------------
# 環境構築ステップ
# ---------------------------------------------------------------------------

def download_embeddable_python(env_dir: Path) -> None:
    """embeddable Python をダウンロードして env_dir に展開する。"""
    env_dir.mkdir(parents=True, exist_ok=True)
    zip_path = env_dir / "_python-embed.zip"

    print(f"  Python {PYTHON_VERSION} embeddable をダウンロード中...")
    print(f"  URL: {PYTHON_EMBED_URL}")
    urllib.request.urlretrieve(PYTHON_EMBED_URL, zip_path)
    print(f"  ダウンロード完了: {zip_path.stat().st_size // 1024} KB")

    print("  展開中...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(env_dir)
    zip_path.unlink()
    print("  展開完了")


def enable_site_imports(pth_file: Path) -> bool:
    """._pth ファイルの '#import site' を 'import site' に書き換える。

    Returns:
        True if the file was modified, False if already enabled.
    """
    content = pth_file.read_text(encoding="utf-8")
    if "import site" in content and "#import site" not in content:
        return False
    modified = content.replace("#import site", "import site")
    pth_file.write_text(modified, encoding="utf-8")
    return True


def enable_pip_in_embeddable(env_dir: Path) -> None:
    """embeddable Python に pip をインストールする。

    1. ._pth ファイルで import site を有効化
    2. get-pip.py をダウンロードして実行
    """
    pth_files = list(env_dir.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError(f"._pth ファイルが見つかりません: {env_dir}")

    for pth_file in pth_files:
        changed = enable_site_imports(pth_file)
        print(f"  {pth_file.name}: import site {'有効化' if changed else '既に有効'}")

    get_pip_path = env_dir / "_get-pip.py"
    print("  get-pip.py をダウンロード中...")
    urllib.request.urlretrieve(GET_PIP_URL, get_pip_path)

    python_exe = env_dir / "python.exe"
    print("  pip をインストール中...")
    subprocess.check_call([str(python_exe), str(get_pip_path)], cwd=str(env_dir))
    get_pip_path.unlink()
    print("  pip インストール完了")


def install_demucs(env_dir: Path) -> None:
    """demucs を embeddable 環境にインストールする（PyTorch 含む）。"""
    python_exe = env_dir / "python.exe"
    print("  demucs をインストール中（PyTorch を含むため数分かかります）...")
    subprocess.check_call([
        str(python_exe), "-m", "pip", "install",
        "--no-warn-script-location",
        "demucs",
    ])
    print("  demucs インストール完了")


# ---------------------------------------------------------------------------
# 統合セットアップ
# ---------------------------------------------------------------------------

def setup_demucs_env(env_dir: Path) -> None:
    """env_dir に embeddable Python + demucs 環境を構築する。

    既に構築済みであればスキップする。
    """
    print(f"\n[確認] 構築先: {env_dir}")
    if is_env_ready(env_dir):
        print("  [OK] 環境は既に構築済みです")
        return

    python_exe = env_dir / "python.exe"
    if not python_exe.is_file():
        print("\n[1] embeddable Python のダウンロード")
        download_embeddable_python(env_dir)

        print("\n[2] pip の有効化")
        enable_pip_in_embeddable(env_dir)
    else:
        print("  python.exe 存在 → pip 確認のみ")

    print("\n[3] demucs のインストール")
    install_demucs(env_dir)

    print("\n[4] 動作確認")
    info = verify_demucs(env_dir)
    if info["ok"]:
        print(f"  [OK] demucs {info['version']} が呼び出せます")
    else:
        print(f"  [NG] demucs の呼び出しに失敗: {info['error']}")
        raise RuntimeError("環境構築後の確認に失敗しました")


# ---------------------------------------------------------------------------
# 動作確認
# ---------------------------------------------------------------------------

def verify_demucs(env_dir: Path) -> dict:
    """embeddable 環境から demucs が呼び出せるか確認する。"""
    python_exe = env_dir / "python.exe"
    if not python_exe.is_file():
        return {"ok": False, "version": "", "error": "python.exe が存在しません"}

    result = subprocess.run(
        [str(python_exe), "-c", "import demucs; print(demucs.__version__)"],
        capture_output=True,
        text=True,
    )
    return {
        "ok": result.returncode == 0,
        "version": result.stdout.strip(),
        "error": result.stderr.strip(),
    }


def print_env_status(env_dir: Path) -> None:
    """環境の現在状態を表示する。"""
    print(f"\n環境パス: {env_dir}")
    python_exe = env_dir / "python.exe"
    pth_files = list(env_dir.glob("python*._pth")) if env_dir.is_dir() else []

    print(f"  python.exe: {'[OK]' if python_exe.is_file() else '[NG] (なし)'}")
    for pth in pth_files:
        content = pth.read_text(encoding="utf-8")
        site_ok = "import site" in content and "#import site" not in content
        print(f"  {pth.name}: import site {'[OK]' if site_ok else '[NG] (無効)'}")

    info = verify_demucs(env_dir)
    if info["ok"]:
        print(f"  demucs: [OK] version {info['version']}")
    else:
        print(f"  demucs: [NG] ({info['error'][:80] if info['error'] else 'not found'})")


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Probe ③: demucs 環境構築")
    parser.add_argument("--check", action="store_true", help="確認のみ（構築しない）")
    parser.add_argument("--target", type=Path, default=None, help="構築先ディレクトリ")
    args = parser.parse_args()

    env_dir = args.target if args.target else find_default_env_dir()

    print("=" * 60)
    print("Probe ③: embeddable Python + demucs 環境構築")
    print("=" * 60)

    if args.check:
        print_env_status(env_dir)
        return

    try:
        setup_demucs_env(env_dir)
        print_env_status(env_dir)
        print("\n[OK] Probe ③ 完了")
    except Exception as exc:
        print(f"\n[NG] エラー: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
