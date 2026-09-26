import os
from pathlib import Path

from ore_music_player.app import run

_VENDOR_RUBBERBAND = Path(__file__).parent.parent.parent / "vendor" / "rubberband"
if _VENDOR_RUBBERBAND.is_dir():
    os.environ["PATH"] = str(_VENDOR_RUBBERBAND) + os.pathsep + os.environ.get("PATH", "")


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
