from __future__ import annotations

import json
from pathlib import Path

from config import OUTPUT_DIR

STATE_FILE = OUTPUT_DIR / "state.json"

_STATE: dict | None = None


def _load() -> dict:
    global _STATE
    if STATE_FILE.exists():
        _STATE = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    elif _STATE is None:
        _STATE = {"items": {}}
    return _STATE


def save() -> None:
    if _STATE is not None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(_STATE, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def key(course_id: int, kind: str, index: int) -> str:
    return f"{course_id}:{kind}:{index}"


def get_item(k: str) -> dict | None:
    return _load()["items"].get(k)


def set_item(k: str, data: dict) -> None:
    _load()["items"][k] = data
    save()


def is_done(k: str) -> bool:
    item = get_item(k)
    if not item:
        return False
    return item.get("status") == "done" and all(
        Path(p).exists() for p in item.get("outputs", [])
    )