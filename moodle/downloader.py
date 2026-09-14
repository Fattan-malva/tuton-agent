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
            name = self._filename(url, i, data)
            full = dest_dir / name
            full.write_bytes(data)
            saved.append(full)
        return saved

    @staticmethod
    def _filename(url: str, idx: int, data: bytes = b"") -> str:
        path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
        base = os.path.basename(path)
        if base and "." in base and not base.lower().endswith((".php", ".bin")):
            return base
        signatures = (
            (b"\x89PNG", ".png"),
            (b"\xff\xd8\xff", ".jpg"),
            (b"%PDF", ".pdf"),
            (b"PK\x03\x04", ".docx"),
        )
        for signature, extension in signatures:
            if data.startswith(signature):
                return f"lampiran_{idx}{extension}"
        return f"lampiran_{idx}"