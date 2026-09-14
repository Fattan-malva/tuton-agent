from __future__ import annotations

from pathlib import Path

from config import Config
from generator.opencode_runner import run_opencode
from moodle.ocr import is_image, ocr_image

_PDF_EXT = {".pdf"}
_XLSX_EXT = {".xlsx", ".xlsm", ".xls"}
_DOCX_EXT = {".docx"}

_TRANSCRIBE_PROMPT = """Kamu adalah agen transkripsi soal. Sebuah {TYPE} soal matematika terlampir pada pesan ini dan kamu bisa melihatnya langsung (modelmu mendukung vision).

TUGAS:
1. Baca seluruh isi {TYPE} yang terlampir.
2. Salin PERSIS seluruh teks soal ke file:
   {OUT}

ATURAN:
- Jangan menjawab soal, jangan berkomentar, jangan menganalisis.
- Salin hanya isi soal (judul, nomor soal, pertanyaan, instruksi).
- Tulis notasi matematika dengan jelas dalam teks polos/markdown:
  matriks -> [[a, b], [c, d]]; pangkat -> x^2; pecahan -> a/b; akar -> sqrt(...).
- Bagian yang tidak terbaca -> tulis [tidak terbaca].
- Tulis file hasil dalam satu kali operasi (buat file baru / timpa isinya).
- Di akhir, output terminal hanya satu baris: SELESAI"""


def _image_candidates() -> list[tuple[str, str]]:
    cands: list[tuple[str, str]] = []
    primary = Config.OPENCODE_VISION_MODEL_IMAGE
    if primary:
        cands.append((primary, ""))
    backup = Config.OPENCODE_VISION_MODEL_IMAGE_BACKUP
    if backup and backup != primary:
        cands.append((backup, Config.OPENCODE_VISION_VARIANT))
    return cands


def _pdf_candidates() -> list[tuple[str, str]]:
    model = Config.OPENCODE_VISION_MODEL_PDF
    if not model:
        return []
    return [(model, Config.OPENCODE_VISION_VARIANT)]


def _transcribe_with_model(
    path: Path, out_file: Path, model: str, variant: str
) -> str:
    """Jalankan agent transcriber (model vision) untuk menyalin soal ke file."""
    out_file.unlink(missing_ok=True)
    kind = "PDF" if path.suffix.lower() in _PDF_EXT else "gambar"
    prompt = (
        _TRANSCRIBE_PROMPT.replace("{TYPE}", kind)
        .replace("{OUT}", str(out_file))
    )
    try:
        run_opencode(
            prompt,
            agent="transcriber",
            attach=[str(path)],
            model=model,
            variant=variant,
            timeout=Config.TUTON_TIMEOUT_TRANSCRIBE,
        )
    except TimeoutError:
        print(f"    ! transkripsi {path.name} timeout di model {model}")
        out_file.unlink(missing_ok=True)
        return ""
    if out_file.exists() and out_file.stat().st_size > 20:
        text = out_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    out_file.unlink(missing_ok=True)
    return ""


def _transcribe_image(path: Path, out_file: Path) -> str:
    """Vision-model transcription, lalu fallback easyocr."""
    for model, variant in _image_candidates():
        text = _transcribe_with_model(path, out_file, model, variant)
        if text and len(text) >= 10:
            return text
    text = ocr_image(path)
    if text:
        return "(fallback easyocr)\n" + text
    return ""


def _transcribe_pdf(path: Path, out_file: Path) -> str:
    """Vision-model transcription, lalu fallback pymupdf."""
    for model, variant in _pdf_candidates():
        text = _transcribe_with_model(path, out_file, model, variant)
        if text and len(text) >= 10:
            return text
    try:
        import fitz

        doc = fitz.open(str(path))
        parts = [pg.get_text().strip() for pg in doc]
        text = "\n".join(p for p in parts if p).strip()
        if text:
            return "(fallback pymupdf)\n" + text
    except Exception as exc:  # noqa: BLE001
        print(f"    ! pymupdf gagal untuk {path.name}: {exc}")
    return ""


def _extract_xlsx(path: Path) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), data_only=True, read_only=True)
    blocks: list[str] = []
    for ws in wb.worksheets:
        head = f"[Sheet: {ws.title}]"
        rows: list[str] = []
        for row in ws.iter_rows(values_only=True):
            cells = [
                str(c).strip() for c in row if c is not None and str(c).strip()
            ]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            blocks.append(head + "\n" + "\n".join(rows))
    wb.close()
    return "\n\n".join(blocks)


def _extract_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    blocks: list[str] = []
    paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    if paras:
        blocks.append("\n".join(paras))
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            blocks.append("\n".join(rows))
    return "\n\n".join(blocks)


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _XLSX_EXT:
        return _extract_xlsx(path)
    if ext in _DOCX_EXT:
        return _extract_docx(path)
    return ""


def process_attachment(path: Path, work_dir: Path) -> str:
    """Ekstrak isi satu lampiran jadi teks (untuk soal.md).

    - Gambar/PDF: salin via agent transcriber (model vision), lalu fallback
      easyocr / pymupdf.
    - Excel/docx: ekstrak lewat Python.
    Kembalikan teks; string kosong bila tidak bisa (perlu cek manual).
    """
    ext = path.suffix.lower()
    if is_image(path) or ext in _PDF_EXT:
        if not path.is_file():
            return ""
        out_file = work_dir / f"transkrip_{path.stem}.md"
        if ext in _PDF_EXT:
            return _transcribe_pdf(path, out_file)
        return _transcribe_image(path, out_file)
    try:
        return _extract_text(path).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"    ! ekstraksi gagal untuk {path.name}: {exc}")
        return ""