"""Reader Lokal: ubah halaman Moodle terotorisasi jadi Markdown bersih.

Tujuan modul ini: agent `tuton` TIDAK punya cookie MoodleSession, jadi ia tidak
bisa membuka `elearning.ut.ac.id` sendiri. Reader menjadi jembatan:

    URL di prompt  ->  Reader (suntik cookie)  ->  Markdown untuk AI

Keunggulan dibanding scraping sendiri lalu menempel teksnya ke prompt: AI
membaca halaman **apa adanya**, jadi instruksi khusus tutor, pedoman penilaian
(rubrik), contoh soal, dan konteks diskusi ikut terbaca. Informasi itulah yang
biasanya hilang saat teks soal dipotong oleh parser.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from config import Config
from moodle.auth import MoodleSession

# Batas agar satu lampiran raksasa tidak melahap memori server.
MAX_BYTES = 25 * 1024 * 1024
_FETCH_TIMEOUT = 60

# Versi bentuk markdown. Naikkan setiap kali `render_moodle_html` /
# penanganan tautannya berubah, supaya cache `.md` versi lama tidak terpakai
# (lihat `ReaderCache._md_key`).
#   v1 = tautan apa adanya (tidak bisa dibuka agen)
#   v2 = tautan ditulis ulang jadi URL Reader (bisa dijelajahi agen)
MD_RENDER_VERSION = "v2"

_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tiff")
_DOC_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".zip", ".txt", ".csv")

# Elemen yang isinya murni kerangka/UI Moodle. Kalau ikut terbawa, AI
# membaca daftar menu, bukan soal.
#
# Dua selector sengaja TIDAK ada di sini:
# - `[data-region]`: Moodle memberi atribut ini pada card body post diskusi
#   (`data-region="content"`), sehingga selector umum itu menghapus TEKS SOAL
#   itu sendiri. Hanya region kerangka yang disebut eksplisit.
# - `.inline`: dipakai Moodle untuk membungkus isi post, bukan cuma tombol.
_DROP_SELECTORS = (
    "script", "style", "noscript", "template", "svg", "iframe", "form",
    "nav", "footer", "header nav", ".navbar", ".navigation", "#region-main-menu",
    ".footer-container", ".footer", ".copyright", ".breadcrumb a[href='#']",
    ".collapsible-actions", ".activity-navigation", ".nav-buttons", ".mnep-content",
    ".hidden", "[hidden]", ".sr-only", ".visually-hidden", ".accesshide",
    "[role=main] nav", ".btn-group", ".action-menu", ".editmenu", ".dropdown",
    ".card-deck .card-actions", ".singlebutton", ".btn", "button",
    ".timeline", ".usertimestamps", ".forumpost .btn", ".vote", ".rating",
    ".warning", ".alert-success", ".alert-info", ".alert-warning", ".alert-danger",
    ".quizattemptmeta", ".quickedit", ".box .btn",
    "#region-main-menu", ".content-nav", ".sectiontabs", ".mod_actions",
    ".mform", ".dimmed", ".sr-only-focusable",
    '[data-region=header]', '[data-region=footer]',
    '[data-region=addsecondarynavigation]', '[data-region=primarynavigation]',
    '[data-region=mobileprimarynav]', '[data-region=secondarynavigation]',
    '[data-region=themelegacy]', '[data-region=side-pre-block]',
    '[data-region=side-post-block]', '[data-region=bottom-of-region-main]',
    '[data-region=task-footer]',
)

# Area yang diprioritaskan untuk diekstrak, dari paling spesifik ke paling umum.
_CONTENT_SELECTORS = (
    "[role=main] .region-main-content", "[role=main] #region-main",
    "[role=main]", "#region-main", ".region-main", "#content",
    "#maincontent", "article", "main",
    ".activity-description", "#intro", ".modintro",
    ".description-inner", ".activity-altcontent",
    ".box.generalbox .no-overflow", ".generalbox",
    ".post-content", "[id^=post-content-]",
    ".no-overflow", ".contentnode", ".main-content", ".content",
)

_TABLE_MAX_ROWS = 40
_MIN_USEFUL_CHARS = 40

# ---------------------------------------------------------------------------
# Pembersihan tambahan.
#
# Selector di atas tidak cukup untuk tema UT (mb2iq) dan Moodle modern: menu
# samping, dropdown user, dan breadcrumb sering memakai class generik seperti
# `.sidecol`/`.moremenu` yang tidak ada di daftar. Kalau ikut terbaca, AI
# spending sebagian besar token untuk membaca daftar menu, bukan soal.
#
# Solusinya: buang elemen yang nama class/id-nya mengandung token "kerangka".
# Token dicocokkan utuh (bukan substring) supaya `modintotool` tidak ikut
# tersaring hanya karena mengandung kata "tool".
# ---------------------------------------------------------------------------
_CHROME_TOKENS = frozenset(
    {
        # Hanya token yang JENIS "%" kerangka. Token seperti `d-flex`,
        # `justify-content-between`, atau `block` TIDAK boleh ada di sini:
        # tema Moodle/Boost membungkus konten soal dengan utility class itu,
        # dan mencocokkannya membuat seluruh deskripsi tugas ikut terhapus.
        "nav", "navbar", "navigation", "menubar",
        "primary-navigation", "secondary-navigation", "main-navigation",
        "submenu", "sidecol", "sidebar", "sidemenu",
        "leftcolumn", "rightcolumn", "breadcrumb",
        "footer", "masthead", "topbar", "topnav", "banner", "drawer",
        "userinfo", "user-info", "usermenu", "user-menu", "langmenu",
        "searchform", "modsearch", "moremenu", "actionmenu", "action-menu",
        "editmenu", "region-main-menu", "siteinfo", "site-info",
        "region-footer", "region-header", "mod_actions",
        "card-actions", "backtotop", "totop", "editing", "quickedit",
        "moodle-action-menu", "mobile-nav", "pagenav", "course-navigation",
        "sidenav", "tool_navigation", "section-navigation",
    }
)

# Aset tema/avatar: URL-nya sama sekali bukan lampiran soal.
_ASSET_URL_RE = re.compile(
    r"/theme/|/theme_|\btheme/image\.php\b|/pix/|/user/icon/|/user/pix/|"
    r"/userdata/|logout\.(?:png|gif|jpe?g|svg)|"
    r"/coursethumbnails?/|/badge/|/calendar/",
    re.I,
)

# Baris-baris status pengumpulan/penilaian. Frequently muncul sebagai tabel
# yang terdengar seperti rubrik padahal tidak ada bobotnya sama sekali.
_STATUS_ROW_RE = re.compile(
    r"^(?:submission status|grading status|time remaining|last modified|"
    r"files attached|attempt number|number of attempts|group submission|"
    r"peer assessment|late submissions?|reminder|feedback released|"
    r"published|assigned|opened?|closed?|available)",
    re.I,
)


# ---------------------------------------------------------------------------
# Fetch + cache
# ---------------------------------------------------------------------------
@dataclass
class Fetched:
    """Hasil satu fetch: URL asli, status, dan isi (bytes)."""

    url: str
    final_url: str = ""
    status: int = 0
    content_type: str = ""
    body: bytes = b""
    error: str = ""
    from_cache: bool = False
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.status < 300 and bool(self.body)

    @property
    def is_html(self) -> bool:
        return "html" in self.content_type.lower() or self.content_type == ""

    @property
    def is_login(self) -> bool:
        """Deteksi halaman login Moodle (session kedaluwarsa)."""
        final = (self.final_url or self.url).lower()
        if "login/index.php" in final:
            return True
        if self.is_html:
            head = self.text[:4000].lower()
            return (
                "moodlesession" in head
                and ('name="username"' in head or "id=\"login" in head)
            )
        return False

    @property
    def text(self) -> str:
        if not self.is_html:
            return ""
        return self.body.decode("utf-8", errors="replace")


class ReaderCache:
    """Cache disk untuk hasil fetch & markdown, supaya tidak memukul Moodle ulang.

    Cache `pages` (HTML mentah) aman dari perubahan renderer. Cache `md` TIDAK:
    bentuk markdown bergantung pada apakah tautannya ditulis ulang menjadi URL
    Reader. Sebelum ada penulisan ulang, entri `md` berisi `https://elearning...
    apa adanya` yang tidak bisa dibuka agen tanpa cookie -- dan cache itu
    bertahan 30 menit di disk. Karena itu kunci `md` memuat versi renderer:
    menaikkan `MD_RENDER_VERSION` otomatis membuat seluruh entri lama tidak
    terpakai, lalu file yatim dibersihkan saat cache dibuat.
    """

    def __init__(self, root: Path, ttl: int = 1800) -> None:
        self.root = root
        self.ttl = ttl
        self._lock = threading.Lock()
        try:
            (root / "pages").mkdir(parents=True, exist_ok=True)
            (root / "md").mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self._purge_stale_md()

    @staticmethod
    def _key(url: str, suffix: str) -> str:
        digest = hashlib.sha1(url.encode("utf-8", "replace")).hexdigest()[:20]
        return f"{digest}{suffix}"

    @classmethod
    def _md_key(cls, url: str) -> str:
        digest = hashlib.sha1(url.encode("utf-8", "replace")).hexdigest()[:20]
        return f"{MD_RENDER_VERSION}_{digest}.md"

    def _purge_stale_md(self) -> None:
        """Hapus file `.md` versi lama supaya direktori cache tidak tumbuh."""
        keep = f"{MD_RENDER_VERSION}_"
        try:
            stale = [
                p for p in (self.root / "md").glob("*.md")
                if not p.name.startswith(keep)
            ]
        except OSError:
            return
        for path in stale:
            try:
                path.unlink()
            except OSError:
                pass

    def _read_fresh(self, path: Path) -> bytes | None:
        try:
            if time.time() - path.stat().st_mtime > self.ttl:
                return None
            return path.read_bytes()
        except OSError:
            return None

    @staticmethod
    def _encode_meta(fetched: Fetched) -> bytes:
        """Header cache sebagai satu baris JSON.

        Dipakai JSON, bukan string berisi `|`, karena pemisah baris pada file
        cache adalah `\n`. Body PDF/DOCX pasti mengandung newline, jadi header
        harus bisa dibaca tanpa ambigu -- dan hanya baris PERTAMA yang boleh
        diperlakukan sebagai header.
        """
        meta = {
            "u": fetched.final_url or fetched.url,
            "s": fetched.status,
            "c": fetched.content_type or "application/octet-stream",
        }
        return json.dumps(meta, ensure_ascii=False).encode("utf-8", "replace")

    def get_page(self, url: str) -> Fetched | None:
        path = self.root / "pages" / self._key(url, ".bin")
        blob = self._read_fresh(path)
        if blob is None:
            return None
        # Hanya baris pertama yang adalah header. Sisa blob adalah body mentah
        # dan TIDAK boleh dipecah -- PDF/DOCX/XML banyak mengandung newline.
        header, sep, body = blob.partition(b"\n")
        if not sep:
            return None
        try:
            meta = json.loads(header.decode("utf-8", "replace"))
            return Fetched(
                url=url,
                final_url=str(meta.get("u") or url),
                status=int(meta.get("s") or 0),
                content_type=str(meta.get("c") or ""),
                body=body,
                from_cache=True,
            )
        except (ValueError, TypeError, AttributeError):
            return None

    def put_page(self, fetched: Fetched) -> None:
        if not fetched.ok:
            return
        path = self.root / "pages" / self._key(fetched.url, ".bin")
        with self._lock:
            try:
                path.write_bytes(self._encode_meta(fetched) + b"\n" + fetched.body)
            except OSError:
                pass

    def get_md(self, url: str) -> str | None:
        path = self.root / "md" / self._md_key(url)
        try:
            if time.time() - path.stat().st_mtime > self.ttl:
                return None
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def put_md(self, url: str, text: str) -> None:
        if not text.strip():
            return
        path = self.root / "md" / self._md_key(url)
        with self._lock:
            try:
                path.write_text(text, encoding="utf-8")
            except OSError:
                pass


class MoodleReader:
    """Fetch berotorasi + render Markdown. Thread-safe lewat session per-thread."""

    def __init__(self, cache: ReaderCache | None = None) -> None:
        self.cache = cache or ReaderCache(Config.TUTON_CACHE_DIR, Config.TUTON_CACHE_TTL)
        self._local = threading.local()

    # -- session per thread (requests.Session tidak aman dipakai paralel) ----
    @property
    def session(self) -> MoodleSession:
        session = getattr(self._local, "session", None)
        if session is None:
            session = MoodleSession()
            self._local.session = session
        return session

    @staticmethod
    def allowed(url: str) -> bool:
        """Guard SSRF: hanya host Moodle yang diizinkan."""
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        try:
            base = urlparse(Config.base_url()).hostname or ""
        except RuntimeError:
            return False
        return (parsed.hostname or "").lower() == base.lower()

    def fetch(self, url: str, *, use_cache: bool = True) -> Fetched:
        url = str(url or "").strip()
        if not self.allowed(url):
            return Fetched(url=url, error=f"URL di luar host Moodle: {url[:120]}")
        if use_cache:
            cached = self.cache.get_page(url)
            if cached is not None:
                return cached
        started = time.monotonic()
        try:
            resp = self.session._request(  # noqa: SLF001 - retry & backoff milik auth
                "GET", url, allow_redirects=True, stream=True
            )
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            body = b""
            for chunk in resp.iter_content(65536):
                body += chunk
                if len(body) > MAX_BYTES:
                    resp.close()
                    return Fetched(
                        url=url,
                        final_url=str(resp.url),
                        status=resp.status_code,
                        content_type=content_type,
                        error=f"melebihi batas {MAX_BYTES // (1024 * 1024)}MB",
                        elapsed=time.monotonic() - started,
                    )
            result = Fetched(
                url=url,
                final_url=str(resp.url),
                status=resp.status_code,
                content_type=content_type,
                body=body,
                elapsed=time.monotonic() - started,
            )
            resp.close()
        except Exception as exc:  # noqa: BLE001 - semua kegagalan jadi Fetched
            return Fetched(url=url, error=f"{type(exc).__name__}: {exc}",
                           elapsed=time.monotonic() - started)
        if result.ok:
            self.cache.put_page(result)
        return result

    # -- render ------------------------------------------------------------
    def render(
        self,
        url: str,
        *,
        kind: str = "generic",
        use_cache: bool = True,
        url_for=None,
    ) -> tuple[str, Fetched]:
        """Kembalikan (markdown, hasil_fetch).

        `url_for` meneruskan callback penulisan ulang tautan (lihat
        `render_moodle_html`). Tanpa itu, tautan di markdown keluar sebagai URL
        Moodle mentah yang tidak bisa dibuka pemanggil tanpa cookie -- sehingga
        agen tidak bisa menelusuri menu/tautan di dalam halaman. Default `None`
        mempertahankan perilaku lama: tautan apa adanya.
        """
        url = self.reader_url_target(url)
        fetched = self.fetch(url, use_cache=use_cache)
        if not fetched.ok:
            return "", fetched
        if not fetched.is_html:
            return self._render_binary(url, fetched), fetched
        md = render_moodle_html(
            fetched.text,
            fetched.final_url or url,
            kind=kind,
            url_for=url_for,
        )
        if use_cache:
            self.cache.put_md(url, md)
        return md, fetched

    @staticmethod
    def reader_url_target(url: str) -> str:
        return str(url or "").strip()

    def _render_binary(self, url: str, fetched: Fetched) -> str:
        """PDF/gambar: beri teks yang bisa diekstrak murah + arahkan ke file."""
        name = _basename(url)
        head = [f"# Lampiran: {name}", "", f"- URL: {url}", f"- Tipe: {fetched.content_type}"]
        text = ""
        if "pdf" in fetched.content_type.lower() or name.lower().endswith(".pdf"):
            text = _pdf_text(fetched.body)
            if text.strip():
                head.append("- Teks layer PDF berhasil diekstrak (di bawah ini).")
            else:
                head.append(
                    "- PDF ini hasil SCAN (tanpa teks layer). Isi soal ada di dalam "
                    "gambar/PDF: pakai file lokal yang disebutkan di prompt dan baca "
                    "dengan tool `read` bila modelmu mendukung vision."
                )
        else:
            head.append(
                "- Berkas biner (gambar/dokumen). Isinya tidak bisa diubah jadi teks "
                "oleh Reader. Pakai file lokal yang disebutkan di prompt dan baca "
                "dengan tool `read` bila modelmu mendukung vision."
            )
        body = "\n".join(head) + "\n\n" + (text.strip() or "_(tidak ada teks yang bisa diekstrak)_")
        return body


def _basename(url: str) -> str:
    try:
        path = urllib.parse.unquote(urlparse(url).path)
    except ValueError:
        return "lampiran"
    name = path.rsplit("/", 1)[-1]
    return name or "lampiran"


def _pdf_text(payload: bytes) -> str:
    """Ekstrak teks layer PDF via pymupdf. Murah; dipakai sebagai fallback
    pertama sebelum memanggil vision model (yang jauh lebih lambat)."""
    try:
        import fitz  # pymupdf

        doc = fitz.open(stream=payload, filetype="pdf")
        try:
            parts = [page.get_text().strip() for page in doc]
        finally:
            doc.close()
        return "\n\n".join(part for part in parts if part)
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# HTML -> Markdown
# ---------------------------------------------------------------------------
_SKIP_TEXT = {
    "google tag (gtag.js)", "mengecek sinyal...",
    "permalink", "reply", "unread", "subscribe", "mark as read", "jump to post",
    "edit", "delete", "quote", "more", "less", "show", "hide", "next", "previous",
    "back to top", "close", "cancel", "submit", "save", "continue",
    "advanced", "collapse all", "expand all", "show all", "show more",
}

_LIST_TAGS = {"ul", "ol"}


_GTAG_RE = re.compile(r"^\s*Google tag \(gtag\.js\)", re.I)


# Elemen akar yang TIDAK PERNAH boleh dibuang, apa pun class-nya. Body Moodle
# membawa class tata letak seperti `sidebar-one` / `header-light`, jadi
# pencocokan token di elemen ini akan menghapus seluruh halaman.
_ROOT_IDS = frozenset(
    {"page", "content", "region-main", "maincontent", "main", "page-content",
     "region-main-content", "page-wrapper", "outlet"}
)
_ROOT_CLASS_HINTS = ("region-main", "contentnode", "maincontent", "pagelayout-")


def _live(el) -> bool:
    """False kalau elemen sudah di-decompose atau bukan Tag.

    Setelah `decompose()`, bs4 menyisakan placeholder di pohon; menyentuh
    `.get()` pada placeholder itu melempar AttributeError. Karena pengoosongan
    kerangka dilakukan beberapa putaran, guard ini wajib ada.
    """
    if el is None or not isinstance(el, Tag):
        return False
    if getattr(el, "decomposed", False):
        return False
    return True


def _is_root(el: Tag) -> bool:
    if not _live(el):
        return True  # paling aman: jangan pernah dibuang
    if el.name in ("html", "body", "main"):
        return True
    if (el.get("role") or "").strip().lower() == "main":
        return True
    if (el.get("id") or "").strip() in _ROOT_IDS:
        return True
    cls = el.get("class") or []
    if isinstance(cls, str):
        cls = [cls]
    for part in cls:
        for hint in _ROOT_CLASS_HINTS:
            if hint in str(part).lower():
                return True
    return False


def _is_chrome(el: Tag) -> bool:
    """True kalau elemen ini pasti kerangka/UI, bukan isi soal.

    Hanya yang tidak ambigu yang tidak ambigu: nama tag dan role ARIA. Pencocokan token
    class dilakukan terpisah (lihat _strip_chrome_tokens) dan hanya dijalankan
    di dalam container konten, karena class tata letak pada elemen terluar bisa
    menghapus halaman utuh.
    """
    if _is_root(el):
        return False
    if el.name in ("nav", "header", "footer", "aside"):
        return True
    if (el.get("role") or "").strip().lower() in ("navigation", "banner", "menubar", "search"):
        return True
    if el.name in ("div", "span", "p") and _GTAG_RE.match(el.get_text(" ", strip=True)):
        return True
    return False


def _has_chrome_token(el: Tag) -> bool:
    """True kalau nama class/id mengandung token kerangka yang dikenal."""
    if _is_root(el):
        return False
    for attr in ("class", "id"):
        raw = el.get(attr) or ""
        # bs4 mengembalikan class sebagai list, bukan string.
        if isinstance(raw, (list, tuple)):
            raw = " ".join(str(part) for part in raw)
        if not raw:
            continue
        for token in re.split(r"[^A-Za-z0-9]+", str(raw)):
            if token.lower() in _CHROME_TOKENS:
                return True
    return False


def _clean_document(soup: BeautifulSoup) -> BeautifulSoup:
    """Fase 1: buang kerangka yang tidak ambigu dari seluruh dokumen.

    Sengaja TIDAK memakai pencocokan token class di sini. Page layout Moodle
    menaruh `sidebar-*`, `header-*`, dan `pagelayout-*` pada elemen terluar, jadi
    satu pencocokan salah sudah bisa menghapus seluruh isi halaman.
    """
    for selector in _DROP_SELECTORS:
        try:
            for el in soup.select(selector):
                if _is_root(el):
                    continue
                el.decompose()
        except Exception:  # noqa: BLE001 - selector aneh tidak boleh mematikan render
            continue
    for _ in range(4):
        victims = [el for el in soup.find_all(True) if _live(el) and _is_chrome(el)]
        if not victims:
            break
        for el in victims:
            el.decompose()
    for el in soup.find_all(style=True):
        el.attrs.pop("style", None)
    for el in soup.find_all(alt=True):
        alt = (el.get("alt") or "").strip()
        if not alt or len(alt) > 180:
            el.attrs.pop("alt", None)
    return soup


def _strip_chrome_tokens(container: Tag) -> None:
    """Fase 3: buang menu/dropdown yang tertinggal DI DALAM container konten.

    Aman karena sudah diketahui container ini adalah region utama: nav atau
    dropdown yang ada di dalamnya memang bukan bagian soal.
    """
    for _ in range(4):
        if not _live(container):
            return
        victims = [el for el in container.find_all(True) if _has_chrome_token(el)]
        if not victims:
            break
        for el in victims:
            if _is_root(el) or not _live(el):
                continue
            el.decompose()


def _is_asset_url(url: str) -> bool:
    """Logo, avatar, ikon tema: muncul di HTML tapi bukan lampiran soal."""
    if not url or url.startswith(("data:", "javascript:", "#", "mailto:")):
        return True
    return bool(_ASSET_URL_RE.search(url.split("?", 1)[0]))


def normalize_url(base: str, href: str) -> str:
    """URL absolut yang tidak menggandakan segmen path.

    Moodle kadang menulis `mod/forum/discuss.php?...` relatif terhadap halaman
    yang sudah berada di `/mod/forum/`, sehingga urljoin menghasilkan
    `/mod/forum/mod/forum/discuss.php` dan server membalas 404. Segmen kembar
    dikecilkan di sini.
    """
    url = urljoin(base, href or "")
    scheme, _, rest = url.partition("://")
    if not rest:
        return url
    path, sep, tail = rest.partition("?")
    parts = [seg for seg in path.split("/") if seg]
    collapsed: list[str] = []
    for seg in parts:
        if collapsed and collapsed[-1] == seg:
            continue
        collapsed.append(seg)
    rebuilt = f"{scheme}://" + "/".join(collapsed)
    return f"{rebuilt}?{tail}" if sep else rebuilt


def _pick_content(soup: BeautifulSoup) -> Tag:
    """Pilih elemen yang paling mungkin berisi isi soal.

    Dua aturan:
    - Kandidat yang di dalam kandidat lain dilewati, supaya `[role=main]` menang
      atas `article.forum-post` di dalamnya. Kalau tidak, deskripsi diskusi ikut
      hilang hanya karena post pembuka lebih dulu ada di daftar selector.
    - Dari kandidat yang tersisa diambil yang TEKSNYA TERLONG. Ini disengaja:
      AI perlu melihat instruksi, pedoman penilaian, status pengumpulan, dan
      lampiran dalam satu halaman, bukan cuma blok pertama yang kebetulan
      memuat teks. Memakai "ambil yang pertama memadai" membuat halaman tugas
      UT hanya menghasilkan tabel status sepanjang 169 karakter.
    """
    candidates: list[Tag] = []
    seen: set[int] = set()
    for selector in _CONTENT_SELECTORS:
        for el in soup.select(selector):
            if id(el) in seen:
                continue
            seen.add(id(el))
            candidates.append(el)

    outer = [
        el
        for el in candidates
        if not any(other is not el and other in el.parents for other in candidates)
    ]
    pool = outer or candidates
    if pool:
        return max(pool, key=_length_of)
    root = soup.select_one("[role=main]") or soup.body or soup
    return root  # type: ignore[return-value]
def _length_of(el: Tag) -> int:
    return len(el.get_text(" ", strip=True))
def _render_tag(node: Tag, page_url: str, url_for) -> str:
    """Markdown inline untuk SATU elemen, termasuk makna tag itu sendiri.

    Ini yang membuat `<a>` jadi tautan dan `<img>` jadi gambar. Kalau logikanya
    taruh di _inline (yang hanya berjalan di anak-anak), elemen yang diteruskan
    langsung ke _inline akan kehilangan tag-nya dan berubah jadi teks telanjang.
    """
    name = node.name.lower()
    if name in ("script", "style", "noscript", "template"):
        return ""
    if name in _LIST_TAGS:
        return _inline(node, page_url, url_for)
    if name == "img":
        src = _attr(node, ("src", "data-src", "data-original"))
        alt = (node.get("alt") or "gambar dalam soal").strip() or "gambar"
        if src and not src.startswith("data:"):
            absolute = normalize_url(page_url, src)
            if _is_asset_url(absolute):
                return ""  # logo/avatar, bukan gambar soal
            return f"\n\n![{alt}]({url_for(absolute, kind='file')})\n\n"
        return ""
    if name in ("a", "area"):
        href = _attr(node, ("href",))
        label = node.get_text(" ", strip=True) or "tautan"
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            return label
        absolute = normalize_url(page_url, href)
        if _is_asset_url(absolute):
            # Ikon tipe berkas / logo: tidak berguna bagi AI, cukup teksnya.
            return f" {label}"
        return f"[{label}]({url_for(absolute, kind='page')})"
    if name == "br":
        return "\n"
    if name in ("strong", "b"):
        inner = _inline(node, page_url, url_for).strip()
        return f"**{inner}**" if inner else ""
    if name in ("em", "i", "cite"):
        inner = _inline(node, page_url, url_for).strip()
        return f"*{inner}*" if inner else ""
    if name in ("code", "kbd", "samp", "tt"):
        return f"`{node.get_text(' ', strip=True)}`"
    if name in ("sup", "sub"):
        inner = node.get_text(" ", strip=True)
        marker = "^" if name == "sup" else "_"
        return f"{inner}{marker}" if inner else ""
    return _inline(node, page_url, url_for)


def _inline(el: Tag, page_url: str, url_for) -> str:
    """Rakit Markdown inline dari anak-anak `el` (tag `el` sendiri diabaikan)."""
    out: list[str] = []
    for child in el.children:
        if isinstance(child, NavigableString):
            out.append(str(child))
        elif isinstance(child, Tag):
            out.append(_render_tag(child, page_url, url_for))
    return re.sub(r"[ \t]{2,}", " ", "".join(out))


def _attr(el: Tag, names: tuple[str, ...]) -> str:
    for name in names:
        value = (el.get(name) or "").strip()
        if value:
            return value
    return ""


def _table_to_md(table: Tag, page_url: str, url_for) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr")[:_TABLE_MAX_ROWS]:
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        row = [
            re.sub(r"\s+", " ", _render_tag(cell, page_url, url_for)).strip()
            for cell in cells
        ]
        if any(row):
            rows.append(row)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    head, *rest = rows
    # Baris pertama yang isinya didominasi angka bukan header.
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rest]
    extra = ""
    if len(table.find_all("tr")) > _TABLE_MAX_ROWS:
        extra = f"\n_(tabel dipotong setelah {_TABLE_MAX_ROWS} baris)_"
    return "\n".join(lines) + extra


def _node_to_md(node: Tag, page_url: str, url_for, out: list[str], depth: int = 0) -> None:
    name = node.name.lower()

    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if text:
            level = int(name[1])
            out.append("")
            out.append(f"\n{'#' * min(level, 6)} {text}\n")
        return

    if name == "table":
        md = _table_to_md(node, page_url, url_for)
        if md:
            out.append("")
            out.append(md)
            out.append("")
        return

    if name in _LIST_TAGS:
        ordered = name == "ol"
        try:
            base = int((node.get("start") or "1").strip())
        except (TypeError, ValueError):
            base = 1
        idx = base
        out.append("")
        for li in node.find_all("li", recursive=False):
            text = re.sub(r"\s+", " ", _render_tag(li, page_url, url_for)).strip()
            if not text or text.lower() in _SKIP_TEXT:
                continue
            marker = f"{idx}." if ordered else "-"
            out.append(f"{marker} {text}")
            idx += 1
        out.append("")
        return

    if name in ("pre",):
        code = node.get_text("\n", strip=False).strip()
        if code:
            out.append("")
            out.append("```\n" + code + "\n```")
            out.append("")
        return

    if name == "blockquote":
        inner = "\n".join(_md_lines(node, page_url, url_for))
        text = inner.strip()
        if text:
            out.append("")
            out.extend(f"> {line}" for line in text.splitlines())
            out.append("")
        return

    if name in ("script", "style", "noscript", "template"):
        return

    # Elemen blok:_render isi, lalu sisipkan baris kosong antar blok.
    has_block_child = any(
        isinstance(c, Tag)
        and c.name.lower()
        in ("p", "div", "ul", "ol", "li", "table", "pre", "blockquote", "h1", "h2",
            "h3", "h4", "h5", "h6", "section", "article", "figure", "dl", "form")
        for c in node.children
    )
    if has_block_child:
        out.append("")
        for child in node.children:
            if isinstance(child, Tag):
                _node_to_md(child, page_url, url_for, out, depth + 1)
        return

    text = re.sub(r"\s+", " ", _render_tag(node, page_url, url_for)).strip()
    if not text or text.lower() in _SKIP_TEXT:
        return
    if len(text) <= 3 and not re.search(r"\w{3}", text):
        return
    out.append(text)


def _md_lines(root: Tag, page_url: str, url_for) -> list[str]:
    out: list[str] = []
    for child in root.children:
        if isinstance(child, Tag):
            _node_to_md(child, page_url, url_for, out)
        elif isinstance(child, NavigableString):
            text = re.sub(r"\s+", " ", str(child)).strip()
            if text and text.lower() not in _SKIP_TEXT:
                out.append(text)
    return out


def _tidy(lines: list[str]) -> str:
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _page_title(soup: BeautifulSoup) -> str:
    for selector in ("h1.main", "h1", "h2.main", "title"):
        el = soup.select_one(selector)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                return text
    return ""


def _crumb(soup: BeautifulSoup) -> str:
    items = [
        re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        for a in soup.select("ol.breadcrumb .breadcrumb-item")
    ]
    items = [i for i in items if i and i not in ("Dashboard", "Home")]
    return " > ".join(items)


def _rubrics(scope: Tag, page_url: str, url_for) -> str:
    """Kumpulkan tabel penilaian/rubrik. Sering jadi penentu utama nilai.

    Tabel status pengumpulan (Submission status/Grading status/Time remaining)
    sengaja dikecualikan: kata "grading" di situ membuat tabel tersebut terbaca
    sebagai pedoman penilaian padahal tidak memuat bobot apa pun -- dan AI bisa
    saja menulis jawaban yang "sesuai" tabel kosong itu.
    """
    wanted = re.compile(
        r"grading|penilaian|assessment|skor|point|rubrik|kompetensi|indikator|"
        r"bobot|weight|kriteria",
        re.I,
    )
    blocks: list[str] = []
    for table in scope.select("table"):
        container = table.find_parent(["div", "section", "article"])
        ctx = (container.get_text(" ", strip=True) if container else "")[:300]
        if not wanted.search(ctx):
            continue
        rows = table.find_all("tr")
        labels = [
            (row.find(["th", "td"]).get_text(" ", strip=True) if row.find(["th", "td"]) else "")
            for row in rows
        ]
        status_rows = [lbl for lbl in labels if lbl and _STATUS_ROW_RE.match(lbl)]
        # Kalau semua baris status, ini bukan rubrik.
        if labels and len(status_rows) == len([lbl for lbl in labels if lbl]):
            continue
        md = _table_to_md(table, page_url, url_for)
        if md:
            blocks.append(md)
    if not blocks:
        return ""
    uniq = list(dict.fromkeys(blocks))
    return "\n\n".join(uniq[:4])


def _starter_posts(scope: Tag, page_url: str, url_for) -> str:
    """Untuk forum: post PEMBUKA saja. Balasan mahasiswa lain bukan bahan soal
    dan kalau ikut dibaca AI bisa menjurus jadi menyalin pekerjaan teman."""
    parts: list[str] = []
    starters = scope.select("[id^=post-content-]") or scope.select("article.forum-post")
    if starters:
        for el in starters[:1]:
            md = _tidy(_md_lines(el, page_url, url_for))
            if md:
                parts.append(md)
    for el in scope.select(".forumdescription, .forumheaderlist, #forum_intro"):
        md = _tidy(_md_lines(el, page_url, url_for))
        if md:
            parts.insert(0, md)
    return "\n\n".join(parts)


def render_moodle_html(
    html: str,
    page_url: str,
    *,
    kind: str = "generic",
    url_for=None,
    include_attachments: bool = True,
) -> str:
    """Ubah HTML halaman Moodle jadi Markdown yang enak dibaca AI.

    Urutan penting dan tidak boleh diacak:
      1. bersihkan kerangka yang jelas (nav/header/footer/form/script)
      2. pilih container konten terbaik
      3. bersihkan sisa menu/dropdown DI DALAM container
    Kalau langkah 1 dan 3 digabung, class tata letak pada elemen terluar bisa
    ikut terhapus dan seluruh halaman hilang -- persis yang pernah terjadi.
    """
    if url_for is None:
        url_for = lambda u, kind="page": u  # noqa: E731 - default: URL apa adanya
    soup = BeautifulSoup(html or "", "html.parser")
    title = _page_title(soup)
    crumb = _crumb(soup)
    _clean_document(soup)

    container = _pick_content(soup)
    _strip_chrome_tokens(container)

    body = _tidy(_md_lines(container, page_url, url_for))
    blocks: list[str] = []
    if title:
        blocks.append(f"# {title}")
    meta: list[str] = []
    if crumb:
        meta.append(f"- Lokasi: {crumb}")
    meta.append(f"- Jenis konten: {kind}")
    meta.append(f"- URL sumber: {page_url}")
    blocks.append("\n".join(meta))

    if kind in ("forum", "diskusi"):
        # Post pembuka SELALU menang kalau ada. Pernah dipakai perbandingan
        # panjang teks, dan itu salah: halaman forum memuat seluruh thread,
        # sehingga balasan mahasiswa lain ikut terbaca dan AI bisa ikut
        # mengikuti gaya/materi jawaban teman. Post pembuka adalah soal resmi.
        starter = _starter_posts(container, page_url, url_for)
        if starter.strip():
            body = starter
        blocks.append("## Isi Diskusi (post pembuka)")
        blocks.append(
            body
            or "_(tidak ada teks post pembuka; kemungkinan soal ada di lampiran "
            "atau di halaman seksi)_"
        )
    else:
        blocks.append("## Isi Halaman")
        blocks.append(body or "_(halaman tidak memuat teks; periksa lampiran)_")

    rubrics = _rubrics(container, page_url, url_for)
    # Kalau tabel rubrik sudah ikut ter-render di dalam body, jangan tampilkan
    # lagi. Duplikat menambah token dan bikin AI mengira rubrik itu
    # instruksi tambahan yang harus dijawab dua kali.
    if rubrics and rubrics.strip() not in body:
        blocks.append("## Pedoman Penilaian / Rubrik")
        blocks.append(rubrics)
        blocks.append(
            "> Tabel di atas adalah pedoman penilaian resmi. Jawaban WAJIB "
            "memenuhi setiap butir penilaian di dalamnya."
        )

    if include_attachments:
        atts = _attachment_lines(container, page_url, url_for)
        if atts:
            blocks.append("## Lampiran")
            blocks.append(atts)

    return _tidy(blocks) + "\n"


def _attachment_lines(scope: Tag, page_url: str, url_for) -> str:
    seen: dict[str, str] = {}
    for tag in scope.select("a[href], img[src], source[src], [data-src], [data-original]"):
        for attr in ("href", "src", "data-src", "data-original"):
            raw = (tag.get(attr) or "").strip()
            if not raw or raw.startswith("data:image/"):
                continue
            absolute = normalize_url(page_url, raw)
            if _is_asset_url(absolute):
                continue  # logo, avatar, ikon tema
            path = absolute.split("?", 1)[0].lower()
            is_file = (
                "pluginfile.php" in path
                or absolute.lower().endswith(_IMAGE_EXT + _DOC_EXT)
            )
            if not is_file:
                continue
            label = tag.get_text(" ", strip=True) or (tag.get("alt") or "").strip()
            if not label or label.lower() in _SKIP_TEXT:
                label = _basename(absolute) or "lampiran"
            label = re.sub(r"\s+", " ", label)[:160]
            seen.setdefault(url_for(absolute, kind="file"), label)
    if not seen:
        return ""
    return "\n".join(f"- {label} -> {url}" for url, label in seen.items())


# ---------------------------------------------------------------------------
# Verifikasi URL (dipakai discovery)
# ---------------------------------------------------------------------------
def verify_url(
    reader: MoodleReader,
    url: str,
    *,
    kind: str,
    use_cache: bool = True,
    work_kind: str = "",
) -> tuple[bool, str, Fetched]:
    """Cek satu URL benar-benar berisi konten yang bisa dipakai AI.

    `kind` = peran link (halaman/seksi/diskusi/lampiran).
    `work_kind` = jenis pekerjaan (diskusi/tugas). Keduanya sengaja dibedakan:
    renderer butuh yang kedua, karena halaman forum harus dirender sebagai
    forum -- hanya post pembuka -- bukan sebagai halaman biasa yang ikut memuat
    balasan mahasiswa lain.
    """
    render_kind = work_kind or kind
    fetched = reader.fetch(url, use_cache=use_cache)
    if fetched.error:
        return False, fetched.error, fetched
    if fetched.status in (401, 403):
        return False, f"HTTP {fetched.status} (akses ditolak)", fetched
    if not fetched.ok:
        return False, f"HTTP {fetched.status or 'kosong'}", fetched
    if fetched.is_login:
        return False, "halaman login (sesi Moodle kedaluwarsa)", fetched
    if not fetched.is_html:
        if len(fetched.body) < 200:
            return False, f"lampiran terlalu kecil ({len(fetched.body)}B)", fetched
        return True, f"lampiran {fetched.content_type or 'biner'}", fetched
    md, _ = reader.render(url, kind=render_kind, use_cache=use_cache)
    useful = _meaningful_length(md)
    if useful < _MIN_USEFUL_CHARS:
        return False, f"halaman kosong ({useful} karakter)", fetched
    return True, f"{useful} karakter", fetched


def _meaningful_length(markdown: str) -> int:
    """Hitung karakter yang benar-benar informasi (buang boilerplate Reader)."""
    text = re.sub(r"^#+\s*.*$", "", markdown, flags=re.MULTILINE)
    text = re.sub(r"^-\s*(Lokasi|Jenis konten|URL sumber):.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    return len(re.sub(r"\s+", " ", text).strip())
