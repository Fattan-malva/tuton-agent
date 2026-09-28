"""State persistence (output/state.json).

Sengaja pakai satu lock modul: item dikerjakan paralel (`--jobs`), dan tanpa
lock, dua thread bisa membaca _STATE, mengubah字典 berbeda, lalu saling menimpa
-- salah satu progres hilang tanpa jejak. File JSON-nya kecil, jadi penguncian
tidak pernah jadi bottleneck.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from config import OUTPUT_DIR

STATE_FILE = OUTPUT_DIR / "state.json"

_LOCK = threading.RLock()
_STATE: dict | None = None


def _load() -> dict:
    global _STATE
    with _LOCK:
        if _STATE is None:
            if STATE_FILE.exists():
                try:
                    _STATE = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    _STATE = {"items": {}}
            else:
                _STATE = {"items": {}}
        return _STATE


def save() -> None:
    with _LOCK:
        if _STATE is None:
            return
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            # Tulis ke file sementara lalu rename: kalau proses dimatikan di
            # tengah penulisan, state.json lama tetap utuh (tidak jadi korup).
            tmp = STATE_FILE.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(_STATE, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(STATE_FILE)
        except OSError:
            pass


def key(course_id: int, kind: str, index: int) -> str:
    return f"{course_id}:{kind}:{index}"


def get_item(k: str) -> dict | None:
    return _load()["items"].get(k)


def set_item(k: str, data: dict) -> None:
    with _LOCK:
        _load()["items"][k] = data
        save()


def is_done(k: str) -> bool:
    item = get_item(k)
    if not item:
        return False
    return item.get("status") == "done" and all(
        Path(p).exists() for p in item.get("outputs", [])
    )
