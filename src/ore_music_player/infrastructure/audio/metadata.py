from __future__ import annotations

from math import isfinite
from pathlib import Path

from mutagen import File, MutagenError


def read_duration_seconds(path: str | Path) -> float | None:
	try:
		audio = File(str(path))
	except (MutagenError, OSError):
		return None

	if audio is None:
		return None

	length = getattr(audio.info, "length", None)
	if length is None:
		return None

	try:
		duration = float(length)
	except (TypeError, ValueError):
		return None

	if not isfinite(duration) or duration < 0:
		return None
	return duration
