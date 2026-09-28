"""Sesi Moodle terotorisasi + percobaan ulang yang tahan gangguan jaringan.

Fase ini menambah retry karena pipeline sekarang berjalan paralel (`--jobs`) dan
serta mengambil banyak halaman. UT Moodle memang sesekali gagal handshake atau
balas 5xx; tanpa retry, satu gangguan sesaat menghentikan seluruh batch -- persis
hal yang harus dihindari oleh tujuan "selalu berhasil mengambil soal".
"""

from __future__ import annotations

import time

import requests

from config import Config

_TIMEOUT = 60
_RETRIES = 3
_RETRY_SLEEP = (1.5, 4.0)

# Status yang layak dicoba lagi: timeout, rate-limit, dan 5xx.
_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _is_login_url(url: str) -> bool:
    return "login/index.php" in (url or "")


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError,
                          requests.TooManyRedirects)):
        return True
    if isinstance(exc, requests.HTTPError):
        resp = getattr(exc, "response", None)
        return resp is not None and resp.status_code in _RETRY_STATUS
    return False


def _sleep_for(attempt: int) -> None:
    time.sleep(_RETRY_SLEEP[min(attempt, len(_RETRY_SLEEP) - 1)])


class MoodleSession:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
            }
        )
        self.session.cookies.update(Config.cookies())

    def absolute(self, path: str) -> str:
        """Jadikan `path` URL absolut. Path relatif tanpa skema akan ditolak
        requests dengan MissingSchema, jadi base URL wajib ada di sini."""
        path = str(path or "")
        if path.startswith(("http://", "https://")):
            return path
        return Config.base_url() + "/" + path.lstrip("/")

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Permintaan dengan percobaan ulang untuk gangguan sesaat."""
        last: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                resp = self.session.request(method, url, timeout=_TIMEOUT, **kwargs)
            except requests.RequestException as exc:
                last = exc
                if not _should_retry(exc) or attempt + 1 >= _RETRIES:
                    raise
                _sleep_for(attempt)
                continue
            if resp.status_code in _RETRY_STATUS and attempt + 1 < _RETRIES:
                last = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                _sleep_for(attempt)
                continue
            return resp
        raise last if last is not None else RuntimeError("permintaan gagal")

    def get(
        self,
        path: str,
        params: dict | None = None,
        *,
        allow_redirects: bool = True,
    ) -> requests.Response:
        url = self.absolute(path)
        resp = self._request("GET", url, params=params, allow_redirects=allow_redirects)
        resp.raise_for_status()
        return resp

    def download(self, url: str) -> bytes:
        """Unduh berkas biner (lampiran).

        Halaman login diperlakukan sebagai kegagalan, bukan CONTENT: tanpa itu,
        Moodle membalas 303 -> /login/index.php -> 303 -> ... dan yang muncul di
        terminal hanya "Exceeded 30 redirects", yang tidak memberi petunjuk sama
        sekali bahwa penyebabnya cookie kedaluwarsa.
        """
        target = self.absolute(url)
        resp = self._request("GET", target, allow_redirects=True)
        if _is_login_url(str(resp.url)) or resp.status_code in (401, 403):
            raise SessionExpired(
                "Sesi Moodle kedaluwarsa saat mengunduh lampiran. Perbarui "
                "MoodleSession di menu Settings."
            )
        resp.raise_for_status()
        return resp.content

    def check_login(self) -> None:
        """Pastikan cookie masih hidup; gagal dengan pesan yang bisa ditindaklanjuti.

        Pengecekan dilakukan TANPA mengikuti redirect. Kalau ikut redirect,
        Moodle memantulkan halaman login saling bolak-balik sampai requests
        melempar TooManyRedirects, dan pesan itu tidak menjelaskan apa pun.
        """
        try:
            resp = self.get("/my/courses.php", allow_redirects=False)
        except SessionExpired:
            raise
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Tidak bisa menghubungi Moodle ({Config.base_url()}): {exc}. "
                "Periksa koneksi internet."
            ) from exc

        if resp.status_code in (301, 302, 303, 307, 308) or _is_login_url(resp.url):
            raise SessionExpired(
                "Sesi Moodle tidak valid / sudah kedaluwarsa. Buka "
                "elearning.ut.ac.id di browser, login, salin cookie MoodleSession, "
                "lalu tempel di menu Settings."
            )
        resp.raise_for_status()


class SessionExpired(RuntimeError):
    """Cookie Moodle tidak berlaku lagi; perlu diperbarui lewat Settings."""
