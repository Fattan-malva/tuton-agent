"""Template jawaban sebagai skema data, bukan berkas DOCX.

Sebuah template adalah daftar blok (judul, identitas, heading, paragraf, daftar,
tabel, kotak, garis, dan `answer`). Renderer di sini membuat DOCX kosong dari
skema itu. Dua mode:

- `pratinjau`: semua blok tampil, teks sampel lorem ipsum. Dipakai galeri dan
  editor.
- `pekerjaan`: hanya judul, identitas, garis, dan blok ber-`keep` yang tampil,
  berhenti di blok `answer`. Isi jawaban ditulis pipeline setelahnya, jadi teks
  sampel tidak pernah ikut ke berkas yang dikumpulkan.

Semua teks dan garis hitam. Skema tidak punya field warna.
"""

from __future__ import annotations

import copy
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from tools.docx import MARKA_TEMPLATE

FONTS = ("Times New Roman", "Arial", "Calibri", "Cambria")
ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
         "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
TIPE_BLOK = ("title", "identity", "soal", "heading", "text", "numbered", "bullets",
             "table", "box", "rule", "answer", "kesimpulan", "references")
# Blok yang hanya berupa sampel. Di mode pekerjaan dibuang kecuali `keep`.
TIPE_SAMPEL = ("text", "numbered", "bullets", "table", "box", "heading")
# Blok yang isinya ditulis pipeline (soal dari Moodle, jawaban dari agent,
# daftar pustaka dari markdown jawaban). Di mode pekerjaan selalu dibuang,
# supaya tidak dobel dengan yang ditulis pipeline.
TIPE_PIPELINE = ("soal", "kesimpulan", "references")
MAKS_BLOK = 60
MAKS_TEKS = 500
MAKS_ITEM = 30

LOREM = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."


class SkemaSalah(ValueError):
    """Skema template tidak sah; pesannya aman ditampilkan ke pengguna."""


def _teks(nilai, bawaan: str = "", maks: int = MAKS_TEKS) -> str:
    return str(nilai if nilai is not None else bawaan).strip()[:maks]


def _angka(nilai, lo: float, hi: float, bawaan: float) -> float:
    try:
        x = float(nilai)
    except (TypeError, ValueError):
        return bawaan
    return min(max(x, lo), hi)


def _normalisasi_blok(b: dict) -> dict:
    tipe = b.get("type")
    if tipe not in TIPE_BLOK:
        raise SkemaSalah(f"Jenis blok tidak dikenal: {tipe!r}.")
    keep = bool(b.get("keep")) and tipe in TIPE_SAMPEL
    out: dict = {"type": tipe, "keep": keep}
    if tipe == "title":
        out.update(text=_teks(b.get("text"), "Judul"), align=b.get("align", "center") if b.get("align") in ALIGN else "center",
                   size_pt=_angka(b.get("size_pt"), 8, 24, 16), bold=bool(b.get("bold", True)),
                   frame=bool(b.get("frame", False)))
    elif tipe == "soal":
        out.update(min_lines=int(_angka(b.get("min_lines"), 2, 30, 5)))
    elif tipe in ("kesimpulan", "references"):
        out.update()
    elif tipe == "identity":
        out.update(bordered=bool(b.get("bordered", True)))
    elif tipe == "heading":
        out.update(level=int(_angka(b.get("level"), 1, 3, 2)), text=_teks(b.get("text"), "Lorem ipsum"))
    elif tipe == "text":
        out.update(text=_teks(b.get("text"), LOREM, 2000), align=b.get("align", "left") if b.get("align") in ALIGN else "left")
    elif tipe in ("numbered", "bullets"):
        items = [_teks(x, LOREM, 300) for x in (b.get("items") or [LOREM])][:MAKS_ITEM]
        if not items:
            raise SkemaSalah(f"Blok {tipe} harus punya minimal satu item.")
        out.update(items=items)
    elif tipe == "table":
        cols = [_teks(x, "Lorem", 60) for x in (b.get("columns") or ["Lorem", "Ipsum"])][:8]
        out.update(columns=cols, rows=int(_angka(b.get("rows"), 1, 10, 2)), bordered=bool(b.get("bordered", True)))
    elif tipe == "box":
        out.update(text=_teks(b.get("text"), LOREM, 1000), min_lines=int(_angka(b.get("min_lines"), 1, 30, 4)))
    elif tipe == "answer":
        out.update(placeholder=_teks(b.get("placeholder"), "Jawaban mahasiswa"))
    return out


def normalisasi(skema: dict) -> dict:
    """Validasi dan rapikan skema. Melempar `SkemaSalah` kalau tidak sah."""
    if not isinstance(skema, dict):
        raise SkemaSalah("Skema template harus berupa objek.")
    font = skema.get("font", "Times New Roman")
    if font not in FONTS:
        raise SkemaSalah(f"Font {font!r} tidak didukung. Pilih salah satu: {', '.join(FONTS)}.")
    blok_mentah = skema.get("blocks") or []
    if not isinstance(blok_mentah, list) or not (1 <= len(blok_mentah) <= MAKS_BLOK):
        raise SkemaSalah(f"Template harus punya 1 sampai {MAKS_BLOK} blok.")
    blok = [_normalisasi_blok(b) for b in blok_mentah if isinstance(b, dict)]
    tipe = [b["type"] for b in blok]
    if tipe[:1] != ["title"] or tipe.count("title") != 1:
        raise SkemaSalah("Blok pertama harus judul, dan judul hanya boleh satu.")
    for wajib in ("identity", "soal", "answer", "references"):
        if tipe.count(wajib) != 1:
            raise SkemaSalah(f"Template harus punya tepat satu blok {wajib}.")
    if tipe.count("kesimpulan") > 1:
        raise SkemaSalah("Blok kesimpulan hanya boleh satu.")
    urut = [tipe.index(t) for t in ("identity", "soal", "answer")]
    if urut != sorted(urut):
        raise SkemaSalah("Urutannya harus identitas, soal, lalu jawaban.")
    if "kesimpulan" in tipe and tipe.index("kesimpulan") < tipe.index("answer"):
        raise SkemaSalah("Kesimpulan harus sesudah blok jawaban.")
    if tipe[-1] != "references":
        raise SkemaSalah("Daftar pustaka harus blok terakhir.")
    return {
        "font": font,
        "size_pt": _angka(skema.get("size_pt"), 8, 14, 12),
        "line": _angka(skema.get("line"), 1.0, 2.5, 1.15),
        "after_pt": _angka(skema.get("after_pt"), 0, 24, 6),
        "margin_cm": _angka(skema.get("margin_cm"), 1.5, 4.0, 2.5),
        "blocks": blok,
    }


# --------------------------------------------------------------- presets
# Lima template dengan layout berbeda. Semua memakai lorem ipsum dan teks hitam.
PRESET: dict[str, dict] = {
    # Mengikuti panduan APA 7 untuk makalah mahasiswa: Times New Roman 12,
    # margin 2,54 cm, spasi ganda, judul tebal di tengah, daftar pustaka dengan
    # hanging indent.
    "akademik-standar": {
        "name": "Akademik standar (APA 7)",
        "description": "Times New Roman 12, spasi ganda, judul di tengah, identitas di bawah judul, daftar pustaka hanging indent.",
        "font": "Times New Roman", "size_pt": 12, "line": 2.0, "after_pt": 0, "margin_cm": 2.54,
        "blocks": [
            {"type": "title", "text": "Lorem ipsum dolor sit amet", "align": "center", "size_pt": 12, "bold": True},
            {"type": "identity", "bordered": False},
            {"type": "soal", "min_lines": 4},
            {"type": "heading", "level": 1, "text": "Pembahasan"},
            {"type": "heading", "level": 2, "text": "Lorem ipsum dolor"},
            {"type": "text", "text": LOREM, "align": "justify"},
            {"type": "answer", "placeholder": "Jawaban"},
            {"type": "kesimpulan"},
            {"type": "references"},
        ],
    },
    # Gaya laporan ringkas: judul rata kiri dengan garis bawah, identitas tanpa
    # bingkai, poin-poin pendek di bagian jawaban.
    "ringkas": {
        "name": "Ringkas",
        "description": "Arial 11, judul rata kiri dengan garis, poin-poin pendek, cocok untuk tugas tanya-jawab.",
        "font": "Arial", "size_pt": 11, "line": 1.15, "after_pt": 4, "margin_cm": 2.0,
        "blocks": [
            {"type": "title", "text": "Lorem ipsum", "align": "left", "size_pt": 15, "bold": True},
            {"type": "rule"},
            {"type": "identity", "bordered": False},
            {"type": "soal", "min_lines": 3},
            {"type": "heading", "level": 3, "text": "Poin utama"},
            {"type": "bullets", "items": [LOREM, "Ut enim ad minim veniam.", "Quis nostrud exercitation."]},
            {"type": "answer", "placeholder": "Jawaban"},
            {"type": "kesimpulan"},
            {"type": "references"},
        ],
    },
    # Gaya analisis: judul berbingkai, tabel identitas berbingkai, tabel data
    # sebagai pendukung analisis.
    "analitis": {
        "name": "Analitis",
        "description": "Calibri 11, judul berbingkai, identitas berbingkai, kotak analisis dan tabel data.",
        "font": "Calibri", "size_pt": 11, "line": 1.15, "after_pt": 8, "margin_cm": 2.2,
        "blocks": [
            {"type": "title", "text": "Lorem ipsum analysis", "align": "center", "size_pt": 15, "bold": True, "frame": True},
            {"type": "identity", "bordered": True},
            {"type": "soal", "min_lines": 5},
            {"type": "heading", "level": 2, "text": "Data pendukung"},
            {"type": "table", "columns": ["Lorem", "Ipsum", "Dolor"], "rows": 3, "bordered": True},
            {"type": "heading", "level": 2, "text": "Analisis"},
            {"type": "text", "text": LOREM, "align": "justify"},
            {"type": "answer", "placeholder": "Analisis"},
            {"type": "kesimpulan"},
            {"type": "references"},
        ],
    },
    # Gaya tanggapan forum: identitas tanpa bingkai, tiap tanggapan dalam
    # paragraf terpisah, tanpa kesimpulan formal.
    "diskusi": {
        "name": "Diskusi",
        "description": "Arial 11, paragraf tanggapan terpisah, cocok untuk tugas diskusi dan refleksi.",
        "font": "Arial", "size_pt": 11, "line": 1.15, "after_pt": 8, "margin_cm": 2.0,
        "blocks": [
            {"type": "title", "text": "Lorem ipsum diskusi", "align": "left", "size_pt": 14, "bold": True},
            {"type": "identity", "bordered": False},
            {"type": "soal", "min_lines": 3},
            {"type": "heading", "level": 3, "text": "Tanggapan"},
            {"type": "text", "text": LOREM, "align": "left"},
            {"type": "text", "text": LOREM, "align": "left"},
            {"type": "answer", "placeholder": "Tanggapan"},
            {"type": "references"},
        ],
    },
    # Gaya tugas terstruktur: judul berbingkai, bagian bernomor, kotak jawaban
    # per bagian, dan kesimpulan.
    "tugas-terstruktur": {
        "name": "Tugas terstruktur",
        "description": "Cambria 11, bagian bernomor, kotak kerja per bagian, cocok untuk tugas bertahap.",
        "font": "Cambria", "size_pt": 11, "line": 1.25, "after_pt": 6, "margin_cm": 2.3,
        "blocks": [
            {"type": "title", "text": "Lorem ipsum tugas", "align": "center", "size_pt": 14, "bold": True, "frame": True},
            {"type": "identity", "bordered": True},
            {"type": "soal", "min_lines": 4},
            {"type": "heading", "level": 2, "text": "Bagian 1"},
            {"type": "numbered", "items": [LOREM, "Ut enim ad minim."]},
            {"type": "box", "text": LOREM, "min_lines": 3},
            {"type": "heading", "level": 2, "text": "Bagian 2"},
            {"type": "answer", "placeholder": "Jawaban bagian 2"},
            {"type": "kesimpulan"},
            {"type": "references"},
        ],
    },
}


def preset_skema(template_id: str) -> dict | None:
    p = PRESET.get(template_id)
    return copy.deepcopy(p) if p else None


def preset_daftar() -> list[dict]:
    return [{"id": k, "name": v["name"], "description": v["description"]} for k, v in PRESET.items()]


# --------------------------------------------------------------- renderer
def _set_font(run_or_style_font_owner, font: str) -> None:
    """Set nama font di semua slot (ascii/hAnsi/eastAsia/cs), buang font tema."""
    rpr = run_or_style_font_owner.element.get_or_add_rPr()
    rf = rpr.get_or_add_rFonts()
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        q = qn(attr)
        if q in rf.attrib:
            del rf.attrib[q]
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(attr), font)


def _hitam(font_owner) -> None:
    font_owner.font.color.rgb = RGBColor(0, 0, 0)


def _pasang_gaya(doc: Document, s: dict) -> None:
    font = s["font"]
    normal = doc.styles["Normal"]
    normal.font.name = font
    normal.font.size = Pt(s["size_pt"])
    _hitam(normal)
    _set_font(normal, font)
    pf = normal.paragraph_format
    pf.line_spacing = s["line"]
    pf.space_after = Pt(s["after_pt"])
    for nama, delta in (("Heading 1", 4), ("Heading 2", 2), ("Heading 3", 1)):
        st = doc.styles[nama]
        st.font.name = font
        st.font.size = Pt(s["size_pt"] + delta)
        st.font.bold = True
        _hitam(st)
        _set_font(st, font)
        st.paragraph_format.space_before = Pt(s["after_pt"] + 4)
        st.paragraph_format.space_after = Pt(s["after_pt"])
        st.paragraph_format.keep_with_next = True
    judul = doc.styles.add_style("Judul Tugas", WD_STYLE_TYPE.PARAGRAPH)
    judul.base_style = normal
    judul.font.bold = True
    _set_font(judul, font)
    _hitam(judul)
    for nama in ("List Number", "List Bullet"):
        st = doc.styles[nama]
        st.font.name = font
        st.font.size = Pt(s["size_pt"])
        _hitam(st)
        _set_font(st, font)


def _bingkai_tabel(tbl) -> None:
    tbl_pr = tbl._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tbl_pr.append(borders)


def _bingkai_paragraf(par) -> None:
    """Bingkai empat sisi di sekeliling satu paragraf (judul berbingkai)."""
    ppr = par._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "8")
        el.set(qn("w:space"), "4")
        el.set(qn("w:color"), "000000")
        bdr.append(el)
    ppr.append(bdr)


def _tanpa_bingkai(tbl) -> None:
    tbl_pr = tbl._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tbl_pr.append(borders)


def _paragraf_rata(doc: Document, teks: str, align: str = "left", *, bold: bool = False,
                   italic: bool = False, size_pt: float | None = None, style: str | None = None):
    par = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    par.alignment = ALIGN.get(align, WD_ALIGN_PARAGRAPH.LEFT)
    run = par.add_run(teks)
    run.bold = bold or None
    run.italic = italic or None
    if size_pt:
        run.font.size = Pt(size_pt)
    _hitam(run)
    return par


def _render_blok(doc: Document, b: dict, s: dict, mode: str) -> None:
    t = b["type"]
    if t in TIPE_PIPELINE and mode == "pekerjaan":
        return
    if t == "title":
        par = _paragraf_rata(doc, "[Judul]" if mode == "pekerjaan" else b["text"], b["align"],
                             bold=b["bold"], size_pt=b["size_pt"], style="Judul Tugas")
        par.alignment = ALIGN[b["align"]]
        if b.get("frame"):
            _bingkai_paragraf(par)
    elif t == "soal":
        doc.add_paragraph("Soal", style="Heading 2")
        _paragraf_rata(doc, LOREM, "justify")
        tbl = doc.add_table(rows=1, cols=1)
        _bingkai_tabel(tbl)
        row = tbl.rows[0]
        row.height = Cm(0.6 * b["min_lines"])
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        _hitam(row.cells[0].paragraphs[0].add_run("[Gambar atau teks soal]"))
        doc.add_paragraph()
    elif t == "kesimpulan":
        doc.add_paragraph("Kesimpulan", style="Heading 2")
        for item in (LOREM, "Ut enim ad minim veniam."):
            doc.add_paragraph(item, style="List Bullet")
    elif t == "references":
        doc.add_paragraph("Daftar Pustaka", style="Heading 2")
        for bagian in (
            [("Lorem, I. A. (2024). ", False), ("Ipsum dolor sit amet", True), (". Penerbit Dolor.", False)],
            [("Sit, A. B., & Amet, C. (2023). Consectetur adipiscing elit. ", False), ("Jurnal Lorem, 12", True), ("(2), 45–67. https://doi.org/10.0000/lorem", False)],
        ):
            par = doc.add_paragraph()
            pf = par.paragraph_format
            pf.left_indent = Cm(1.27)
            pf.first_line_indent = Cm(-1.27)
            for teks, miring in bagian:
                run = par.add_run(teks)
                run.italic = miring or None
                _hitam(run)
    elif t == "identity":
        tbl = doc.add_table(rows=0, cols=2)
        _bingkai_tabel(tbl) if b["bordered"] else _tanpa_bingkai(tbl)
        for label in ("Nama", "NIM", "Semester", "UT Daerah"):
            cells = tbl.add_row().cells
            r = cells[0].paragraphs[0].add_run(label)
            r.bold = True
            _hitam(r)
            cells[1].paragraphs[0].add_run("")
        for row in tbl.rows:
            row.cells[0].width = Cm(4.0)
            row.cells[1].width = Cm(12.0)
        doc.add_paragraph()
    elif t == "heading":
        if mode == "pekerjaan" and not b["keep"]:
            return
        doc.add_paragraph(b["text"], style=f"Heading {b['level']}")
    elif t == "text":
        if mode == "pekerjaan" and not b["keep"]:
            return
        _paragraf_rata(doc, b["text"], b["align"])
    elif t in ("numbered", "bullets"):
        if mode == "pekerjaan" and not b["keep"]:
            return
        gaya = "List Number" if t == "numbered" else "List Bullet"
        for item in b["items"]:
            doc.add_paragraph(item, style=gaya)
    elif t == "table":
        if mode == "pekerjaan" and not b["keep"]:
            return
        tbl = doc.add_table(rows=1 + b["rows"], cols=len(b["columns"]))
        _bingkai_tabel(tbl) if b["bordered"] else _tanpa_bingkai(tbl)
        for i, nama in enumerate(b["columns"]):
            r = tbl.rows[0].cells[i].paragraphs[0].add_run(nama)
            r.bold = True
            _hitam(r)
        doc.add_paragraph()
    elif t == "box":
        if mode == "pekerjaan" and not b["keep"]:
            return
        tbl = doc.add_table(rows=1, cols=1)
        _bingkai_tabel(tbl)
        row = tbl.rows[0]
        row.height = Cm(0.6 * b["min_lines"])
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        r = row.cells[0].paragraphs[0].add_run(b["text"])
        _hitam(r)
        doc.add_paragraph()
    elif t == "rule":
        par = doc.add_paragraph()
        ppr = par._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "8")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "000000")
        bdr.append(bottom)
        ppr.append(bdr)
    elif t == "answer":
        if mode == "pratinjau":
            _paragraf_rata(doc, f"[{b['placeholder']}]", "left", italic=True)


def render(skema: dict, out: Path, mode: str = "pekerjaan") -> Path:
    """Tulis DOCX dari skema. `mode` = `pratinjau` atau `pekerjaan`."""
    if mode not in ("pratinjau", "pekerjaan"):
        raise ValueError("mode harus pratinjau atau pekerjaan.")
    s = normalisasi(skema)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    m = Cm(s["margin_cm"])
    sec.left_margin = sec.right_margin = m
    sec.top_margin = sec.bottom_margin = Cm(s["margin_cm"] + 0.3)
    _pasang_gaya(doc, s)
    doc.core_properties.keywords = MARKA_TEMPLATE
    for b in s["blocks"]:
        if b["type"] == "answer":
            if mode == "pekerjaan":
                break
            _render_blok(doc, b, s, mode)
            continue
        _render_blok(doc, b, s, mode)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out
