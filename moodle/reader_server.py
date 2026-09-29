"""Server HTTP lokal yang menyajikan halaman Moodle terotorisasi untuk AI.

Agent `tuton` dijalankan lewat `opencode run` dan tidak membawa cookie
MoodleSession, jadi ia tidak bisa membuka elearning.ut.ac.id. Server ini
menjembataninya: AI memanggil URL di prompt, server menyuntik cookie lalu
mengembalikan Markdown (atau berkas biner).

    /healthz                      -> status server + jumlah permintaan
    /soal?u=<url>&t=<token>       -> Markdown halaman (atau teks PDF)
    /file?u=<url>&t=<token>       -> bytes asli (gambar/PDF/dokumen)

Keamanan:
- bind 127.0.0.1 saja (tidak terekspos ke jaringan).
- token acak per-proses; tanpa token akan mendapat 403.
- guard SSRF: hanya host MOODLE_BASE_URL yang boleh diambil.
- batas ukuran & timeout supaya satu lampiran besar tidak melahap memori.
"""

from __future__ import annotations

import json
import secrets
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from config import Config
from moodle import reader as reader_mod
from moodle.reader import Fetched, MoodleReader, render_moodle_html

_READER: MoodleReader | None = None
_TOKEN: str = ""
_STATE: dict = {"port": 0, "requests": 0, "started": 0, "error": ""}
_LOCK = threading.Lock()
_SERVER: ThreadingHTTPServer | None = None


def reader() -> MoodleReader:
    global _READER
    if _READER is None:
        _READER = MoodleReader()
    return _READER


def token() -> str:
    return _TOKEN


def base_url() -> str:
    port = _STATE.get("port") or 0
    return f"http://127.0.0.1:{port}" if port else ""


def soalu(url: str, kind: str = "generic") -> str:
    """Bentuk URL Reader untuk sebuah URL Moodle (untuk disisipkan ke prompt)."""
    quoted = urllib.parse.quote(url, safe="")
    kind_q = urllib.parse.quote(kind, safe="")
    return f"{base_url()}/soal?u={quoted}&k={kind_q}&t={_TOKEN}"


def fileurl(url: str, kind: str = "file") -> str:
    quoted = urllib.parse.quote(url, safe="")
    return f"{base_url()}/file?u={quoted}&t={_TOKEN}"


# ---------------------------------------------------------------------------
# Logika handler (dipisah supaya bisa diuji tanpa menjalankan server)
# ---------------------------------------------------------------------------
def handle_soal(url: str, kind: str, *, use_cache: bool = True) -> tuple[int, str, str]:
    """(status, content_type, body_text) untuk /soal."""
    if not url:
        return 400, "text/plain; charset=utf-8", "URL wajib diisi (parameter u)."
    r = reader()
    if not r.allowed(url):
        return 403, "text/plain; charset=utf-8", (
            "URL di luar host Moodle. Reader hanya menyajikan halaman dari "
            f"{Config.MOODLE_BASE_URL}."
        )
    md, fetched = r.render(url, kind=kind, use_cache=use_cache)
    if not md.strip():
        return _fail_status(fetched), "text/plain; charset=utf-8", _fail_text(fetched, url)
    header = (
        f"<!-- Reader Lokal | sumber: {url} | status: HTTP {fetched.status} "
        f"| cache: {'ya' if fetched.from_cache else 'tidak'} -->"
    )
    return 200, "text/markdown; charset=utf-8", f"{header}\n\n{md}"


def handle_file(url: str) -> tuple[int, str, bytes]:
    """(status, content_type, bytes) untuk /file."""
    if not url:
        return 400, "text/plain; charset=utf-8", b"URL wajib diisi (parameter u)."
    r = reader()
    if not r.allowed(url):
        return 403, "text/plain; charset=utf-8", b"URL di luar host Moodle."
    fetched: Fetched = r.fetch(url)
    if not fetched.ok:
        if fetched.is_login:
            return 401, "text/plain; charset=utf-8", (
                b"Sesi Moodle kedaluwarsa. Perbarui MoodleSession di Settings."
            )
        return (
            _fail_status(fetched),
            "text/plain; charset=utf-8",
            _fail_text(fetched, url).encode("utf-8", "replace"),
        )
    ctype = fetched.content_type or "application/octet-stream"
    return 200, ctype, fetched.body


def _fail_status(fetched: Fetched) -> int:
    if fetched.error:
        return 502
    if fetched.is_login:
        return 401
    return fetched.status or 502


def _fail_text(fetched: Fetched, url: str) -> str:
    if fetched.is_login:
        return (
            "Halaman ini mengembalikan form login: sesi MoodleSession sudah "
            "kedaluwarsa. Minta pengguna memperbarui cookie di Settings, lalu "
            f"coba lagi. URL: {url}"
        )
    if fetched.error:
        return f"Gagal mengambil {url}: {fetched.error}"
    if 400 <= fetched.status < 500:
        return f"{url} tidak tersedia (HTTP {fetched.status}). Coba URL lain."
    return (
        f"{url} tidak bisa dibaca (HTTP {fetched.status or 'kosong'}). "
        "Coba URL lain yang diberikan, atau nyatakan honestly dalam jawaban "
        "bahwa sumber ini tidak bisa diakses."
    )


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------
class _QuietServer(ThreadingHTTPServer):
    """ThreadingHTTPServer yang tidak mencetak traceback untuk koneksi putus.

    `socketserver` secara default mencetak traceback penuh ke stderr setiap
    handler melempar exception. Client Reader (opencode) sering menutup koneksi
    duluan -- misalnya membatalkan fetch saat masih menunggu render -- sehingga
    tiap socket yang ditutup memicu ConnectionResetError yang terlihat seperti
    crash. Noise ini sempat menutupi pesan kegagalan yang sebenarnya.
    """

    daemon_threads = True

    def handle_error(self, request, client_address) -> None:  # noqa: ANN001, ANN202
        exc = sys.exc_info()[1]
        if isinstance(
            exc,
            (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, TimeoutError),
        ):
            return
        super().handle_error(request, client_address)


class _Handler(BaseHTTPRequestHandler):
    server_version = "TutonReader/1.0"
    protocol_version = "HTTP/1.1"
    # Batas tunggu sebelum socket dianggap mati, supaya thread handler tidak
    # menggantung tanpa batas pada readline.
    timeout = 30

    def log_message(self, fmt, *args):  # noqa: A003 - supaya terminal tidak penuh
        return

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except (
            ConnectionResetError,
            BrokenPipeError,
            ConnectionAbortedError,
            TimeoutError,
        ):
            self.close_connection = True

    def _query(self) -> dict:
        parsed = urlparse(self.path)
        raw = urllib.parse.parse_qs(parsed.query)
        return {k: (v[0] if v else "") for k, v in raw.items()}

    def _authorized(self, q: dict) -> bool:
        return bool(_TOKEN) and secrets.compare_digest(q.get("t", ""), _TOKEN)

    def _send(self, status: int, ctype: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _send_text(self, status: int, text: str) -> None:
        self._send(status, "text/markdown; charset=utf-8", text.encode("utf-8", "replace"))

    def do_GET(self):  # noqa: N802 - nama wajib dari BaseHTTPRequestHandler
        with _LOCK:
            _STATE["requests"] = int(_STATE.get("requests", 0)) + 1
        q = self._query()
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path in ("/", "/healthz"):
            payload = dict(_STATE)
            payload.update({"ok": bool(_STATE.get("port")), "base_url": base_url()})
            self._send(
                200,
                "application/json",
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
            return

        if not self._authorized(q):
            self._send_text(
                403,
                "Token tidak valid. Reader hanya untuk agent tuton pada run "
                "yang sedang berjalan.",
            )
            return

        if path == "/soal":
            status, ctype, body = handle_soal(q.get("u", ""), q.get("k", "generic"))
            self._send(status, ctype, body.encode("utf-8", "replace"))
            return

        if path == "/file":
            status, ctype, body = handle_file(q.get("u", ""))
            self._send(status, ctype, body)
            return

        self._send_text(404, "Endpoint tidak dikenal. Paket /soal, /file, /healthz.")


def _pick_port(preferred: int) -> int:
    """Pakai port yang diminta; kalau bentok, cari port bebas berikutnya."""
    for candidate in [preferred, *range(preferred + 1, preferred + 40)]:
        if candidate <= 0:
            continue
        try:
            _QuietServer(("127.0.0.1", candidate), _Handler).server_close()
            return candidate
        except OSError:
            continue
    return 0


def ensure_reader(preferred: int | None = None) -> str:
    """Nyalakan Reader kalau belum jalan. Kembalikan base URL ('' = gagal).

    Idempoten: pemanggilan berulang pada proses yang sama tidak membuat server
    kedua, dan port yang sama dipakai ulang.
    """
    global _SERVER, _TOKEN, _READER
    if _STATE.get("port"):
        return base_url()
    import time as _time

    _TOKEN = secrets.token_urlsafe(18)
    _READER = MoodleReader()

    port = _pick_port(int(preferred or Config.TUTON_READER_PORT or 8765))
    if not port:
        _STATE["error"] = "tidak ada port bebas untuk Reader"
        return ""

    try:
        server = _QuietServer(("127.0.0.1", port), _Handler)
    except OSError as exc:
        _STATE["error"] = f"gagal menjalankan Reader: {exc}"
        return ""

    _SERVER = server
    _STATE.update({"port": port, "started": _time.time(), "requests": 0, "error": ""})
    threading.Thread(target=server.serve_forever, name="tuton-reader", daemon=True).start()
    return base_url()


def stop_reader() -> None:
    global _SERVER
    if _SERVER is not None:
        try:
            _SERVER.shutdown()
            _SERVER.server_close()
        except Exception:  # noqa: BLE001
            pass
        _SERVER = None
    _STATE["port"] = 0


__all__ = [
    "MoodleReader",
    "base_url",
    "ensure_reader",
    "fileurl",
    "handle_file",
    "handle_soal",
    "render_moodle_html",
    "reader",
    "soalu",
    "stop_reader",
    "token",
]
