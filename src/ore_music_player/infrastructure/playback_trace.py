from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def trace_playback_event(event: str, **fields: Any) -> None:
    trace_path = os.environ.get("ORE_MUSIC_TRACE")
    if not trace_path:
        return
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "pid": os.getpid(),
        "event": event,
        **fields,
    }
    path = Path(trace_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as trace_file:
            trace_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as error:
        print(f"playback trace write failed: {error}", file=os.sys.stderr)
