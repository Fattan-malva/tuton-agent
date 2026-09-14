from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_LATEX_REPLACEMENTS = {
    r"\rightarrow": "→",
    r"\to": "→",
    r"\leftarrow": "←",
    r"\leftrightarrow": "↔",
    r"\times": "×",
    r"\cdot": "·",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\neq": "≠",
    r"\pm": "±",
    r"\infty": "∞",
    r"\ldots": "...",
}

# OMML (Word math) namespace
_MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _omml_run(text: str) -> str:
    return f"<m:r><m:t>{_esc(text)}</m:t></m:r>"


def _omml_sup(base: str, exp: str) -> str:
    return f"<m:sSup><m:e>{base}</m:e><m:sup>{exp}</m:sup></m:sSup>"


def _omml_sqrt(inner: str) -> str:
    return (
        '<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr>'
        f"<m:deg/><m:e>{inner}</m:e></m:rad>"
    )


def _omml_matrix(cell_rows: list[list[str]]) -> str:
    body = "".join(
        "<m:mr>" + "".join(f"<m:e>{cell}</m:e>" for cell in row) + "</m:mr>"
        for row in cell_rows
    )
    matrix = f"<m:m>{body}</m:m>"
    return (
        '<m:d><m:dPr><m:begChr m:val="["/><m:endChr m:val="]"/></m:dPr>'
        f"<m:e>{matrix}</m:e></m:d>"
    )


def _math_nodes(s: str) -> list[str]:
    """Parse mini-notasi matematika jadi daftar element OMML (xml string).

    Didukung: matriks [[a, b], [c, d]], pangkat x^2, akar sqrt(...),
    angka desimal, variabel huruf, dan operator + - = × · ( ) .
    Jika ada yang tak dikenali dipakai sebagai teks biasa.
    """
    nodes: list[str] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c.isspace() or c == ",":
            i += 1
            continue
        if s.startswith("[[", i):
            j = s.find("]]", i)
            if j == -1:
                nodes.append(_omml_run(s[i:]))
                break
            inner = s[i + 2 : j]
            rows: list[list[str]] = []
            for part in re.split(r"\]\s*,\s*\[", inner):
                cells = [c.strip() for c in part.split(",") if c.strip()]
                rows.append(
                    ["".join(_math_nodes(cell)) if cell else _omml_run("") for cell in cells]
                )
            nodes.append(_omml_matrix(rows))
            i = j + 2
            continue
        if s.startswith("sqrt(", i):
            depth, k = 1, i + 5
            while k < n and depth:
                if s[k] == "(":
                    depth += 1
                elif s[k] == ")":
                    depth -= 1
                k += 1
            inner = s[i + 5 : k - 1] if depth == 0 else s[i + 5 :]
            nodes.append(_omml_sqrt("".join(_math_nodes(inner))))
            i = k
            continue
        if c == "^":
            base = nodes.pop() if nodes else _omml_run("")
            j = i + 1
            while j < n and (s[j].isspace() or s[j] == ","):
                j += 1
            if j < n and s[j] == "(":
                depth, k = 1, j + 1
                while k < n and depth:
                    if s[k] == "(":
                        depth += 1
                    elif s[k] == ")":
                        depth -= 1
                    k += 1
                exp = "".join(_math_nodes(s[j + 1 : k - 1])) if depth == 0 else _omml_run(s[j:k])
                nodes.append(_omml_sup(base, exp))
                i = k
                continue
            if j < n:
                exp_part = s[j:]
                m = re.match(r"\d+(?:\.\d+)?|[A-Za-z]+", exp_part)
                if m:
                    exp = "".join(_math_nodes(m.group()))
                    nodes.append(_omml_sup(base, exp))
                    i = j + len(m.group())
                    continue
            nodes.append(_omml_run("^"))
            i += 1
            continue
        m = re.match(r"\d+(?:\.\d+)?", s[i:])
        if m:
            nodes.append(_omml_run(m.group()))
            i += m.end()
            continue
        if c.isalpha():
            nodes.append(_omml_run(c))
            i += 1
            continue
        nodes.append(_omml_run(c))
        i += 1
    return nodes


def _equation_omml(math_str: str) -> str:
    content = "".join(_math_nodes(math_str)) or _omml_run("")
    return f'<m:oMath xmlns:m="{_MATH_NS}">{content}</m:oMath>'


def _append_equation(paragraph, math_str: str):
    try:
        from lxml import etree

        el = etree.fromstring(_equation_omml(math_str).encode("utf-8"))
        paragraph._p.append(el)
    except Exception:  # noqa: BLE001
        paragraph.add_run(math_str)


def _add_runs(paragraph, text: str):
    """Terapkan **bold** dan *italic* sederhana ke satu paragraf."""
    text = _normalize_text(text)
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            _add_italic_runs(paragraph, text[pos:m.start()])
        run = paragraph.add_run(m.group(1))
        run.bold = True
        pos = m.end()
    _add_italic_runs(paragraph, text[pos:])


def _add_italic_runs(paragraph, text: str):
    text = _normalize_text(text)
    pos = 0
    for m in _ITALIC_RE.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos:m.start()])
        run = paragraph.add_run(m.group(1))
        run.italic = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def _normalize_text(text: str) -> str:
    """Hilangkan artefak LaTeX/Markdown yang tidak boleh tampil mentah di Word."""
    for source, replacement in _LATEX_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    text = re.sub(r"\\(?:left|right)\b", "", text)
    text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"(?<![A-Za-z])rightarrow(?![A-Za-z])", "→", text)
    text = re.sub(r"(?<![A-Za-z])leftarrow(?![A-Za-z])", "←", text)
    return text


def _is_table_row(line: str) -> bool:
    return line.strip().startswith("|") and line.strip().endswith("|") and "|" in line[1:]


def _render_markdown(doc: Document, md: str):
    from docx.shared import Cm

    lines = md.splitlines()
    i = 0
    ordered_idx = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Inline math: convert one-line $...$ expressions to Word equations.
        if line.count("$") >= 2 and "$$" not in line:
            p = doc.add_paragraph()
            parts = re.split(r"\$([^$]+)\$", line)
            for idx, part in enumerate(parts):
                if not part:
                    continue
                if idx % 2:
                    _append_equation(p, _normalize_text(part))
                else:
                    _add_runs(p, part)
            i += 1
            continue

        # Tabel markdown
        if _is_table_row(line) and i + 1 < len(lines) and re.match(
            r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]
        ):
            header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows = []
            j = i + 2
            while j < len(lines) and _is_table_row(lines[j]):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            table = doc.add_table(rows=1, cols=len(header_cells))
            table.style = "Table Grid"
            for col, cell in enumerate(header_cells):
                table.rows[0].cells[col].text = cell
                table.rows[0].cells[col].paragraphs[0].runs[0].bold = True
            for row_data in rows:
                cells = table.add_row().cells
                for col in range(len(header_cells)):
                    if col < len(row_data):
                        cells[col].text = row_data[col]
                    else:
                        cells[col].text = ""
            doc.add_paragraph()
            i = j
            continue

        # Equation Word (OMML): baris yang memuat $$...$$
        if "$$" in line:
            m = re.match(r"^([-*])\s+", line)
            style = "List Bullet" if m else None
            base = re.sub(r"^[-*]\s+", "", line)
            p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
            parts = base.split("$$")
            for idx, seg in enumerate(parts):
                if idx % 2 == 0:
                    if seg.strip():
                        _add_runs(p, seg)
                else:
                    _append_equation(p, seg)
            if re.fullmatch(r"\$\$.*\$\$", base.strip()):
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            ordered_idx = 0
            i += 1
            continue

        # Heading
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            p = doc.add_paragraph()
            run = p.add_run(m.group(2).strip())
            run.bold = True
            if level == 2:
                run.font.size = Pt(14)
            elif level == 3:
                run.font.size = Pt(12)
            i += 1
            continue

        # Bullet list
        if re.match(r"^[-*]\s+", line):
            p = doc.add_paragraph(style="List Bullet")
            _add_runs(p, re.sub(r"^[-*]\s+", "", line))
            i += 1
            ordered_idx = 0
            continue

        # Ordered list
        mo = re.match(r"^(\d+)[.)]\s+(.*)$", line)
        if mo:
            if ordered_idx == 0:
                ordered_idx = 1
            p = doc.add_paragraph(style="List Number")
            _add_runs(p, mo.group(2))
            ordered_idx += 1
            i += 1
            continue

        ordered_idx = 0
        # Empty line → skip; blockquote → plain paragraph
        if not line.strip():
            i += 1
            continue
        p = doc.add_paragraph()
        _add_runs(p, line.strip())
        i += 1


def build_docx(
    *,
    jawaban_md: str,
    soal_text: str,
    meta: dict,
    out_docx: Path,
    include_soal: bool = True,
) -> Path:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    rpr = style.element.get_or_add_rPr()
    rf = rpr.get_or_add_rFonts()
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        q = qn(attr)
        if q in rf.attrib:
            del rf.attrib[q]
    rf.set(qn("w:eastAsia"), "Times New Roman")

    # Header identitas
    for label, key in (("Nama", "nama"), ("NIM", "nim"), ("Prodi", "prodi"), ("Matkul", "matkul")):
        p = doc.add_paragraph()
        r = p.add_run(f"{label} : ")
        r.bold = True
        p.add_run(str(meta.get(key, "")))

    # Judul
    title = f"{meta.get('kind_label', '')} {meta.get('display_index', '')} {meta.get('matkul', '')}".strip()
    tp = doc.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = tp.add_run(title)
    tr.bold = True
    tr.font.size = Pt(13)

    # Soal
    if include_soal and soal_text.strip():
        doc.add_paragraph()
        sp = doc.add_paragraph()
        sr = sp.add_run("Soal")
        sr.bold = True
        sr.font.size = Pt(14)
        for line in soal_text.splitlines():
            if line.strip():
                doc.add_paragraph().add_run(line)

    # Jawab (dari markdown opencode)
    try:
        jawab_idx = jawaban_md.lower().find("## jawab")
        body = jawaban_md[jawab_idx:] if jawab_idx != -1 else jawaban_md
    except Exception:  # noqa: BLE001
        body = jawaban_md
    _render_markdown(doc, body)

    _apply_hanging_indent_refs(doc)

    out_docx.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_docx))
    return out_docx


def _apply_hanging_indent_refs(doc: Document):
    """Referensi (setelah 'Daftar Pustaka') diberi hanging indent ala APA."""
    from docx.shared import Cm

    found = False
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt.lower().startswith("daftar pustaka"):
            found = True
            continue
        if found and txt:
            pf = p.paragraph_format
            pf.left_indent = Cm(0.63)
            pf.first_line_indent = Cm(-0.63)


def _convert_to_doc(docx_path: Path, doc_path: Path) -> bool:
    try:
        import win32com.client  # type: ignore

        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        try:
            wd = word.Documents.Open(str(docx_path.resolve()))
            wd.SaveAs2(str(doc_path.resolve()), FileFormat=0)  # 0 = Word 97-2003 .doc
            wd.Close(False)
        finally:
            word.Quit()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  ! Konversi ke .doc dilewati ({exc}). File .docx dipertahankan.")
        return False


def save_doc(jawaban_md: str, soal_text: str, meta: dict, out_dir: Path) -> tuple[Path, Path]:
    """Simpan jawaban sebagai satu file .docx final (equation OMML asli).

    Equation asli (Word Equation) hanya dapat disimpan dalam format OOXML
    (.docx); konversi ke .doc lama akan mengubah equation menjadi gambar.
    Return (docx_path, docx_path) agar pemanggil tetap API tuple.
    """
    base = meta.get("file_base", "jawaban")
    docx_path = out_dir / f"{base}.docx"
    doc_path = out_dir / f"{base}.doc"
    doc_path.unlink(missing_ok=True)

    build_docx(
        jawaban_md=jawaban_md,
        soal_text=soal_text,
        meta=meta,
        out_docx=docx_path,
    )
    return docx_path, docx_path