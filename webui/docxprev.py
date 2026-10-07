"""Render berkas DOCX menjadi HTML sederhana untuk modal pratinjau.

Pratinjau di tab Result tidak perlu selengkap Word. Yang dibutuhkan hanya
struktur yang enak dibaca -- judul, paragraf, tebal/miring, tabel, daftar,
dan gambar -- diterjemahkan ke HTML polos yang seluruh gayanya datang dari
`app.css` (kelas `.prev-*`). Satu-satunya dependensi python-docx sudah
dipakai pipeline, dan dimuat malas di dalam `pratinjau()` supaya server web
tidak menambah waktu mulai hanya untuk membuka tab Result.
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

RE_HEADING = re.compile(r"^(?:heading|head)\s*(\d)$", re.I)
NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# Gambar yang bisa ditampilkan peramban. EMF/WMF sengaja dibuang: pemuatan
# gambar yang tidak akan tampil hanya membuang-buang byte preview.
MIME_GAMBAR = {"image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"}
# Anggaran seluruh gambar dalam satu pratinjau. Satu dokumen bisa memuat
# puluhan tangkapan layar; kalau semuanya disertakan, modal berhenti beberapa
# detik hanya untuk mengurai base64.
ANGGARAN_GAMBAR = 4 * 1024 * 1024


def _flag(rpr, tag: str) -> bool:
    """Nilai sebuah penanda format seperti `w:b`.

    Ketiadaan `w:val` berarti aktif; `val="0"` berarti sebaliknya. Tanpa
    pemeriksaan ini, `w:b w:val="0"` (teks yang sengaja di-bold-off) akan
    ikut menjadi tebal.
    """
    if rpr is None:
        return False
    el = rpr.find(tag)
    if el is None:
        return False
    val = el.get(NS_W + "val")
    return val is None or val not in {"0", "false", "off", "none"}


def _src_gambar(node, doc, ctx: dict) -> str:
    """Ambil data URI dari `a:blip` di dalam `w:drawing`/`w:pict`.

    Relasinya menempel di part dokumen utama, bukan di paragraf, jadi `doc`
    yang dibawa ke sini -- dan `related_parts` yang mengubah rId menjadi
    blob berkas gambarnya.
    """
    from docx.oxml.ns import qn

    for el in node.iter():
        if el.tag != qn("a:blip"):
            continue
        rid = el.get(qn("r:embed")) or el.get(qn("r:link"))
        if not rid:
            continue
        try:
            bagian = doc.part.related_parts[rid]
        except KeyError:
            continue
        blob = getattr(bagian, "blob", None)
        mime = getattr(bagian, "content_type", "") or ""
        if not blob or mime not in MIME_GAMBAR:
            continue
        if len(blob) > ctx["sisa"]:
            continue
        ctx["sisa"] -= len(blob)
        return f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}"
    return ""


def _run_html(run, doc, ctx: dict) -> str:
    from docx.oxml.ns import qn

    rpr = run.find(qn("w:rPr"))
    keluar: list[str] = []
    for anak in run:
        if anak.tag == qn("w:t"):
            keluar.append(html.escape(anak.text or ""))
        elif anak.tag == qn("w:tab"):
            keluar.append("\t")
        elif anak.tag in (qn("w:br"), qn("w:cr")):
            keluar.append("<br/>")
        elif anak.tag in (qn("w:drawing"), qn("w:pict"), qn("w:object")):
            src = _src_gambar(anak, doc, ctx)
            if src:
                keluar.append(f'<img class="prev-gbr" src="{src}" alt="" loading="lazy"/>')
        elif anak.tag == qn("w:noBreakHyphen"):
            keluar.append("-")
    isi = "".join(keluar)
    if not isi:
        return ""
    if _flag(rpr, qn("w:b")):
        isi = f"<strong>{isi}</strong>"
    if _flag(rpr, qn("w:i")):
        isi = f"<em>{isi}</em>"
    if _flag(rpr, qn("w:strike")):
        isi = f"<s>{isi}</s>"
    if _flag(rpr, qn("w:u")):
        isi = f"<u>{isi}</u>"
    return isi


def _url_hiperlink(node, doc) -> str:
    from docx.oxml.ns import qn

    anchor = node.get(qn("w:anchor"))
    rid = node.get(qn("r:id"))
    if not rid:
        return anchor or ""
    rel = doc.part.rels.get(rid)
    if rel is None:
        return anchor or ""
    return getattr(rel, "target_ref", "") or anchor or ""


def _teks_paragraf(par, doc, ctx: dict) -> str:
    """Teks satu paragraf, termasuk yang ada di dalam hyperlink/track-change."""
    from docx.oxml.ns import qn

    keluar: list[str] = []
    for anak in par._p:
        if anak.tag == qn("w:r"):
            keluar.append(_run_html(anak, doc, ctx))
        elif anak.tag == qn("w:hyperlink"):
            isi = "".join(
                _run_html(r, doc, ctx) for r in anak if r.tag == qn("w:r")
            )
            url = _url_hiperlink(anak, doc)
            if url and isi:
                keluar.append(
                    f'<a href="{html.escape(url, quote=True)}" target="_blank" '
                    f'rel="noopener">{isi}</a>'
                )
            else:
                keluar.append(isi)
        elif anak.tag in (qn("w:ins"), qn("w:sdt")):
            isi = anak.iter(qn("w:r"))
            keluar.append("".join(_run_html(r, doc, ctx) for r in isi))
    return "".join(keluar)


def _tabel_html(tabel, doc, ctx: dict) -> str:
    baris: list[str] = []
    for i, r in enumerate(tabel.rows):
        sel: list[str] = []
        for c in r.cells:
            isi = "".join(_teks_paragraf(p, doc, ctx) for p in c.paragraphs)
            sel.append(f"<td>{isi}</td>")
        baris.append(f"<tr>{''.join(sel)}</tr>")
    return f'<table class="prev-tbl">{"".join(baris)}</table>'


def _blok_paragraf(par, doc, ctx: dict) -> tuple[str, str]:
    """Ubah satu paragraf jadi (jenis blok, HTML) untuk digabung nanti."""
    try:
        gaya = (par.style.name if par.style is not None else "") or ""
    except (ValueError, AttributeError):
        gaya = ""
    isi = _teks_paragraf(par, doc, ctx)
    if not isi.strip():
        return ("kosong", "")

    m = RE_HEADING.match(gaya.strip())
    if m:
        n = min(int(m.group(1)), 6)
        return ("h", f"<h{n}>{isi}</h{n}>")
    if gaya.strip().lower() == "title":
        return ("h", f"<h1>{isi}</h1>")
    if gaya.strip().lower().startswith("list"):
        jenis = "ol" if any(t in gaya.lower() for t in ("number", "ordered")) else "ul"
        return (f"li-{jenis}", f"<li>{isi}</li>")
    return ("p", f"<p>{isi}</p>")


def pratinjau(path: Path) -> str:
    """Ubah satu berkas `.docx` jadi HTML blok untuk modal pratinjau.

    Melempar exception bila berkas bukan DOCX yang sah; pemanggil yang
    menerjemahkannya jadi pesan galat ke pengguna.
    """
    from docx import Document
    from docx.table import Table

    doc = Document(str(path))
    ctx: dict = {"sisa": ANGGARAN_GAMBAR}
    blok: list[tuple[str, str]] = []
    for isi in doc.iter_inner_content():
        if isinstance(isi, Table):
            blok.append(("tabel", _tabel_html(isi, doc, ctx)))
            continue
        blok.append(_blok_paragraf(isi, doc, ctx))

    # Item daftar berurutan dibungkus satu <ul>/<ol>; kalau tidak digabung,
    # setiap baris menghasilkan daftar sendiri-sendiri dan nomornya mulai
    # dari 1 lagi.
    keluar: list[str] = []
    i = 0
    while i < len(blok):
        jenis, isi = blok[i]
        if jenis.startswith("li-"):
            t = jenis[3:]
            grup: list[str] = []
            while i < len(blok) and blok[i][0] == jenis:
                grup.append(blok[i][1])
                i += 1
            keluar.append(f"<{t}>{''.join(grup)}</{t}>")
            continue
        if jenis != "kosong":
            keluar.append(isi)
        i += 1

    return "\n".join(keluar)
