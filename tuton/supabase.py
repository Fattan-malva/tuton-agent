"""Supabase store for per-user settings: Moodle cookie, identity, app config.

One row per Clerk user in `public.user_identities`. The service key never
reaches the browser; every read/write goes through the Python server.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import requests

from tuton import config

TABLE = "user_identities"
_IDENTITAS = ("nama", "nim", "semester", "ut_daerah", "prodi")

# Supabase mem-pause project gratis setelah 7 hari tanpa aktivitas. 6 jam
# memberi ruang dua kali lipat lebih dari cukup.
INTERVAL_KEEPALIVE = 6 * 60 * 60
_thread: threading.Thread | None = None


def _headers(prefer: str = "") -> dict[str, str]:
    key = config.SUPABASE_KEY
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def aktif() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_KEY)


def _url() -> str:
    return f"{config.SUPABASE_URL}/rest/v1/{TABLE}"


def _get(user_id: str) -> dict:
    """Baris profil satu user; `{}` kalau belum ada atau Supabase mati.

    Kegagalan jaringan tidak boleh menjatuhkan dashboard: pengguna akan
    melihat pengaturan kosong dan bisa mengisinya ulang.
    """
    if not aktif() or not user_id:
        return {}
    try:
        r = requests.get(
            _url(),
            params={"select": "*", "user_id": f"eq.{user_id}", "limit": "1"},
            headers=_headers(),
            timeout=10,
        )
        if not r.ok:
            return {}
        rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else {}
    except (requests.RequestException, ValueError):
        return {}


def profil_dari_row(row: dict, user_id: str) -> dict:
    """Bentuk profil untuk UI dari satu baris Supabase."""
    cookie = str(row.get("cookie_moodle") or "")
    return {
        "user_id": user_id,
        "email": str(row.get("email") or ""),
        "nama_akun": str(row.get("name") or ""),
        "identitas": {k: str(row.get(k) or "") for k in _IDENTITAS},
        "cookie_ada": bool(cookie),
        "cookie_ujung": cookie[-4:] if cookie else "",
        "diperbarui": row.get("updated_at"),
    }


def profil(user_id: str) -> dict:
    """Profil siap dipakai UI: identitas, cookie tersamar, status isian."""
    return profil_dari_row(_get(user_id), user_id)


def scope_dari_row(row: dict, user_id: str) -> dict:
    return {
        "user_id": user_id,
        "cookie_moodle": str(row.get("cookie_moodle") or ""),
        "identitas": {k: str(row.get(k) or "") for k in _IDENTITAS},
    }



def simpan(user_id: str, user: dict, payload: dict) -> None:
    """Tulis identitas dan/atau cookie. Field yang tidak dikirim tidak diubah.

    `cookie_moodle` berupa string kosong sengaja berarti "hapus", sedangkan
    field yang tidak ada di payload dibiarkan apa adanya -- UI mengirim semua
    kolom identitas setiap kali menyimpan, tapi cookie hanya dikirim kalau
    pengguna benar-benar mengetik yang baru.
    """
    if not aktif() or not user_id:
        raise ValueError("Supabase belum dikonfigurasi (SUPABASE_URL / SUPABASE_SERVICE_KEY).")

    row: dict = {"user_id": user_id, "updated_at": datetime.now(timezone.utc).isoformat()}
    email = (user.get("email") or "").strip()
    nama = (user.get("name") or email or user_id).strip()
    row["email"] = email
    row["name"] = nama

    ident = payload.get("identitas")
    if isinstance(ident, dict):
        for k in _IDENTITAS:
            if k in ident:
                row[k] = str(ident.get(k) or "").strip()

    if "cookie_moodle" in payload:
        row["cookie_moodle"] = _bersih_cookie(str(payload.get("cookie_moodle") or ""))

    r = requests.post(
        _url(),
        params={"on_conflict": "user_id"},
        headers=_headers("resolution=merge-duplicates,return=minimal"),
        json=row,
        timeout=15,
    )
    if not r.ok:
        raise ValueError(f"Supabase menolak penyimpanan ({r.status_code}): {r.text[:200]}")


def _bersih_cookie(nilai: str) -> str:
    """Buang spasi/newline; terima bentuk `Nama=Nilai` maupun nilai saja."""
    return nilai.replace("\r", "").replace("\n", "").strip()


# ------------------------------------------------------------------ keepalive

_TERAKHIR: dict[str, float] = {}


def sentuh() -> None:
    """Aktivitas ringan supaya project Supabase tidak di-pause (7 hari idle).

    Yang dihitung Supabase sebagai aktivitas adalah request API apa pun. Query
    `select id` pada tabel kecil jauh lebih meyakinkan daripada membuka REST
    root (yang hanya membaca cache skema), dan biayanya satu baris. Kalau
    migration belum dijalankan, jatuh ke REST root supaya keepalive tetap
    berjalan.
    """
    if not aktif():
        return
    _TERAKHIR["waktu"] = time.time()
    for url, params in (
        (f"{config.SUPABASE_URL}/rest/v1/tuton_keepalive", {"select": "id", "limit": "1"}),
        (f"{config.SUPABASE_URL}/rest/v1/", None),
    ):
        try:
            r = requests.get(url, params=params, headers=_headers(), timeout=15)
            if r.status_code < 400 or url.endswith("/rest/v1/"):
                return
        except requests.RequestException:
            continue


def status_keepalive() -> dict:
    terakhir = _TERAKHIR.get("waktu")
    return {
        "aktif": _thread is not None and _thread.is_alive(),
        "interval_detik": INTERVAL_KEEPALIVE,
        "terakhir": terakhir,
        "umur_detik": (time.time() - terakhir) if terakhir else None,
    }


def _loop(interval: int) -> None:
    """Keepalive berjalan seumur proses; tidak perlu berhenti rapi.

    Interval 6 jam membuat project tetap aktif walau container jarang
    dipakai, dan tetap di bawah batas pause 7 hari kalau ada satu-dua
    jadwal yang terlewat karena container sedang restart.
    """
    while True:
        sentuh()
        time.sleep(interval)


def mulai_keepalive(interval: int = INTERVAL_KEEPALIVE) -> None:
    global _thread
    if _thread is not None or not aktif():
        return
    _thread = threading.Thread(target=_loop, args=(interval,), name="supabase-keepalive", daemon=True)
    _thread.start()
