from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH)
mpv_directory = project_root / "vendor" / "mpv"
mpv_dlls = list(mpv_directory.glob("*.dll"))
if not any(path.name in {"libmpv-2.dll", "mpv-2.dll", "mpv-1.dll"} for path in mpv_dlls):
    raise SystemExit(
        "vendor/mpv is missing a libmpv DLL. "
        "Place the mpv shared runtime there before building."
    )


a = Analysis(
    [str(project_root / "src" / "ore_music_player" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[(str(path), "vendor/mpv") for path in mpv_dlls],
    datas=[
        (
            str(project_root / "src" / "ore_music_player" / "assets"),
            "ore_music_player/assets",
        ),
        (
            str(project_root / "src" / "ore_music_player" / "infrastructure" / "apply_update.ps1"),
            "ore_music_player/infrastructure",
        ),
    ],
    hiddenimports=collect_submodules("mpv"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ore-music-player",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(project_root / "src" / "ore_music_player" / "assets" / "app_icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="ore-music-player",
)