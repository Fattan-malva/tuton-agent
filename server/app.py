"""Server web lokal untuk pipeline tutor UT (murni standard library).

Menyajikan UI statis, API JSON, streaming log lewat Server-Sent Events (SSE),
dan unggah berkas multipart untuk mode input manual. Tidak ada dependency
baru: hanya modul `http.server` bawaan Python.

Jalankan:

    py server/app.py            # Windows
    python server/app.py        # Linux

Lalu buka http://127.0.0.1:8000 (atau WEB_PORT di .env).
"""

from __future__ import annotations

import errno
import json
import mimetypes
import os
import platform
import re
import shutil
import signal
import sys
import tempfile
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Pastikan modul root (pipeline, config, ...) bisa diimpor.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import contextvars  # noqa: E402

import requests  # noqa: E402

from tuton import config  # noqa: E402
from tuton import clerk  # noqa: E402
from tuton import supabase  # noqa: E402
from tuton import templates  # noqa: E402
import docxprev  # noqa: E402
from server.jobs import JobManager  # noqa: E402
from tuton import courses  # noqa: E402
from tuton import moodle  # noqa: E402
from tuton import openai_client  # noqa: E402
from tuton import runtime_config  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
# Saat pengembangan, `server/static` belum tentu ada (hasil build Next.js
# di-copy ke sana hanya ketika image Docker dibuat). Pakai `frontend/out` langsung
# supaya `python server/app.py` tetap bisa dipakai tanpa langkah copy.
if not (STATIC_DIR / "index.html").is_file():
    STATIC_DIR = ROOT / "frontend" / "out"
MANAGER = JobManager()
# Cache Moodle. Semua cache di bawah dikunci per user: satu akun bisa punya
# cookie valid sementara akun lain sudah kedaluwarsa, dan daftar course/nilai
# berbeda antar akun. Nilai tuple (waktu, ttl_detik, data); TTL sukses panjang,
# TTL gagal pendek supaya cookie baru yang disimpan lewat Pengaturan langsung
# terbaca.
_MOODLE_STATUS_CACHE: dict[str, tuple[float, float, dict]] = {}
_MOODLE_STATUS_LOCK = threading.Lock()
_NILAI_CACHE: dict[str, tuple[float, float, dict]] = {}
_NILAI_LOCK = threading.Lock()
_JADWAL_CACHE: dict[tuple[str, str], tuple[float, float, dict]] = {}
_JADWAL_LOCK = threading.Lock()
_TTL_OK = 600.0
_TTL_GAGAL = 30.0

# Sesi per course. Membaca satu course berarti satu request per section, jadi
# hasilnya disimpan sebentar di memori; itu yang membuat pindah-pindah pilihan
# mata kuliah terasa langsung.
#
# Ini BUKAN cache "percaya saja": daftar sesi berubah saat dosen membuka sesi
# baru, jadi UI punya tombol segarkan yang memanggil endpoint dengan
# `?paksa=1` dan melewati cache ini sepenuhnya. Tanpa jalan keluar itu, sesi
# baru bisa tersembunyi sampai TTL habis dan pengguna tidak punya cara
# memunculkannya.
_SESI_CACHE: dict[str, tuple[float, float, list[dict]]] = {}
_SESI_LOCK = threading.Lock()
_TTL_SESI = 120.0


def _sesi_course(cid: str, paksa: bool = False) -> list[dict]:
    """Sesi yang punya soal untuk course akun aktif, dengan cache singkat."""
    kunci = f"{config.current_user()}:{cid}"
    with _SESI_LOCK:
        now = time.monotonic()
        entri = _SESI_CACHE.get(kunci)
        if not paksa and entri and now - entri[0] < entri[1]:
            return entri[2]
    hasil = MANAGER.sessions(cid)
    with _SESI_LOCK:
        _SESI_CACHE[kunci] = (time.monotonic(), _TTL_SESI, hasil)
    return hasil


def _sesi_semua(paksa: bool = False) -> list[dict]:
    """Sesi lintas semua course akun aktif, dengan cache singkat yang sama."""
    kunci = f"{config.current_user()}:*"
    with _SESI_LOCK:
        now = time.monotonic()
        entri = _SESI_CACHE.get(kunci)
        if not paksa and entri and now - entri[0] < _TTL_SESI:
            return entri[2]
    hasil = MANAGER.semua_sesi()
    with _SESI_LOCK:
        _SESI_CACHE[kunci] = (time.monotonic(), _TTL_SESI, hasil)
    return hasil


def _moodle_login() -> dict:
    """Status cookie Moodle akun yang sedang memanggil.

    Cookie dibaca ulang dari Supabase untuk tiap pengecekan (bukan dari
    `.env` bersama), karena tiap akun punya sesi Moodle sendiri.
    """
    user_id = config.current_user()
    with _MOODLE_STATUS_LOCK:
        now = time.monotonic()
        entri = _MOODLE_STATUS_CACHE.get(user_id)
        if entri:
            waktu, ttl, data = entri
            if now - waktu < ttl:
                return dict(data)
        try:
            klien = moodle.Moodle()
            masuk, pesan = klien.cek_login()
            result = {"masuk": masuk, "pesan": pesan}
        except Exception as exc:  # noqa: BLE001
            result = {"masuk": False, "pesan": str(exc)}
        # Cookie mati di-cache sebentar saja (20 detik) supaya perbaikan
        # cookie lewat Pengaturan langsung terasa di halaman berikutnya.
        _MOODLE_STATUS_CACHE[user_id] = (now, 60.0 if result["masuk"] else 20.0, result)
        return dict(result)


def _paksa(query: dict) -> bool:
    """True kalau klien minta melewati cache (`?paksa=1`)."""
    nilai = query.get("paksa")
    if isinstance(nilai, list):
        nilai = nilai[0] if nilai else ""
    return str(nilai or "").strip().lower() in {"1", "true", "ya", "yes"}


def _moodle_masuk() -> str | None:
    """Pagar cookie: kembalikan pesan error kalau cookie Moodle tidak valid.

    Dipakai endpoint yang menyajikan data Moodle (courses, sesi, jadwal,
    nilai). Tanpa pagar ini, cache memori/disk bisa menyajikan daftar lama
    selama cookie sudah mati sehingga select matkul terlihat "hidup" padahal
    sesi sudah ditolak server.
    """
    status = _moodle_login()
    if status.get("masuk"):
        return None
    return status.get("pesan") or "Cookie Moodle tidak valid."


def _nilai_semua() -> dict:
    """Nilai Tugas & Diskusi semua matkul milik akun yang memanggil.

    Sukses di-cache 10 menit; hasil error cuma 30 detik supaya setelah cookie
    diganti nilai langsung bisa ditarik lagi tanpa menunggu cache lama.
    """
    user_id = config.current_user()
    with _NILAI_LOCK:
        now = time.monotonic()
        entri = _NILAI_CACHE.get(user_id)
        if entri:
            waktu, ttl, data = entri
            if now - waktu < ttl:
                return data
        galat = _moodle_masuk()
        if galat:
            hasil = {"courses": [], "sesi": [], "error": galat}
        else:
            try:
                klien = moodle.Moodle()
                daftar = courses.daftar_mata_kuliah(klien)
                courses_out: list[dict] = []
                sesi_semua: set[int] = set()
                for mk in daftar:
                    per_sesi = courses.nilai_mata_kuliah(klien, mk.id)
                    if not per_sesi:
                        continue
                    sesi_semua.update(per_sesi.keys())
                    courses_out.append(
                        {
                            "id": mk.id,
                            "nama": mk.nama,
                            "nilai_total": courses.nilai_total_mata_kuliah(klien, mk.id),
                            "titik": [
                                {"sesi": s, **per_sesi[s]} for s in sorted(per_sesi)
                            ],
                        }
                    )
                hasil = {"courses": courses_out, "sesi": sorted(sesi_semua)}
            except Exception as exc:  # noqa: BLE001
                hasil = {"courses": [], "sesi": [], "error": str(exc)}
        _NILAI_CACHE[user_id] = (now, _TTL_OK if not hasil.get("error") else _TTL_GAGAL, hasil)
        return hasil


def _nilai_total(cid: str) -> dict:
    """Nilai total satu course untuk kartu detail Courses."""
    galat = _moodle_masuk()
    if galat:
        return {"nilai_total": None, "error": galat}
    try:
        klien = moodle.Moodle()
        return {"nilai_total": courses.nilai_total_mata_kuliah(klien, cid)}
    except Exception as exc:  # noqa: BLE001
        return {"nilai_total": None, "error": str(exc)}


def _jadwal(cid: str) -> dict:
    """Jadwal Diskusi & Tugas satu course, di-cache 10 menit.

    Mengambil tanggal `Opened:`/`Due:` dari tiap halaman activity -- bisa
    belasan request saat pertama kali, jadi hasilnya disimpan di memori
    dan halamannya sendiri sudah ikut tercache oleh klien Moodle.

    NIM diambil dari profil Supabase akun yang login (bukan `.env`), karena
    status Diskusi hanya sah bila dicocokkan dengan post forum milik NIM
    pemilik akun. Bila belum diisi, item Diskusi ditandai `nim_required`.
    """
    kunci = (config.current_user(), cid)
    with _JADWAL_LOCK:
        now = time.monotonic()
        entri = _JADWAL_CACHE.get(kunci)
        if entri and now - entri[0] < entri[1]:
            return entri[2]
        try:
            klien = moodle.Moodle()
            profil = supabase.profil(config.current_user())
            nim = str((profil.get("identitas") or {}).get("nim") or "").strip()
            # Langsung ke course yang diminta: mencari lewat daftar seluruh
            # course berarti membuka /my/ lalu setiap halaman course hanya
            # untuk menemukan satu id, dan itu yang membuat kartu ini lambat.
            matkul = courses.mata_kuliah_dari_id(klien, cid)
            hasil = {
                "items": courses.jadwal_mata_kuliah(klien, matkul, nim=nim),
                "nim_ada": bool(nim),
            }
        except Exception as exc:  # noqa: BLE001
            hasil = {"items": [], "error": str(exc)}
        ttl = _TTL_OK if not hasil.get("error") else _TTL_GAGAL
        _JADWAL_CACHE[kunci] = (now, ttl, hasil)
        return hasil


# ----------------------------------------------------------- multipart


def _parse_multipart(body: bytes, boundary: str) -> list[tuple[str, str | None, bytes]]:
    """Parse body multipart jadi list (nama, nama_berkas?, isi)."""
    delim = b"--" + boundary.encode()
    out: list[tuple[str, str | None, bytes]] = []
    for bagian in body.split(delim):
        if bagian in (b"", b"--", b"--\r\n"):
            continue
        if bagian.startswith(b"--"):  # penutup stream
            continue
        if bagian.startswith(b"\r\n"):
            bagian = bagian[2:]
        if b"\r\n\r\n" not in bagian:
            continue
        head, _, data = bagian.partition(b"\r\n\r\n")
        if data.endswith(b"\r\n"):
            data = data[:-2]
        headers: dict[str, str] = {}
        for baris in head.split(b"\r\n"):
            if b":" in baris:
                k, v = baris.split(b":", 1)
                headers[k.decode().strip().lower()] = v.decode().strip()
        cd = headers.get("content-disposition", "")
        nama = re.search(r'name="([^"]*)"', cd)
        berkas = re.search(r'filename="([^"]*)"', cd)
        out.append(
            (
                nama.group(1) if nama else "",
                berkas.group(1) if berkas else None,
                data,
            )
        )
    return out


# ------------------------------------------------------------- helpers


def _results_list() -> list[dict]:
    """Daftar DOCX milik akun pemanggil, dari metadata Supabase.

    Sumber kebenaran hasil sekarang Storage + tabel `user_results`, bukan
    folder `output/` di disk: job bisa jalan di mesin lain, dan berkas hasil
    tidak boleh tercampur antar akun. Bentuk item dipertahankan sama dengan
    versi lama (`slug`, `sesi`, `nama`, `ukuran`, `waktu`) supaya tab Result
    tidak perlu diubah.
    """
    out: list[dict] = []
    for row in supabase.result_list(config.current_user()):
        try:
            waktu = datetime.fromisoformat(
                str(row.get("updated_at") or "").replace("Z", "+00:00")
            ).timestamp()
        except (TypeError, ValueError):
            waktu = 0.0
        out.append(
            {
                "slug": str(row.get("slug") or ""),
                "sesi": str(row.get("sesi") or ""),
                "nama": str(row.get("nama") or ""),
                "ukuran": int(row.get("ukuran") or 0),
                "waktu": waktu,
            }
        )
    return sorted(out, key=lambda x: x["waktu"], reverse=True)


def _hasil_cek_bagian(rel: str) -> list[str]:
    """Pecah path relatif hasil dan tolak yang tidak masuk akal.

    Rute hasil dulu menyentuh disk, jadi path-nya harus ditenturkan. Sekarang
    objeknya ada di Storage dengan path `<user_id>/<slug>/<sesi>/<nama>`;
    pemisahan tetap perlu supaya satu akun tidak bisa menyusun
    `slug/../user_lain/...`.
    """
    bagian = [b for b in rel.replace("\\", "/").split("/") if b not in ("", ".")]
    if not bagian or any(b in {".."} or "/" in b for b in bagian):
        return []
    return bagian


def _hasil_hapus(payload: dict) -> dict:
    """Hapus satu berkas, satu folder sesi, atau seluruh folder mata kuliah.

    Tingkatnya ditentukan isi body: `nama` berarti berkas, tanpa `nama` tapi
    ada `sesi` berarti folder sesi, tanpa keduanya berarti seluruh folder
    mata kuliah beserta semua DOCX-nya. Semua query dibatasi `user_id` akun
    pemanggil, jadi tidak ada cara menyentuh hasil akun lain lewat body.
    """
    slug = str(payload.get("slug") or "")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", slug) or ".." in slug:
        raise ValueError("Nama mata kuliah tidak sah.")

    sesi = str(payload.get("sesi") or "")
    nama = str(payload.get("nama") or "")
    if sesi and not re.fullmatch(r"sesi-\d+", sesi):
        raise ValueError("Nomor sesi tidak sah.")
    if nama and not sesi:
        raise ValueError("Nomor sesi wajib diisi untuk menghapus satu berkas.")

    user_id = config.current_user()
    ada = [
        x for x in supabase.result_list(user_id)
        if x.get("slug") == slug
        and (not sesi or x.get("sesi") == sesi)
        and (not nama or x.get("nama") == nama)
    ]
    if not ada:
        raise ValueError("Hasil tidak ditemukan.")

    supabase.result_delete(user_id, slug, sesi, nama)
    if nama:
        return {"ok": True, "tingkat": "berkas", "path": f"{user_id}/{slug}/{sesi}/{nama}"}
    if sesi:
        return {"ok": True, "tingkat": "sesi", "path": f"{user_id}/{slug}/{sesi}"}
    return {"ok": True, "tingkat": "matkul", "path": f"{user_id}/{slug}"}


def _kirim_json(handler, obj, status: int = 200) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


_TOKEN_CACHE: dict[str, tuple[float, dict]] = {}
_TOKEN_LOCK = threading.Lock()
_TOKEN_TTL = 60.0

# Pengguna Clerk untuk request yang sedang berjalan. Dipakai fungsi yang butuh
# email/nama (upsert Supabase) tanpa harus menerima argumen tambahan dari
# pemanggilnya -- pola yang sama dengan `config._SCOPE`.
_PENGGUNA: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "tuton_pengguna", default=None
)


def _pengguna_sekarang() -> dict:
    return _PENGGUNA.get() or {}


def _scope_args() -> dict:
    """Argumen `config.scope()` dari pengguna yang sedang memanggil."""
    return config.scope_args()


def _bearer(handler) -> str:
    value = handler.headers.get("Authorization", "")
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    # EventSource tidak bisa mengirim header. Hanya endpoint streaming yang
    # memakai jalur ini; token Clerk berumur pendek (~60 detik) sehingga
    # risikonya kecil, tapi jangan dipakai untuk request biasa.
    query = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    path = urllib.parse.urlparse(handler.path).path
    # Unduhan lewat <a>/navigasi browser juga tidak bisa membawa header;
    # token di query hanya diterima di sini, sama seperti EventSource.
    if path.endswith("/stream") or path.startswith("/api/download"):
        return str((query.get("token") or [""])[0]).strip()
    return ""


def _user(handler) -> dict | None:
    """Verifikasi token Clerk. Hasilnya di-cache 60 detik per token.

    Satu halaman memanggil 4-6 endpoint sekaligus. Tanpa cache ini tiap
    endpoint berarti dua round-trip ke Clerk (sesi + user), dan dashboard
    terasa lambat hanya karena masalah autentikasi.

    Profil Supabase ikut diambil di sini dan disimpan pada hasil cache, supaya
    satu request tidak menembak Supabase dua kali (verifikasi token lalu
    pemasangan scope).
    """
    token = _bearer(handler)
    if not token:
        return None
    now = time.monotonic()
    with _TOKEN_LOCK:
        entri = _TOKEN_CACHE.get(token)
        if entri and now - entri[0] < _TOKEN_TTL:
            return entri[1]
    user = clerk.authenticate(token)
    if user:
        row = supabase._get(user["id"])
        if not row:
            # Baris profil dibuat sekali saat login pertama supaya pengguna
            # punya tempat menyimpan identitas. Kegagalan (migration belum
            # dijalankan) tidak boleh menggagalkan request.
            try:
                supabase.simpan(user["id"], user, {})
            except (ValueError, requests.RequestException):
                pass
        user["_row"] = row
        supabase.sentuh()
    with _TOKEN_LOCK:
        if len(_TOKEN_CACHE) > 500:
            _TOKEN_CACHE.clear()
        _TOKEN_CACHE[token] = (now, user)
    return user


def _lupakan_token(handler) -> None:
    """Buang cache token request ini setelah profil diubah.

    Tanpa ini, cookie yang baru disimpan lewat Pengaturan baru dipakai
    setelah TTL cache token habis dan pengguna melihat sesi Moodle lama.
    Cache provider ikut dibuang supaya perubahan dari menu Provider langsung
    terlihat pada request berikutnya, bukan setelah TTL 20 detik.
    """
    token = _bearer(handler)
    with _TOKEN_LOCK:
        entri = _TOKEN_CACHE.pop(token, None)
    user_id = str(((entri[1] if entri else None) or {}).get("id") or "")
    if user_id:
        supabase.providers_lupakan(user_id)


def _pasang_scope(handler) -> dict | None:
    """Pasang identitas pemanggil ke ContextVar (idempoten per request)."""
    token = getattr(handler, "_scope_token", None)
    if token is not None:
        return getattr(handler, "_current_user", None)
    user = _user(handler)
    if not user:
        return None
    args = supabase.scope_dari_row(user.get("_row") or {}, user["id"])
    # Provider lama di `runtime/runtime.json` dipindahkan ke akun ini saat
    # pertama kali terlihat belum punya provider, supaya pipeline yang
    # dijalankan sebelum halaman Provider dibuka tetap punya kredensial.
    if not (args.get("provider_data") or {}).get("providers"):
        if runtime_config.migrasi_ke_user(user["id"]):
            args["provider_data"] = supabase.providers_data(user["id"])
    handler._scope_token = config._SCOPE.set(config.Scope(**args))
    handler._user_token = _PENGGUNA.set(user)
    handler._current_user = user
    return user


def _lepas_scope(handler) -> None:
    """Kembalikan ContextVar ke nilai lama.

    Thread HTTP dipakai ulang untuk request berikutnya. Tanpa reset, request
    tanpa token bisa mewarisi identitas pemanggil sebelumnya dan membaca data
    akun lain.
    """
    token = getattr(handler, "_scope_token", None)
    if token is not None:
        config._SCOPE.reset(token)
        handler._scope_token = None
    token = getattr(handler, "_user_token", None)
    if token is not None:
        _PENGGUNA.reset(token)
        handler._user_token = None
    handler._current_user = None


def _terautentikasi(handler) -> bool:
    return bool(_pasang_scope(handler))


def _butuh_auth(handler) -> bool:
    if _terautentikasi(handler):
        return False
    # Bearer token is intentionally never returned in a cookie or body.
    body = b'{"error":"auth"}'
    handler.send_response(401)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return True


# --------------------------------------------------------- status/agents


def _provider_publik(p: dict) -> dict:
    """Provider untuk klien: API key tidak pernah ikut dikirim utuh."""
    return {
        "id": p.get("id") or "",
        "name": p.get("name") or p.get("id") or "",
        "base_url": p.get("base_url") or "",
        "models": [str(m) for m in (p.get("models") or [])],
        "ada_key": bool(p.get("api_key")),
    }


def _models() -> dict:
    models = runtime_config.semua_model()
    return {
        "models": models,
        "error": "" if models else "Belum ada model. Tambahkan provider di menu Provider.",
    }


def _provider_state() -> dict:
    # `runtime_config` sudah membaca sumber yang tepat untuk konteks ini:
    # baris Supabase akun pemanggil untuk web, berkas untuk CLI. Migrasi
    # berkas lama ke akun terjadi di `_pasang_scope`, jadi di sini data sudah
    # final dan tidak ada round-trip Supabase tambahan.
    return {
        "providers": [_provider_publik(p) for p in runtime_config.providers()],
        "agents": runtime_config.muat()["agents"],
        "models": runtime_config.semua_model(),
        "error": _models()["error"],
    }


def _skills_dir() -> Path:
    return config.SKILLS_DIR


def _skills_list() -> list[dict]:
    out: list[dict] = []
    for path in sorted(_skills_dir().glob("*/SKILL.md")):
        try:
            stat = path.stat()
        except OSError:
            continue
        out.append(
            {
                "name": path.parent.name,
                "ukuran": stat.st_size,
                "waktu": stat.st_mtime,
            }
        )
    return out


def _skill_nama(nilai: str) -> str:
    nama = str(nilai or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", nama):
        raise ValueError("Nama skill hanya huruf kecil, angka, garis, dan garis bawah.")
    return nama


def _panduan_awal(profil: dict) -> bool:
    """True untuk akun baru: identitas dan cookie Moodle belum ada apa apa."""
    ident = profil.get("identitas") or {}
    if profil.get("cookie_ada"):
        return False
    return all(
        not str(ident.get(k) or "").strip()
        for k in ("nama", "nim", "semester", "ut_daerah", "prodi")
    )


def _status() -> dict:
    provider = runtime_config.providers()
    model = runtime_config.semua_model()
    profil = supabase.profil(config.current_user())
    return {
        "providers": f"{len(provider)} provider / {len(model)} model",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "primary_model": config.env("PRIMARY_MODEL") or config.PRIMARY_MODEL,
        "vision_model": config.env("VISION_MODEL") or config.VISION_MODEL,
        "auth_required": True,
        "cookie_ada": bool(profil.get("cookie_ada")),
        "keepalive": supabase.status_keepalive(),
    }


def _agents() -> list[dict]:
    prim = config.env("PRIMARY_MODEL") or config.PRIMARY_MODEL
    vis = config.env("VISION_MODEL") or config.VISION_MODEL
    return [
        {
            "name": nama,
            "model": runtime_config.model_agent(
                nama, vis if nama == config.AGENT_VISION else prim
            ),
        }
        for nama in runtime_config.AGENTS
    ]


# ----------------------------------------------------------- settings


# Kolom identitas di tabel Supabase dipetakan ke nama kunci UI; satu sumber
# tunggal di `tuton.config.IDENTITAS_KEYS` dipakai juga untuk label DOCX.
_IDENTITAS_KOLOM = {k.upper(): k for k in config.IDENTITAS_KEYS}

_KUNCI_EDIT = [
    "URL_MOODLE", "PRIMARY_MODEL", "VISION_MODEL", "FALLBACK_MODELS",
    "WEB_HOST", "WEB_PORT",
] + list(_IDENTITAS_KOLOM)
_KUNCI_RAHASIA = {"COOKIE_MOODLE"}
# Kunci yang memengaruhi koneksi Moodle; kalau salah satunya berubah, semua
# cache yang isinya hasil scrape lama harus dibersihkan sekaligus.
_KUNCI_MOODLE = {"COOKIE_MOODLE", "URL_MOODLE"}


def _reset_cache_moodle() -> int:
    """Bersihkan semua cache turunan cookie Moodle milik user aktif.

    Cakupannya: status login (60 detik), nilai (10 menit), jadwal per course
    (10 menit), daftar sesi per course (2 menit), dan halaman HTML hasil
    scrape di folder `cache/` (TTL 1 jam). Tanpa ini, cookie baru dari menu
    Pengaturan tidak pernah sampai ke halaman lain sampai semua cache
    kedaluwarsa sendiri.
    """
    user_id = config.current_user()
    with _MOODLE_STATUS_LOCK:
        _MOODLE_STATUS_CACHE.pop(user_id, None)
    with _NILAI_LOCK:
        _NILAI_CACHE.pop(user_id, None)
    with _JADWAL_LOCK:
        for kunci in [k for k in _JADWAL_CACHE if k[0] == user_id]:
            _JADWAL_CACHE.pop(kunci, None)
    with _SESI_LOCK:
        prefix = f"{user_id}:"
        for kunci in [k for k in _SESI_CACHE if k.startswith(prefix)]:
            _SESI_CACHE.pop(kunci, None)
    MANAGER.reset_courses_cache()
    jumlah = 0
    try:
        for berkas in Path(config.cache_dir()).glob("*.html"):
            try:
                berkas.unlink()
                jumlah += 1
            except OSError:
                pass
    except OSError:
        pass
    return jumlah


def _settings_get() -> list[dict]:
    profile = supabase.profil(config.current_user())
    ident = profile.get("identitas") or {}
    out: list[dict] = []
    # Moodle session and DOCX identity are per Clerk user; never expose or
    # persist them in the shared `.env`.
    for k in config.IDENTITAS_KEYS:
        out.append(
            {
                "key": k.upper(),
                "value": str(ident.get(k) or ""),
                "rahasia": False,
            }
        )
    out.append({
        "key": "COOKIE_MOODLE",
        "value": "*" * 16 if profile.get("cookie_ada") else "",
        "rahasia": True,
        "ada": bool(profile.get("cookie_ada")),
    })
    # Provider, model per agent, dan API key milik akun ada di menu Provider
    # (Supabase `user_providers`). Nilai di bawah adalah default `.env`
    # bersama: dipakai hanya kalau akun belum memilih model per agent.
    for k in ("PRIMARY_MODEL", "VISION_MODEL", "FALLBACK_MODELS"):
        out.append({"key": k, "value": config.env(k), "rahasia": False})
    return out


def _settings_post(payload: dict) -> dict:
    """Simpan pengaturan: identitas/cookie ke Supabase, model ke .env.

    Cookie dan identitas hanya milik akun pemanggil, jadi tidak pernah
    ditulis ke `.env` bersama -- kalau ditulis, akun berikutnya yang login
    akan memakai sesi Moodle dan NIM orang lain.
    """
    user = _pengguna_sekarang()
    user_id = config.current_user()
    nim_lama = str((supabase.profil(user_id).get("identitas") or {}).get("nim", "")) if user_id else ""
    nim_baru = nim_lama
    identitas: dict[str, str] = {}
    cookie_baru: str | None = None
    berubah = False
    nilai_env: dict[str, str] = {}
    for k, v in payload.items():
        if k in _IDENTITAS_KOLOM:
            identitas[_IDENTITAS_KOLOM[k]] = str(v or "").strip()
            if k == "NIM":
                nim_baru = str(v or "").strip()
            continue
        if k == "COOKIE_MOODLE":
            teks = str(v or "").strip()
            # Kolom rahasia yang dikosongkan berarti "jangan ubah", bukan
            # "hapus". Hapus cookie dilakukan lewat tombol Putuskan Moodle.
            if teks:
                cookie_baru = teks
            continue
        if k not in _KUNCI_EDIT:
            continue
        nilai_env[k] = str(v).strip()

    if nilai_env or cookie_baru or identitas:
        if user_id:
            kirim: dict = {}
            if identitas:
                kirim["identitas"] = identitas
            if cookie_baru:
                kirim["cookie_moodle"] = cookie_baru
            if kirim:
                supabase.simpan(user_id, user, kirim)
    for k, nilai in nilai_env.items():
        config.set_env_value(k, nilai)
        if k == "FALLBACK_MODELS":
            # config sudah dievaluasi saat impor, jadi daftar cadangan perlu
            # dihitung ulang di memori. Tanpa ini perubahan hanya berlaku
            # setelah server di-restart, dan job berikutnya tetap memakai
            # model cadangan yang lama.
            config.FALLBACK_MODELS = [
                m.strip() for m in nilai.split(",") if m.strip()
            ]
        if k in _KUNCI_MOODLE:
            berubah = True
    if cookie_baru:
        berubah = True
    if nim_baru != nim_lama:
        # Status Diskusi bergantung pada NIM; jadwal lama harus dihitung ulang.
        with _JADWAL_LOCK:
            for kunci in [k for k in _JADWAL_CACHE if k[0] == user_id]:
                _JADWAL_CACHE.pop(kunci, None)
    if berubah:
        # Cookie/URL Moodle baru: buang semua hasil scrape lama supaya
        # dashboard, select matkul, nilai, dan jadwal langsung memakai
        # sesi yang baru tanpa perlu restart server.
        dibersihkan = _reset_cache_moodle()
        # Sumber token cache ikut dibuang, supaya cookie yang baru tidak
        # tertunda sampai TTL token habis.
        _lupakan_token(self)
        return {"ok": True, "moodle_disegarkan": True, "cache_dibersihkan": dibersihkan}
    return {"ok": True}


# ----------------------------------------------------- provider / skill


def _daftar_model_payload(payload: dict) -> list[str]:
    models = payload.get("models")
    if isinstance(models, str):
        models = re.split(r"[,\n]+", models)
    if not isinstance(models, list):
        models = []
    return [str(m).strip() for m in models if str(m).strip()]


def _provider_simpan(payload: dict) -> dict:
    data = runtime_config.muat_ubah()
    pid = str(payload.get("id") or "").strip()
    nama = str(payload.get("name") or "").strip()
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    if not nama:
        raise ValueError("Nama provider wajib diisi.")
    if not re.match(r"^https?://", base_url):
        raise ValueError("Base URL harus diawali http:// atau https://.")
    models = _daftar_model_payload(payload)
    if not models:
        raise ValueError("Jalankan Tes & ambil model dulu supaya daftar model terisi.")
    if pid:
        if not runtime_config.id_valid(pid):
            raise ValueError("ID provider tidak sah.")
    else:
        pid = runtime_config.slug(nama)
        if not runtime_config.id_valid(pid):
            raise ValueError("Nama provider tidak bisa dijadikan ID.")
        dasar, n = pid, 2
        while runtime_config.provider(pid):
            pid = f"{dasar}-{n}"
            n += 1
    lama = runtime_config.provider(pid) or {}
    api_key = str(payload.get("api_key") or "").strip()
    entri = {
        "id": pid,
        "name": nama,
        "base_url": base_url,
        "api_key": api_key or lama.get("api_key") or "",
        "models": models,
    }
    data["providers"] = [
        entri if p.get("id") == pid else p for p in data["providers"]
    ]
    if not any(p.get("id") == pid for p in data["providers"]):
        data["providers"].append(entri)
    runtime_config.simpan(data)
    return {"ok": True, "id": pid}


def _provider_hapus(payload: dict) -> dict:
    pid = str(payload.get("id") or "").strip()
    data = runtime_config.muat_ubah()
    data["providers"] = [p for p in data["providers"] if p.get("id") != pid]
    data["agents"] = {
        k: v for k, v in data["agents"].items()
        if not str(v).startswith(f"{pid}/")
    }
    runtime_config.simpan(data)
    return {"ok": True}


def _provider_tes(payload: dict) -> dict:
    pid = str(payload.get("id") or "").strip()
    lama = (runtime_config.provider(pid) or {}) if pid else {}
    try:
        models = openai_client.daftar_model(
            str(payload.get("base_url") or lama.get("base_url") or "").strip(),
            str(payload.get("api_key") or lama.get("api_key") or "").strip(),
        )
        return {"ok": True, "models": models}
    except openai_client.GalatProvider as exc:
        return {"ok": False, "error": exc.pesan}


def _agent_model_simpan(payload: dict) -> dict:
    models = payload.get("models")
    if not isinstance(models, dict):
        raise ValueError("Format model agent tidak dikenal.")
    data = runtime_config.muat_ubah()
    agents = dict(data["agents"])
    for nama, ref in models.items():
        if nama not in runtime_config.AGENTS:
            continue
        ref = str(ref or "").strip()
        if ref:
            runtime_config.resolve(ref)
            agents[nama] = ref
        else:
            agents.pop(nama, None)
    data["agents"] = agents
    runtime_config.simpan(data)
    return {"ok": True}


def _skill_simpan(payload: dict) -> dict:
    nama = _skill_nama(payload.get("name"))
    isi = payload.get("content")
    if not isinstance(isi, str) or not isi.strip():
        raise ValueError("Isi skill tidak boleh kosong.")
    folder = _skills_dir() / nama
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(isi, encoding="utf-8")
    return {"ok": True, "name": nama}


def _skill_hapus(payload: dict) -> dict:
    nama = _skill_nama(payload.get("name"))
    folder = _skills_dir() / nama
    if not folder.is_dir():
        raise ValueError("Skill tidak ditemukan.")
    shutil.rmtree(folder)
    return {"ok": True}


def _template_simpan(payload: dict) -> dict:
    template_id = str(payload.get("id") or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", template_id):
        raise ValueError("ID template tidak sah.")
    schema = payload.get("schema", {})
    if not isinstance(schema, dict):
        raise ValueError("Schema template harus berupa objek.")
    supabase.template_save(_pengguna_sekarang(), {"id": template_id, "name": str(payload.get("name") or template_id).strip()[:120], "description": str(payload.get("description") or "").strip()[:500], "schema": schema, "is_default": bool(payload.get("is_default"))})
    return {"ok": True}


# ----------------------------------------------------------- job submit


def _slug_dari(params: dict) -> str:
    nama = params.get("matkul_nama") or params.get("matkul_id") or "manual"
    return config.slugify(nama, "manual")


def _submit_scrape(params: dict) -> dict:
    # Pagar cookie: gagal cepat dengan pesan jelas sebelum job masuk antrean.
    galat = _moodle_masuk()
    if galat:
        raise ValueError(galat)
    # Jenis yang dipilih di form run Moodle: "" (otomatis) / "Tugas" /
    # "Diskusi". Dinormalkan di sini supaya nilai tak dikenal tidak
    # berakhir di `sesi.soal` dan menyaringnya jadi kosong tanpa pesan.
    jenis = str(params.get("jenis") or "").strip()
    if jenis not in {"", "Tugas", "Diskusi", "Kuis"}:
        raise ValueError("Jenis soal tidak dikenal.")
    params = {**params, "jenis": jenis, "template_id": templates.resolve(_pengguna_sekarang(), params.get("template_id"))["id"]}
    sesi = int(params.get("sesi") or 0)
    if params.get("matkul_id") == "semua":
        if sesi < 1:
            raise ValueError("Pilih sesi untuk semua mata kuliah.")
        jenis = str(params.get("jenis") or "").strip()
        ids: list[str] = []
        skipped: list[dict[str, str]] = []
        klien = moodle.Moodle()
        daftar = courses.daftar_mata_kuliah_lengkap(klien)
        for mk in daftar:
            try:
                sesi_list = courses.sesi_berisi_soal(klien, mk)
            except Exception as exc:  # noqa: BLE001
                skipped.append({"matkul": mk.nama, "alasan": f"preflight gagal: {exc}"})
                continue
            pasangan = dict(sesi_list)
            if sesi not in pasangan or not pasangan.get(sesi, 0):
                skipped.append({"matkul": mk.nama, "alasan": f"sesi {sesi} tidak punya soal"})
                continue
            if jenis:
                try:
                    aktivitas = courses.daftar_aktivitas(klien, mk, sesi)
                except Exception as exc:  # noqa: BLE001
                    skipped.append({"matkul": mk.nama, "alasan": f"filter {jenis} gagal: {exc}"})
                    continue
                if not any(
                    a.boleh_ke_soal and a.jenis_soal == jenis
                    for a in aktivitas
                ):
                    skipped.append({"matkul": mk.nama, "alasan": f"tidak punya soal {jenis}"})
                    continue
            job = MANAGER.submit(
                "scrape",
                {**params, "matkul_id": mk.id},
                mk.slug,
                sesi,
                user=_pengguna_sekarang(),
                scope_args=_scope_args(),
            )
            ids.append(job.id)
        if not ids:
            raise ValueError(
                f"Tidak ada mata kuliah yang punya soal"
                f"{' ' + jenis if jenis else ''} pada sesi {sesi}."
            )
        return {"jobs": ids, "skipped": skipped}
    job = MANAGER.submit(
        "scrape", params, _slug_dari(params), sesi,
        user=_pengguna_sekarang(), scope_args=_scope_args(),
    )
    return {"jobs": [job.id], "skipped": []}


def _submit_manual(body: bytes, ctype: str) -> str:
    m = re.search(r"boundary=([^;]+)", ctype)
    if not m:
        raise ValueError("Boundary multipart tidak ditemukan.")
    boundary = m.group(1).strip().strip('"')
    bagian = _parse_multipart(body, boundary)

    teks: dict[str, str] = {}
    file_akhir: list[str] = []
    for nama, nama_berkas, data in bagian:
        if nama_berkas is None:
            teks[nama] = data.decode("utf-8", errors="replace")
    slug = _slug_dari(teks)
    sesi = int(teks.get("sesi") or 1)
    for nama, nama_berkas, data in bagian:
        if nama_berkas is not None:
            # Nama dari klien adalah path, bukan nama: ambil komponen
            # terakhirnya saja supaya `../` tidak bisa keluar dari folder soal.
            nama_aman = Path(nama_berkas.replace("\\", "/")).name
            if not nama_aman or nama_aman in {".", ".."}:
                raise ValueError("Nama berkas soal tidak sah.")
            folder = config.work_dirs(slug, sesi)["berkas"] / "soal"
            folder.mkdir(parents=True, exist_ok=True)
            tujuan = folder / nama_aman
            if tujuan.exists():
                tujuan = folder / f"{tujuan.stem}-{int(os.getpid())}{tujuan.suffix}"
            tujuan.write_bytes(data)
            file_akhir.append(str(tujuan))

    params = {
        "matkul_nama": teks.get("matkul_nama", ""),
        "matkul_kode": teks.get("matkul_kode", ""),
        "matkul_kelas": teks.get("matkul_kelas", ""),
        "sesi": sesi,
        "jenis": teks.get("jenis", "Tugas"),
        "question": teks.get("question", ""),
        "files": file_akhir,
        # Satu kunci untuk web dan CLI: `jobs._run` membaca `tanpa_gambar`.
        "tanpa_gambar": teks.get("dengan_gambar", "on") != "on",
        "dengan_referensi": teks.get("dengan_referensi", "on") == "on",
        "tanpa_docx": teks.get("tanpa_docx", "") == "on",
        "model": teks.get("model", ""),
        "model_mata": teks.get("model_mata", ""),
        "template_id": templates.resolve(_pengguna_sekarang(), teks.get("template_id"))["id"],
    }
    job = MANAGER.submit(
        "manual", params, slug or "manual", sesi,
        user=_pengguna_sekarang(), scope_args=_scope_args(),
    )
    return job.id


# --------------------------------------------------------------- handler


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "TutonWeb/1.0"

    def log_message(self, *_a) -> None:  # senyap; log ke terminal utama
        pass

    def handle_error(self, request, client_address) -> None:
        # Koneksi terputus (browser menutup, refresh, membatalkan) bukan
        # kegagalan server -- jangan cetak traceback ke terminal.
        import sys as _sys

        exc = _sys.exc_info()[1]
        if isinstance(
            exc,
            (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, TimeoutError),
        ):
            return
        super().handle_error(request, client_address)

    def finish(self) -> None:
        # BaseHTTPRequestHandler may reuse the same worker thread. Never leak
        # one user's ContextVar into the next request.
        try:
            _lepas_scope(self)
        finally:
            super().finish()

    # ---- GET
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            return self._api_get(path, urllib.parse.parse_qs(parsed.query))
        if path == "/":
            return self._static("index.html")
        return self._static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            return self._api_post(path)
        self._not_found()

    def do_HEAD(self) -> None:  # noqa: N802
        # Prefetch Next.js memakai HEAD untuk rute halaman. Tanpa ini server
        # menjawab 501 dan konsol peramban penuh error.
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            self.send_response(405)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return self._static(path, head=True)

    # ---- static
    def _static(self, rel: str, head: bool = False) -> None:
        target = self._static_target(rel)
        if target is None:
            return self._not_found(head)
        ctype, _ = mimetypes.guess_type(target.name)
        if target.suffix == ".js":
            ctype = "application/javascript"
        elif target.suffix == ".css":
            ctype = "text/css"
        elif target.suffix == ".txt":
            ctype = "text/plain; charset=utf-8"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        rel_posix = target.relative_to(STATIC_DIR.resolve()).as_posix()
        if rel_posix.startswith("_next/static/"):
            # Nama berkas Next.js mengandung hash isi, aman di-cache selamanya.
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        elif target.suffix in {".html", ".txt", ".json"}:
            self.send_header("Cache-Control", "no-cache")
        elif target.suffix in {".png", ".svg", ".ico", ".webp", ".woff2"}:
            self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def _static_target(self, rel: str) -> Path | None:
        """Cari berkas hasil `next build` untuk sebuah URL.

        Static export menyimpan rute sebagai `<rute>/index.html` plus payload
        RSC (`index.txt`, `__next.*.txt`) yang dipakai navigasi client-side.
        Keduanya harus disajikan apa adanya, dan `/buat` tanpa garis miring
        harus jatuh ke `buat/index.html`.
        """
        base = STATIC_DIR.resolve()
        bersih = urllib.parse.unquote(rel.replace("\\", "/")).lstrip("/")
        if not bersih:
            kandidat = ["index.html"]
        elif bersih.endswith("/"):
            kandidat = [bersih + "index.html", bersih + "index.txt"]
        elif "." in bersih.rsplit("/", 1)[-1]:
            kandidat = [bersih]
        else:
            kandidat = [
                bersih + "/index.html",
                bersih + ".html",
                bersih,
                bersih + "/index.txt",
                bersih + ".txt",
            ]
        for k in kandidat:
            target = (base / k).resolve()
            if target.is_relative_to(base) and target.is_file():
                return target
        return None

    def _not_found(self, head: bool = False) -> None:
        # Content-Length wajib ada, sama seperti respons 401 di `_butuh_auth`:
        # `/favicon.ico` (diminta otomatis tiap kali tab dibuka) juga lewat
        # sini, jadi tanpa header ini satu koneksi browser ikut menggantung.
        body = b"Tidak ditemukan"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    # ---- API GET
    def _api_get(self, path: str, query: dict[str, list[str]] | None = None) -> None:
        if path == "/api/session":
            user = _user(self)
            if not user:
                return _kirim_json(self, {"authenticated": False})
            prof = supabase.profil(user["id"])
            return _kirim_json(
                self,
                {
                    "authenticated": True,
                    "user": {
                        "id": user["id"],
                        "email": user.get("email", ""),
                        "name": user.get("name", ""),
                    },
                    "profile": prof,
                    # Panduan awal hanya untuk akun yang belum punya identitas
                    # maupun cookie Moodle. Dihitung di server supaya modal
                    # tidak berkedip untuk akun lama yang datanya lengkap.
                    "panduan_awal": _panduan_awal(prof),
                },
            )
        if path == "/api/profil":
            user = _user(self)
            if not user:
                return _kirim_json(self, {"error": "auth"}, 401)
            return _kirim_json(self, supabase.profil(user["id"]))
        if _butuh_auth(self):
            return
        if path == "/api/status":
            return _kirim_json(self, _status())
        if path == "/api/agents":
            return _kirim_json(self, _agents())
        if path == "/api/models":
            return _kirim_json(self, _models())
        if path.startswith("/api/templates/file/"):
            return self._template_berkas(urllib.parse.unquote(path[len("/api/templates/file/"):]))
        if path == "/api/templates":
            return _kirim_json(self, {"templates": templates.daftar(_pengguna_sekarang()), "default_id": templates.resolve(_pengguna_sekarang())["id"]})
        if path == "/api/moodle-status":
            return _kirim_json(self, _moodle_login())
        if path == "/api/nilai":
            return _kirim_json(self, _nilai_semua())
        if path.startswith("/api/courses/") and path.endswith("/nilai-total"):
            return _kirim_json(self, _nilai_total(path.split("/")[3]))
        if path == "/api/courses":
            # Tidak ada `_moodle_masuk()` di sini: pengecekan itu memanggil
            # `/my/` lagi, padahal `MANAGER.courses()` juga membuka `/my/`
            # dan galatnya sudah berupa `MoodleError` yang jelas. Satu request
            # per pemuatan halaman ini cukup.
            try:
                return _kirim_json(self, MANAGER.courses())
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"error": str(exc)}, 400)
        if path == "/api/sessions":
            try:
                return _kirim_json(self, _sesi_semua(paksa=_paksa(query)))
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"error": str(exc)}, 400)
        if path.startswith("/api/jadwal/"):
            return _kirim_json(self, _jadwal(path.split("/")[3]))
        if path == "/api/results":
            return _kirim_json(self, _results_list())
        if path.startswith("/api/results/preview/"):
            return self._hasil_pratinjau(
                urllib.parse.unquote(path[len("/api/results/preview/"):])
            )
        if path == "/api/jobs":
            return _kirim_json(self, self._jobs_list())
        if path.startswith("/api/jobs/") and path.endswith("/events"):
            return self._kirim_events(path.split("/")[3])
        if path.startswith("/api/jobs/") and path.endswith("/stream"):
            return self._stream(path.split("/")[3], query or {})
        if re.fullmatch(r"/api/jobs/[A-Za-z0-9\-]+", path):
            return self._job_detail(path.split("/")[3])
        if path.startswith("/api/courses/") and path.endswith("/sessions"):
            cid = path.split("/")[3]
            try:
                return _kirim_json(self, _sesi_course(cid, paksa=_paksa(query)))
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"error": str(exc)}, 400)
        if path == "/api/settings":
            return _kirim_json(self, _settings_get())
        if path == "/api/providers":
            return _kirim_json(self, _provider_state())
        if path == "/api/skills":
            return _kirim_json(self, {"skills": _skills_list()})
        if path.startswith("/api/skills/"):
            nama = urllib.parse.unquote(path.split("/")[3])
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", nama or ""):
                return _kirim_json(self, {"error": "Nama skill tidak sah."}, 400)
            berkas = _skills_dir() / nama / "SKILL.md"
            if not berkas.is_file():
                return _kirim_json(self, {"error": "Skill tidak ditemukan."}, 404)
            return _kirim_json(
                self, {"name": nama, "content": berkas.read_text(encoding="utf-8", errors="replace")}
            )
        if path.startswith("/api/download/"):
            return self._download(path.split("/")[3])
        if path.startswith("/api/download-output/"):
            return self._download_output(urllib.parse.unquote(path[len("/api/download-output/"):]))
        self._not_found()

    # ---- API POST
    def _api_post(self, path: str) -> None:
        # Clerk logout dilakukan di browser (session.signOut). Endpoint ini
        # sengaja hanya kompatibilitas untuk tombol UI lama.
        if path == "/api/logout":
            return _kirim_json(self, {"ok": True})
        if _butuh_auth(self):
            return
        stop_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9\-]+)/stop", path)
        if stop_match:
            job = MANAGER.jobs.get(stop_match.group(1))
            if not self._milik_saya(job) or not MANAGER.stop(stop_match.group(1)):
                return _kirim_json(self, {"ok": False, "error": "Job tidak aktif atau tidak ditemukan."}, 404)
            return _kirim_json(self, {"ok": True})
        # Bersihkan log permanen (memori + events.jsonl). Tanpa endpoint ini,
        # tombol Bersihkan di UI cuma mengosongkan DOM; log lama balik lagi
        # lewat replay saat halaman dimuat ulang.
        clear_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9\-]+)/clear-log", path)
        if clear_match:
            job = MANAGER.jobs.get(clear_match.group(1))
            if not self._milik_saya(job) or not MANAGER.clear_events(clear_match.group(1)):
                return _kirim_json(self, {"ok": False, "error": "Job tidak ditemukan."}, 404)
            return _kirim_json(self, {"ok": True})
        # Hapus job beserta folder kerjanya. Id yang tidak dikenal 404,
        # job yang masih hidup 409 -- bedanya supaya UI bisa membedakan
        # "salah id" dari "harus hentikan dulu".
        hapus_job = re.fullmatch(r"/api/jobs/([A-Za-z0-9\-]+)/delete", path)
        if hapus_job:
            jid = hapus_job.group(1)
            with MANAGER.lock:
                job = MANAGER.jobs.get(jid)
            if not self._milik_saya(job):
                return _kirim_json(self, {"ok": False, "error": "Job tidak ditemukan."}, 404)
            ok, pesan = MANAGER.hapus(jid)
            if not ok:
                return _kirim_json(self, {"ok": False, "error": pesan}, 409)
            return _kirim_json(self, {"ok": True, "pesan": pesan})
        # Hapus berkas hasil: satu berkas, satu folder sesi, atau seluruh
        # folder mata kuliah. Tiga tingkat lewat satu body -- lihat
        # `_hasil_hapus` untuk pembacaannya.
        if path == "/api/results/delete":
            try:
                payload = json.loads(self._baca_body().decode("utf-8"))
                return _kirim_json(self, _hasil_hapus(payload))
            except ValueError as exc:
                return _kirim_json(self, {"error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"error": str(exc)}, 500)
        if path == "/api/profil":
            user = getattr(self, "_current_user", None)
            if not user:
                return _kirim_json(self, {"error": "auth"}, 401)
            try:
                payload = json.loads(self._baca_body().decode("utf-8") or "{}")
                supabase.simpan(user["id"], user, payload)
                _lupakan_token(self)
                _reset_cache_moodle()
                return _kirim_json(self, {"ok": True, "profil": supabase.profil(user["id"])})
            except ValueError as exc:
                return _kirim_json(self, {"ok": False, "error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"ok": False, "error": str(exc)}, 500)
        if path.startswith("/api/providers/") or path in {
            "/api/agents/models", "/api/skills/save", "/api/skills/delete",
            "/api/templates/save", "/api/templates/default",
        }:
            try:
                payload = json.loads(self._baca_body().decode("utf-8") or "{}")
                aksi = {
                    "/api/providers/save": _provider_simpan,
                    "/api/providers/delete": _provider_hapus,
                    "/api/providers/test": _provider_tes,
                    "/api/agents/models": _agent_model_simpan,
                    "/api/skills/save": _skill_simpan,
                    "/api/skills/delete": _skill_hapus,
                    "/api/templates/save": _template_simpan,
                    "/api/templates/default": lambda p: _template_simpan({**p, "is_default": True}),
                }.get(path)
                if aksi is None:
                    return _kirim_json(self, {"error": "Aksi tidak dikenal."}, 404)
                return _kirim_json(self, aksi(payload))
            except ValueError as exc:
                return _kirim_json(self, {"error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"error": str(exc)}, 500)
        if path == "/api/jobs/scrape":
            try:
                payload = json.loads(self._baca_body().decode("utf-8"))
                return _kirim_json(self, _submit_scrape(payload))
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"error": str(exc)}, 400)
        if path == "/api/jobs/manual":
            try:
                ctype = self.headers.get("Content-Type", "")
                body = self._baca_body()
                jid = _submit_manual(body, ctype)
                return _kirim_json(self, {"jobs": [jid]})
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"error": str(exc)}, 400)
        if path == "/api/settings":
            try:
                payload = json.loads(self._baca_body().decode("utf-8"))
                return _kirim_json(self, _settings_post(payload))
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"error": str(exc)}, 400)
        self._not_found()

    # ---- body
    def _baca_body(self) -> bytes:
        panjang = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(panjang) if panjang else b""

    # ---- jobs
    def _milik_saya(self, job) -> bool:
        """Job hanya terlihat oleh akun yang membuatnya."""
        return job is not None and job.user_id == config.current_user()

    def _jobs_list(self) -> list[dict]:
        saya = config.current_user()
        with MANAGER.lock:
            jobs = [j for j in MANAGER.jobs.values() if j.user_id == saya]
        out = []
        for j in sorted(jobs, key=lambda x: x.dibuat, reverse=True):
            out.append(
                {
                    "id": j.id, "kind": j.kind, "status": j.status,
                    "slug": j.slug, "sesi": j.sesi,
                    "matkul": j.params.get("matkul_nama")
                    or j.params.get("matkul_id") or "manual",
                    "jenis": j.params.get("jenis", ""),
                    "dibuat": j.dibuat, "error": j.error,
                    "hasil": j.hasil,
                }
            )
        return out

    def _job_detail(self, jid: str) -> None:
        job = MANAGER.jobs.get(jid)
        if not self._milik_saya(job):
            return self._not_found()
        _kirim_json(
            self,
            {
                "id": job.id, "kind": job.kind, "status": job.status,
                "slug": job.slug, "sesi": job.sesi, "params": job.params,
                "error": job.error, "hasil": job.hasil, "dibuat": job.dibuat,
            },
        )

    def _kirim_events(self, jid: str) -> None:
        job = MANAGER.jobs.get(jid)
        if not self._milik_saya(job):
            return self._not_found()
        events: list[dict] = []
        with job.cond:
            events = list(job.events)
        if not events and job.event_file.is_file():
            for baris in job.event_file.read_text(encoding="utf-8", errors="replace").splitlines():
                baris = baris.strip()
                if baris:
                    try:
                        events.append(json.loads(baris))
                    except ValueError:
                        pass
        _kirim_json(self, events)

    # ---- SSE
    def _stream(self, jid: str, query: dict[str, list[str]]) -> None:
        job = MANAGER.jobs.get(jid)
        if not self._milik_saya(job):
            return self._not_found()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            after = max(
                0,
                int(self.headers.get("Last-Event-ID") or (query.get("after") or ["0"])[0]),
            )
        except ValueError:
            after = 0
        try:
            while True:
                with job.cond:
                    events = [ev for ev in job.events if ev.get("seq", 0) > after]
                    finished = job.finished
                    status = job.status
                for ev in events:
                    after = max(after, ev.get("seq", after))
                    self.wfile.write(
                        f"id: {after}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8")
                    )
                    self.wfile.flush()
                if finished:
                    self.wfile.write(
                        f"event: done\ndata: {json.dumps({'status': status})}\n\n".encode(
                            "utf-8"
                        )
                    )
                    self.wfile.flush()
                    break
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                time.sleep(0.4)
        except (BrokenPipeError, ConnectionResetError):
            return

    # ---- download
    def _hasil_ambil(self, rel: str) -> tuple[bytes, str] | None:
        """Ambil satu objek hasil milik akun pemanggil dari Storage.

        `rel` berbentuk `<slug>/<sesi>/<nama>` (sama seperti isi `storage_path`
        tanpa awalan `<user_id>/`), jadi akun tidak bisa meminta path akun
        lain: awalan user selalu dari konteks login, bukan dari klien.
        """
        bagian = _hasil_cek_bagian(rel)
        if len(bagian) != 3:
            return None
        slug, sesi, nama = bagian
        user_id = config.current_user()
        if not user_id:
            return None
        isi = supabase.result_download(user_id, f"{user_id}/{slug}/{sesi}/{nama}")
        if isi is None:
            return None
        return isi, nama

    def _download_output(self, rel: str) -> None:
        """Unduh DOCX hasil dari Storage tanpa lewat job di memori."""
        diambil = self._hasil_ambil(rel)
        if diambil is None:
            return self._not_found()
        data, nama = diambil
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f'attachment; filename="{nama}"')
        self.end_headers()
        self.wfile.write(data)

    def _template_berkas(self, template_id: str) -> None:
        """Kirim berkas DOCX template bawaan agar pratinjau memakai isi aslinya.

        Hanya template bawaan yang punya berkas (lihat `templates.docx_path`);
        ID asing atau template kustom tanpa berkas dijawab 404.
        """
        try:
            berkas = templates.docx_path(_pengguna_sekarang(), template_id)
        except ValueError:
            return self._not_found()
        if berkas is None:
            return self._not_found()
        data = berkas.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---- pratinjau
    def _hasil_pratinjau(self, rel: str) -> None:
        """Kirim isi DOCX sebagai HTML blok untuk modal pratinjau.

        Diubah di server, bukan di peramban: peramban tidak bisa membaca
        `.docx`, dan mengirim seluruh berkas agar diurai di sana hanya
        membuang unduhan. HTML-nya HTML polos tanpa gaya apa pun; seluruh
        tampilan datang dari kelas `.prev-*` di `app.css`.
        """
        diambil = self._hasil_ambil(rel)
        if diambil is None:
            return self._not_found()
        data, nama = diambil
        if not nama.lower().endswith(".docx"):
            return _kirim_json(self, {"error": "Pratinjau hanya untuk berkas .docx."}, 400)
        try:
            # `docxprev.pratinjau` membaca berkas, jadi objek dari Storage
            # ditulis ke berkas sementara lalu dibuang lagi.
            with tempfile.TemporaryDirectory(prefix="tuton-prev-") as tmp:
                path = Path(tmp) / "pratinjau.docx"
                path.write_bytes(data)
                isi = docxprev.pratinjau(path)
        except Exception as exc:  # noqa: BLE001 - berkas korup atau bukan DOCX
            return _kirim_json(self, {"error": f"Berkas tidak bisa dipratinjau: {exc}"}, 400)
        _kirim_json(self, {"html": isi, "nama": nama, "renderer": "docx-preview"})

    def _download(self, jid: str) -> None:
        job = MANAGER.jobs.get(jid)
        if not self._milik_saya(job) or not job.hasil.get("docx"):
            return self._not_found()
        path = Path(job.hasil["docx"])
        if not path.is_file():
            return self._not_found()
        # Buka dulu, lalu pakai fstat pada handle yang sama untuk
        # Content-Length. Dengan begitu yang dikirim selalu satu versi
        # berkas yang utuh walau pipeline menimpanya (inode lama tetap
        # hidup sampai handle ditutup). Mengambil `path.stat()` sebelum
        # buka bisa mismatch dan menghasilkan unduhan terpotong/corrupt.
        try:
            fh = open(path, "rb")
        except OSError:
            return self._not_found()
        try:
            size = os.fstat(fh.fileno()).st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.end_headers()
            shutil.copyfileobj(fh, self.wfile)
        finally:
            fh.close()


# --------------------------------------------------------------- main


class QuietHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer yang mendiamkan koneksi terputus.

    ``ConnectionResetError`` (browser menutup/refresh) lolos ke
    ``handle_error`` milik server, bukan handler, jadi pengabaian di
    ``Handler.handle_error`` tidak cukup. Di sini kita diamkan di level
    server supaya terminal tidak penuh traceback tiap kali browser membatalkan
    permintaan.
    """

    allow_reuse_address = False
    # Koneksi yang masih terbuka (stream SSE log, misalnya) tidak boleh
    # menahan proses saat server dimatikan: tanpa ini shutdown berakhir
    # menunggu thread non-daemon sampai akhirnya kena SIGKILL.
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        import sys as _sys

        exc = _sys.exc_info()[1]
        if isinstance(
            exc,
            (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, TimeoutError),
        ):
            return
        super().handle_error(request, client_address)


def main() -> None:
    host = config.env("WEB_HOST") or "127.0.0.1"
    try:
        port = int(config.env("WEB_PORT") or "8000")
    except ValueError:
        port = 8000
    try:
        httpd = QuietHTTPServer((host, port), Handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE or getattr(exc, "winerror", None) == 10048:
            print(
                f"Port {port} pada {host} sudah dipakai. Hentikan server lama "
                "atau ubah WEB_PORT di .env.",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        raise
    print(f"UI Tuton jalan di http://{host}:{port}")
    if not config.CLERK_SECRET_KEY:
        print(
            "  PERINGATAN: CLERK_SECRET_KEY kosong; semua request API akan 401.",
            file=sys.stderr,
        )
    if not supabase.aktif():
        print(
            "  PERINGATAN: SUPABASE_URL/SUPABASE_SERVICE_KEY kosong; "
            "profil user tidak bisa disimpan.",
            file=sys.stderr,
        )
    supabase.mulai_keepalive()
    print(f"  Supabase keepalive: tiap {supabase.INTERVAL_KEEPALIVE // 3600} jam")

    # podman/docker mengirim SIGTERM ke PID 1 saat `stop`/recreate. Python
    # tidak memasang handler SIGTERM, dan untuk PID 1 sinyal dengan aksi
    # default justru DIABAIKAN -- prosesnya tidak pernah mati sampai podman
    # menunggu grace period 10 detik lalu melempar SIGKILL (terlihat di log:
    # "StopSignal SIGTERM failed ... resorting to SIGKILL"). Tiap redeploy jadi
    # rugi 10 detik. Handler ini menghentikan loop server dengan rapi.
    def _hentikan_sinyal(*_args: object) -> None:
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _hentikan_sinyal)
    signal.signal(signal.SIGINT, _hentikan_sinyal)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("\nDihentikan.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
