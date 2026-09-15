from __future__ import annotations

import requests

from config import Config

_TIMEOUT = 60


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

    def get(self, path: str, params: dict | None = None) -> requests.Response:
        url = path if path.startswith("http") else Config.MOODLE_BASE_URL + path
        resp = self.session.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp

    def download(self, url: str) -> bytes:
        resp = self.session.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.content

    def check_login(self) -> None:
        resp = self.get("/my/courses.php")
        if resp.status_code == 200 and "login/index.php" in resp.url:
            raise RuntimeError(
                "Sesi Moodle tidak valid / login gagal. "
                "Perbarui MOODLE_COOKIE (MoodleSession) di Settings"
            )