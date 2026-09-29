"""Pulihkan struktur matriks dari text layer PDF, tanpa OCR dan tanpa AI.

MASALAH YANG DISOLUSIKAN
------------------------
`pymupdf` membaca text layer PDF sebagai baris teks datar. Matriks yang di
dokumen kontinu terpecah jadi beberapa baris terpisah:

    A = ( 2  1 )
        ( 0  3 )

Karakter di dalamnya sudah BENAR -- tidak ada satu pun karakter yang salah
baca. Yang hilang hanya tata letak 2D-nya. `get_text("rawdict")` menyimpan
posisi SETIAP karakter, jadi matriks bisa dibangun ulang secara deterministik:
tidak ada OCR, tidak ada model, tidak ada tebakan. Janji "rekonstruksi urutan
elemen" yang sebelumnya harus ditebak agen boleh hilang.

KAIDAH KONSERVATIF
------------------
Aturan deteksinya sengaja ketat, dan ini disengaja:

- Kalau tidak yakin itu matriks, teksnya **tidak diubah sama sekali** dan
  dibiarkan seperti hasil bacaan biasa.
--dominated Versi pertama aturan ini terlalu longgar dan salah menandai prosa
  ("Baris 1, Kolom 1: ...") sebagai matriks, yang justru merusak soal yang
  sebenarnya sudah benar. Domba lain: baris yang memuat kata, bullet, atau
  terlalu panjang langsung ditolak.

Konsekuensinya kasus terburuk adalah "tidak ada perubahan" -- sama dengan
perilaku sebelum modul ini ada, tidak pernah lebih buruk.
"""

from __future__ import annotations

import re

# Angka dengan tanda minus. PDF matematika sering memakai U+2212 MINUS SIGN
# (yang benar secara tipografi), bukan ASCII '-'. Kalau ini tidak diterima,
# sel `-6` akan terbaca `6` dan jumlah kolom jadi tidak konsisten -- matriks
# yang sah lalu ditolak, bukan dirusak.
_NUMBER_RE = re.compile(r"[-−]?\d+(?:[.,]\d+)?")

# Kata sepanjang >=3 huruf. Dipakai untuk menolak prosa. Karena itu singkatan
# matriks umum (AB, BC) sengaja boleh muncul, karenaitam hanya 2 huruf dan
# tidak akan terpotong oleh batas ini.
_WORD_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)

# Batas lebar satu baris matriks. Baris matriks nyaris selalu pendek; prosa
# yang jatuh ke rentang ini selalu panjang. 28 ~= satu baris matrix 4x4 di
# Times 10pt.
_MAX_ROW_CHARS = 28

# Jarak y (pt) antar baris yang masih dianggap satu blok matriks. Baris matriks
# berjarak ~16-20pt; paragraf prosa jauh lebih rapat.
_ROW_BAND_PT = 22.0


class _Line:
    """Satu baris teks dengan posisi y-nya."""

    __slots__ = ("y", "text")

    def __init__(self, y: float, text: str) -> None:
        self.y = y
        self.text = text


def _page_lines(page) -> list[_Line]:
    """Kumpulkan baris teks halaman beserta posisi y, terurut dari atas."""
    rows: dict[float, str] = {}
    try:
        blocks = page.get_text("rawdict").get("blocks", [])
    except Exception:  # noqa: BLE001 - format halaman tak terduga
        return []
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                # `rawdict` menyimpan karakter per karakter; `dict` menyimpan
                # string. Dipakai yang sudah jadi kalau tersedia agar tidak
                # perlu menyusun ulang.
                if "chars" in span:
                    text = "".join(ch.get("c", "") for ch in span["chars"])
                else:
                    text = span.get("text", "")
                if not text.strip():
                    continue
                y = float(span["bbox"][1])
                rows[y] = rows.get(y, "") + text
    return [_Line(y, rows[y]) for y in sorted(rows)]


def _matrix_rows(lines: list[_Line]) -> list[list[str]] | None:
    """Kalau `lines` adalah satu blok matriks, kembalikan isninya per baris.

    `None` kalau tidak yakin -- itu sinyal "jangan sentuh teksnya".
    """
    rows: list[list[str]] = []
    for line in lines:
        match = re.search(r"\(\s*([^()]*?)\s*\)", line.text)
        if not match:
            return None
        values = [_norm_number(v) for v in _NUMBER_RE.findall(match.group(1))]
        if not values:
            return None
        # Sisa di DALAM kurung setelah angka dibuang harus kosong/tanda baca.
        residue = _NUMBER_RE.sub("", match.group(1))
        residue = residue.replace("-", "").replace("−", "")
        if _WORD_RE.search(residue):
            return None
        # Sisa di LUAR kurung hanya boleh label pendek ("A =", "AB +", "2A =").
        # Kalimat prosa seperti "Baris 1, Kolom 1: (2 4)" juga punya kurung
        # berisi angka, tapi kata-katanya berada di luar kurung -- wajib
        # ditolak, kalau tidak prosa itu ditulis ulang menjadi matriks dan soal
        # yang sebenarnya benar ikut rusak.
        #
        # Yang diperiksa hanya SEGMENT TERAKHIR sebelum kurung (setelah koma
        # terakhir), karena dokumen matematika lazim diawali kalimat pengantar
        # singkat -- "Jadi, 2A = ( 4 2 )", "Maka, AB = ( 0 13 )". Kalau seluruh
        # teks luar kurung ikut diperiksa, matriks sah seperti tiga contoh itu
        # ikut hilang.
        before = line.text[: match.start()].rstrip()
        tail = before.rsplit(",", 1)[-1]
        if _WORD_RE.search(tail):
            return None
        if len(line.text.strip()) > _MAX_ROW_CHARS:
            return None
        rows.append(values)

    if len(rows) < 2:
        return None
    # Jumlah kolom harus seragam. Kalau tidak, matriksnya memang ambigu
    # (mis. 2x2 vs 1x4) -- JANGAN ditebak, biarkan teks aslinya.
    if len({len(r) for r in rows}) != 1:
        return None
    # Minimal 2 kolom: satu kolom tunggal lebih mungkin baris biasa
    # "(Bab 1)" daripada matriks 2x1.
    if len(rows[0]) < 2:
        return None
    return rows


def _format_matrix(rows: list[list[str]]) -> str:
    """Bentuk notasi matriks yang diminta definisi agen penulis.

    Format WAJIB `[[a, b], [c, d]]` -- sama persis dengan yang tertulis di
    `.opencode/agent/tuton.md` ("matriks -> [[a, b], [c, d]]"). Kalau formatnya
    beda, agen tidak mengenali itu matriks dan akan menuliskannya ulang sebagai
    teks bebas -- yang justru mengembalikan masalah baris pecah.
    """
    inner = ", ".join(
        "[" + ", ".join(_norm_number(v) for v in row) + "]" for row in rows
    )
    return "[" + inner + "]"


def _norm_number(value: str) -> str:
    """Normalkan angka: desimal koma -> titik, minus Unicode -> ASCII."""
    return value.replace(",", ".").replace("−", "-")


def _group_bands(lines: list[_Line]) -> list[list[_Line]]:
    """Kelompokkan baris berurutan yang jaraknya dekat menjadi satu blok."""
    bands: list[list[_Line]] = []
    current: list[_Line] = []
    last_y: float | None = None
    for line in lines:
        if last_y is not None and (line.y - last_y) > _ROW_BAND_PT:
            bands.append(current)
            current = []
        current.append(line)
        last_y = line.y
    if current:
        bands.append(current)
    return bands


def render_pdf_text(path) -> str:
    """Teks PDF dengan matriks dipulihkan ke bentuk matriks.

    Selalu mengembalikan teks; kalau tidak ada matriks yang bisa dipulihkan,
    hasilnya sama persis dengan `page.get_text()` biasa.
    """
    try:
        import fitz
    except ImportError:  # pragma: no cover - pymupdf selalu terpasang
        return ""

    try:
        doc = fitz.open(str(path))
    except Exception:  # noqa: BLE001
        return ""

    page_texts: list[str] = []
    try:
        for page in doc:
            lines = _page_lines(page)
            bands = _group_bands(lines)
            emitted_matrix: set[int] = set()
            out: list[str] = []
            for idx, band in enumerate(bands):
                rows = _matrix_rows(band) if len(band) >= 2 else None
                if rows:
                    out.append(_format_matrix(rows))
                    emitted_matrix.add(idx)
                else:
                    out.extend(line.text for line in band)
            page_texts.append("\n".join(out).strip())
    finally:
        doc.close()
    return "\n\n".join(part for part in page_texts if part).strip()
