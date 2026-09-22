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


def _para_html(p_el) -> str:
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
    return f"<p{class_attr}>{inner}</p>"


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
    """Konversi .docx hasil agent menjadi dokumen HTML (dengan equation MathML)."""
    doc = Document(str(path))
    body = doc.element.body
    blocks: list[str] = []
    for child in body.iterchildren():
        n = _local(child)
        if n == "p":
            blocks.append(_para_html(child))
        elif n == "tbl":
            blocks.append(_tbl_html(child))
    content = "\n".join(b for b in blocks if b.strip())
    return _HTML_DOC.replace("{content}", content)