from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from moodle.auth import MoodleSession


class AttachmentDownloader:
    def __init__(self, session: MoodleSession) -> None:
        self.session = session

    def download_all(self, urls: list[str], dest_dir: Path) -> list[Path]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for i, url in enumerate(urls, 1):
            try:
                data = self.session.download(url)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! gagal download {url[:120]}: {exc}")
                continue
            name = self._filename(url, i)
            full = dest_dir / name
            full.write_bytes(data)
            saved.append(full)
        return saved

    @staticmethod
    def _filename(url: str, idx: int) -> str:
        path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
        base = os.path.basename(path)
        if base and "." in base:
            return base
        return f"lampiran_{idx}"