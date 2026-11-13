"""Server web lokal untuk pipeline tutor UT (murni standard library).

Menyajikan UI statis, API JSON, streaming log lewat Server-Sent Events (SSE),
dan unggah berkas multipart untuk mode input manual. Tidak ada dependency
baru: hanya modul `http.server` bawaan Python.

Jalankan:

    py webui/server.py            # Windows
    python webui/server.py        # Linux

Lalu buka http://127.0.0.1:8000 (atau WEB_PORT di .env).
"""

from __future__ import annotations

import io
import errno
import json
import mimetypes
import os
import platform
import re
import shutil
import signal
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Pastikan modul root (pipeline, config, ...) bisa diimpor.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import agent_runner  # noqa: E402
import auth  # noqa: E402
import docxprev  # noqa: E402
from jobs import JobManager  # noqa: E402
import courses  # noqa: E402
import moodle  # noqa: E402
import mcp_client  # noqa: E402
import openai_client  # noqa: E402
import runtime_config  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
# Saat pengembangan, `webui/static` belum tentu ada (hasil build Next.js
# di-copy ke sana hanya ketika image Docker dibuat). Pakai `web/out` langsung
# supaya `python webui/server.py` tetap bisa dipakai tanpa langkah copy.
if not (STATIC_DIR / "index.html").is_file():
    STATIC_DIR = ROOT / "web" / "out"
COOKIE_NAME = "tuton_session"
SECRET = auth.buat_secret()
MANAGER = JobManager()
# Cache Moodle: tuple (waktu, ttl_detik, data). TTL sukses panjang, TTL gagal
# pendek supaya cookie baru yang disimpan lewat Pengaturan langsung terbaca
# -- hasil error tidak boleh berdiam 10 menit di cache.
_MOODLE_STATUS_CACHE: tuple[float, float, dict] | None = None
_MOODLE_STATUS_LOCK = threading.Lock()
_NILAI_CACHE: tuple[float, float, dict] | None = None
_NILAI_LOCK = threading.Lock()
_JADWAL_CACHE: dict[str, tuple[float, float, dict]] = {}
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
    """Sesi yang punya soal untuk satu course, dengan cache singkat."""
    with _SESI_LOCK:
        now = time.monotonic()
        entri = _SESI_CACHE.get(cid)
        if not paksa and entri and now - entri[0] < entri[1]:
            return entri[2]
    hasil = MANAGER.sessions(cid)
    with _SESI_LOCK:
        _SESI_CACHE[cid] = (time.monotonic(), _TTL_SESI, hasil)
    return hasil


def _sesi_semua(paksa: bool = False) -> list[dict]:
    """Sesi lintas semua mata kuliah, dengan cache singkat yang sama."""
    kunci = "*"
    with _SESI_LOCK:
        now = time.monotonic()
        entri = _SESI_CACHE.get(kunci)
        if not paksa and entri and now - entri[0] < entri[1]:
            return entri[2]
    hasil = MANAGER.semua_sesi()
    with _SESI_LOCK:
        _SESI_CACHE[kunci] = (time.monotonic(), _TTL_SESI, hasil)
    return hasil


def _moodle_login() -> dict:
    global _MOODLE_STATUS_CACHE
    with _MOODLE_STATUS_LOCK:
        now = time.monotonic()
        if _MOODLE_STATUS_CACHE:
            waktu, ttl, data = _MOODLE_STATUS_CACHE
            if now - waktu < ttl:
                return dict(data)
        try:
            import moodle  # noqa: PLC0415

            klien = moodle.Moodle()
            masuk, pesan = klien.cek_login()
            result = {"masuk": masuk, "pesan": pesan}
        except Exception as exc:  # noqa: BLE001
            result = {"masuk": False, "pesan": str(exc)}
        # Cookie mati di-cache sebentar saja (20 detik) supaya perbaikan
        # cookie lewat Pengaturan langsung terasa di halaman berikutnya.
        _MOODLE_STATUS_CACHE = (now, 60.0 if result["masuk"] else 20.0, result)
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
    """Nilai Tugas & Diskusi semua matkul.

    Sukses di-cache 10 menit; hasil error cuma 30 detik supaya setelah cookie
    diganti nilai langsung bisa ditarik lagi tanpa menunggu cache lama.
    """
    global _NILAI_CACHE
    with _NILAI_LOCK:
        now = time.monotonic()
        if _NILAI_CACHE:
            waktu, ttl, data = _NILAI_CACHE
            if now - waktu < ttl:
                return data
        galat = _moodle_masuk()
        if galat:
            hasil = {"courses": [], "sesi": [], "error": galat}
        else:
            try:
                import moodle  # noqa: PLC0415
                import courses  # noqa: PLC0415

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
                            "titik": [
                                {"sesi": s, **per_sesi[s]} for s in sorted(per_sesi)
                            ],
                        }
                    )
                hasil = {"courses": courses_out, "sesi": sorted(sesi_semua)}
            except Exception as exc:  # noqa: BLE001
                hasil = {"courses": [], "sesi": [], "error": str(exc)}
        _NILAI_CACHE = (now, _TTL_OK if not hasil.get("error") else _TTL_GAGAL, hasil)
        return hasil


def _jadwal(cid: str) -> dict:
    """Jadwal Diskusi & Tugas satu course, di-cache 10 menit.

    Mengambil tanggal `Opened:`/`Due:` dari tiap halaman activity -- bisa
    belasan request saat pertama kali, jadi hasilnya disimpan di memori
    dan halamannya sendiri sudah ikut tercache oleh klien Moodle.
    """
    with _JADWAL_LOCK:
        now = time.monotonic()
        entri = _JADWAL_CACHE.get(cid)
        if entri and now - entri[0] < entri[1]:
            return entri[2]
        try:
            import moodle  # noqa: PLC0415
            import courses  # noqa: PLC0415

            klien = moodle.Moodle()
            # Langsung ke course yang diminta: mencari lewat daftar seluruh
            # course berarti membuka /my/ lalu setiap halaman course hanya
            # untuk menemukan satu id, dan itu yang membuat kartu ini lambat.
            matkul = courses.mata_kuliah_dari_id(klien, cid)
            hasil = {"items": courses.jadwal_mata_kuliah(klien, matkul)}
        except Exception as exc:  # noqa: BLE001
            hasil = {"items": [], "error": str(exc)}
        ttl = _TTL_OK if not hasil.get("error") else _TTL_GAGAL
        _JADWAL_CACHE[cid] = (now, ttl, hasil)
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
    """Daftar DOCX yang ada di disk, dari folder kerja.

    Sumber kebenaran hasil adalah folder `output/`, bukan state job di
    memori: setelah server di-restart, job lama hilang dari memori padahal
    berkasnya tetap ada. Tanpa ini tab Result kosong walau output penuh.
    """
    out: list[dict] = []
    base = config.OUTPUT_DIR
    if base.is_dir():
        for path in sorted(base.glob("*/*/*.docx")):
            try:
                st = path.stat()
            except OSError:
                continue
            out.append(
                {
                    "slug": path.parent.parent.name,
                    "sesi": path.parent.name,
                    "nama": path.name,
                    "ukuran": st.st_size,
                    "waktu": st.st_mtime,
                }
            )
    return sorted(out, key=lambda x: x["waktu"], reverse=True)


def _hasil_target(rel: str) -> Path | None:
    """Tentukur satu jalur relatif di dalam `output/`, atau `None` kalau lolos.

    Semua rute yang menyentuh `output/` (unduh, pratinjau, hapus) melewat
    jalurnya lewat sini. Tiga lapis pagar: path absolut di-*resolve* dulu
    (menetralkan `..` dan tautan simbolis), lalu harus benar-benar berada di
    dalam `output/` -- bukan sekadar berawalan sama, karena `output2/` juga
    berawalan `output`. Resolusi dilakukan per bagian, bukan sebagai satu
    potongan dari klien, supaya `../../etc/passwd` langsung ditolak.
    """
    base = config.OUTPUT_DIR.resolve()
    bagian = [b for b in rel.replace("\\", "/").split("/") if b not in ("", ".")]
    if not bagian or any(b == ".." for b in bagian):
        return None
    try:
        target = base
        for b in bagian:
            target = target / b
        target = target.resolve()
    except OSError:
        return None
    if not str(target).startswith(str(base) + os.sep):
        return None
    return target


def _hasil_hapus(payload: dict) -> dict:
    """Hapus satu berkas, satu folder sesi, atau seluruh folder mata kuliah.

    Tingkatnya ditentukan isi body: `nama` berarti berkas, tanpa `nama` tapi
    ada `sesi` berarti folder sesi, tanpa keduanya berarti seluruh folder
    mata kuliah beserta semua DOCX-nya. Selalu lewat `_hasil_target`.
    """
    slug = str(payload.get("slug") or "")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", slug) or ".." in slug:
        raise ValueError("Nama mata kuliah tidak sah.")
    base = config.OUTPUT_DIR.resolve()
    akar = _hasil_target(slug)
    if akar is None:
        raise ValueError("Folder mata kuliah tidak ada di output/.")

    sesi = str(payload.get("sesi") or "")
    nama = str(payload.get("nama") or "")

    if nama:
        if not re.fullmatch(r"sesi-\d+", sesi):
            raise ValueError("Nomor sesi tidak sah.")
        target = _hasil_target(f"{slug}/{sesi}/{nama}")
        if target is None or not target.is_file():
            raise ValueError("Berkas tidak ditemukan.")
        target.unlink()
        return {"ok": True, "tingkat": "berkas", "path": str(target.relative_to(base))}

    if sesi:
        if not re.fullmatch(r"sesi-\d+", sesi):
            raise ValueError("Nomor sesi tidak sah.")
        target = _hasil_target(f"{slug}/{sesi}")
        if target is None or not target.is_dir():
            raise ValueError("Folder sesi tidak ditemukan.")
        shutil.rmtree(target)
        return {"ok": True, "tingkat": "sesi", "path": str(target.relative_to(base))}

    if not akar.is_dir():
        raise ValueError("Folder mata kuliah tidak ditemukan.")
    shutil.rmtree(akar)
    return {"ok": True, "tingkat": "matkul", "path": slug}


def _kirim_json(handler, obj, status: int = 200) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _kirim_teks(handler, teks: str, status: int = 200) -> None:
    body = teks.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _terautentikasi(handler) -> bool:
    if not config.env("APP_PASSWORD"):
        return True  # kata sandi kosong -> gerbang dimatikan
    cookie = handler.headers.get("Cookie", "")
    for potong in cookie.split(";"):
        potong = potong.strip()
        if potong.startswith(f"{COOKIE_NAME}="):
            token = potong[len(COOKIE_NAME) + 1 :]
            return auth.cek_tanda(token, SECRET)
    return False


def _butuh_auth(handler) -> bool:
    if _terautentikasi(handler):
        return False
    # Content-Length WAJIB ikut ditulis. Tanpa itu, dengan HTTP/1.1 klien
    # (nginx maupun browser) menunggu connection close untuk tahu body sudah
    # selesai -- respons menggantung sampai proxy_read_timeout nginx (300
    # detik). Karena browser cuma punya 6 koneksi per origin, enam request
    # yang menggantung membuat SELURUH halaman berikutnya ikut macet.
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
    return {
        "providers": [_provider_publik(p) for p in runtime_config.providers()],
        "agents": runtime_config.muat()["agents"],
        "models": runtime_config.semua_model(),
        "error": _models()["error"],
    }


def _mcp_publik(server: dict) -> dict:
    return {
        "id": server.get("id") or "",
        "name": server.get("name") or server.get("id") or "",
        "url": server.get("url") or "",
        "headers": sorted((server.get("headers") or {}).keys()),
        "agents": server.get("agents") or [],
        "tools": server.get("tools") or [],
        "enabled": server.get("enabled") is not False,
    }


def _skills_dir() -> Path:
    return config.BASE_DIR / ".opencode" / "skills"


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


def _status() -> dict:
    provider = runtime_config.providers()
    model = runtime_config.semua_model()
    return {
        "providers": f"{len(provider)} provider / {len(model)} model",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "primary_model": config.env("PRIMARY_MODEL") or config.PRIMARY_MODEL,
        "vision_model": config.env("VISION_MODEL") or config.VISION_MODEL,
        "auth_required": bool(config.env("APP_PASSWORD")),
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


_KUNCI_EDIT = [
    "URL_MOODLE", "PRIMARY_MODEL", "VISION_MODEL", "FALLBACK_MODELS",
    "NAMA", "NIM", "SEMESTER", "UT_DAERAH", "PRODI",
    "APP_USERNAME", "WEB_HOST", "WEB_PORT",
]
_KUNCI_RAHASIA = {"COOKIE_MOODLE", "APP_PASSWORD"}
# Kunci yang memengaruhi koneksi Moodle; kalau salah satunya berubah, semua
# cache yang isinya hasil scrape lama harus dibersihkan sekaligus.
_KUNCI_MOODLE = {"COOKIE_MOODLE", "URL_MOODLE"}


def _reset_cache_moodle() -> int:
    """Bersihkan semua cache turunan cookie Moodle.

    Cakupannya: status login (60 detik), nilai (10 menit), jadwal per course
    (10 menit), daftar sesi per course (2 menit), dan halaman HTML hasil
    scrape di folder `cache/` (TTL 1 jam). Tanpa ini, cookie baru dari menu
    Pengaturan tidak pernah sampai ke halaman lain sampai semua cache
    kedaluwarsa sendiri.
    """
    global _MOODLE_STATUS_CACHE, _NILAI_CACHE
    with _MOODLE_STATUS_LOCK:
        _MOODLE_STATUS_CACHE = None
    with _NILAI_LOCK:
        _NILAI_CACHE = None
    with _JADWAL_LOCK:
        _JADWAL_CACHE.clear()
    with _SESI_LOCK:
        _SESI_CACHE.clear()
    MANAGER.reset_courses_cache()
    jumlah = 0
    try:
        for berkas in Path(config.CACHE_DIR).glob("*.html"):
            try:
                berkas.unlink()
                jumlah += 1
            except OSError:
                pass
    except OSError:
        pass
    return jumlah


def _settings_get() -> list[dict]:
    out: list[dict] = []
    for k in _KUNCI_EDIT:
        out.append({"key": k, "value": config.env(k), "rahasia": False})
    for k in _KUNCI_RAHASIA:
        val = config.env(k)
        out.append(
            {
                "key": k,
                "value": ("*" * len(val)) if val else "",
                "rahasia": True,
                "ada": bool(val),
            }
        )
    return out


def _settings_post(payload: dict) -> dict:
    lama = {k: config.env(k) for k in _KUNCI_MOODLE}
    nim_lama = config.env("NIM")
    nim_berubah = False
    berubah = False
    for k, v in payload.items():
        if k not in _KUNCI_EDIT and k not in _KUNCI_RAHASIA:
            continue
        if k in _KUNCI_RAHASIA and not str(v).strip():
            continue  # kosong -> jangan timpa rahasia yang ada
        nilai = str(v).strip()
        if k in _KUNCI_MOODLE and nilai != lama[k]:
            berubah = True
        if k == "NIM" and nilai != nim_lama:
            nim_berubah = True
        config.set_env_value(k, nilai)
        if k == "FALLBACK_MODELS":
            # config sudah dievaluasi saat impor, jadi daftar cadangan perlu
            # dihitung ulang di memori. Tanpa ini perubahan hanya berlaku
            # setelah server di-restart, dan job berikutnya tetap memakai
            # model cadangan yang lama.
            config.FALLBACK_MODELS = [
                m.strip() for m in nilai.split(",") if m.strip()
            ]
    if nim_berubah:
        # Status Diskusi bergantung pada NIM; jadwal lama harus dihitung ulang.
        with _JADWAL_LOCK:
            _JADWAL_CACHE.clear()
    if berubah:
        # Cookie/URL Moodle baru: buang semua hasil scrape lama supaya
        # dashboard, select matkul, nilai, dan jadwal langsung memakai
        # sesi yang baru tanpa perlu restart server.
        dibersihkan = _reset_cache_moodle()
        return {"ok": True, "moodle_disegarkan": True, "cache_dibersihkan": dibersihkan}
    return {"ok": True}


# ------------------------------------------------- provider / mcp / skill


def _daftar_model_payload(payload: dict) -> list[str]:
    models = payload.get("models")
    if isinstance(models, str):
        models = re.split(r"[,\n]+", models)
    if not isinstance(models, list):
        models = []
    return [str(m).strip() for m in models if str(m).strip()]


def _provider_simpan(payload: dict) -> dict:
    data = runtime_config.muat()
    pid = str(payload.get("id") or "").strip()
    nama = str(payload.get("name") or "").strip()
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    if not nama:
        raise ValueError("Nama provider wajib diisi.")
    if not re.match(r"^https?://", base_url):
        raise ValueError("Base URL harus diawali http:// atau https://.")
    models = _daftar_model_payload(payload)
    if not models:
        raise ValueError("Isi minimal satu model ID.")
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
    data = runtime_config.muat()
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
    data = runtime_config.muat()
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


def _mcp_simpan(payload: dict) -> dict:
    data = runtime_config.muat()
    sid = str(payload.get("id") or "").strip()
    nama = str(payload.get("name") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not nama:
        raise ValueError("Nama server MCP wajib diisi.")
    if not re.match(r"^https?://", url):
        raise ValueError("URL MCP harus diawali http:// atau https://.")
    if not sid:
        sid = runtime_config.slug(nama)
        if not runtime_config.id_valid(sid):
            raise ValueError("Nama server tidak bisa dijadikan ID.")
        dasar, n = sid, 2
        while any(m.get("id") == sid for m in data["mcp"]):
            sid = f"{dasar}-{n}"
            n += 1
    lama = next((m for m in data["mcp"] if m.get("id") == sid), {})
    headers = payload.get("headers")
    if not isinstance(headers, dict) or not headers:
        headers = lama.get("headers") or {}
    headers = {
        str(k).strip(): str(v).strip()
        for k, v in headers.items()
        if str(k).strip() and str(v).strip()
    }
    agents = payload.get("agents")
    if not isinstance(agents, list):
        agents = lama.get("agents") or []
    agents = [a for a in agents if a in runtime_config.AGENTS]
    entri = {
        "id": sid,
        "name": nama,
        "url": url,
        "headers": headers,
        "agents": agents,
        "tools": [str(t) for t in (payload.get("tools") or []) if str(t).strip()],
        "enabled": payload.get("enabled") is not False,
    }
    data["mcp"] = [entri if m.get("id") == sid else m for m in data["mcp"]]
    if not any(m.get("id") == sid for m in data["mcp"]):
        data["mcp"].append(entri)
    runtime_config.simpan(data)
    return {"ok": True, "id": sid}


def _mcp_hapus(payload: dict) -> dict:
    sid = str(payload.get("id") or "").strip()
    data = runtime_config.muat()
    data["mcp"] = [m for m in data["mcp"] if m.get("id") != sid]
    runtime_config.simpan(data)
    return {"ok": True}


def _mcp_tes(payload: dict) -> dict:
    sid = str(payload.get("id") or "").strip()
    lama = next((m for m in runtime_config.muat()["mcp"] if m.get("id") == sid), {})
    server = {
        "id": sid or "uji",
        "url": str(payload.get("url") or lama.get("url") or "").strip(),
        "headers": payload.get("headers") or (lama.get("headers") or {}),
    }
    try:
        tools = mcp_client.daftar_tool(server)
        return {
            "ok": True,
            "tools": [
                {"name": t.get("name"), "description": t.get("description") or ""}
                for t in tools
            ],
        }
    except mcp_client.GalatMcp as exc:
        return {"ok": False, "error": str(exc)}


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
    params = {**params, "jenis": jenis}
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
            )
            ids.append(job.id)
        if not ids:
            raise ValueError(
                f"Tidak ada mata kuliah yang punya soal"
                f"{' ' + jenis if jenis else ''} pada sesi {sesi}."
            )
        return {"jobs": ids, "skipped": skipped}
    job = MANAGER.submit("scrape", params, _slug_dari(params), sesi)
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
            folder = config.work_dirs(slug, sesi)["berkas"] / "soal"
            folder.mkdir(parents=True, exist_ok=True)
            tujuan = folder / nama_berkas
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
        "dengan_gambar": teks.get("dengan_gambar", "on") == "on",
        "dengan_referensi": teks.get("dengan_referensi", "on") == "on",
        "tanpa_docx": teks.get("tanpa_docx", "") == "on",
        "model": teks.get("model", ""),
        "model_mata": teks.get("model_mata", ""),
    }
    job = MANAGER.submit("manual", params, slug or "manual", sesi)
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
            return _kirim_json(self, {"authenticated": _terautentikasi(self)})
        if _butuh_auth(self):
            return
        if path == "/api/status":
            return _kirim_json(self, _status())
        if path == "/api/agents":
            return _kirim_json(self, _agents())
        if path == "/api/models":
            return _kirim_json(self, _models())
        if path == "/api/moodle-status":
            return _kirim_json(self, _moodle_login())
        if path == "/api/nilai":
            return _kirim_json(self, _nilai_semua())
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
        if path == "/api/mcp":
            return _kirim_json(
                self, {"servers": [_mcp_publik(m) for m in runtime_config.muat()["mcp"]]}
            )
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
        if path == "/api/login":
            return self._login()
        if path == "/api/logout":
            # Cookie harus benar-benar dihapus (Max-Age=0). Kalau cuma
            # mengembalikan {"ok":true}, browser masih membawa token yang
            # sah sehingga halaman yang dimuat ulang tetap terlihat masuk.
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Set-Cookie",
                f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
            )
            self.end_headers()
            self.wfile.write(body)
            return
        if _butuh_auth(self):
            return
        stop_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9\-]+)/stop", path)
        if stop_match:
            if not MANAGER.stop(stop_match.group(1)):
                return _kirim_json(self, {"ok": False, "error": "Job tidak aktif atau tidak ditemukan."}, 404)
            return _kirim_json(self, {"ok": True})
        # Bersihkan log permanen (memori + events.jsonl). Tanpa endpoint ini,
        # tombol Bersihkan di UI cuma mengosongkan DOM; log lama balik lagi
        # lewat replay saat halaman dimuat ulang.
        clear_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9\-]+)/clear-log", path)
        if clear_match:
            if not MANAGER.clear_events(clear_match.group(1)):
                return _kirim_json(self, {"ok": False, "error": "Job tidak ditemukan."}, 404)
            return _kirim_json(self, {"ok": True})
        # Hapus job beserta folder kerjanya. Id yang tidak dikenal 404,
        # job yang masih hidup 409 -- bedanya supaya UI bisa membedakan
        # "salah id" dari "harus hentikan dulu".
        hapus_job = re.fullmatch(r"/api/jobs/([A-Za-z0-9\-]+)/delete", path)
        if hapus_job:
            jid = hapus_job.group(1)
            with MANAGER.lock:
                ada = jid in MANAGER.jobs
            if not ada:
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
        if path.startswith("/api/providers/") or path in {
            "/api/agents/models", "/api/mcp/save", "/api/mcp/delete",
            "/api/mcp/test", "/api/skills/save", "/api/skills/delete",
        }:
            try:
                payload = json.loads(self._baca_body().decode("utf-8") or "{}")
                aksi = {
                    "/api/providers/save": _provider_simpan,
                    "/api/providers/delete": _provider_hapus,
                    "/api/providers/test": _provider_tes,
                    "/api/agents/models": _agent_model_simpan,
                    "/api/mcp/save": _mcp_simpan,
                    "/api/mcp/delete": _mcp_hapus,
                    "/api/mcp/test": _mcp_tes,
                    "/api/skills/save": _skill_simpan,
                    "/api/skills/delete": _skill_hapus,
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

    # ---- login
    def _login(self) -> None:
        try:
            payload = json.loads(self._baca_body().decode("utf-8"))
        except ValueError:
            return _kirim_json(self, {"ok": False, "error": "body salah"}, 400)
        user = str(payload.get("username", ""))
        pw = str(payload.get("password", ""))
        if auth.verifikasi(
            user,
            pw,
            config.env("APP_USERNAME", config.APP_USERNAME),
            config.env("APP_PASSWORD", config.APP_PASSWORD),
        ):
            # "Ingat saya" dicentang (default): token & cookie berlaku30 hari.
            # Tanpa centang, cookie sengaja TANPA Max-Age supaya berupa
            # session cookie -- ikut hilang begitu peramban ditutup.
            ingat = bool(payload.get("remember", True))
            masa = 60 * 60 * 24 * 30 if ingat else 60 * 60 * 12
            token = auth.tanda(SECRET, user, masa)
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            cookie = f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax"
            if ingat:
                cookie += f"; Max-Age={masa}"
            self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)
        else:
            _kirim_json(self, {"ok": False, "error": "Nama atau kata sandi salah"}, 401)

    # ---- jobs
    def _jobs_list(self) -> list[dict]:
        with MANAGER.lock:
            jobs = list(MANAGER.jobs.values())
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
        if job is None:
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
        if job is None:
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
        if job is None:
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
    def _download_output(self, rel: str) -> None:
        """Unduh DOCX dari folder `output/` tanpa harus lewat job di memori."""
        path = _hasil_target(rel)
        if path is None or not path.is_file():
            return self._not_found()
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

    # ---- pratinjau
    def _hasil_pratinjau(self, rel: str) -> None:
        """Kirim isi DOCX sebagai HTML blok untuk modal pratinjau.

        Diubah di server, bukan di peramban: peramban tidak bisa membaca
        `.docx`, dan mengirim seluruh berkas agar diurai di sana hanya
        membuang unduhan. HTML-nya HTML polos tanpa gaya apa pun; seluruh
        tampilan datang dari kelas `.prev-*` di `app.css`.
        """
        path = _hasil_target(rel)
        if path is None or not path.is_file():
            return self._not_found()
        if path.suffix.lower() != ".docx":
            return _kirim_json(self, {"error": "Pratinjau hanya untuk berkas .docx."}, 400)
        try:
            isi = docxprev.pratinjau(path)
        except Exception as exc:  # noqa: BLE001 - berkas korup atau bukan DOCX
            return _kirim_json(self, {"error": f"Berkas tidak bisa dipratinjau: {exc}"}, 400)
        _kirim_json(self, {"html": isi, "nama": path.name})

    def _download(self, jid: str) -> None:
        job = MANAGER.jobs.get(jid)
        if job is None or not job.hasil.get("docx"):
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
    if not config.env("APP_PASSWORD"):
        print("  (APP_PASSWORD kosong: gerbang login dimatikan)")

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
