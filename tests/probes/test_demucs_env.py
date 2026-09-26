"""
Probe ③ テスト: embeddable Python + demucs 環境構築ロジックの検証。

ネットワーク不要のテスト（デフォルト実行）:
    - パス解決ロジック
    - ._pth ファイル修正ロジック
    - is_env_ready の判定ロジック

ネットワーク必要なテスト（環境変数 PROBE_NETWORK=1 で有効化）:
    - embeddable Python のダウンロード・展開
    - pip のブートストラップ
    - demucs のインストール（非常に重い）

実行:
    python -m pytest tests/probes/test_demucs_env.py -v              # 高速テストのみ
    PROBE_NETWORK=1 python -m pytest tests/probes/test_demucs_env.py -v  # 全テスト
    PROBE_NETWORK=1 python -m pytest tests/probes/test_demucs_env.py -v -k "not install"  # pip まで
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "probes"))
from probe_demucs_env import (
    download_embeddable_python,
    enable_pip_in_embeddable,
    enable_site_imports,
    find_default_env_dir,
    is_env_ready,
    setup_demucs_env,
    verify_demucs,
)

NEEDS_NETWORK = pytest.mark.skipif(
    os.environ.get("PROBE_NETWORK") != "1",
    reason="PROBE_NETWORK=1 が必要（ネットワーク接続と数百 MB のダウンロードが発生）",
)


# ---------------------------------------------------------------------------
# パス解決
# ---------------------------------------------------------------------------

def test_find_default_env_dir_is_under_vendor_or_appdata() -> None:
    env_dir = find_default_env_dir()
    vendor_candidate = Path(__file__).parents[2] / "vendor" / "demucs-env"
    appdata = Path(os.environ.get("APPDATA", "")) / "OreMusicPlayer" / "demucs-env"

    assert env_dir in (vendor_candidate, appdata), (
        f"想定外のパス: {env_dir}"
    )
    print(f"\n  env_dir: {env_dir}")


def test_find_default_env_dir_prefers_vendor_when_vendor_exists() -> None:
    env_dir = find_default_env_dir()
    vendor_dir = Path(__file__).parents[2] / "vendor"
    if vendor_dir.is_dir():
        assert env_dir == vendor_dir / "demucs-env"


# ---------------------------------------------------------------------------
# ._pth ファイル修正ロジック
# ---------------------------------------------------------------------------

def test_enable_site_imports_uncomments_import_site(tmp_path: Path) -> None:
    pth = tmp_path / "python311._pth"
    pth.write_text("python311.zip\n.\n\n#import site\n", encoding="utf-8")

    changed = enable_site_imports(pth)

    assert changed is True
    content = pth.read_text(encoding="utf-8")
    assert "import site" in content
    assert "#import site" not in content


def test_enable_site_imports_is_idempotent(tmp_path: Path) -> None:
    pth = tmp_path / "python311._pth"
    pth.write_text("python311.zip\n.\n\nimport site\n", encoding="utf-8")

    changed = enable_site_imports(pth)

    assert changed is False
    content = pth.read_text(encoding="utf-8")
    assert content.count("import site") == 1


def test_enable_site_imports_preserves_other_lines(tmp_path: Path) -> None:
    original = "python311.zip\n.\n\n#import site\n"
    pth = tmp_path / "python311._pth"
    pth.write_text(original, encoding="utf-8")

    enable_site_imports(pth)
    content = pth.read_text(encoding="utf-8")

    assert "python311.zip" in content
    assert "." in content


# ---------------------------------------------------------------------------
# is_env_ready
# ---------------------------------------------------------------------------

def test_is_env_ready_returns_false_when_dir_empty(tmp_path: Path) -> None:
    assert is_env_ready(tmp_path) is False


def test_is_env_ready_returns_false_when_python_exe_missing(tmp_path: Path) -> None:
    (tmp_path / "demucs").mkdir()
    assert is_env_ready(tmp_path) is False


def test_is_env_ready_returns_false_when_demucs_not_installed(tmp_path: Path) -> None:
    python_exe = tmp_path / "python.exe"
    python_exe.write_bytes(b"")
    assert is_env_ready(tmp_path) is False


# ---------------------------------------------------------------------------
# verify_demucs
# ---------------------------------------------------------------------------

def test_verify_demucs_returns_not_ok_when_dir_empty(tmp_path: Path) -> None:
    result = verify_demucs(tmp_path)
    assert result["ok"] is False
    assert result["version"] == ""


def test_verify_demucs_uses_env_python_not_system_python(tmp_path: Path) -> None:
    """verify_demucs は env_dir/python.exe を使うことを確認する。"""
    result = verify_demucs(tmp_path)
    assert "python.exe が存在しません" in result["error"]


# ---------------------------------------------------------------------------
# .gitignore
# ---------------------------------------------------------------------------

def test_demucs_env_dir_is_gitignored() -> None:
    """vendor/demucs-env/ が .gitignore に登録されていることを確認する。"""
    gitignore = Path(__file__).parents[2] / ".gitignore"
    if not gitignore.is_file():
        pytest.skip(".gitignore が存在しません")

    content = gitignore.read_text(encoding="utf-8")
    assert "demucs-env" in content, (
        "vendor/demucs-env/ が .gitignore に登録されていません。\n"
        "echo 'vendor/demucs-env/' >> .gitignore を実行してください。"
    )


# ---------------------------------------------------------------------------
# ネットワークテスト（PROBE_NETWORK=1 で有効）
# ---------------------------------------------------------------------------

@NEEDS_NETWORK
def test_download_embeddable_python_creates_python_exe(tmp_path: Path) -> None:
    """embeddable Python をダウンロードして python.exe が展開されることを確認する。"""
    env_dir = tmp_path / "embed-python"
    download_embeddable_python(env_dir)

    python_exe = env_dir / "python.exe"
    assert python_exe.is_file(), "python.exe が見つかりません"

    pth_files = list(env_dir.glob("python*._pth"))
    assert pth_files, "._pth ファイルが見つかりません"

    size_mb = sum(f.stat().st_size for f in env_dir.iterdir()) // (1024 * 1024)
    print(f"\n  展開サイズ: {size_mb} MB")
    print(f"  ._pth ファイル: {[p.name for p in pth_files]}")


@NEEDS_NETWORK
def test_enable_pip_installs_pip_into_embeddable(tmp_path: Path) -> None:
    """pip が embeddable Python に入ることを確認する（get-pip.py 実行）。"""
    env_dir = tmp_path / "embed-python"
    download_embeddable_python(env_dir)
    enable_pip_in_embeddable(env_dir)

    python_exe = env_dir / "python.exe"
    result = subprocess.run(
        [str(python_exe), "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"pip が動作しません: {result.stderr}"
    print(f"\n  {result.stdout.strip()}")


@NEEDS_NETWORK
def test_install_demucs_makes_env_ready(tmp_path: Path) -> None:
    """demucs をインストールして is_env_ready が True になることを確認する。

    非常に重いテスト（PyTorch 含む、数分かかる）。
    """
    env_dir = tmp_path / "demucs-env"
    setup_demucs_env(env_dir)

    assert is_env_ready(env_dir), "環境構築後も is_env_ready が False です"

    info = verify_demucs(env_dir)
    assert info["ok"], f"demucs の呼び出しに失敗: {info['error']}"
    print(f"\n  demucs version: {info['version']}")
