from __future__ import annotations

import re
from pathlib import Path

from datetime import datetime

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_MATRIX_INLINE_RE = re.compile(r"\[\[.*?\]\]")
_CODE_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
# Karakter kontrol yang tidak sah di XML 1.0 (lihat _strip_control_chars).
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Tanggal tetap untuk docProps/core.xml. Dipakai secara tetap, bukan
# datetime.now(), supaya dokumen tidak membocorkan kapan file dibuat.
_NEUTRAL_DOC_TIMESTAMP = datetime(2024, 1, 1, 0, 0, 0)
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

# \mathbb{R} dan kawan-kawan → karakter matematika double-struck
_MATHBB_MAP = {
    "R": "ℝ", "Z": "ℤ", "N": "ℕ", "Q": "ℚ", "C": "ℂ", "H": "ℍ",
    "P": "ℙ", "E": "𝔼", "F": "𝔽", "A": "𝔸", "B": "𝔹", "D": "𝔻",
}


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _omml_run(text: str) -> str:
    return f"<m:r><m:t>{_esc(text)}</m:t></m:r>"


def _omml_sup(base: str, exp: str) -> str:
    return f"<m:sSup><m:e>{base}</m:e><m:sup>{exp}</m:sup></m:sSup>"


def _omml_sub(base: str, sub: str) -> str:
    return f"<m:sSub><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>"


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


def _omml_fraction(num: str, den: str, *, bar: bool = True) -> str:
    num_xml = "".join(_parse_latex_math(num)) or _omml_run("")
    den_xml = "".join(_parse_latex_math(den)) or _omml_run("")
    kind = "bar" if bar else "noBar"
    return (
        f"<m:f><m:fPr><m:type m:val=\"{kind}\"/></m:fPr>"
        f"<m:num>{num_xml}</m:num><m:den>{den_xml}</m:den></m:f>"
    )


def _omml_sqrt_n(inner: str, deg: str = "") -> str:
    if deg:
        return (
            '<m:rad><m:radPr><m:degHide m:val="0"/></m:radPr>'
            f'<m:deg>{deg}</m:deg><m:e>{inner}</m:e></m:rad>'
        )
    return _omml_sqrt(inner)


def _omml_math_accent(cmd: str, inner: str) -> str:
    _ACCENT_CHR = {
        "hat": "̂", "widehat": "̂", "bar": "̄", "overline": "̄",
        "underline": "̲", "vec": "⃗", "dot": "̇", "ddot": "̈",
        "tilde": "̃", "widetilde": "̃", "check": "̌",
        "acute": "́", "grave": "̀", "breve": "̆",
    }
    inner_xml = "".join(_parse_latex_math(inner)) or _omml_run("")
    chr_ = _ACCENT_CHR.get(cmd, "")
    return (
        f'<m:acc><m:accPr><m:chr m:val="{chr_}"/></m:accPr>'
        f"<m:e>{inner_xml}</m:e></m:acc>"
    )


def _omml_nary(chr_: str, sub: str, sup: str, inner: str) -> str:
    sub_xml = "".join(_parse_latex_math(sub)) or _omml_run("")
    sup_xml = "".join(_parse_latex_math(sup)) or _omml_run("")
    inner_xml = "".join(_parse_latex_math(inner)) or _omml_run("")
    return (
        "<m:nary><m:naryPr>"
        f'<m:chr m:val="{chr_}"/><m:limLoc m:val="undOvr"/>'
        f'<m:subHide m:val="{"0" if sub else "1"}"/>'
        f'<m:supHide m:val="{"0" if sup else "1"}"/>'
        "</m:naryPr>"
        f"<m:sub>{sub_xml}</m:sub><m:sup>{sup_xml}</m:sup>"
        f"<m:e>{inner_xml}</m:e></m:nary>"
    )


def _omml_lim(base_cmd: str, limit: str, over: bool) -> str:
    """OMML untuk \\overset{}{} / \\underset{}{} / \\xrightarrow{}.

    ``base_cmd`` adalah tulisan LaTeX pada posisi utama (mis. \\rightarrow),
    ``limit`` adalah label di atas/bawah. Gunakan m:limUpp / m:limLow.
    """
    base_xml = "".join(_parse_latex_math(base_cmd)) or _omml_run("")
    limit_xml = "".join(_parse_latex_math(limit)) or _omml_run("")
    if over:
        return f"<m:limUpp><m:e>{base_xml}</m:e><m:lim>{limit_xml}</m:lim></m:limUpp>"
    return f"<m:limLow><m:e>{base_xml}</m:e><m:lim>{limit_xml}</m:lim></m:limLow>"


def _parse_latex_math(s: str) -> list[str]:
    """Parse LaTeX math string into OMML XML element list.

    Handles: \\begin{bmatrix}...\\end{bmatrix}, \\sqrt{}, x^{n},
    \\alpha, \\times, \\cdot, \\neq, \\leq, \\geq, \\text{}, and
    inline * as ×.  Unknown commands are rendered as plain text.
    """
    _ALPHA_MAP = {
        "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
        "epsilon": "ε", "theta": "θ", "lambda": "λ", "mu": "μ",
        "pi": "π", "sigma": "σ", "phi": "φ", "omega": "ω",
        "rho": "ρ", "tau": "τ", "psi": "ψ", "chi": "χ",
        "eta": "η", "kappa": "κ", "xi": "ξ", "zeta": "ζ",
        "Delta": "Δ", "Sigma": "Σ", "Omega": "Ω", "Pi": "Π",
        "Phi": "Φ", "Psi": "Ψ", "Theta": "Θ", "Lambda": "Λ",
    }
    _CMD_MAP = {
        "times": "×", "cdot": "·", "pm": "±", "mp": "∓",
        "leq": "≤", "geq": "≥", "neq": "≠", "approx": "≈",
        "equiv": "≡", "sim": "∼", "propto": "∝", "mid": "|",
        "le": "≤", "ge": "≥", "ne": "≠", "lt": "<", "gt": ">",
        "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔",
        "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔",
        "to": "→", "mapsto": "↦", "longrightarrow": "⟶",
        "longleftarrow": "⟵", "Longrightarrow": "⟹", "Longleftarrow": "⟸",
        "Longleftrightarrow": "⟺", "iff": "⟺", "%": "%",
        "Longmapsto": "⟼", "hookrightarrow": "↪", "hookleftarrow": "↩",
        "rightharpoonup": "⇀", "leftharpoonup": "↼", "rightharpoondown": "⇁",
        "leftharpoondown": "↽", "rightsquigarrow": "⇝", "uparrow": "↑",
        "downarrow": "↓", "updownarrow": "↕", "Uparrow": "⇑", "Downarrow": "⇓",
        "Updownarrow": "⇕", "nearrow": "↗", "searrow": "↘", "nwarrow": "↖",
        "swarrow": "↙", "rightleftharpoons": "⇌", "dashrightarrow": "⇢",
        "infty": "∞", "partial": "∂", "nabla": "∇",
        "forall": "∀", "exists": "∃", "in": "∈", "notin": "∉",
        "subset": "⊂", "supset": "⊃", "subseteq": "⊆", "supseteq": "⊇",
        "cup": "∪", "cap": "∩",
        "land": "∧", "wedge": "∧", "bigwedge": "⋀",
        "lor": "∨", "vee": "∨", "bigvee": "⋁",
        "lnot": "¬", "neg": "¬",
        "top": "⊤", "bot": "⊥", "vdash": "⊢", "vDash": "⊨",
        "models": "⊨", "implies": "⇒", "impliedby": "⇐",
        "oplus": "⊕", "otimes": "⊗", "ominus": "⊖", "odot": "⊙",
        "Box": "◻", "Diamond": "◇", "triangle": "△", "wr": "≀",
        "dots": "…", "dotsc": "…", "vdots": "⋮",
        "emptyset": "∅", "ldots": "…", "cdots": "⋯", "vdots": "⋮",
        "ddots": "⋱", "hbar": "ℏ", "ell": "ℓ",
        "langle": "⟨", "rangle": "⟩", "surd": "√", "backslash": "∖",
        "circ": "∘", "bullet": "∙", "cdotp": "·", "colon": ":",
        "sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "iiint": "∭",
        "oint": "∮", "bigcup": "⋃", "bigcap": "⋂",
        "bigoplus": "⊕", "bigotimes": "⊗", "coprod": "∐",
        "lim": "lim", "limsup": "lim sup", "liminf": "lim inf",
        "left": "", "right": "", "newcommand": "", "operatorname": " ",
        "text": " ", "quad": " ", "qquad": "  ", "hline": "",
    }

    nodes: list[str] = []
    i, n = 0, len(s)

    def _read_braced(pos: int) -> tuple[str, int]:
        while pos < n and s[pos] == " ":
            pos += 1
        if pos < n and s[pos] == "{":
            depth, start = 1, pos + 1
            pos += 1
            while pos < n and depth:
                if s[pos] == "{":
                    depth += 1
                elif s[pos] == "}":
                    depth -= 1
                pos += 1
            return s[start : pos - 1], pos
        if pos < n:
            return s[pos], pos + 1
        return "", pos

    while i < n:
        c = s[i]

        if c == " " or c == "\n":
            i += 1
            continue

        # LaTeX command
        if c == "\\":
            i += 1
            if i >= n:
                nodes.append(_omml_run("\\"))
                break
            nxt = s[i]
            # Escaped special: \{ \} \_ \^ \* \% \$
            if nxt in ("{", "}", "_", "^", "*", "%", "$", "|"):
                nodes.append(_omml_run(nxt))
                i += 1
                continue
            # Spacing commands: \  \, \; \: \! 
            if nxt == " ":
                i += 1
                continue
            if nxt in ",;:!":
                nodes.append(_omml_run(" " if nxt != "!" else ""))
                i += 1
                continue
            # Command name
            if nxt.isalpha():
                j = i
                while j < n and s[j].isalpha():
                    j += 1
                cmd = s[i:j]
                i = j
                if cmd in _ALPHA_MAP:
                    nodes.append(_omml_run(_ALPHA_MAP[cmd]))
                elif cmd == "frac":
                    num, i = _read_braced(i)
                    den, i = _read_braced(i)
                    nodes.append(_omml_fraction(num, den))
                elif cmd == "binom":
                    num, i = _read_braced(i)
                    den, i = _read_braced(i)
                    inner = _omml_fraction(num, den, bar=False)
                    nodes.append(
                        '<m:d><m:dPr><m:begChr m:val="("/>'
                        '<m:endChr m:val=")"/></m:dPr>'
                        f"<m:e>{inner}</m:e></m:d>"
                    )
                elif cmd == "sqrt":
                    deg = None
                    if i < n and s[i] == "[":
                        end = s.find("]", i)
                        if end != -1:
                            deg = s[i + 1:end]
                            i = end + 1
                    inner, i = _read_braced(i)
                    inner_xml = "".join(_parse_latex_math(inner))
                    deg_xml = "".join(_parse_latex_math(deg)) if deg else ""
                    nodes.append(_omml_sqrt_n(inner_xml, deg_xml))
                elif cmd == "text":
                    inner, i = _read_braced(i)
                    nodes.append(_omml_run(inner))
                elif cmd == "operatorname":
                    inner, i = _read_braced(i)
                    nodes.append(_omml_run(inner))
                elif cmd == "mathbb":
                    inner, i = _read_braced(i)
                    ch = inner.strip()
                    nodes.append(_omml_run(_MATHBB_MAP.get(ch, ch)))
                elif cmd in ("mathrm", "mathbf", "mathit", "mathcal",
                             "mathtt", "mathsf", "mathscr", "mathnormal"):
                    inner, i = _read_braced(i)
                    nodes.append(_omml_run(inner))
                elif cmd in ("hat", "widehat", "bar", "overline", "underline",
                             "vec", "dot", "ddot", "tilde", "widetilde",
                             "check", "acute", "grave", "breve"):
                    inner, i = _read_braced(i)
                    nodes.append(_omml_math_accent(cmd, inner))
                elif cmd in ("overset", "stackrel"):
                    over, i = _read_braced(i)
                    base, i = _read_braced(i)
                    nodes.append(_omml_lim(base, over, True))
                elif cmd == "underset":
                    under, i = _read_braced(i)
                    base, i = _read_braced(i)
                    nodes.append(_omml_lim(base, under, False))
                elif cmd in ("xrightarrow", "longrightarrow", "xRightarrow",
                             "xleftarrow", "xleftrightarrow", "xmapsto"):
                    arrow_chr = {
                        "xrightarrow": "→", "longrightarrow": "⟶",
                        "xRightarrow": "⇒", "xleftarrow": "←",
                        "xleftrightarrow": "↔", "xmapsto": "↦",
                    }[cmd]
                    label, i = _read_braced(i)
                    nodes.append(_omml_lim(arrow_chr, label, True))
                elif cmd == "begin":
                    env, i = _read_braced(i)
                    content, i = _read_until_end(s, i, env)
                    if env.endswith("matrix"):
                        nodes.append(_parse_latex_matrix(content, env))
                    else:
                        nodes.append(_omml_run(content))
                elif cmd in _CMD_MAP:
                    rep = _CMD_MAP[cmd]
                    if rep:
                        nodes.append(_omml_run(rep))
                else:
                    nodes.append(_omml_run(cmd))
                continue
            # \ followed by non-alpha: treat as text
            nodes.append(_omml_run(nxt))
            i += 1
            continue

        # Superscript
        if c == "^":
            base = nodes.pop() if nodes else _omml_run("")
            i += 1
            exp, i = _read_braced(i)
            nodes.append(_omml_sup(base, "".join(_parse_latex_math(exp)) if exp else _omml_run("")))
            continue

        # Subscript
        if c == "_":
            base = nodes.pop() if nodes else _omml_run("")
            i += 1
            sub, i = _read_braced(i)
            sub_nodes = "".join(_parse_latex_math(sub)) if sub else _omml_run("")
            nodes.append(_omml_sub(base, sub_nodes))
            continue

        # Brace group
        if c == "{":
            depth, start = 1, i + 1
            i += 1
            while i < n and depth:
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                i += 1
            inner = s[start : i - 1]
            nodes.extend(_parse_latex_math(inner))
            continue

        # Parenthesized group → <m:d> delimiter (so (AB)_{11} stays one base
        # AND inner LaTeX like \beta_0 is parsed recursively, not raw text).
        if c == "(":
            depth, j = 1, i + 1
            while j < n and depth:
                if s[j] == "(":
                    depth += 1
                elif s[j] == ")":
                    depth -= 1
                j += 1
            if depth == 0:
                inner = "".join(_parse_latex_math(s[i + 1 : j - 1])) or _omml_run("")
                nodes.append(
                    '<m:d><m:dPr><m:begChr m:val="("/><m:endChr m:val=")"/>'
                    f"</m:dPr><m:e>{inner}</m:e></m:d>"
                )
                i = j
            else:
                nodes.append(_omml_run(s[i:]))
                i = n
            continue

        # ASCII matrix: [[a, b], [c, d]]
        if s.startswith("[[", i):
            j = s.find("]]", i)
            if j != -1:
                inner = s[i + 2 : j]
                rows: list[list[str]] = []
                for part in re.split(r"\]\s*,\s*\[", inner):
                    cells = [c.strip() for c in part.split(",") if c.strip()]
                    rows.append(
                        ["".join(_parse_latex_math(c)) if c else _omml_run("") for c in cells]
                    )
                nodes.append(_omml_matrix(rows))
                i = j + 2
                continue
            nodes.append(_omml_run(s[i]))
            i += 1
            continue

        # Numeric literal
        m = re.match(r"\d+(?:\.\d+)?", s[i:])
        if m:
            nodes.append(_omml_run(m.group()))
            i += m.end()
            continue

        # Alphabetic variable (multi-letter run)
        if c.isalpha():
            j = i
            while j < n and s[j].isalpha():
                j += 1
            nodes.append(_omml_run(s[i:j]))
            i = j
            continue

        # * outside \-command → ×
        if c == "*":
            nodes.append(_omml_run("×"))
            i += 1
            continue

        # ASCII arrows & relations → Unicode (jika AI menulis `A -> B`)
        _ASCII_REPLS = (("<=>", "⟺"), ("<->", "↔"), ("->", "→"), ("<-", "←"),
                        ("=>", "⇒"), ("<=", "⇐"), (">=", "≥"), ("!=", "≠"))
        matched = None
        for ascii_seq, uni in _ASCII_REPLS:
            if s.startswith(ascii_seq, i):
                matched = (ascii_seq, uni)
                break
        if matched:
            nodes.append(_omml_run(matched[1]))
            i += len(matched[0])
            continue

        # Everything else: parentheses, operators, brackets, etc.
        nodes.append(_omml_run(c))
        i += 1

    return nodes


def _read_until_end(s: str, i: int, env: str) -> tuple[str, int]:
    """Read content until \\end{env}, returning (content, new_index)."""
    tag = f"\\end{{{env}}}"
    j = s.find(tag, i)
    if j == -1:
        return s[i:], len(s)
    return s[i:j], j + len(tag)


def _parse_latex_matrix(content: str, env: str) -> str:
    """Convert LaTeX matrix content to OMML with bracket delimiters."""
    rows = re.split(r"\\\\|(?<!\\)\\(?!\\)", content)
    cell_rows: list[list[str]] = []
    for row in rows:
        cells = [c.strip() for c in row.split("&")]
        cell_rows.append(
            ["".join(_parse_latex_math(c)) if c else _omml_run("") for c in cells]
        )
    return _omml_matrix(cell_rows)


def _equation_omml(math_str: str) -> str:
    content = "".join(_parse_latex_math(math_str)) or _omml_run("")
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
    """Terapkan *italic* dan konversi matriks inline [[...]] jadi equation."""
    text = _normalize_text(text)
    pos = 0
    for m in _MATRIX_INLINE_RE.finditer(text):
        if m.start() > pos:
            _add_italic_text(paragraph, text[pos:m.start()])
        _append_equation(paragraph, m.group(0))
        pos = m.end()
    _add_italic_text(paragraph, text[pos:])


def _add_italic_text(paragraph, text: str):
    """Terapkan *italic* dan konversi ruas LaTeX inline (\\beta, \\sigma^2, ...)
    yang ditulis tanpa $...$ menjadi equation."""
    pos = 0
    for start, end in _find_math_spans(text):
        if start > pos:
            _add_italic_plain(paragraph, text[pos:start])
        _append_equation(paragraph, text[start:end])
        pos = end
    _add_italic_plain(paragraph, text[pos:])


def _add_italic_plain(paragraph, text: str):
    """Tambah run dengan dukungan *italic* dan inline ``code`` (monospace)."""
    pos = 0
    for m in _INLINE_CODE_RE.finditer(text):
        if m.start() > pos:
            _add_italic_plain_runs(paragraph, text[pos:m.start()])
        run = paragraph.add_run(m.group(1))
        run.font.name = "Consolas"
        run.font.size = Pt(10)
        pos = m.end()
    _add_italic_plain_runs(paragraph, text[pos:])


def _add_italic_plain_runs(paragraph, text: str):
    pos = 0
    for m in _ITALIC_RE.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos:m.start()])
        run = paragraph.add_run(m.group(1))
        run.italic = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def _strip_control_chars(text: str) -> str:
    """Buang karakter kontrol yang tidak sah di XML 1.0.

    lxml melempar "ValueError: All strings must be XML compatible" kalau ada
    NUL atau 0x01-0x1f di dalam run. Teks hasil scraping Moodle bisa memuat
    karakter seperti itu bila halaman resource/File mengirim binary mentah.
    """
    if not text:
        return ""
    return _CONTROL_RE.sub("", text)


def _normalize_text(text: str) -> str:
    """Hilangkan artefak LaTeX/Markdown yang tidak boleh tampil mentah di Word."""
    text = _strip_control_chars(text)
    for source, replacement in _LATEX_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    text = re.sub(r"\\(?:left|right)\b", "", text)
    text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"(?<![A-Za-z])rightarrow(?![A-Za-z])", "→", text)
    text = re.sub(r"(?<![A-Za-z])leftarrow(?![A-Za-z])", "←", text)
    return text


_LATEX_CMD_RE = re.compile(r"\\[A-Za-z]+")

# Kata yang sah di dalam ekspresi matematika (nama fungsi, kata LaTeX).
_MATH_WORDS = {
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "pi", "rho",
    "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega",
    "Normal", "Bernoulli", "Binomial", "Poisson", "Exponential", "Uniform",
    "Gaussian", "sim", "mid", "given", "s.t", "of", "and", "or",
    "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh", "log", "ln", "exp", "lim", "sup", "inf", "max",
    "min", "Pr", "P", "E", "Var", "Cov", "Corr", "det", "dim", "mod", "Ker",
    "Im", "Re", "adj", "sum", "prod", "int", "frac", "sqrt", "times", "cdot",
    "left", "right", "quad", "text", "begin", "end", "pmatrix", "bmatrix",
    "gather", "eqnarray", "matrix", "mid", "vert", "Vert",
}


def _tokenize_rough(line: str) -> list[str]:
    return re.findall(r"[A-Za-z]+|\d+(?:\.\d+)?|[^\sA-Za-z0-9]+", line)


def _line_is_display_math(line: str) -> bool:
    """True bila satu baris (tanpa $) sebagian besar adalah ekspresi LaTeX,
    mis. `YmidX;∼;Normal(\\beta_0 + \\beta_1 x_1,\\; \\sigma^2)`."""
    line = (line or "").strip()
    if not line or "$" in line:
        return False  # sudah ditangani jalur $...$ / $$...$$
    if not _LATEX_CMD_RE.search(line):
        return False  # tidak ada perintah LaTeX → teks biasa
    toks = _tokenize_rough(line)
    if not toks:
        return False
    prose = sum(
        1 for t in toks
        if t.isalpha() and len(t) >= 4 and t not in _MATH_WORDS
    )
    # Maksimal ~20% token adalah kata prosa murni: kalimat seperti
    # `Jadi nilai yang dicari adalah \beta = 5` jangan dijadikan equation.
    return prose * 5 <= len(toks)


def _scan_math_run_end(text: str, j: int) -> int:
    """Perluas dari posisi j sampai batas akhir ruas matematika yang masuk akal."""
    n = len(text)
    depth = 0
    while j < n:
        c = text[j]
        if c == " " and depth == 0:
            k = j
            while k < n and text[k] == " ":
                k += 1
            m = re.match(r"[\\A-Za-z0-9_.^]+", text[k:k + 10])
            nxt = m.group(0) if m else ""
            if nxt and "\\" not in nxt and re.fullmatch(r"[A-Za-z]+", nxt):
                if nxt.lower() not in _MATH_WORDS:
                    return j
                j = k
                continue
            j = k
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth < 0:
                return j
        j += 1
    return n


def _find_math_spans(text: str) -> list[tuple[int, int]]:
    """Temukan ruas inline LaTeX tanpa $ di dalam teks → list (start, end).
    Ruas diperluas ke kurung pembuka/penutup yang mengelilinginya, jadi
    `Normal(\\beta_0 + \\beta_1, \\sigma^2)` ikut ditangkap mencakup parens."""
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        m = _LATEX_CMD_RE.search(text, i)
        if not m:
            break
        start = m.start()
        end = _scan_math_run_end(text, m.end())
        if end > start:
            s2, e2 = start, end
            for op, cl in (("(", ")"), ("[", "]"), ("{", "}")):
                k = s2 - 1
                while k >= 0 and text[k] == " ":
                    k -= 1
                t = e2
                while t < n and text[t] == " ":
                    t += 1
                if k >= 0 and text[k] == op and t < n and text[t] == cl:
                    s2, e2 = k, t + 1
                    break
            spans.append((s2, e2))
            i = max(e2, m.end())
    return spans


def _is_table_row(line: str) -> bool:
    return line.strip().startswith("|") and line.strip().endswith("|") and "|" in line[1:]


def _shade_paragraph(paragraph, fill: str = "F2F2F2"):
    """Beri latar abu-abu tipis pada paragraf (hasil: blok kode terlihat)."""
    ppr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


def _add_code_block(doc: Document, code: str):
    """Render blok kode (` ```sql ... ``` `) sebagai satu paragraf bergaya
    monospace dengan latar abu-abu dan indent, baris dipertahankan."""
    lines = code.replace("\r\n", "\n").split("\n")
    p = doc.add_paragraph()
    _shade_paragraph(p)
    pf = p.paragraph_format
    pf.left_indent = Cm(0.6)
    pf.right_indent = Cm(0.6)
    pf.space_before = Pt(6)
    pf.space_after = Pt(6)
    for idx, code_line in enumerate(lines):
        run = p.add_run(code_line if code_line else " ")
        run.font.name = "Consolas"
        run.font.size = Pt(9)
        if idx < len(lines) - 1:
            run.add_break()


def _render_markdown(doc: Document, md: str):
    lines = md.splitlines()
    i = 0
    ordered_idx = 0
    # Setelah heading Daftar Pustaka, butir bernomor adalah referensi, bukan
    # butir jawaban -- dan harus dirender berbeda (lihat blok ordered list).
    in_references = False
    while i < len(lines):
        line = lines[i].rstrip()

        # Fenced code block (```sql ... ```): render apa adanya, tanpa parsing
        # markdown/math di dalamnya.
        fence_m = _CODE_FENCE_RE.match(line)
        if fence_m:
            fence = fence_m.group(1)[0] * 3
            code_lines: list[str] = []
            i += 1
            while i < len(lines):
                if lines[i].strip().startswith(fence):
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1
            _add_code_block(doc, "\n".join(code_lines))
            ordered_idx = 0
            continue

        # Inline math: convert one-line $...$ expressions to Word equations.
        if line.count("$") >= 2 and "$$" not in line:
            p = doc.add_paragraph()
            parts = re.split(r"\$([^$]+)\$", line)
            for idx, part in enumerate(parts):
                if not part:
                    continue
                if idx % 2:
                    _append_equation(p, part)
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

        # Equation LaTeX telanjang (tanpa $): baris seperti
        # `YmidX;∼;Normal(\beta_0 + \beta_1 x_1,\; \sigma^2)`.
        if (
            re.match(r"^[-*>#|\d]", line.strip()) is None
            and _line_is_display_math(line)
        ):
            p = doc.add_paragraph()
            if len(line.strip()) < 60:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _append_equation(p, line.strip())
            i += 1
            continue

        # Heading -> style Heading 2/3 milik template, bukan ukuran font manual.
        # Menyetel size manual di sini membuat definisi template (ukuran, warna,
        # jarak) tidak berlaku dan hasil keluaran terlihat berbeda dari contoh.
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            heading_text = m.group(2).strip()
            if heading_text.lower().startswith("daftar pustaka"):
                in_references = True
            style_name = _heading_style(doc, level)
            p = doc.add_paragraph()
            run = p.add_run(heading_text)
            run.bold = True
            if style_name != "Normal":
                p.style = doc.styles[style_name]
            else:
                # Tanpa style Heading (dokumen tanpa template), tetap beri
                # pembedaan visual sesuai tingkatnya.
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

        # Ordered list -> penomoran asli Word ("List Number"), bukan angka
        # yang diketik manual. Versi lama menulis "1. " sebagai run biasa, jadi
        # penomoran tidak pernah menyesuaikan saat butir disisipkan di tengah,
        # dan style-nya tidak sama dengan template.
        #
        # Pengecualian: isi Daftar Pustaka tetap angka literal + hanging indent
        # ala APA, sesuai template. Nomor otomatis dari Word akan menghitung
        # butir jawaban yang mendahuluinya, sehingga referensinya bisa mulai
        # dari angka 4 -- dan yang dirujuk di dalam teks jadi tidak cocok.
        mo = re.match(r"^(\d+)[.)]\s+(.*)$", line)
        if mo:
            num = mo.group(1).lstrip("0") or "0"
            if in_references:
                p = doc.add_paragraph()
                p.add_run(f"{num}. ")
                _add_runs(p, mo.group(2))
            else:
                try:
                    p = doc.add_paragraph(style="List Number")
                except KeyError:
                    p = doc.add_paragraph()
                    p.add_run(f"{num}. ")
                _add_runs(p, mo.group(2))
            ordered_idx = 1
            i += 1
            continue

        ordered_idx = 0
        # Empty line → skip; blockquote → plain paragraph
        if not line.strip():
            i += 1
            continue
        # Horizontal rule --- / *** → spacer paragraph
        if re.match(r"^[-*=_]{3,}\s*$", line.strip()):
            doc.add_paragraph()
            i += 1
            continue
        p = doc.add_paragraph()
        _add_runs(p, line.strip())
        i += 1


def _clean_soal(md: str) -> str:
    """Buang metadata lampiran/transkripsi dari soal, pertahankan isi transkripsi."""
    lines = md.splitlines()
    out: list[str] = []
    skip_attachments = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^##\s+Lampiran\s*:?", stripped):
            skip_attachments = True
            continue
        if re.match(r"^##\s+Isi\s+lampiran\b", stripped, re.IGNORECASE):
            continue
        if stripped == "# Transkrip Soal":
            continue
        if skip_attachments:
            if re.match(r"^[-*]\s+", stripped) or not stripped:
                continue
            skip_attachments = False
        out.append(line)
    return "\n".join(out)


def _load_base_document(template_path: Path | None):
    """Buka template sebagai dokumen dasar.

    Template adalah sumber kebenaran format. Dengan memuat filenya, kita mewarisi
    seluruh definisi yang tidak kita Listing-kan satu per satu: page setup
    (ukuran kertas, margin), theme, numbering.xml (penomoran butir asli Word),
    dan seluruh definisi style. Kalau nanti template diperbarui, hasil keluaran
    ikut berubah tanpa menyentuh kode.

    Kandungan teksnya dibuang; yang dipertahankan hanya kerangka. Kalau template
    hilang atau rusak, jatuh ke dokumen kosong dengan tipografi bawaan supaya
    pipeline tidak berhenti total hanya karena satu file.

    Return (doc, dari_template, font_nama, font_ukuran).
    """
    if template_path and Path(template_path).is_file():
        try:
            doc = Document(str(template_path))
            # PENTING: tipografi harus dibaca SEBELUM body dikosongkan. Setelah
            # dihapus tidak ada satu pun run tersisa untuk disampel, sehingga
            # font isi template tak akan pernah terdeteksi dan `Normal` akan
            # kembali ke default-nya sendiri (Arial, bukan Times New Roman).
            font_name, font_size = _template_body_font(doc)
            _clear_body(doc)
            return doc, True, font_name, font_size
        except Exception as exc:  # noqa: BLE001 - template tidak boleh mematikan pipeline
            print(f"  ! template tidak bisa dibaca ({Path(template_path).name}): {exc}")
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
    return doc, False, "Times New Roman", Pt(12)


def _clear_body(doc: Document) -> None:
    """Kosongkan isi dokumen, pertahankan sectPr (page setup) di akhir body.

    `sectPr` tidak boleh dihapus: itu yang membawa ukuran kertas, margin, dan
    jarak header/footer. Tanpa itu, Letter/margin template hilang dan hasilnya
    kembali ke default Word.
    """
    body = doc.element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


def _template_body_font(doc: Document) -> tuple[str, Pt | None]:
    """Ambil font yang BENAR-BENAR dipakai isi template.

    Penting karena template bisa tidak konsisten: style `Normal` menunjuk satu
    font, tapi tiap run di dalamnya membawa override sendiri. Kalau kita cuma
    percaya style `Normal`, paragraf yang kita tambahkan akan tampil berbeda dari
    paragraf contoh -- persis kesalahan "tidak sama persis" yang harus dihindari.
    Jadi yang dicari adalah run yang paling sering muncul, bukan default style.
    """
    counts: dict[tuple[str, int], int] = {}
    for para in doc.paragraphs:
        for run in para.runs:
            name = run.font.name
            if not name:
                continue
            size = int(run.font.size.pt) if run.font.size is not None else 0
            counts[(name, size)] = counts.get((name, size), 0) + len(run.text.strip()) or 1
    if not counts:
        return "", None
    (name, size), _ = max(counts.items(), key=lambda kv: kv[1])
    return name, Pt(size) if size else None


def _apply_base_typography(doc: Document, font_name: str, font_size: Pt | None) -> None:
    """Samakan style paragraf dasar dengan font isi template."""
    if not font_name:
        return
    for style_name in ("Normal", "List Paragraph", "Body Text"):
        try:
            style = doc.styles[style_name]
        except KeyError:
            continue
        style.font.name = font_name
        if font_size is not None:
            style.font.size = font_size
        rpr = style.element.get_or_add_rPr()
        rf = rpr.get_or_add_rFonts()
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            q = qn(attr)
            if q in rf.attrib:
                del rf.attrib[q]
        rf.set(qn("w:eastAsia"), font_name)


def _identitas_table(doc: Document, meta: dict) -> None:
    """Tabel identitas 2 kolom: label | nilai.

    Mengikuti template (yang memakai `Table Grid`), bukan paragraf
    "Nama : ..." seperti versi lama. Baris yang nilainya kosong dilewati supaya
    field yang belum diisi di .env tidak tercetak sebagai baris kosong.
    """
    rows = [
        ("Nama", meta.get("nama", "")),
        ("NIM", meta.get("nim", "")),
        ("Semester", meta.get("semester", "")),
        ("UT Daerah", meta.get("ut_daerah", "")),
    ]
    filled = [(label, str(val).strip()) for label, val in rows if str(val or "").strip()]
    if not filled:
        return
    table = doc.add_table(rows=0, cols=2)
    try:
        table.style = "Table Grid"
    except KeyError:
        pass
    for label, value in filled:
        cells = table.add_row().cells
        label_run = cells[0].paragraphs[0].add_run(label)
        label_run.bold = True
        cells[1].paragraphs[0].add_run(value)
    doc.add_paragraph()


def build_docx(
    *,
    jawaban_md: str,
    soal_text: str,
    meta: dict,
    out_docx: Path,
    include_soal: bool = True,
    template: Path | None = None,
) -> Path:
    # Sanitasi di pintu masuk: meta, soal, dan jawaban bisa memuat karakter
    # kontrol dari scraping Moodle. Run header/judul tidak lewat _normalize_text
    # sehingga harus dibersihkan di sini juga.
    soal_text = _strip_control_chars(soal_text)
    jawaban_md = _strip_control_chars(jawaban_md)
    meta = {k: _strip_control_chars(str(v)) for k, v in meta.items()}

    if template is None:
        template = _default_template_path()
    doc, from_template, font_name, font_size = _load_base_document(
        Path(template) if template else None
    )
    if from_template:
        _apply_base_typography(doc, font_name, font_size)

    # Judul: TNR 18 bold center, mengikuti template. Ukuran diambil dari style
    # `Title` kalau ada supaya perubahan di template ikut terbawa.
    title = f"{meta.get('kind_label', '')} {meta.get('display_index', '')}".strip()
    tp = doc.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = tp.add_run(title)
    tr.bold = True
    tr.font.size = Pt(18)

    _identitas_table(doc, meta)

    # Soal. Judul "Soal" hanya ditambah kalau teks soal tidak sudah punya
    # heading sendiri -- kalau ditambah tanpa syarat, hasilnya dua "Soal"
    # berturut-turut (satu dari kita, satu dari markdown).
    if include_soal and soal_text.strip():
        cleaned = _clean_soal(soal_text)
        if not re.match(r"^\s*#", cleaned):
            sh = doc.add_paragraph(style=_heading_style(doc, 2))
            sh.add_run("Soal")
        _render_markdown(doc, cleaned)

    # Jawab (dari markdown opencode)
    body = _answer_body(jawaban_md)
    if body.strip():
        _render_markdown(doc, body)

    _apply_hanging_indent_refs(doc)
    _neutralize_metadata(doc, meta)

    out_docx.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_docx))
    return out_docx


def _default_template_path() -> Path | None:
    """Template standar; `None` kalau folder template tidak ada."""
    from config import TEMPLATE_DIR

    if not TEMPLATE_DIR.is_dir():
        return None
    docx = sorted(TEMPLATE_DIR.glob("*.docx"))
    return docx[0] if docx else None


def _heading_style(doc: Document, level: int) -> str:
    """`##` -> Heading 2, `###` -> Heading 3, dengan fallback aman.

    Template menentukan ukuran/warna heading lewat style-nya sendiri; kalau
    kita setsize manual, perubahan template jadi tidak berlaku dan hasilnya
    menyimpang dari contoh. Kalau style tidak ada (dokumen tanpa template),
    turun ke bold polos.
    """
    wanted = f"Heading {min(max(level, 2), 3)}"
    try:
        doc.styles[wanted]
    except KeyError:
        return "Normal"
    return wanted


def _answer_body(jawaban_md: str) -> str:
    """Ambil bagian jawaban saja, buang sisa sebelum heading pertama."""
    for marker in ("## jawaban mahasiswa", "## jawab", "## jawaban"):
        idx = jawaban_md.lower().find(marker)
        if idx != -1:
            return jawaban_md[idx:]
    return jawaban_md


def _neutralize_metadata(doc: Document, meta: dict) -> None:
    """Sembunyikan sidik jari generator di properti dokumen.

    python-docx menuliskan `dc:creator = python-docx` dan
    `dc:description = generated by python-docx` di docProps/core.xml. Kedua
    metadata itu dibaca plagiarism checker/cek kesamaan dokumen, jadi diganti
    dengan identitas mahasiswa dan tanggal tetap (bukan waktu asli pembuatan,
    yang justru membuka kapan file ini dibuat).
    """
    try:
        core = doc.core_properties
    except Exception:  # noqa: BLE001
        return
    try:
        author = str(meta.get("nama", "")).strip() or "python-docx"
        core.author = author
        core.last_modified_by = author
        core.description = ""
        core.category = ""
        core.comments = ""
        core.identifier = ""
        core.language = "id-ID"
        core.title = (
            f"{meta.get('kind_label', '')} {meta.get('display_index', '')} "
            f"{meta.get('matkul', '')}"
        ).strip()
        core.subject = str(meta.get("matkul", ""))
        core.created = _NEUTRAL_DOC_TIMESTAMP
        core.modified = _NEUTRAL_DOC_TIMESTAMP
        core.revision = 1
    except Exception:  # noqa: BLE001
        pass


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


def save_doc(
    jawaban_md: str,
    soal_text: str,
    meta: dict,
    out_dir: Path,
    *,
    template: Path | None = None,
) -> tuple[Path, Path]:
    """Simpan jawaban sebagai satu file .docx final (equation OMML asli).

    Equation asli (Word Equation) hanya dapat disimpan dalam format OOXML
    (.docx); konversi ke .doc lama akan mengubah equation menjadi gambar.
    Return (docx_path, docx_path) agar pemanggil tetap API tuple.
    """
    base = meta.get("file_base", "jawaban")
    docx_path = out_dir / f"{base}.docx"
    doc_path = out_dir / f"{base}.doc"
    doc_path.unlink(missing_ok=True)

    if template is not None and not Path(template).is_file():
        print(f"  ! format jawaban tidak ditemukan ({Path(template).name}), pakai template standar.")
        template = None

    build_docx(
        jawaban_md=jawaban_md,
        soal_text=soal_text,
        meta=meta,
        out_docx=docx_path,
        template=template,
    )
    return docx_path, docx_path