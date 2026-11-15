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
# OMML (persamaan Word). Rumus yang ditulis `tools/docx.py` masuk ke DOCX
# sebagai `m:oMath`, bukan sebagai teks -- Word menampilkannya dengan font
# matematika, sedangkan pratinjau versi lama tidak membacanya sama sekali
# sehingga seluruh rumus hilang dan paragrafnya terlihat kosong.
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
# Gambar yang bisa ditampilkan peramban. EMF/WMF sengaja dibuang: pemuatan
# gambar yang tidak akan tampil hanya membuang-buang byte preview.
MIME_GAMBAR = {"image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"}
# Anggaran seluruh gambar dalam satu pratinjau. Satu dokumen bisa memuat
# puluhan tangkapan layar; kalau semuanya disertakan, modal berhenti beberapa
# detik hanya untuk mengurai base64.
ANGGARAN_GAMBAR = 4 * 1024 * 1024


def _t(tag: str) -> str:
    """Nama tag OMML tanpa namespace, mis. `sSup`."""
    return tag[len(M):] if tag.startswith(M) else tag


def _anak(node, tag: str):
    for el in node:
        if el.tag == M + tag:
            return el
    return None


def _dalam(node, tag: str) -> str:
    """Render isi `m:<tag>` sebagai HTML; kosong kalau elemennya tidak ada."""
    el = _anak(node, tag)
    return _omml_html(el) if el is not None else ""


def _val(el, nama: str = "val", bawaan: str = "") -> str:
    if el is None:
        return bawaan
    v = el.get(M + nama) or el.get(NS_W + nama)
    return bawaan if v is None else v


# Karakter pembuka/penutup untuk `m:d`. OMML menyimpan `begChr`/`endChr`
# sebagai atribut, dan nilai kosong berarti kurung tidak ditampilkan.
_KURUNG = {"": "", "(": "(", ")": ")", "[": "[", "]": "]", "{": "{", "}": "}",
           "|": "|", "‖": "‖", "〈": "〈", "〉": "〉", "⟨": "⟨", "⟩": "⟩"}


def _omml_html(node) -> str:
    """Render satu elemen OMML jadi HTML.

    Yang ditangani adalah kosakata yang benar-benar dipakai `tools/docx.py`
    saat menulis rumus: run, kurung, pangkat/indeks, pecahan, akar, matriks,
    baris rata, operator besar (sigma/integral), aksen, dan lim. Tag lain
    dirender isinya saja supaya tidak ada teks yang hilang -- lebih baik
    tampil tanpa format daripada hilang seperti sebelumnya.
    """
    if node is None:
        return ""
    tag = _t(node.tag)

    # ---------- run: teks literal
    if tag == "t":
        return html.escape(node.text or "")
    if tag == "r":
        teks = "".join(
            html.escape(e.text or "") if _t(e.tag) == "t" else ""
            for e in node
        )
        return f'<span class="prev-mrun">{teks}</span>' if teks else ""

    # ---------- kurung: m:d
    if tag == "d":
        pr = _anak(node, "dPr")
        buka = _val(_anak(pr, "begChr"), bawaan="(") if pr is not None else "("
        tutup = _val(_anak(pr, "endChr"), bawaan=")") if pr is not None else ")"
        buka = _KURUNG.get(buka, buka)
        tutup = _KURUNG.get(tutup, tutup)
        isi = "".join(_omml_html(e) for e in node if _t(e.tag) == "e")
        return (
            f'<span class="prev-mdelim"><span class="prev-mopen">{html.escape(buka)}</span>'
            f"{isi}"
            f'<span class="prev-mclose">{html.escape(tutup)}</span></span>'
        )

    # ---------- pangkat / indeks
    if tag == "sSup":
        return (
            f'<span class="prev-mscript">{_dalam(node, "e")}'
            f'<sup>{_dalam(node, "sup")}</sup></span>'
        )
    if tag == "sSub":
        return (
            f'<span class="prev-mscript">{_dalam(node, "e")}'
            f'<sub>{_dalam(node, "sub")}</sub></span>'
        )
    if tag == "sSubSup":
        return (
            f'<span class="prev-mscript">{_dalam(node, "e")}'
            f'<sub>{_dalam(node, "sub")}</sub><sup>{_dalam(node, "sup")}</sup></span>'
        )

    # ---------- pecahan
    if tag == "f":
        pr = _anak(node, "fPr")
        jenis = _val(_anak(pr, "type"), bawaan="bar") if pr is not None else "bar"
        kelas = "prev-mfrac" + (" noline" if jenis in ("noBar", "lin") else "")
        return (
            f'<span class="{kelas}"><span class="prev-mnum">{_dalam(node, "num")}</span>'
            f'<span class="prev-mden">{_dalam(node, "den")}</span></span>'
        )

    # ---------- akar
    if tag == "rad":
        pr = _anak(node, "radPr")
        sembunyi = _val(_anak(pr, "degHide"), bawaan="0") if pr is not None else "0"
        deg = "" if sembunyi in {"1", "true", "on"} else _dalam(node, "deg")
        isi = _dalam(node, "e")
        if deg.strip():
            return f'<span class="prev-mrad"><sup class="prev-mdeg">{deg}</sup>√<span class="prev-mradic">{isi}</span></span>'
        return f'<span class="prev-mrad">√<span class="prev-mradic">{isi}</span></span>'

    # ---------- matriks / kisi
    if tag == "m":
        baris: list[str] = []
        for mr in node:
            if _t(mr.tag) != "mr":
                continue
            sel = "".join(
                f'<span class="prev-mcell">{_omml_html(e)}</span>'
                for e in mr if _t(e.tag) == "e"
            )
            baris.append(f'<span class="prev-mrow">{sel}</span>')
        return f'<span class="prev-mmatrix">{"".join(baris)}</span>'

    # ---------- baris rata (aligned/cases)
    if tag == "eqArr":
        baris = "".join(
            f'<span class="prev-mrow">{_omml_html(e)}</span>'
            for e in node if _t(e.tag) == "e"
        )
        return f'<span class="prev-meqarr">{baris}</span>'

    # ---------- operator besar: sigma, integral, produk
    if tag == "nary":
        pr = _anak(node, "naryPr")
        chr_ = _val(_anak(pr, "chr"), bawaan="∫") if pr is not None else "∫"
        bawah = _dalam(node, "sub")
        atas = _dalam(node, "sup")
        batas = ""
        if bawah or atas:
            batas = (
                f'<span class="prev-mlims"><sup>{atas}</sup><sub>{bawah}</sub></span>'
            )
        return (
            f'<span class="prev-mnary"><span class="prev-mop">{html.escape(chr_)}</span>'
            f"{batas}{_dalam(node, 'e')}</span>"
        )

    # ---------- aksen (vektor, topi, garis atas)
    if tag == "acc":
        pr = _anak(node, "accPr")
        chr_ = _val(_anak(pr, "chr"), bawaan="\u0302") if pr is not None else "\u0302"
        return (
            f'<span class="prev-macc"><span class="prev-macc-chr">{html.escape(chr_)}</span>'
            f"{_dalam(node, 'e')}</span>"
        )

    # ---------- batas atas/bawah (lim, overset)
    if tag in ("limLow", "limUpp"):
        dasar = _dalam(node, "e")
        batas = _dalam(node, "lim")
        return (
            f'<span class="prev-mlim"><span class="prev-mlim-top">{batas}</span>'
            f'<span class="prev-mlim-base">{dasar}</span></span>'
        )

    # ---------- teks terformat di dalam rumus (m:rPr sudah ditangani run)
    if tag.endswith("Pr") or tag == "ctrlPr":
        return ""

    # ---------- sisanya: render anak-anaknya
    return "".join(_omml_html(e) for e in node)



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
            else:
                # Gambar yang tidak bisa ditampilkan (mis. EMF/WMF) tetap
                # diberi keterangan, supaya paragrafnya tidak tampak kosong
                # dan pembaca tahu ada objek yang tidak didukung pratinjau.
                keluar.append('<span class="prev-objek">[objek tidak dapat ditampilkan]</span>')
        elif anak.tag in (qn("w:noBreakHyphen"),):
            keluar.append("-")
        elif anak.tag in (M + "oMath", M + "oMathPara"):
            keluar.append(_omml_html(anak))
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
        elif anak.tag in (M + "oMath", M + "oMathPara"):
            # Persamaan level-paragraf bukan anak `w:r`, jadi harus ditangkap
            # di sini. Tanpa cabang ini rumus yang berdiri sendiri (justru
            # yang paling penting, mis. matriks dan sistem persamaan) tidak
            # pernah sampai ke pratinjau.
            keluar.append(_omml_html(anak))
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
    from docx.oxml.ns import qn

    baris: list[str] = []
    for r in tabel.rows:
        sel: list[str] = []
        for c in r.cells:
            # Sel bisa berisi tabel bersarang, jadi isinya dibaca dari
            # `iter_inner_content()` -- bukan hanya paragraf. Tanpa ini,
            # sel yang isinya tabel (kop identitas, rubrik) keluar kosong.
            bagian: list[str] = []
            for isi in c.iter_inner_content():
                if hasattr(isi, "rows") and hasattr(isi, "columns"):
                    bagian.append(_tabel_html(isi, doc, ctx))
                else:
                    bagian.append(_teks_paragraf(isi, doc, ctx))
            sel.append(f"<td>{''.join(bagian)}</td>")
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
