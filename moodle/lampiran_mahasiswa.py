"""Deteksi lampiran yang merupakan kiriman mahasiswa lain, bukan soal.

Dari log run sungguhan (Aljabar Linear Elementer 95 sesi 4), lampiran Diskusi
berisi tiga berkas: satu screenshot soal resmi, dan dua PDF jawaban mahasiswa
lain (`Jawaban Diskusi STMA4113 Sesi 4 Habib Musi_058296657.pdf` dan
`ILHAM SULHAKIM.pdf`). Ketiganya ditranskripsi ke satu berkas, lalu agent
penulis membacanya -- dan jawaban yang keluar memakai x=1, y=2, z=3, sama
dengan jawaban mahasiswa yang PDF-nya ikut ditranskripsi.

Jadi ini bukan kegagalan agent, melainkan kegagalan di lapisan pemisahan:
pipeline belum pernah membedakan "lampiran soal" dari "kiriman mahasiswa".
Semua fungsi di sini murni dan tanpa model, karena harus cepat (dipanggil untuk
setiap lampiran) dan harus bisa dipertanggungjawabkan -- keputusan "ini bukan
soal" tidak boleh datang dari tebakan model.

Dua sumber bukti, dipakai berurutan:

1. **Nama berkas.** Pola yang paling sering muncul di UT adalah nama_NIM
   (`Habib Musi_058296657.pdf`) dan `Jawaban <Kata> <Nama> <NIM>.pdf`. Ini
   gratis, dan tidak pernah salah untuk berkas yang namanya memuat NIM 8-12
   digit.
2. **Isi teks.** PDF jawaban mahasiswa hampir selalu memuat blok identitas di
   halaman pertama: "Nama ... / NIM ...". Soal resmi dari UT tidak pernah
   memuat NIM orang. Ini menangkap berkas yang namanya tidak jujur.

Kalau keduanya tidak cocok, lampiran dianggap soal. Kesalahan membaca soal
tidak sengaja sebagai "kiriman mahasiswa" lebih besar daripada sebaliknya:
mengecualikan satu lampiran yang sebenarnya soal membuat pipeline lalu
mencari soalnya di halaman, sedangkan memasukkan jawaban mahasiswa membuat
tugas ini tidak dikerjakan sama sekali.
soalnya di halaman, sedangkan memasukkan jawaban mahasiswa membuat tugas ini
tidak dikerjakan sama sekali.
"""

from __future__ import annotations

import re
from pathlib import Path

# NIM UT: 8 sampai 12 digit, dan di nama berkas hampir selalu pakai
# underscore atau spasi sebelum NIM.
_RE_NIM = re.compile(r"(?<![\d])\d{8,12}(?![\d])")

# Kata yang menandai berkas ini sebuah tugas yang sudah dikerjakan, bukan soal.
_RE_KERJAAN = re.compile(
    r"jawaban"
    r"|(?:tugas|diskusi|esai|talent\s+pool)\s*[.\-_]?\s*\d+"
    r"|(?:praktikum|makalah|karya\s+tulis|laporan)\b"
    r"|(?:pilihan|seksi)\s+\d+",
    re.IGNORECASE,
)

# Kata yang menandai lampiran resmi dari UT.
_RE_RESMI = re.compile(
    r"bmp|bahan\s+pembelajaran|módulo|modul|modul\s+\d|"
    r"mata\s+kuliah|\bmk\b|\btm\b|\bmsim\d|\bmata\d{4}|"
    r"panduan|tugas\s+belajar|kb\d|pertemuan|sesi\s+\d",
    re.IGNORECASE,
)

# Nama orang, dua bentuk. Yang kedua penting justru karena mahasiswa sering
# mengetik namanya seluruh besar: "ILHAM SULHAKIM.pdf" tidak punya NIM, tidak
# punya kata "jawaban", dan tidak punya teks lapisan yang bisa dibaca -- satu-
# satunya bukti ada di nama berkasnya.
_RE_NAMA_CAMPUR = re.compile(
    r"\b[A-Z][a-z]{2,}\s+[A-Z][A-Za-z]{2,}(?:\s+[A-Z][A-Za-z]{2,})*\b"
)
_RE_NAMA_KAPITAL = re.compile(r"\b[A-Z]{3,}(?:[\s_-]+[A-Z]{3,})+\b")

# Berkas yang dikerjakan ulang: "diskusi2_revisi", "tugas1-fix", "jawaban
# revisi". Berpasangan dengan kata tugas/diskusi, karena "revisi" sendiri
# muncul di berkas resmi juga.
_RE_REVISI = re.compile(r"revisi|revisi|perbaikan|perbaikan|fix(?:ed)?\b|jadi\s+final", re.IGNORECASE)

# Blok identitas di halaman pertama dokumen mahasiswa.
_RE_BLOK_IDENTITAS = re.compile(
    r"\bnim\b\s*[:.]?\s*(?:no\.?\s*)?\d{6,14}"
    r"|\bnama\b\s*[:.]?\s*[A-Z][a-z]{2,}"
    r"|\bdikumpulkan\s+(?:oleh|by)\b"
    r"|\bdisusun\s+oleh\b"
    r"|\bsaya\s+meng Duties\b",
    re.IGNORECASE,
)

# Heading jawaban: dokumen mahasiswa selalu menandainya.
_RE_JAWABAN = re.compile(
    r"^\s*(?:\d+\s*[.)]\s*)?(?:jawaban|jawapan)\s*(?:soal\s*)?\d*\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Pola isi soal resmi: memuat perintah dan tanda hubung pengantar.
_RE_PERINTAH = re.compile(
    r"^(?:soal|tugas|diskusi|pertanyaan)\s*\d*\s*$|"
    r"\b(buatlah|carilah|tentukan|hitunglah|jelaskan|uraikan|tuliskan|"
    r"sebutkan|tentukanlah|diskusikan)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Singkatan yang muncul di berkas resmi UT dan tidak pernah di jawaban
# mahasiswa. Kehadiran satu saja sudah cukup.
_RE_SINGKATAN_UT = re.compile(r"\b(MATA|STMA|MATM|MSI|MSIM|PPM|EKTP|MK|TM|KB)\s?\d{3,5}\b")

# Alasan yang dikembalikan supaya bisa dicatat di transkrip dan di peta.
ALASAN_NIM = "nama berkas memuat NIM"
ALASAN_IDENTITAS = "isi memuat blok identitas mahasiswa"
ALASAN_JAWABAN = "isi memuat heading jawaban, bukan soal"


def _teks_awal(path: Path, *, max_bytes: int = 400_000) -> str:
    """Teks lapisan pertama sebuah lampiran, sebatas ``max_bytes``.

    Dibatasi karena berkas ini bisa berukuran besar, dan yang diperiksa hanya
    halaman-halaman awal: blok identitas dan heading jawaban selalu ada di
    sana. PDF tanpa lapisan teks (hasil scan) mengembalikan string kosong --
    lalu keputusan diambil dari nama berkasnya saja, yang untuk PDF jawaban
    mahasiswa hampir selalu memuat NIM.
    """
    if not path.is_file():
        return ""
    try:
        data = path.read_bytes()[:max_bytes]
    except OSError:
        return ""

    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            import pymupdf  # type: ignore

            with pymupdf.open(stream=data, filetype="pdf") as doc:
                return "\n".join(page.get_text() for page in list(doc)[:3])
        except Exception:  # noqa: BLE001 - PDF rusak / bukan PDF asli
            return _pdf_teks_sederhana(data.decode("latin-1", "ignore"))
    if ext in (".docx", ".pptx", ".xlsx"):
        try:
            from zipfile import ZipFile

            with ZipFile(path) as z:
                xml = b"".join(
                    z.read(n)
                    for n in z.namelist()
                    if n.endswith(".xml") and "document" in n or n.endswith("slide1.xml")
                )
            return re.sub(r"<[^>]+>", " ", xml.decode("utf-8", "ignore"))
        except Exception:  # noqa: BLE001
            return ""
    if ext in (".txt", ".md", ".csv"):
        return data.decode("utf-8", "ignore")
    return ""  # gambar: tidak ada teks lapisan; andalkan nama berkas


def _pdf_teks_sederhana(blob: str) -> str:
    """Teks dari PDF yang tidak bisa dibuka pymupdf.

    Hanya untuk menangkap pola yang kuat (NIM, "Nama", "Jawaban:"). Isinya tidak
    dimaksudkan terbaca, hanya dipakai sebagai bukti.
    """
    potong = blob.encode("latin-1", "ignore")
    return potong.decode("latin-1", "ignore")


def looks_like_student_submission(path: Path, text: str = "") -> str | None:
    """Kembalikan alasan kalau lampiran ini kiriman mahasiswa, else ``None``.

    `text` boleh Already diisi pemanggil (mis. transkripsi vision yang sudah
    ada di cache) supaya berkas tidak diekstrak dua kali.
    """
    nama = path.name
    isi = text or _teks_awal(path)

    # 1) NIM di nama berkas. Paling kuat dan paling sering.
    if _RE_NIM.search(nama):
        return ALASAN_NIM

    # 2) Blok identitas di isi. PDF jawaban mahasiswa selalu punya ini.
    if isi and _RE_BLOK_IDENTITAS.search(isi):
        return ALASAN_IDENTITAS

    datar = nama.replace("_", " ")

    # 3) Nama berkas yang jelas-jenis tugas + nama orang.
    if _RE_KERJAAN.search(nama) and (
        _RE_NAMA_CAMPUR.search(datar) or _RE_NAMA_KAPITAL.search(nama)
    ):
        return "nama berkas menandai tugas yang sudah dikerjakan"

    # 4) Nama orang kapital penuh tanpa satu pun penanda resmi. Ini yang
    #    menangkap "ILHAM SULHAKIM.pdf": tanpa NIM, tanpa kata "jawaban",
    #    dan PDF-nya hasil scan sehingga tidak ada teks lapisan untuk diperiksa.
    #    Berkas resmi UT tidak pernah bernama dua kata kapital penuh.
    if _RE_NAMA_KAPITAL.search(nama) and not (
        _RE_RESMI.search(nama) or _RE_SINGKATAN_UT.search(nama)
    ):
        return "nama berkas seperti nama orang (kapital penuh)"

    # 5) Diskusi/tugas yang kena revisi: berkas kerja, bukan soal.
    if _RE_KERJAAN.search(nama) and _RE_REVISI.search(nama):
        return "nama berkas menandai berkas yang sudah dikerjakan ulang"

    # 6) Heading jawaban tanpa apa pun yang menandai ini sebagai soal resmi.
    if isi and _RE_JAWABAN.search(isi):
        ada_perintah = bool(_RE_PERINTAH.search(isi))
        ada_singkatan = bool(_RE_SINGKATAN_UT.search(isi) or _RE_RESMI.search(isi))
        if not (ada_perintah and ada_singkatan):
            return ALASAN_JAWABAN

    return None


def pisahkan_lampiran(
    paths: list[Path],
    transkrip: dict[str, str] | None = None,
) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Bagi lampiran jadi (soal, [(berkas, alasan)]).

    `transkrip` adalah peta {nama_berkas: teks} dari tahap transkripsi, dipakai
    supaya berkas tidak diekstrak dua kali hanya untuk decided.
    """
    soal: list[Path] = []
    mahasiswa: list[tuple[Path, str]] = []
    for path in paths:
        teks = (transkrip or {}).get(path.name, "")
        alasan = looks_like_student_submission(path, teks)
        if alasan:
            mahasiswa.append((path, alasan))
        else:
            soal.append(path)
    return soal, mahasiswa
