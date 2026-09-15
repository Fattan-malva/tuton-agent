from __future__ import annotations

import base64
import os
import re
import urllib.parse
from pathlib import Path

from moodle.auth import MoodleSession

_DATA_URI_RE = re.compile(r"^data:image/(?P<mime>[a-zA-Z0-9.+-]+);base64,(?P<data>[A-Za-z0-9+/=\r\n]+?)$")

_MIME_EXT = {
    "png": ".png",
    "jpeg": ".jpg",
    "jpg": ".jpg",
    "gif": ".gif",
    "webp": ".webp",
    "bmp": ".bmp",
    "tiff": ".tiff",
    "svg+xml": ".svg",
}


class AttachmentDownloader:
    def __init__(self, session: MoodleSession) -> None:
        self.session = session

    def download_all(self, urls: list[str], dest_dir: Path) -> list[Path]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for i, url in enumerate(urls, 1):
            if url.startswith("data:image/"):
                full = self._save_data_uri(url, dest_dir, i)
                if full is not None:
                    saved.append(full)
                continue
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
    def _save_data_uri(url: str, dest_dir: Path, idx: int) -> Path | None:
        m = _DATA_URI_RE.match(url)
        if not m:
            print(f"  ! data URI tidak dikenali (lampiran #{idx}), dilewati")
            return None
        try:
            payload = base64.b64decode(re.sub(r"\s+", "", m.group("data")))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! gagal decode data URI #{idx}: {exc}")
            return None
        ext = _MIME_EXT.get(m.group("mime").lower(), ".png")
        full = dest_dir / f"soal_gambar_{idx}{ext}"
        full.write_bytes(payload)
        return full

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