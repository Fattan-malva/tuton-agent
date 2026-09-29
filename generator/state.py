"""State persistence (output/state.json).

Sengaja pakai satu lock modul: item dikerjakan paralel (`--jobs`), dan tanpa
lock, dua thread bisa membaca _STATE, mengubah field berbeda, lalu saling
menimpa -- salah satu progres hilang tanpa jejak. File JSON-nya kecil, jadi
penguncian tidak pernah jadi bottleneck.

Cache di memori TIDAK boleh dipangling: `server.py` (Flask) dan `main.py`
(pipeline) adalah dua proses berbeda yang menulis file yang sama. Kalau server
memegang salinan selamanya, /api/status dan /api/results terus mengembalikan
keadaan lama dan file .docx yang baru jadi tidak pernah muncul di menu Hasil
sampai server di-restart. Jadi salinan di invalidated begitu mtime/ukuran file
berubah, yaitu setiap kali proses lain menulis.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from config import OUTPUT_DIR

STATE_FILE = OUTPUT_DIR / "state.json"

_LOCK = threading.RLock()
_STATE: dict | None = None
# Cap file yang jadi asal _STATE: (mtime_ns, ukuran). None = belum pernah dibaca.
_STATE_STAMP: tuple[int, int] | None = None


def _file_stamp() -> tuple[int, int] | None:
    """Sidik jari file state.json, atau None kalau file belum ada."""
    try:
        stat = STATE_FILE.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _read() -> dict:
    """Baca state.json dari disk; file rusak/kosong -> state kosong."""
    if not STATE_FILE.exists():
        return {"items": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": {}}
    if not isinstance(data, dict):
        return {"items": {}}
    data.setdefault("items", {})
    return data


def _load() -> dict:
    """State terkini; muat ulang dari disk bila file berubah di luar proses."""
    global _STATE, _STATE_STAMP
    with _LOCK:
        stamp = _file_stamp()
        if _STATE is None or stamp != _STATE_STAMP:
            _STATE = _read()
            # Cap SETELAH baca: bila proses lain menulis tepat di antara baca dan
            # stat, cap lama tersimpan dan pembacaan berikutnya akan memuat ulang.
            _STATE_STAMP = stamp
        return _STATE


def reload() -> dict:
    """Paksa muat ulang dari disk dan kembalikan state terbaru."""
    global _STATE, _STATE_STAMP
    with _LOCK:
        _STATE = None
        _STATE_STAMP = None
        return _load()


def save() -> None:
    global _STATE_STAMP
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
            # Cap ikut diperbarui supaya pembacaan berikutnya tidak reload sia-sia.
            _STATE_STAMP = _file_stamp()
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
