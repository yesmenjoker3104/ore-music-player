import os
import sys
from pathlib import Path

from ore_music_player.app import run

if getattr(sys, "frozen", False):
    _VENDOR_RUBBERBAND = Path(sys._MEIPASS) / "vendor" / "rubberband"
else:
    _VENDOR_RUBBERBAND = Path(__file__).parent.parent.parent / "vendor" / "rubberband"
if _VENDOR_RUBBERBAND.is_dir():
    os.environ["PATH"] = str(_VENDOR_RUBBERBAND) + os.pathsep + os.environ.get("PATH", "")


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
