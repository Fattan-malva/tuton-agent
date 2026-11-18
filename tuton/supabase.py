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
from tuton import crypto

TABLE = "user_identities"
PROVIDER_TABLE = "user_providers"
RESULT_TABLE = "user_results"
TEMPLATE_TABLE = "user_templates"
SKILL_TABLE = "user_skills"
STORAGE_BUCKET = config.SUPABASE_BUCKET_RESULTS
_IDENTITAS = ("nama", "nim", "semester", "ut_daerah", "prodi")

# Supabase mem-pause project gratis setelah 7 hari tanpa aktivitas. 6 jam
# memberi ruang dua kali lipat lebih dari cukup.
INTERVAL_KEEPALIVE = 6 * 60 * 60
_thread: threading.Thread | None = None


def _headers(prefer: str = "", *, upsert: bool = False) -> dict[str, str]:
    key = config.SUPABASE_KEY
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    if upsert:
        # Storage menolak unggahan ulang tanpa header ini; dipakai supaya
        # menjalankan ulang satu sesi menimpa berkas yang sama, bukan gagal.
        h["x-upsert"] = "true"
    return h


def aktif() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_KEY)


def _url(table: str = TABLE) -> str:
    return f"{config.SUPABASE_URL}/rest/v1/{table}"


def _storage_url(path: str = "", *, authenticated: bool = False) -> str:
    """URL objek Storage. `authenticated` dipakai untuk unduh bucket privat."""
    bagian = "object/authenticated" if authenticated else "object"
    dasar = f"{config.SUPABASE_URL}/storage/v1/{bagian}/{STORAGE_BUCKET}"
    return f"{dasar}/{path}" if path else dasar


def _get(user_id: str) -> dict:
    """Baris profil satu user; `{}` kalau belum ada atau Supabase mati.

    Kegagalan jaringan tidak boleh menjatuhkan dashboard: pengguna akan
    melihat pengaturan kosong dan bisa mengisinya ulang. Cookie pada baris
    hasil dibuka di sini (di memori saja) dan baris plaintext lama dienkripsi
    ulang sekali, supaya kredensial tidak pernah tersimpan apa adanya.
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
        row = rows[0] if isinstance(rows, list) and rows else {}
    except (requests.RequestException, ValueError):
        return {}
    if not row:
        return {}
    mentah = str(row.get("cookie_moodle") or "")
    if mentah and not crypto.terenkripsi(mentah):
        # Data sebelum enkripsi diaktifkan: pakai sekali ini, lalu simpan
        # dalam bentuk terenkripsi supaya tidak tertinggal plaintext.
        if crypto.tersedia():
            try:
                _patch(user_id, {"cookie_moodle": crypto.enkripsi(mentah)})
            except (ValueError, requests.RequestException):
                pass
        # Pemanggil selalu menerima nilai siap pakai, bukan ciphertext.
        row["cookie_moodle"] = mentah
    else:
        row["cookie_moodle"] = crypto.dekripsi(mentah)
    return row


def _patch(user_id: str, values: dict) -> None:
    """Ubah sebagian kolom satu baris profil (tanpa upsert)."""
    r = requests.patch(
        _url(),
        params={"user_id": f"eq.{user_id}"},
        headers=_headers("return=minimal"),
        json=values,
        timeout=15,
    )
    if not r.ok:
        raise ValueError(f"Supabase menolak pembaruan ({r.status_code}): {r.text[:200]}")


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
        # Provider ikut di-scope supaya pipeline/agent runner di thread job
        # memakai kredensial pemilik job, bukan berkas bersama atau akun lain.
        "provider_data": providers_data(user_id),
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
        # Kosong berarti "hapus". Nilai disimpan terenkripsi, jadi database
        # tidak pernah memuat kredensial Moodle yang bisa langsung dipakai.
        bersih = _bersih_cookie(str(payload.get("cookie_moodle") or ""))
        row["cookie_moodle"] = crypto.enkripsi(bersih) if bersih else ""

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


# ------------------------------------------------------------------ providers
#
# Provider (base URL + API key + daftar model) dan pilihan model per agent
# adalah milik tiap akun, bukan mesin: satu akun bisa memakai kredensialnya
# sendiri tanpa melihat atau memakai API key akun lain. Semuanya di tabel
# `user_providers` (satu baris per user, JSONB), sehingga tidak ada lagi
# berkas `runtime/runtime.json` bersama untuk request web.
#
# Jalur CLI tetap memakai `runtime_config` (berkas) supaya `python main.py`
# bisa jalan tanpa login. Migrasi awal dari berkas ke akun yang sedang login
# dikerjakan `runtime_config.migrasi_ke_user()`, dipanggil endpoint provider.

_PROVIDER_KOSONG = {"providers": [], "agents": {}}
# Profil/provider dibaca pada setiap request (identitas pemanggil harus
# segar), tetapi satu halaman memanggil 4-6 endpoint sekaligus. Cache pendek
# ini mencegah 6 round-trip ke Supabase untuk data yang sama; penyimpanan
# provider selalu membuang entrinya sehingga perubahan langsung terlihat.
_PROVIDER_CACHE: dict[str, tuple[float, dict]] = {}
_PROVIDER_TTL = 20.0
_PROVIDER_LOCK = threading.Lock()


def template_list(user_id: str) -> list[dict]:
    if not aktif() or not user_id:
        return []
    try:
        r = requests.get(_url(TEMPLATE_TABLE), params={"select": "id,name,description", "user_id": f"eq.{user_id}", "order": "updated_at.desc"}, headers=_headers(), timeout=10)
        return r.json() if r.ok and isinstance(r.json(), list) else []
    except requests.RequestException:
        return []


def template_default(user_id: str) -> str:
    """ID template default akun, disimpan di profil (boleh template bawaan)."""
    if not aktif() or not user_id:
        return ""
    try:
        r = requests.get(_url(), params={"select": "template_default", "user_id": f"eq.{user_id}", "limit": "1"}, headers=_headers(), timeout=10)
        rows = r.json() if r.ok else []
        return str(rows[0].get("template_default") or "") if rows else ""
    except (requests.RequestException, ValueError):
        return ""


def template_set_default(user_id: str, template_id: str) -> None:
    """Simpan pilihan default tanpa menyentuh isi template-nya."""
    if not aktif() or not user_id:
        raise ValueError("Supabase belum dikonfigurasi.")
    r = requests.post(
        _url(),
        params={"on_conflict": "user_id"},
        headers=_headers("resolution=merge-duplicates,return=minimal"),
        json={"user_id": user_id, "template_default": template_id},
        timeout=15,
    )
    if not r.ok:
        raise ValueError(f"Supabase menolak pembaruan ({r.status_code}): {r.text[:200]}")


def template_get(user_id: str, template_id: str) -> dict | None:
    if not aktif() or not user_id:
        return None
    try:
        r = requests.get(_url(TEMPLATE_TABLE), params={"select": "id,name,description,schema", "user_id": f"eq.{user_id}", "id": f"eq.{template_id}", "limit": "1"}, headers=_headers(), timeout=10)
        rows = r.json() if r.ok and isinstance(r.json(), list) else []
        return rows[0] if rows else None
    except requests.RequestException:
        return None


def template_save(user_id: str, template: dict) -> None:
    if not aktif() or not user_id:
        return
    values = {"user_id": user_id, "id": str(template.get("id", "")), "name": str(template.get("name", "")), "description": str(template.get("description", "")), "schema": template.get("schema", {})}
    requests.post(_url(TEMPLATE_TABLE), json=values, headers=_headers("resolution=merge-duplicates"), timeout=10).raise_for_status()


def skill_list(user_id: str) -> list[dict]:
    """Salinan skill milik akun (menimpa bawaan dengan nama yang sama)."""
    if not aktif() or not user_id:
        return []
    try:
        r = requests.get(
            _url(SKILL_TABLE),
            params={"select": "name,content,updated_at", "user_id": f"eq.{user_id}"},
            headers=_headers(),
            timeout=10,
        )
        rows = r.json() if r.ok else []
        return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
    except (requests.RequestException, ValueError):
        return []


def skill_get(user_id: str, nama: str) -> dict | None:
    if not aktif() or not user_id:
        return None
    try:
        r = requests.get(
            _url(SKILL_TABLE),
            params={"select": "name,content", "user_id": f"eq.{user_id}",
                    "name": f"eq.{nama}", "limit": "1"},
            headers=_headers(),
            timeout=10,
        )
        rows = r.json() if r.ok else []
        return rows[0] if isinstance(rows, list) and rows else None
    except (requests.RequestException, ValueError):
        return None


def skill_save(user_id: str, nama: str, content: str) -> None:
    if not aktif() or not user_id:
        raise ValueError("Supabase belum dikonfigurasi.")
    r = requests.post(
        _url(SKILL_TABLE),
        params={"on_conflict": "user_id,name"},
        headers=_headers("resolution=merge-duplicates,return=minimal"),
        json={"user_id": user_id, "name": nama, "content": content},
        timeout=15,
    )
    if not r.ok:
        raise ValueError(f"Supabase menolak penyimpanan skill ({r.status_code}): {r.text[:200]}")


def skill_delete(user_id: str, nama: str) -> None:
    if not aktif() or not user_id:
        return
    r = requests.delete(
        _url(SKILL_TABLE),
        params={"user_id": f"eq.{user_id}", "name": f"eq.{nama}"},
        headers=_headers("return=minimal"),
        timeout=15,
    )
    if not r.ok:
        raise ValueError(f"Supabase menolak hapus skill ({r.status_code}): {r.text[:200]}")


def skill_default(user_id: str) -> str:
    if not aktif() or not user_id:
        return ""
    try:
        r = requests.get(
            _url(),
            params={"select": "skill_default", "user_id": f"eq.{user_id}", "limit": "1"},
            headers=_headers(),
            timeout=10,
        )
        rows = r.json() if r.ok else []
        return str(rows[0].get("skill_default") or "") if rows else ""
    except (requests.RequestException, ValueError):
        return ""


def skill_set_default(user_id: str, nama: str) -> None:
    if not aktif() or not user_id:
        raise ValueError("Supabase belum dikonfigurasi.")
    r = requests.post(
        _url(),
        params={"on_conflict": "user_id"},
        headers=_headers("resolution=merge-duplicates,return=minimal"),
        json={"user_id": user_id, "skill_default": nama},
        timeout=15,
    )
    if not r.ok:
        raise ValueError(f"Supabase menolak pembaruan ({r.status_code}): {r.text[:200]}")


def providers_data(user_id: str, wajib: bool = False) -> dict:
    """Provider + model agent milik satu user, bentuknya sama dengan runtime lama.

    `wajib=True` melempar `ValueError` kalau sumbernya tidak terbaca. Itu
    dipakai endpoint yang menulis ulang seluruh dokumen: menyimpan hasil
    pembacaan kosong karena gangguan jaringan akan menghapus provider.
    """
    if not aktif() or not user_id:
        if wajib:
            raise ValueError("Supabase belum dikonfigurasi.")
        return dict(_PROVIDER_KOSONG)
    with _PROVIDER_LOCK:
        entri = _PROVIDER_CACHE.get(user_id)
        if entri and time.monotonic() - entri[0] < _PROVIDER_TTL:
            return entri[1]
    data = dict(_PROVIDER_KOSONG)
    try:
        r = requests.get(
            _url(PROVIDER_TABLE),
            params={"select": "providers,agents", "user_id": f"eq.{user_id}", "limit": "1"},
            headers=_headers(),
            timeout=10,
        )
        if not r.ok:
            raise ValueError(f"Supabase menolak pembacaan provider ({r.status_code}).")
        rows = r.json()
        row = rows[0] if isinstance(rows, list) and rows else {}
        providers = row.get("providers")
        agents = row.get("agents")
        if isinstance(providers, list):
            data["providers"] = [p for p in providers if isinstance(p, dict)]
        if isinstance(agents, dict):
            data["agents"] = agents
    except (requests.RequestException, ValueError) as exc:
        # Jaringan bermasalah: jangan simpan di cache supaya percobaan
        # berikutnya tetap menembak Supabase.
        if wajib:
            raise ValueError(f"Provider tidak bisa dibaca dari Supabase: {exc}") from exc
        return dict(_PROVIDER_KOSONG)
    with _PROVIDER_LOCK:
        _PROVIDER_CACHE[user_id] = (time.monotonic(), data)
    return data


def providers_lupakan(user_id: str) -> None:
    with _PROVIDER_LOCK:
        _PROVIDER_CACHE.pop(user_id, None)


def providers_simpan(user_id: str, data: dict) -> None:
    """Tulis seluruh daftar provider + model agent milik satu user."""
    if not aktif() or not user_id:
        raise ValueError("Supabase belum dikonfigurasi, provider tidak bisa disimpan.")
    row = {
        "user_id": user_id,
        "providers": [p for p in (data.get("providers") or []) if isinstance(p, dict)],
        "agents": dict(data.get("agents") or {}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = requests.post(
        _url(PROVIDER_TABLE),
        params={"on_conflict": "user_id"},
        headers=_headers("resolution=merge-duplicates,return=minimal"),
        json=row,
        timeout=15,
    )
    if not r.ok:
        raise ValueError(
            f"Supabase menolak penyimpanan provider ({r.status_code}): {r.text[:200]}"
        )
    providers_lupakan(user_id)


# ------------------------------------------------------------------ results


def _result_path(user_id: str, slug: str, sesi: str, nama: str) -> str:
    parts = [str(user_id), str(slug), str(sesi), str(nama)]
    if any(not p or p in {".", ".."} or "/" in p or "\\" in p for p in parts):
        raise ValueError("Path hasil tidak sah.")
    return "/".join(parts)


def result_upload(user_id: str, slug: str, sesi: str, nama: str, content: bytes) -> dict:
    """Unggah DOCX ke bucket privat, lalu simpan metadata.

    Metadata (`user_results`) adalah sumber kebenaran daftar hasil: objek di
    Storage tidak bisa di-query berdasarkan prefix tanpa kunci service, jadi
    baris inilah yang dibaca tab Result dan yang menentukan unduhan sah.
    """
    if not aktif() or not user_id:
        raise ValueError("Supabase belum dikonfigurasi.")
    path = _result_path(user_id, slug, sesi, nama)
    r = requests.post(
        _storage_url(path),
        headers={
            **_headers(upsert=True),
            "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
        data=content,
        timeout=60,
    )
    if not r.ok:
        raise ValueError(f"Unggah hasil gagal ({r.status_code}): {r.text[:200]}")
    row = {
        "user_id": user_id,
        "slug": slug,
        "sesi": sesi,
        "nama": nama,
        "storage_path": path,
        "ukuran": len(content),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = requests.post(
        _url(RESULT_TABLE),
        params={"on_conflict": "user_id,storage_path"},
        headers=_headers("resolution=merge-duplicates,return=minimal"),
        json=row,
        timeout=15,
    )
    if not r.ok:
        raise ValueError(f"Metadata hasil gagal ({r.status_code}): {r.text[:200]}")
    return row


def result_list(user_id: str) -> list[dict]:
    """Metadata hasil satu akun, terbaru dulu; `[]` kalau tabel belum ada."""
    if not aktif() or not user_id:
        return []
    try:
        r = requests.get(
            _url(RESULT_TABLE),
            params={
                "select": "slug,sesi,nama,ukuran,updated_at,storage_path",
                "user_id": f"eq.{user_id}",
                "order": "updated_at.desc",
            },
            headers=_headers(),
            timeout=15,
        )
        if not r.ok:
            return []
        rows = r.json()
        return rows if isinstance(rows, list) else []
    except (requests.RequestException, ValueError):
        return []


def result_download(user_id: str, storage_path: str) -> bytes | None:
    """Unduh objek bucket privat. Path harus milik `user_id` yang meminta."""
    if not storage_path.startswith(str(user_id) + "/"):
        return None
    try:
        r = requests.get(
            _storage_url(storage_path, authenticated=True),
            headers=_headers(),
            timeout=60,
        )
        return r.content if r.ok else None
    except requests.RequestException:
        return None


def _result_rows(params: dict[str, str]) -> list[dict]:
    """Semua baris yang cocok, halaman demi halaman sampai kosong."""
    rows = []
    while True:
        r = requests.get(
            _url(RESULT_TABLE),
            params={"select": "user_id,slug,sesi,nama,storage_path", **params,
                    "order": "storage_path.asc", "limit": "1000", "offset": str(len(rows))},
            headers=_headers(),
            timeout=15,
        )
        if not r.ok:
            raise ValueError(f"Supabase menolak pembacaan hasil ({r.status_code}): {r.text[:200]}")
        page = r.json()
        if not isinstance(page, list):
            raise ValueError("Supabase mengembalikan metadata hasil tidak sah.")
        if not page:
            return rows
        rows.extend(page)


def _result_filter(user_id: str, slug: str, sesi: str = "", nama: str = "") -> dict[str, str]:
    params = {"user_id": f"eq.{user_id}", "slug": f"eq.{slug}"}
    if sesi:
        params["sesi"] = f"eq.{sesi}"
    if nama:
        params["nama"] = f"eq.{nama}"
    return params


def _result_storage_paths(prefix: str) -> set[str]:
    """List objek di bawah prefix secara rekursif; dibutuhkan untuk objek yatim."""
    paths = set()
    pending = [prefix]
    while pending:
        folder = pending.pop()
        offset = 0
        while True:
            r = requests.post(
                f"{config.SUPABASE_URL}/storage/v1/object/list/{STORAGE_BUCKET}",
                headers=_headers(),
                json={"prefix": folder, "limit": 1000, "offset": offset},
                timeout=30,
            )
            if not r.ok:
                raise ValueError(f"Supabase menolak pembacaan objek hasil ({r.status_code}): {r.text[:200]}")
            page = r.json()
            if not isinstance(page, list):
                raise ValueError("Supabase mengembalikan daftar objek hasil tidak sah.")
            for item in page:
                name = item.get("name") if isinstance(item, dict) else None
                if not isinstance(name, str) or not name or name in {".", ".."} or "/" in name or "\\" in name:
                    raise ValueError("Supabase mengembalikan path objek hasil tidak sah.")
                path = f"{folder}/{name}"
                if item.get("id") is None:
                    pending.append(path)
                else:
                    paths.add(path)
            if not page:
                break
            offset += len(page)
    return paths


def result_exists(user_id: str, slug: str, sesi: str, nama: str) -> bool:
    """Cek metadata remote persis; gangguan Supabase tidak boleh terlihat sebagai ketiadaan."""
    if not aktif() or not user_id:
        raise ValueError("Supabase belum dikonfigurasi.")
    _result_path(user_id, slug, sesi, nama)
    rows = _result_rows(_result_filter(user_id, slug, sesi, nama))
    return any(
        row.get("user_id") == user_id and row.get("slug") == slug
        and row.get("sesi") == sesi and row.get("nama") == nama
        for row in rows
    )


def result_delete(user_id: str, slug: str, sesi: str = "", nama: str = "") -> None:
    """Hapus metadata dan objek terdaftar maupun yatim, hanya dalam scope ini."""
    if not aktif() or not user_id:
        return
    if not slug or any(p in {".", ".."} or "/" in p or "\\" in p for p in (user_id, slug, sesi, nama)):
        raise ValueError("Path hasil tidak sah.")
    params = _result_filter(user_id, slug, sesi, nama)
    rows = _result_rows(params)
    prefix = f"{user_id}/{slug}"
    paths = _result_storage_paths(prefix)
    paths.update(
        path for row in rows
        if isinstance((path := row.get("storage_path")), str)
        and path.startswith(prefix + "/")
    )
    # shortcut: hanya objek berkedalaman layout hasil (4 bagian); objek asing
    # lebih dalam dibiarkan, upgrade kalau layout pernah berubah.
    paths = {
        path for path in paths
        if len(pp := path.split("/")) == 4
        and pp[:2] == [user_id, slug]
        and (not sesi or pp[2] == sesi)
        and (not nama or pp[3] == nama)
    }
    if paths:
        r = requests.delete(
            f"{config.SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}",
            headers=_headers(),
            json={"prefixes": sorted(paths)},
            timeout=30,
        )
        if not r.ok:
            raise ValueError(f"Supabase menolak hapus objek hasil ({r.status_code}): {r.text[:200]}")
    r = requests.delete(_url(RESULT_TABLE), params=params, headers=_headers(), timeout=15)
    if not r.ok:
        raise ValueError(f"Supabase menolak hapus metadata ({r.status_code}): {r.text[:200]}")


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
