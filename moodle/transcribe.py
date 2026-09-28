from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
import subprocess
import time

from config import Config, OUTPUT_DIR, PROJECT_ROOT
from generator.opencode_runner import run_opencode
from moodle.ocr import IMAGE_EXT as _IMAGE_EXT
from moodle.ocr import is_image, ocr_image

_PDF_EXT = {".pdf"}
_XLSX_EXT = {".xlsx", ".xlsm", ".xls"}
_DOCX_EXT = {".docx"}
_PPTX_EXT = {".pptx", ".pptm"}
_OOXML_EXT = _DOCX_EXT | _PPTX_EXT
# Format Office lama (biner OLE, bukan zip) tidak bisa dibaca tanpa LibreOffice.
_LEGACY_OFFICE_EXT = {".doc", ".ppt", ".pps", ".xls", ".odt", ".odp", ".rtf"}

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
    """Model vision untuk gambar: pilih otomatis yang mendukung input image."""
    return list(_candidates(pdf=False))


def _pdf_candidates() -> list[tuple[str, str]]:
    """Model vision untuk PDF: pilih otomatis yang mendukung input image+pdf."""
    return list(_candidates(pdf=True))


# ============================================================================
# Auto-deteksi model vision.
#
# PENTING: flag `opencode models --verbose` sudah dihapus di opencode terbaru
# (CLI balas "Unrecognized flag"). Versi lama modul ini memanggilnya, subprocess
# gagal, daftar model jadi kosong, lalu SEMUA transkripsi gambar/PDF jatuh ke
# easyocr di CPU -- lambat, sering salah baca, dan butuh unduhan bobot besar.
# Itu sumber keterlambatan terbesar di pipeline.
#
# Strategi baru (bertingkat, selalu berakhir ke sesuatu yang jalan):
#   1. CLI lama yang masih mendukung --verbose -> pakai info capabilities.
#   2. CLI baru (satu id per baris) -> pakai urutan dari .env
#      (OPENCODE_VISION_PREFER), lalu model lain yang tersedia.
#   3. CLI gagal total -> pakai daftar statis di bawah.
# Hasil transkripsi tetap divalidasi (panjang minimum) sebelum diterima, jadi
# model yang ternyata tidak bisa melihat hanya membuang sedikit waktu, bukan
# menghasilkan-soal palsu.
# ============================================================================
_models_cache: tuple[float, list[dict]] | None = None
_MODELS_CACHE_TTL = 300  # detik: daftar model jarang berubah

# Dipakai hanya bila `opencode models` sama sekali tidak bisa dipanggil.
# Model gratis yang umumnya mendukung vision.
_STATIC_VISION_FALLBACK = (
    "opencode/muse-spark-1.3-contributor-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/ling-3.0-flash-fin-free",
    "google/gemini-2.5-flash",
    "openrouter/xiaomi/mimo-v2.5",
    "openrouter/qwen/qwen2.5-vl-72b-instruct",
)


def _parse_verbose_models(data: str) -> list[dict]:
    """Parse `opencode models --verbose` (opencode lama): `id` lalu JSON."""
    models: list[dict] = []
    pending_name: str | None = None
    depth = 0
    buf: list[str] = []
    for raw in data.splitlines():
        if pending_name is None:
            line = raw.strip()
            if not line:
                continue
            pending_name = line
            depth = 0
            buf = []
            continue
        if not buf and "{" not in raw:
            continue
        buf.append(raw)
        depth += raw.count("{") - raw.count("}")
        if depth == 0:
            try:
                meta = json.loads("\n".join(buf))
            except json.JSONDecodeError:
                meta = {}
            if meta:
                full = f"{meta.get('providerID', '')}/{meta.get('id', '')}".strip("/")
                caps = meta.get("capabilities") or meta.get("modalities") or {}
                inp = caps.get("input") or {}
                if not inp:
                    inp = meta.get("input") or {}
                models.append(
                    {
                        "full_id": full,
                        "status": meta.get("status", "active"),
                        "variants": meta.get("variants") or [],
                        "input": inp,
                    }
                )
            pending_name = None
    return models


def _run_models_cli(extra_args: list[str]) -> tuple[int, str]:
    """Jalankan `opencode models <extra_args>` -> (returncode, output gabungan)."""
    try:
        from generator.opencode_runner import _resolve_opencode

        cmd = _resolve_opencode() + ["models"] + extra_args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            cwd=str(PROJECT_ROOT),
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except Exception as exc:  # noqa: BLE001 - apa pun blokirannya, lanjut fallback
        print(f"    ! gagal memanggil opencode models: {exc}")
        return 1, str(exc)


def _parse_plain_models(data: str) -> list[str]:
    """Parse `opencode models` versi baru: satu `provider/id` per baris."""
    ids: list[str] = []
    skip_words = ("DESCRIPTION", "USAGE", "FLAGS", "GLOBAL FLAGS", "ERROR")
    for raw in data.splitlines():
        line = raw.strip()
        if not line or line.startswith(skip_words) or line.startswith("-"):
            continue
        if line.startswith(("opencode.exe", "At line:", "CategoryInfo", "FullyQualified")):
            continue  # noise dari PowerShell
        if "/" not in line or " " in line:
            continue
        ids.append(line)
    return list(dict.fromkeys(ids))


def _fetch_models() -> list[dict]:
    """Daftar model opencode yang tersedia; sertakan info capability bila ada."""
    global _models_cache
    now = time.time()
    if _models_cache is not None and now - _models_cache[0] < _MODELS_CACHE_TTL:
        return _models_cache[1]

    models: list[dict] = []
    code, out = _run_models_cli(["--verbose"])
    if code == 0 and "{" in out:
        models = _parse_verbose_models(out)
    if not models:
        code, out = _run_models_cli([])
        if code == 0:
            for mid in _parse_plain_models(out):
                models.append({"full_id": mid, "status": "active", "variants": [], "input": {}})
    if not models:
        print("    ! opencode models tidak mengembalikan daftar; pakai daftar statis.")
        models = [
            {"full_id": mid, "status": "active", "variants": [], "input": {}}
            for mid in _STATIC_VISION_FALLBACK
        ]

    _models_cache = (now, models)
    return models


def _filter_vision_models(models: list[dict], *, pdf: bool) -> list[dict]:
    """Model yang MELEWATI pemeriksaan (tidak menyaring, hanya mengurutkan).

    Nama Disini sengaja tidak menyaring model: opencode yang memutuskan routing
    lampiran, dan kita tidak bisa tahu 100% capability sebuah model dari CLI.
    Yang penting: jangan pernah mengembalikan daftar kosong, karena itu yang
    membuat pipeline jatuh ke easyocr.
    """
    active: list[dict] = []
    for m in models:
        mid = (m.get("full_id") or "").strip()
        if not mid:
            continue
        if (m.get("status") or "active") != "active":
            continue
        inp = m.get("input") or {}
        # Bila CLI memang memberi info capability, hormati (mis. model teks
        # murni tidak layak dicoba untuk gambar).
        if inp:
            if not inp.get("image"):
                continue
            if pdf and inp.get("pdf") is False:
                continue
        active.append(m)
    if not active:
        active = [
            m for m in models if (m.get("full_id") or "").strip()
        ] or [{"full_id": mid, "input": {}} for mid in _STATIC_VISION_FALLBACK]
    return active


def _match_model_id(pref: str, ids: list[str]) -> str | None:
    pref = pref.strip().strip("/")
    for mid in ids:
        if mid == pref or mid.endswith("/" + pref):
            return mid
    return None


def _ordered_vision_ids(*, pdf: bool) -> list[str]:
    """Urutan model vision: prefer dari .env > daftar statis > semua tersedia."""
    available = _filter_vision_models(_fetch_models(), pdf=pdf)
    ids: list[str] = []
    for m in available:
        fid = (m.get("full_id") or "").strip()
        if fid and fid not in ids:
            ids.append(fid)
    prefer = list(Config.OPENCODE_VISION_PREFER) + list(_STATIC_VISION_FALLBACK)
    if prefer:
        ranked: list[str] = []
        for candidate in prefer:
            hit = _match_model_id(candidate, ids)
            if hit and hit not in ranked:
                ranked.append(hit)
        ids = ranked + [i for i in ids if i not in ranked]
    return ids


def _candidates(*, pdf: bool) -> list[tuple[str, str]]:
    """(model_id, variant) untuk transcriber, dibatasi jumlah.

    Pembatasan itu penting: setiap percobaan adalah satu proses `opencode run`
    berbiaya nyata. Tanpa batas, daftar model yang tersedia (ratusan) akan
    dicoba satu per satu dan satu lampiran bisa menahan belasan menit.
    """
    models = _filter_vision_models(_fetch_models(), pdf=pdf)
    variants_map = {
        m.get("full_id", ""): set(m.get("variants") or []) for m in models
    }
    variant = Config.OPENCODE_VISION_VARIANT
    cands: list[tuple[str, str]] = []
    for mid in _ordered_vision_ids(pdf=pdf)[:_MAX_VISION_TRIES]:
        v = variant if variant and variant in variants_map.get(mid, set()) else ""
        cands.append((mid, v))
    if not cands:
        # Fallback: minimal satu percobaan lewat model default opencode.
        cands = [("", variant)]
    return cands


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
        result = run_opencode(
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
    if result.returncode != 0:
        print(f"    ! transkripsi {path.name} gagal di model {model} (exit {result.returncode})")
    if out_file.exists() and out_file.stat().st_size > 20:
        text = out_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    out_file.unlink(missing_ok=True)
    return ""


# ---------------------------------------------------------------------------
# Cache transkripsi.
#
# Vision model butuh puluhan detik per gambar. Tanpa cache, setiap `--force`
# atau retry mengulang pekerjaan yang persis sama. Kunci = SHA-256 isi berkas,
# jadi berkas yang tidak berubah tidak pernah ditranskripsi dua kali, dan berkas
# yang berubah (dosen upload versi baru) otomatis misses cache.
# ---------------------------------------------------------------------------
_TRANSKRIP_DIR = OUTPUT_DIR / ".cache" / "transkrip"
_MIN_TEXT = 10  # di bawah ini dianggap model tidak bisa membaca
_MAX_VISION_TRIES = int((Config.OPENCODE_VISION_TRIES or 3))
# Teks layer PDF dianggap sah bila >= ini karakter. Sengaja RENDAH: PDF soal
# di UT sering cuma 2-3 baris, dan teks layer selalu lebih otoritatif
# daripada OCR. Ambang 200 pernah membuat PDF valid ditolak, lalu fallback
# easyocr mengubah "1NF" jadi "INF" -- AI menjawab tentang simbol yang salah.
_MIN_PDF_TEXT_CHARS = int(Config.TUTON_PDF_TEXT_MIN_CHARS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_file(path: Path) -> Path:
    return _TRANSKRIP_DIR / f"{_sha256(path)}{path.suffix.lower()}.md"


def _cache_get(path: Path) -> str:
    cache = _cache_file(path)
    try:
        if not cache.exists():
            return ""
        if time.time() - cache.stat().st_mtime > 7 * 24 * 3600:
            return ""  # kadaluarsa setelah seminggu
        return cache.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _cache_put(path: Path, text: str) -> None:
    if not text.strip():
        return
    try:
        _TRANSKRIP_DIR.mkdir(parents=True, exist_ok=True)
        _cache_file(path).write_text(text, encoding="utf-8")
    except OSError:
        pass


def _usable(text: str) -> bool:
    return bool(text and len(text.strip()) >= _MIN_TEXT)


def _transcribe_image(path: Path, out_file: Path) -> str:
    """Transkripsi gambar: cache -> vision model -> easyocr."""
    cached = _cache_get(path)
    if _usable(cached):
        print(f"    · cache transkripsi {path.name} (dipakai ulang)")
        return cached
    for model, variant in _image_candidates():
        text = _transcribe_with_model(path, out_file, model, variant)
        if _usable(text):
            _cache_put(path, text)
            return text
    text = ocr_image(path)
    if _usable(text):
        text = "(fallback easyocr)\n" + text
        _cache_put(path, text)
        return text
    return ""


def _pdf_text_layer(path: Path) -> str:
    """Teks yang sudah tercetak di PDF (bukan hasil scan). Murah, jadi selalu
    dicoba lebih dulu -- ini yang memangkas sebagian besar waktu transkripsi."""
    try:
        import fitz

        doc = fitz.open(str(path))
        try:
            parts = [page.get_text().strip() for page in doc]
        finally:
            doc.close()
    except Exception as exc:  # noqa: BLE001
        print(f"    ! pymupdf gagal untuk {path.name}: {exc}")
        return ""
    text = "\n\n".join(part for part in parts if part).strip()
    return text if len(re.sub(r"\s+", " ", text)) >= _MIN_PDF_TEXT_CHARS else ""


def _transcribe_pdf(path: Path, out_file: Path) -> str:
    """Transkripsi PDF: cache -> teks layer -> vision model -> render per halaman."""
    cached = _cache_get(path)
    if _usable(cached):
        print(f"    · cache transkripsi {path.name} (dipakai ulang)")
        return cached

    if Config.TUTON_PDF_TEXT_FIRST:
        layer = _pdf_text_layer(path)
        if layer:
            _cache_put(path, layer)
            return layer

    for model, variant in _pdf_candidates():
        text = _transcribe_with_model(path, out_file, model, variant)
        if _usable(text):
            _cache_put(path, text)
            return text

    layer = _pdf_text_layer(path)
    if layer:
        _cache_put(path, layer)
        return layer

    try:
        import fitz

        doc = fitz.open(str(path))
        parts: list[str] = []
        try:
            for index, page in enumerate(doc, 1):
                image_path = path.parent / f".page_{path.stem}_{index}.png"
                page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(str(image_path))
                try:
                    page_text = _transcribe_image(image_path, out_file)
                    if page_text:
                        parts.append(f"--- halaman {index} ---\n{page_text}")
                finally:
                    image_path.unlink(missing_ok=True)
        finally:
            doc.close()
        if parts:
            text = "\n\n".join(parts)
            _cache_put(path, text)
            return text
    except Exception as exc:  # noqa: BLE001
        print(f"    ! render halaman gagal untuk {path.name}: {exc}")
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


def _extract_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _ooxml_slide_text(archive: zipfile.ZipFile, prefix: str) -> list[str]:
    """Kumpulkan teks dari XML OOXML (slide/notes) sesuai urutan nomor."""
    import xml.etree.ElementTree as ET

    a_ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

    def _number(name: str) -> tuple[int, str]:
        stem = name.rsplit("/", 1)[-1].removesuffix(".xml")
        digits = "".join(ch for ch in stem if ch.isdigit())
        return (int(digits) if digits else 0, stem)

    names = sorted(
        (n for n in archive.namelist() if n.startswith(prefix) and n.endswith(".xml")),
        key=_number,
    )
    slides: list[str] = []
    for name in names:
        try:
            root = ET.fromstring(archive.read(name))
        except ET.ParseError:
            continue
        lines: list[str] = []
        # <a:p> = satu paragraf; <a:t> = run teks di dalamnya.
        for para in root.iter(f"{a_ns}p"):
            text = "".join(node.text or "" for node in para.iter(f"{a_ns}t")).strip()
            if text:
                lines.append(text)
        if lines:
            label = name.rsplit("/", 1)[-1].removesuffix(".xml")
            slides.append(f"[{label}]\n" + "\n".join(lines))
    return slides


def _extract_pptx(path: Path) -> str:
    """Teks slide + catatan pembicara dari file .pptx (zip + XML, tanpa library)."""
    blocks: list[str] = []
    with zipfile.ZipFile(path) as archive:
        blocks.extend(_ooxml_slide_text(archive, "ppt/slides/slide"))
        blocks.extend(_ooxml_slide_text(archive, "ppt/notesSlides/notesSlide"))
    return "\n\n".join(blocks)


def _extract_embedded_images(path: Path, work_dir: Path) -> list[str]:
    """Transcribe gambar yang tertanam di dokumen OOXML (docx/pptx).

    Gambar kecil (logo/asap ikon) dilewati: transkripsi vision mahal (~20-60s per
    gambar) tapi isinya tidak pernah berupa soal. Jumlahnya juga dibatasi supaya
    satu lampiran tidak menahan proses belasan menit.
    """
    min_bytes = 12_000
    max_images = 12
    results: list[str] = []
    skipped_small = 0
    with zipfile.ZipFile(path) as archive:
        media = sorted(
            n for n in archive.namelist()
            if n.startswith(("word/media/", "ppt/media/"))
            and not n.endswith("/")
            and Path(n).suffix.lower() in _IMAGE_EXT
        )
        index = 0
        for name in media:
            payload = archive.read(name)
            if len(payload) < min_bytes:
                skipped_small += 1
                continue
            if index >= max_images:
                break
            index += 1
            base = name.rsplit("/", 1)[-1]
            image_path = work_dir / f".embedded_{path.stem}_{index}{Path(base).suffix.lower()}"
            image_path.write_bytes(payload)
            try:
                text = _transcribe_image(image_path, work_dir / f"transkrip_{image_path.stem}.md")
                if text:
                    results.append(f"[gambar #{index} di dalam dokumen: {base}]\n{text}")
            finally:
                image_path.unlink(missing_ok=True)
    if skipped_small:
        print(f"    · {skipped_small} gambar kecil (logo) diabaikan.")
    return results


def _extract_docx_images(path: Path, work_dir: Path) -> list[str]:
    """Transcribe images embedded inside a DOCX attachment."""
    return _extract_embedded_images(path, work_dir)


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _XLSX_EXT:
        return _extract_xlsx(path)
    if ext in _PPTX_EXT:
        return _extract_pptx(path)
    if ext in _DOCX_EXT:
        return _extract_docx(path)
    if ext in {".txt", ".csv", ".tsv", ".md"}:
        return _extract_text_file(path)
    if ext in _LEGACY_OFFICE_EXT:
        print(
            f"    ! {path.name}: format lama '{ext}' belum didukung. "
            "Simpan ulang sebagai PDF/PPTX/DOCX, atau unggah gambarnya."
        )
        return ""
    print(
        f"    ! {path.name}: ekstensi '{ext or '(tanpa ekstensi)'}' tidak dikenali. "
        "Gunakan PDF, gambar (png/jpg), DOCX, XLSX, PPTX, atau TXT."
    )
    return ""


_QUESTION_MARK_RE = re.compile(r"\?")
_DIGIT_RE = re.compile(r"\d")


def looks_like_question_text(text: str, *, min_chars: int = 25) -> bool:
    """Heuristik: apakah teks ini masuk akal sebagai isi soal?

    Sengaja konservatif. Menolak teks yang meragukan lebih baik daripada
    membiarkan model yang tidak bisa melihat imagenya mengarang isi soal --
    karena AI tetap akan menjawab berdasarkan teks itu.
    """
    body = (text or "").strip()
    if len(body) < min_chars:
        return False
    if _QUESTION_MARK_RE.search(body):
        return True
    # Soal hitung/matematika hampir selalu punya angka.
    if len(_DIGIT_RE.findall(body)) >= 4:
        return True
    # Soal esai: cari kata tanya atau kata perintah yang lazim.
    return bool(
        re.search(
            r"\b(jelaskan|uraikan|sebutkan|tuliskan|Buatkan|Buatlah|"
            r"diskusikan|carilah|tentukan|hitunglah|apakah|apa|jelaskanlah)\b",
            body,
            re.I,
        )
    )


def transcribe_many(paths: list[Path], work_dir: Path) -> dict[str, str]:
    """Transkripsi beberapa lampiran; mengembalikan {nama_berkas: teks}.

    Dipakai otomatis oleh pipeline setelah lampiran diunduh. Setiap berkas
    diproses independen supaya satu yang gagal tidak menghentikan yang lain.
    """
    results: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = process_attachment(path, work_dir)
        except Exception as exc:  # noqa: BLE001 - satu berkas gagal tidak stop yang lain
            print(f"    ! transkripsi {path.name} gagal: {exc}")
            continue
        if not text.strip():
            continue
        if not looks_like_question_text(text):
            print(
                f"    ! transkripsi {path.name} ditolak: hasil tidak terbaca "
                "seperti soal (kemungkinan model vision tidak bisa melihat "
                "berkas ini)."
            )
            continue
        results[path.name] = text.strip()
    return results


def process_attachment(path: Path, work_dir: Path) -> str:
    """Ekstrak isi satu lampiran jadi teks (untuk soal.md).

    - Gambar/PDF: salin via agent transcriber (model vision), lalu fallback
      easyocr / pymupdf.
    - Excel/docx/pptx: ekstrak lewat Python (teks + gambar tertanam).
    Kembalikan teks; string kosong bila tidak bisa (perlu cek manual).
    """
    ext = path.suffix.lower()
    if not path.is_file():
        print(f"    ! lampiran tidak ditemukan: {path}")
        return ""
    if is_image(path) or ext in _PDF_EXT:
        out_file = work_dir / f"transkrip_{path.stem}.md"
        if ext in _PDF_EXT:
            return _transcribe_pdf(path, out_file)
        return _transcribe_image(path, out_file)
    try:
        text = _extract_text(path).strip()
        if ext in _OOXML_EXT:
            embedded = _extract_embedded_images(path, work_dir)
            if embedded:
                text = "\n\n".join(part for part in (text, *embedded) if part)
        return text
    except Exception as exc:  # noqa: BLE001
        print(f"    ! ekstraksi gagal untuk {path.name}: {exc}")
        return ""