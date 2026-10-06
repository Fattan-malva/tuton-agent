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
import subprocess
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
import auth  # noqa: E402
from jobs import JobManager  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
COOKIE_NAME = "tuton_session"
SECRET = auth.buat_secret()
MANAGER = JobManager()
_MODEL_CACHE: tuple[float, list[str]] | None = None
_OPENCODE_VERSION_CACHE: tuple[bool, str | None] = (False, None)
_MOODLE_STATUS_CACHE: tuple[float, dict] | None = None
_MOODLE_STATUS_LOCK = threading.Lock()
_NILAI_CACHE: tuple[float, dict] | None = None
_NILAI_LOCK = threading.Lock()


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


def _opencode_version() -> str | None:
    global _OPENCODE_VERSION_CACHE
    if _OPENCODE_VERSION_CACHE[0]:
        return _OPENCODE_VERSION_CACHE[1]
    exe = config.cari_opencode()
    if exe is None:
        version = None
    else:
        try:
            out = subprocess.run(
                [str(exe), "--version"], capture_output=True, text=True, timeout=15
            )
            baris = (out.stdout or out.stderr).strip().splitlines()
            version = baris[0].strip() if baris else "terpasang"
        except (OSError, subprocess.SubprocessError):
            version = "terpasang (versi gagal dibaca)"
    _OPENCODE_VERSION_CACHE = (True, version)
    return version


def _opencode_models() -> dict:
    global _MODEL_CACHE
    now = time.time()
    if _MODEL_CACHE and now - _MODEL_CACHE[0] < 300:
        return {"models": _MODEL_CACHE[1], "error": ""}
    exe = config.cari_opencode()
    if exe is None:
        return {"models": [], "error": "OpenCode tidak ditemukan."}
    command = [str(exe), "models"]
    if exe.suffix.lower() in {".cmd", ".bat"}:
        command = ["cmd", "/c", *command]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return {"models": [], "error": "Daftar model OpenCode gagal dimuat."}
    if result.returncode != 0:
        return {"models": [], "error": "Daftar model OpenCode gagal dimuat."}
    models = list(dict.fromkeys(line.strip() for line in result.stdout.splitlines() if line.strip()))
    if not models:
        return {"models": [], "error": "Tidak ada model OpenCode yang tersedia."}
    _MODEL_CACHE = (now, models)
    return {"models": models, "error": ""}


def _moodle_login() -> dict:
    global _MOODLE_STATUS_CACHE
    with _MOODLE_STATUS_LOCK:
        now = time.monotonic()
        if _MOODLE_STATUS_CACHE and now - _MOODLE_STATUS_CACHE[0] < 60:
            return dict(_MOODLE_STATUS_CACHE[1])
        try:
            import moodle  # noqa: PLC0415

            klien = moodle.Moodle()
            masuk, pesan = klien.cek_login()
            result = {"masuk": masuk, "pesan": pesan}
        except Exception as exc:  # noqa: BLE001
            result = {"masuk": False, "pesan": str(exc)}
        _MOODLE_STATUS_CACHE = (now, result)
        return dict(result)


def _nilai_semua() -> dict:
    """Nilai Tugas & Diskusi semua matkul, di-cache 10 menit."""
    global _NILAI_CACHE
    with _NILAI_LOCK:
        now = time.monotonic()
        if _NILAI_CACHE and now - _NILAI_CACHE[0] < 600:
            return _NILAI_CACHE[1]
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
        _NILAI_CACHE = (now, hasil)
        return hasil


def _status() -> dict:
    return {
        "opencode": _opencode_version(),
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
        {"name": config.AGENT_SCRAPPER, "model": prim},
        {"name": config.AGENT_RESEARCH, "model": prim},
        {"name": config.AGENT_VISION, "model": vis},
        {"name": config.AGENT_WORKER, "model": prim},
    ]


# ----------------------------------------------------------- settings


_KUNCI_EDIT = [
    "URL_MOODLE", "PRIMARY_MODEL", "VISION_MODEL",
    "NAMA", "NIM", "SEMESTER", "UT_DAERAH", "PRODI",
    "APP_USERNAME", "WEB_HOST", "WEB_PORT",
]
_KUNCI_RAHASIA = {"COOKIE_MOODLE", "APP_PASSWORD"}


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
    for k, v in payload.items():
        if k not in _KUNCI_EDIT and k not in _KUNCI_RAHASIA:
            continue
        if k in _KUNCI_RAHASIA and not str(v).strip():
            continue  # kosong -> jangan timpa rahasia yang ada
        config.set_env_value(k, str(v))
    return {"ok": True}


# ----------------------------------------------------------- job submit


def _slug_dari(params: dict) -> str:
    nama = params.get("matkul_nama") or params.get("matkul_id") or "manual"
    return config.slugify(nama, "manual")


def _submit_scrape(params: dict) -> list[str]:
    sesi = int(params.get("sesi") or 0)
    if params.get("matkul_id") == "semua":
        ids: list[str] = []
        for mk in MANAGER.courses():
            job = MANAGER.submit(
                "scrape",
                {**params, "matkul_id": mk["id"]},
                mk["slug"],
                sesi,
            )
            ids.append(job.id)
        return ids
    job = MANAGER.submit("scrape", params, _slug_dari(params), sesi)
    return [job.id]


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
        path = urllib.parse.urlparse(self.path).path
        if path == "/" or path == "/index.html":
            return self._static("index.html")
        if path.startswith("/static/"):
            return self._static(urllib.parse.unquote(path[len("/static/"):]))
        if path.startswith("/api/"):
            return self._api_get(path)
        self._not_found()

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            return self._api_post(path)
        self._not_found()

    # ---- static
    def _static(self, rel: str) -> None:
        rel = rel.replace("\\", "/")
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            return self._not_found()
        ctype, _ = mimetypes.guess_type(target.name)
        if target.suffix == ".js":
            ctype = "application/javascript"
        elif target.suffix == ".css":
            ctype = "text/css"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        if target.suffix in {".html", ".js", ".css"}:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _not_found(self) -> None:
        # Content-Length wajib ada, sama seperti respons 401 di `_butuh_auth`:
        # `/favicon.ico` (diminta otomatis tiap kali tab dibuka) juga lewat
        # sini, jadi tanpa header ini satu koneksi browser ikut menggantung.
        body = b"Tidak ditemukan"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- API GET
    def _api_get(self, path: str) -> None:
        if path == "/api/session":
            return _kirim_json(self, {"authenticated": _terautentikasi(self)})
        if _butuh_auth(self):
            return
        if path == "/api/status":
            return _kirim_json(self, _status())
        if path == "/api/agents":
            return _kirim_json(self, _agents())
        if path == "/api/models":
            return _kirim_json(self, _opencode_models())
        if path == "/api/moodle-status":
            return _kirim_json(self, _moodle_login())
        if path == "/api/nilai":
            return _kirim_json(self, _nilai_semua())
        if path == "/api/courses":
            try:
                return _kirim_json(self, MANAGER.courses())
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"error": str(exc)}, 400)
        if path == "/api/results":
            return _kirim_json(self, _results_list())
        if path == "/api/jobs":
            return _kirim_json(self, self._jobs_list())
        if path.startswith("/api/jobs/") and path.endswith("/events"):
            return self._kirim_events(path.split("/")[3])
        if path.startswith("/api/jobs/") and path.endswith("/stream"):
            return self._stream(path.split("/")[3])
        if re.fullmatch(r"/api/jobs/[A-Za-z0-9\-]+", path):
            return self._job_detail(path.split("/")[3])
        if path.startswith("/api/courses/") and path.endswith("/sessions"):
            cid = path.split("/")[3]
            try:
                return _kirim_json(self, MANAGER.sessions(cid))
            except Exception as exc:  # noqa: BLE001
                return _kirim_json(self, {"error": str(exc)}, 400)
        if path == "/api/settings":
            return _kirim_json(self, _settings_get())
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
            _kirim_json(self, {"ok": True})
            return
        if _butuh_auth(self):
            return
        stop_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9\-]+)/stop", path)
        if stop_match:
            if not MANAGER.stop(stop_match.group(1)):
                return _kirim_json(self, {"ok": False, "error": "Job tidak aktif atau tidak ditemukan."}, 404)
            return _kirim_json(self, {"ok": True})
        if path == "/api/jobs/scrape":
            try:
                payload = json.loads(self._baca_body().decode("utf-8"))
                ids = _submit_scrape(payload)
                return _kirim_json(self, {"jobs": ids})
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
            token = auth.tanda(SECRET, user)
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Set-Cookie",
                f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; "
                f"Max-Age=43200",
            )
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
        if job.event_file.is_file():
            for baris in job.event_file.read_text(encoding="utf-8", errors="replace").splitlines():
                baris = baris.strip()
                if baris:
                    try:
                        events.append(json.loads(baris))
                    except ValueError:
                        pass
        elif job.events:
            # Folder kerja bisa sudah dibersihkan setelah DOCX jadi, jadi
            # berkas event ikut hilang. Fallback ke buffer di memori supaya
            # muat ulang halaman tetap menampilkan log yang sama.
            events = list(job.events)
        _kirim_json(self, events)

    # ---- SSE
    def _stream(self, jid: str) -> None:
        job = MANAGER.jobs.get(jid)
        if job is None:
            return self._not_found()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        idx = 0
        try:
            while True:
                while idx < len(job.events):
                    ev = job.events[idx]
                    idx += 1
                    self.wfile.write(
                        f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8")
                    )
                    self.wfile.flush()
                if job.finished and idx >= len(job.events):
                    self.wfile.write(
                        f"event: done\ndata: {json.dumps({'status': job.status})}\n\n".encode(
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
        base = config.OUTPUT_DIR.resolve()
        try:
            path = (base / rel).resolve()
        except OSError:
            return self._not_found()
        if not str(path).startswith(str(base)) or not path.is_file():
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

    # Panaskan cache opencode di background. Versi dan daftar model sama-sama
    # butuh menjalankan subproses `opencode` (±1-6 detik, tergantung kecepatan
    # provider). Kalau baru dihitung saat request pertama tiba, Dashboard dan
    # Settings terasa macet sekali tiap kali server di-restart.
    def _panaskan_cache() -> None:
        try:
            _opencode_version()
            _opencode_models()
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_panaskan_cache, daemon=True).start()

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
