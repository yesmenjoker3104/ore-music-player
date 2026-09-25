from __future__ import annotations


def format_duration(seconds: float | None) -> str:
	if seconds is None:
		return "--:--"

	total_seconds = max(0, int(seconds))
	minutes, remainder = divmod(total_seconds, 60)
	hours, minutes = divmod(minutes, 60)
	if hours:
		return f"{hours}:{minutes:02d}:{remainder:02d}"
	return f"{minutes}:{remainder:02d}"