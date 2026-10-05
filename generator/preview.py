from __future__ import annotations

import html as _html
import re
from typing import Any

from docx import Document
from lxml import etree

_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_WM = f"{{{_W}}}"
_MM = f"{{{_M}}}"

_SKIP_INLINE = {
    "pPr", "bookmarkStart", "bookmarkEnd", "proofErr",
    "lastRenderedPageBreak", "sectPr", "rPr", "mPr", "tblPr",
}

_ALIGN_CLASS = {"center": "aln-center", "right": "aln-right", "both": "aln-justify"}

_HTML_DOC = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Preview Dokumen</title>
<script>
window.MathJax = {
  tex: { inlineMath: [], displayMath: [] },
  startup: { typeset: true }
};
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<style>
  :root { color-scheme: light; }
  html, body { margin: 0; padding: 0; background: #fff; }
  body {
    font-family: Georgia, 'Times New Roman', Times, serif;
    font-size: 15px; line-height: 1.65; color: #1a1a1a;
    padding: 48px 56px 80px; max-width: 860px; margin: 0 auto;
  }
  p { margin: 0 0 8px; overflow-wrap: anywhere; }
  p.aln-center { text-align: center; }
  p.aln-right { text-align: right; }
  p.aln-justify { text-align: justify; }
  table { border-collapse: collapse; margin: 12px 0; width: 100%; }
  td { border: 1px solid #b3b3b3; padding: 6px 10px; vertical-align: top; font-size: 14px; }
  .b { font-weight: 700; }
  .i { font-style: italic; }
  mjx-container { margin: 2px 0 !important; }
</style>
</head>
<body>
{content}
</body>
</html>
"""


def _esc(text: str) -> str:
    return _html.escape(text)


def _local(el) -> str:
    return etree.QName(el).localname


def _w_text(el) -> str:
    return "".join(t.text or "" for t in el.iter(f"{_WM}t"))


def _m_text(el) -> str:
    return "".join(t.text or "" for t in el.iter(f"{_MM}t"))


# --- OMML → MathML ---------------------------------------------------------


def _math_text_run(text: str) -> str:
    """Klasifikasikan teks equation jadi m:mi/mn/mo/mtext yang wajar."""
    parts: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        m = re.match(r"[A-Za-z]+", text[i:])
        if m:
            parts.append(f"<mi>{_esc(m.group())}</mi>")
            i += m.end()
            continue
        m = re.match(r"\d+(?:[.,]\d+)?", text[i:])
        if m:
            parts.append(f"<mn>{_esc(m.group())}</mn>")
            i += m.end()
            continue
        c = text[i]
        if c in "+-×=·<>≤≥≠±√∞()[]{},.:;%∁&~_":
            parts.append(f"<mo>{_esc(c)}</mo>")
        else:
            parts.append(f"<mtext>{_esc(c)}</mtext>")
        i += 1
    return "".join(parts)


def _children_math(el) -> str:
    out: list[str] = []
    head = el.text or ""
    if head and head.strip():
        out.append(_math_text_run(head))
    for child in el:
        out.append(_omml_node(child))
        tail = child.tail or ""
        if tail.strip():
            out.append(_math_text_run(tail))
    return "".join(out)


def _omml_node(node) -> str:
    """Konversi satu node OMML jadi MathML. Berbasis struktur yang dihasilkan
    generator/docx.py (r, sSup, sSub, rad, d, m, f, nary, acc, ...)."""
    n = _local(node)
    if n == "t":
        txt = node.text or ""
        return _math_text_run(txt) if txt.strip() else ""
    if n == "r":
        text = _m_text(node)
        return _math_text_run(text) if text.strip() else ""
    if n == "chr":
        return f"<mo>{_esc(node.get(f'{_MM}val') or node.get('val') or '')}</mo>"
    if n in ("e", "num", "den", "deg", "sub", "sup", "fName"):
        inner = _children_math(node)
        return f"<mrow>{inner}</mrow>" if inner else ""
    if n == "sSup":
        base = node.find(f"{_MM}e")
        sup = node.find(f"{_MM}sup")
        b = _omml_node(base) if base is not None else ""
        s = _omml_node(sup) if sup is not None else ""
        return f"<msup><mrow>{b}</mrow><mrow>{s}</mrow></msup>"
    if n == "sSub":
        base = node.find(f"{_MM}e")
        sub = node.find(f"{_MM}sub")
        b = _omml_node(base) if base is not None else ""
        s = _omml_node(sub) if sub is not None else ""
        return f"<msub><mrow>{b}</mrow><mrow>{s}</mrow></msub>"
    if n == "rad":
        e = node.find(f"{_MM}e")
        deg = node.find(f"{_MM}deg")
        e_html = _omml_node(e) if e is not None else ""
        has_deg = deg is not None and any(
            True for _ in deg.iter() if (_.text or "").strip()
        )
        if has_deg:
            d = _omml_node(deg)
            return f"<mroot><mrow>{e_html}</mrow><mrow>{d}</mrow></mroot>"
        return f"<msqrt><mrow>{e_html}</mrow></msqrt>"
    if n == "d":
        beg, end = "(", ")"
        dpr = node.find(f"{_MM}dPr")
        if dpr is not None:
            bc = dpr.find(f"{_MM}begChr")
            ec = dpr.find(f"{_MM}endChr")
            if bc is not None:
                beg = bc.get(f"{_MM}val") or beg
            if ec is not None:
                end = ec.get(f"{_MM}val") or end
        inner = _children_math(node)
        return (
            f'<mfenced open="{_esc(beg)}" close="{_esc(end)}">'
            f"<mrow>{inner}</mrow></mfenced>"
        )
    if n == "m":
        rows = []
        for mr in node.findall(f"{_MM}mr"):
            cells = []
            for e_el in mr.findall(f"{_MM}e"):
                cells.append(f"<mtd>{_omml_node(e_el)}</mtd>")
            rows.append("<mtr>" + "".join(cells) + "</mtr>")
        return "<mtable>" + "".join(rows) + "</mtable>"
    if n == "f":
        num = node.find(f"{_MM}num")
        den = node.find(f"{_MM}den")
        num_html = _omml_node(num) if num is not None else "<mrow/>"
        den_html = _omml_node(den) if den is not None else "<mrow/>"
        return f"<mfrac><mrow>{num_html}</mrow><mrow>{den_html}</mrow></mfrac>"
    if n == "nary":
        chr_val = ""
        for pr in node.findall(f"{_MM}naryPr"):
            c = pr.find(f"{_MM}chr")
            if c is not None:
                chr_val = c.get(f"{_MM}val") or ""
        sub = node.find(f"{_MM}sub")
        sup = node.find(f"{_MM}sup")
        e = node.find(f"{_MM}e")
        op = f"<mo>{_esc(chr_val)}</mo>"
        if sub is not None or sup is not None:
            s_html = _omml_node(sub) if sub is not None else "<mrow/>"
            p_html = _omml_node(sup) if sup is not None else "<mrow/>"
            head = f"<munderover>{op}<mrow>{s_html}</mrow><mrow>{p_html}</mrow></munderover>"
        else:
            head = op
        term = _omml_node(e) if e is not None else ""
        return f"<mrow>{head}{term}</mrow>"
    if n == "acc":
        e = node.find(f"{_MM}e")
        chr_val = ""
        for pr in node.findall(f"{_MM}accPr"):
            c = pr.find(f"{_MM}chr")
            if c is not None:
                chr_val = c.get(f"{_MM}val") or ""
        e_html = _omml_node(e) if e is not None else ""
        return f"<mover><mrow>{e_html}</mrow><mo>{_esc(chr_val)}</mo></mover>"
    if n in ("limLow", "limUpp"):
        e = node.find(f"{_MM}e")
        limit = node.find(f"{_MM}lim")
        e_html = _omml_node(e) if e is not None else "<mrow/>"
        limit_html = _omml_node(limit) if limit is not None else "<mrow/>"
        tag = "munder" if n == "limLow" else "mover"
        return f"<{tag}><mrow>{e_html}</mrow><mrow>{limit_html}</mrow></{tag}>"
    if n == "func":
        fname = node.find(f"{_MM}fName")
        e = node.find(f"{_MM}e")
        return f"<mrow>{_omml_node(fname) if fname is not None else ''}{_omml_node(e) if e is not None else ''}</mrow>"
    inner = _children_math(node)
    return f"<mrow>{inner}</mrow>" if inner else ""


def _math_ml(omath_el) -> str:
    return (
        '<math xmlns="http://www.w3.org/1998/Math/MathML">'
        + _children_math(omath_el)
        + "</math>"
    )


# --- Wordprocessing → HTML --------------------------------------------------


def _run_html(r_el) -> str:
    rpr = r_el.find(f"{_WM}rPr")
    bold = italic = False
    if rpr is not None:
        bold = rpr.find(f"{_WM}b") is not None
        italic = rpr.find(f"{_WM}i") is not None
    text = _w_text(r_el)
    if not text:
        return ""
    cls = []
    if bold:
        cls.append("b")
    if italic:
        cls.append("i")
    class_attr = f' class="{" ".join(cls)}"' if cls else ""
    return f"<span{class_attr}>{_esc(text)}</span>"


def _inline(el, depth: int = 0) -> str:
    if depth > 40:
        return ""
    out: list[str] = []
    for child in el:
        n = _local(child)
        if n in _SKIP_INLINE:
            continue
        if n == "r":
            out.append(_run_html(child))
        elif n in ("oMath", "oMathPara"):
            out.append(_math_ml(child))
        elif n == "hyperlink":
            out.append(_inline(child, depth + 1))
        elif n == "tab":
            out.append("&nbsp;&nbsp;&nbsp;&nbsp;")
        elif n == "br":
            out.append("<br/>")
        elif child.tag.startswith(_WM):
            out.append(_inline(child, depth + 1))
        else:
            tail = child.tail or ""
            if tail.strip():
                out.append(_esc(tail))
    return "".join(out)


def _para_html(p_el, *, indent: str = "", tag: str = "p") -> str:
    """Satu blok paragraf sebagai HTML.

    `tag` dipakai untuk butir daftar: isinya harus dibungkus `<li>`, bukan
    `<p>`. Browser akan memindahkan `<p>` keluar dari `<ol>` karena HTML itu
    tidak mengizinkan paragraf langsung di dalam daftar -- akibatnya nomornya
    hilang dan Daftar Pustaka/daftar bernomor tampil berantakan di preview.
    """
    ppr = p_el.find(f"{_WM}pPr")
    align = None
    style = None
    if ppr is not None:
        jc = ppr.find(f"{_WM}jc")
        if jc is not None:
            align = jc.get(f"{_WM}val")
        ps = ppr.find(f"{_WM}pStyle")
        if ps is not None:
            style = ps.get(f"{_WM}val")
    cls = []
    if align in _ALIGN_CLASS:
        cls.append(_ALIGN_CLASS[align])
    if style:
        low = style.lower()
        if "title" in low:
            cls.append("doc-title")
        elif "heading" in low:
            cls.append("doc-head")
    inner = _inline(p_el, 0).strip()
    if not inner:
        inner = "&nbsp;"
    class_attr = f' class="{" ".join(cls)}"' if cls else ""
    style_attr = f' style="{indent}"' if indent else ""
    return f"<{tag}{class_attr}{style_attr}>{inner}</{tag}>"


def _twip(el, nama: str) -> int | None:
    """Nilai atribut `w:<nama>` sebagai bilangan bulat, atau None."""
    v = el.get(f"{_WM}{nama}")
    if v is None:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _ind_css(p_el) -> str:
    """Terjemahkan `w:ind` paragraf menjadi CSS, dalam satuan titik.

    Dipakai untuk indentasi gantung Daftar Pustaka. Tanpa ini, dokumen yang
    ditampilkan di layar terlihat tanpa indentasi gantung sama sekali --
    padahal berkas yang diunduh memakainya, jadi yang dilihat pengguna di
    preview bukan dokumen yang dia terima.
    """
    ppr = p_el.find(f"{_WM}pPr")
    if ppr is None:
        return ""
    ind = ppr.find(f"{_WM}ind")
    if ind is None:
        return ""
    bagian: list[str] = []
    kiri = _twip(ind, "left") or _twip(ind, "start")
    kanan = _twip(ind, "right")
    gantung = _twip(ind, "hanging")
    if gantung is None:
        # `firstLine` negatif berarti indentasi gantung dalam bentuk lain.
        first = _twip(ind, "firstLine")
        gantung = -first if first is not None and first < 0 else None
    if kiri:
        bagian.append(f"padding-left:{kiri / 20:g}pt")
    if kanan:
        bagian.append(f"padding-right:{kanan / 20:g}pt")
    if gantung:
        bagian.append(f"text-indent:{-gantung / 20:g}pt")
    return ";".join(bagian)


def _numbering_info(path) -> tuple[dict[str, str], dict[str, int]]:
    """Baca `numbering.xml`: peta `w:numId` -> format, dan -> nomor awal.

    Penomoran native Word tidak ada di `document.xml`; yang ada di sana hanya
    rujukan `w:numId`, sedangkan jenis angka dan titik mulainya disimpan di
    `numbering.xml`. Tanpa dua peta ini, semua butir akan tampil sama -- padahal
    dokumen aslinya membedakan butir bernomor dari butir bertanda, dan daftar
    kedua dimulai dari nomor yang ditulis agen, bukan dari kelanjutan butir
    sebelumnya.
    """
    fmt: dict[str, str] = {}
    mulai: dict[str, int] = {}
    try:
        root = etree.fromstring(Document(str(path)).part.numbering_part.blob)
    except Exception:  # noqa: BLE001 - dokumen tanpa numbering.xml tetap bisa dipratinjau
        return fmt, mulai

    abstract_fmt: dict[str, str] = {}
    for abstract in root.findall(f"{_WM}abstractNum"):
        aid = abstract.get(f"{_WM}abstractNumId")
        lvl = abstract.find(f"{_WM}lvl")
        if aid is None or lvl is None:
            continue
        node = lvl.find(f"{_WM}numFmt")
        abstract_fmt[aid] = (
            node.get(f"{_WM}val") if node is not None else "decimal"
        ) or "decimal"

    for num in root.findall(f"{_WM}num"):
        nid = num.get(f"{_WM}numId")
        ref = num.find(f"{_WM}abstractNumId")
        if nid is None:
            continue
        if ref is not None:
            fmt[nid] = abstract_fmt.get(ref.get(f"{_WM}val") or "", "decimal")
        override = num.find(f"{_WM}lvlOverride")
        if override is not None:
            start = override.find(f"{_WM}startOverride")
            angka = _twip(start, "val") if start is not None else None
            if angka:
                mulai[nid] = angka
    return fmt, mulai


def _info_daftar(p_el, num_fmt: dict[str, str]) -> tuple[str | None, str]:
    """Tag daftar (`ol`/`ul`) dan `w:numId` untuk satu paragraf.

    `(None, "")` kalau paragraf ini bukan butir daftar. Penanda gaya
    `ListNumber` pada style tidak dipakai sebagai penentu, karena pipeline
    memasang `w:numPr` langsung pada paragraf -- dan gaya saja tetap dibaca
    sebagai cadangan oleh `_gaya_daftar`.
    """
    ppr = p_el.find(f"{_WM}pPr")
    if ppr is not None:
        numpr = ppr.find(f"{_WM}numPr")
        if numpr is not None:
            node = numpr.find(f"{_WM}numId")
            num_id = node.get(f"{_WM}val") or "" if node is not None else ""
            if num_id:
                return ("ul" if num_fmt.get(num_id) == "bullet" else "ol"), num_id
    # Cadangan: dokumen yang butir daftarnya cuma Bringing style `ListNumber`
    # tanpa `w:numPr`. Tanpa ini, butir seperti itu tampil sebagai paragraf
    # biasa -- persis-butir yang paling sering dilihat pengguna.
    ps = ppr.find(f"{_WM}pStyle") if ppr is not None else None
    if ps is not None:
        gaya = (ps.get(f"{_WM}val") or "").replace(" ", "").lower()
        if gaya == "listnumber":
            return "ol", "style:ListNumber"
        if gaya == "listbullet":
            return "ul", "style:ListBullet"
    return None, ""


def _tbl_html(tbl_el) -> str:
    rows: list[str] = []
    for tr in tbl_el.findall(f"{_WM}tr"):
        cells: list[str] = []
        for tc in tr.findall(f"{_WM}tc"):
            inner = "".join(_para_html(p) for p in tc.findall(f"{_WM}p"))
            cells.append(f"<td>{inner}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "<table>" + "\n".join(rows) + "</table>"


def docx_to_html(path) -> str:
    """Konversi .docx hasil agent menjadi dokumen HTML (dengan equation MathML).

    Butir daftar dikelompokkan jadi `<ol>`/`<ul>` sungguhan, bukan ditulis
    sebagai paragraf biasa. Word menghitung penomorannya sendiri, jadi angka
    yang tampil di preview harus dihitung ulang di sini juga; kalau tidak,
    butir kedua tampil tanpa nomor dan yang dilihat pengguna berbeda dari
    berkas yang dia unduh.
    """
    doc = Document(str(path))
    body = doc.element.body
    num_fmt, num_mulai = _numbering_info(path)
    blocks: list[str] = []
    tag_aktif: str | None = None

    def tutup() -> None:
        if tag_aktif:
            blocks.append(f"</{tag_aktif}>")

    for child in body.iterchildren():
        n = _local(child)
        if n == "tbl":
            tutup()
            tag_aktif = None
            blocks.append(_tbl_html(child))
            continue
        if n != "p":
            continue

        tag, kunci = _info_daftar(child, num_fmt)
        if tag is None:
            tutup()
            tag_aktif = None
            blocks.append(_para_html(child, indent=_ind_css(child)))
            continue

        if tag != tag_aktif:
            tutup()
            tag_aktif = tag
            mulai = num_mulai.get(kunci)
            attr = f' start="{mulai}"' if tag == "ol" and mulai and mulai != 1 else ""
            blocks.append(f"<{tag}{attr}>")
        blocks.append(_para_html(child, indent=_ind_css(child), tag="li"))
    tutup()
    content = "\n".join(b for b in blocks if b.strip())
    return _HTML_DOC.replace("{content}", content)