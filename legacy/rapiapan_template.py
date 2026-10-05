#!/usr/bin/env python3
"""Rapiikan template `ContohFormatJawaban.docx` satu kali.

Template dipakai sebagai lembar jawaban: pipeline menyalinnya, mengisi judul
dan tabel identitas, lalu membuang sisanya mulai dari `Heading 2` pertama
(`generator.docx._siapkan_lembar`). Yang wajib bersih adalah apa yang tersisa
SETELAH pemotongan itu -- kalau tidak, skrip ini akan melaporkan ratusan baris
contoh jawaban yang memang sudah dibuang pipeline sebagai masalah.

Dua hal yang tidak boleh ikut terisi:

- Sel nilai pada tabel identitas. Template diisi identitas mahasiswa contoh,
  jadi kalau `.env` kosong, nama dan NIM orang lain ikut masuk ke berkas yang
  diserahkan ke tutor.
- Paragraf apa pun di atas titik potong yang bukan judul dan bukan label.

Jalankan sekali setelah mengganti template:

    python tools/rapiapan_template.py --check
    python tools/rapiapan_template.py --apply

`--apply` menulis salinan baru, bukan menimpa aslinya, supaya template yang
sedang dipakai pipeline tidak berubah sebelum sempat diperiksa.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from docx import Document  # noqa: E402

from generator.docx import _ganti_teks_paragraf as _ganti_teks  # noqa: E402
from generator.docx import _IDENTITAS_LABELS  # noqa: E402
from generator.docx import _siapkan_lembar  # noqa: E402

TEMPLATE = ROOT / "template" / "ContohFormatJawaban.docx"
OUTPUT = ROOT / "template" / "ContohFormatJawaban.rapi.docx"

# Label pada tabel identitas diambil dari generator, bukan ditulis ulang di
# sini. Tulis ulang berarti tool ini bisa diam-diam ikut usang: label baru
# ditambah ke generator tapi tidak ke tool, lalu identitas mahasiswa contoh
# lolos ke berkas yang diserahkan.
# `IDENTITAS_LABELS` memetakan label (sudah dinormalisasi) ke kunci `meta`.
IDENTITAS_LABELS = _IDENTITAS_LABELS

# Paragraf judul memang sisa yang wajar: `generator.docx._isi_judul`
# menulis ulang paragraf pertama yang tidak kosong, jadi teks di situ selalu
# tertimpa. Yang berbahaya bukan teksnya, tapi kalau paragraf itu hilang --
# karena yang ditulis ulang adalah paragraf PERTAMA yang tidak kosong, dan
# isinya bisa jadi teks soal, bukan judul.
JUDUL_PENANDA = "[Judul Tugas/Diskusi]"


def sisa_isi(path: Path) -> list[str]:
    """Teks yang masih tertinggal setelah pemotongan `_siapkan_lembar`."""
    doc = Document(str(path))
    terpotong = _siapkan_lembar(doc)

    sisa: list[str] = []
    judul_baru = False
    for p in doc.paragraphs:
        teks = p.text.strip()
        if not teks:
            continue
        if p.style is not None and str(p.style.name).startswith("Heading"):
            sisa.append(f"[heading:{p.style.name}] {teks}")
            continue
        if not judul_baru:
            # Paragraf pertama yang tidak kosong adalah judul menurut
            # `_isi_judul`, jadi isinya akan ditimpa. Pastikan ada.
            judul_baru = True
            if JUDUL_PENANDA not in teks:
                sisa.append(f"[judul] {teks}")
            continue
        sisa.append(teks)
    if not judul_baru:
        sisa.insert(0, "Tidak ada paragraf judul: _isi_judul tidak akan menimpanya")

    for tabel in doc.tables:
        for baris in tabel.rows:
            sel = [c.text.strip() for c in baris.cells]
            if len(sel) < 2 or not sel[0]:
                continue
            label = sel[0].lower().rstrip(":").strip()
            nilai = sel[1]
            if label in IDENTITAS_LABELS:
                if nilai:
                    sisa.append(f"[identitas] {sel[0]} = {nilai}")
                continue
            sisa.append(f"[tabel] {sel[0]} | {nilai}")

    if not terpotong:
        sisa.insert(0, "TIDAK ADA Heading 2: pipeline akan jatuh ke _clear_body")
    return sisa


def rapikan(doc: Document) -> tuple[int, bool]:
    """Kosongkan identitas dan beri penanda pada paragraf judul.

    Mengembalikan `(jumlah_baris_identitas, judul_ditandai)`.
    """
    jumlah = 0
    judul_ditandai = False
    for p in doc.paragraphs:
        if p.text.strip():
            _ganti_teks(p, JUDUL_PENANDA)
            judul_ditandai = True
            break
    if not doc.tables:
        return jumlah, judul_ditandai
    for baris in doc.tables[0].rows:
        sel = baris.cells
        if len(sel) < 2:
            continue
        label = sel[0].text.strip().lower().rstrip(":").strip()
        if label not in IDENTITAS_LABELS:
            continue
        if not sel[1].text.strip():
            continue
        _ganti_teks(sel[1].paragraphs[0], "")
        jumlah += 1
    return jumlah, judul_ditandai


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    grup = ap.add_mutually_exclusive_group(required=True)
    grup.add_argument("--check", action="store_true", help="hanya laporkan")
    grup.add_argument("--apply", action="store_true", help="tulis salinan rapi")
    ap.add_argument(
        "--file",
        default="",
        help="periksa berkas ini, bukan template yang dipakai pipeline",
    )
    args = ap.parse_args()

    sumber = Path(args.file) if args.file else TEMPLATE
    if not sumber.is_absolute():
        sumber = ROOT / sumber
    if not sumber.exists():
        print(f"Tidak ada template: {sumber}", file=sys.stderr)
        return 2

    sisa = sisa_isi(sumber)
    print(f"Template  : {sumber.relative_to(ROOT) if ROOT in sumber.parents else sumber}")
    print(f"Sisa isi  : {len(sisa)}")
    for teks in sisa[:25]:
        print(f"  · {teks[:100]}")
    if len(sisa) > 25:
        print(f"  · ... {len(sisa) - 25} baris lagi")

    if args.check:
        print()
        print("Template bersih." if not sisa else "Template masih ada sisa isi.")
        return 0 if not sisa else 1

    doc = Document(str(sumber))
    jumlah, judul = rapikan(doc)
    doc.save(str(OUTPUT))
    print()
    print(f"Sel identitas dikosongkan : {jumlah} baris")
    print(f"Judul ditandai            : {'ya' if judul else 'tidak ada paragraf judul'}")
    print(f"Tulis                     : {OUTPUT.relative_to(ROOT)}")
    print()
    print("Periksa dulu sebelum menimpa:")
    print(f"  python tools/rapiapan_template.py --check --file {OUTPUT.relative_to(ROOT)}")
    print(f"  mv {OUTPUT.name} {TEMPLATE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
