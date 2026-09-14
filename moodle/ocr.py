from __future__ import annotations

from pathlib import Path

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr

        _reader = easyocr.Reader(["id", "en"], gpu=False, verbose=False)
    return _reader


def is_image(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_EXT


def ocr_image(path: Path) -> str:
    """Ekstrak teks dari gambar soal (untuk model tanpa kemampuan vision)."""
    try:
        reader = _get_reader()
        result = reader.readtext(str(path), detail=0, paragraph=True)
        parts = [str(x).strip() for x in result if str(x).strip()]
        return "\n".join(parts)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! OCR gagal untuk {path.name}: {exc}")
        return ""


def ocr_images(paths: list[Path]) -> list[tuple[Path, str]]:
    """OCR semua gambar yang ada di daftar path."""
    extracted: list[tuple[Path, str]] = []
    images = [p for p in paths if is_image(p)]
    if not images:
        return extracted
    # lazy load: hanya mulai kalau memang ada gambar
    reader = _get_reader()
    for img in images:
        text = ""
        try:
            result = reader.readtext(str(img), detail=0, paragraph=True)
            text = "\n".join(str(x).strip() for x in result if str(x).strip())
        except Exception as exc:  # noqa: BLE001
            print(f"  ! OCR gagal untuk {img.name}: {exc}")
        if text.strip():
            extracted.append((img, text.strip()))
    return extracted