"""Kumpulkan & verifikasi URL sumber soal untuk satu aktivitas.

Tujuan: menjamin AI selalu punya sumber yang benar-benar bisa dibaca. Alih-alih
menggantungkan diri pada satu selector CSS yang bisa gagal, modul ini mengumpulkan
seluruh kandidat URL (halaman aktivitas, halaman seksi, thread diskusi, lampiran),
memverifikasi satu per satu lewat Reader, dan hanya menyerahkan yang benar-benar
berisi soal.

Kalau kandidat pertama kosong, kandidat berikutnya tetap dipakai sebagai
cadangan. Inilah yang membuat "selalu berhasil mendapatkan soal" bukan
sekadar harapan.
"selalu berhasil mendapatkan soal" bukan sekadar harapan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config import Config
from moodle.reader import MoodleReader, _is_asset_url, normalize_url, verify_url
from moodle.scraper import Activity

# Peran URL, menentukan urutan prioritas dan cara AI membacanya.
ROLE_PAGE = "halaman"       # halaman aktivitas (isi soal utama)
ROLE_SECTION = "seksi"      # halaman course per seksi (instruksi tutor)
ROLE_DISCUSSION = "diskusi"  # thread diskusi (post pembuka)
ROLE_ATTACHMENT = "lampiran"  # berkas soal (PDF/gambar/dokumen)

_ROLE_ORDER = {ROLE_PAGE: 0, ROLE_DISCUSSION: 1, ROLE_SECTION: 2, ROLE_ATTACHMENT: 3}

_THREAD_RE = re.compile(r"(?:mod/forum/)?discuss\.php\?[^\"'#]*", re.I)
_FILE_EXT_RE = re.compile(
    r"\.(png|jpe?g|gif|bmp|webp|tiff?|pdf|docx?|xlsx?|xlsm|pptx?|odt|zip|txt|csv)(?:$|/)",
    re.I,
)


@dataclass
class SourceLink:
    """Satu URL kandidat beserta hasil verifikasinya."""

    url: str
    role: str
    ok: bool = False
    note: str = ""
    text_len: int = 0
    reader_url: str = ""

    @property
    def priority(self) -> int:
        return _ROLE_ORDER.get(self.role, 9)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "reader_url": self.reader_url,
            "role": self.role,
            "ok": self.ok,
            "note": self.note,
            "text_len": self.text_len,
        }


@dataclass
class SoalSource:
    """Kumpulan sumber untuk satu item: URL terverifikasi + lampiran."""

    item: Activity
    kind: str
    links: list[SourceLink] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    primary_url: str = ""
    soal_text: str = ""          # markdown halaman utama (untuk bagian Soal di docx)
    attempts: int = 0
    note: str = ""

    @property
    def ok_links(self) -> list[SourceLink]:
        return sorted(
            (link for link in self.links if link.ok),
            key=lambda link: (link.priority, -link.text_len),
        )

    @property
    def failed_links(self) -> list[SourceLink]:
        return [link for link in self.links if not link.ok]

    @property
    def page_links(self) -> list[SourceLink]:
        """URL yang dibaca AI lewat Reader (bukan berkas biner)."""
        return [link for link in self.ok_links if link.role != ROLE_ATTACHMENT]

    @property
    def file_links(self) -> list[SourceLink]:
        return [link for link in self.ok_links if link.role == ROLE_ATTACHMENT]

    def reader_urls(self) -> list[str]:
        """URL Reader siap pakai, urut dari paling penting."""
        return [link.reader_url for link in self.page_links if link.reader_url]

    def summary(self) -> str:
        if not self.ok_links:
            return "tidak ada sumber yang bisa diverifikasi"
        parts = []
        for role, label in (
            (ROLE_PAGE, "halaman"),
            (ROLE_DISCUSSION, "diskusi"),
            (ROLE_SECTION, "seksi"),
            (ROLE_ATTACHMENT, "lampiran"),
        ):
            count = sum(1 for link in self.ok_links if link.role == role)
            if count:
                parts.append(f"{count} {label}")
        return ", ".join(parts)

    def to_dict(self) -> dict:
        return {
            "title": self.item.title,
            "kind": self.kind,
            "primary_url": self.primary_url,
            "note": self.note,
            "summary": self.summary(),
            "links": [link.to_dict() for link in self.links],
        }


class SourceDiscovery:
    """Kumpulkan kandidat URL lalu verifikasi lewat Reader."""

    def __init__(self, reader: MoodleReader, *, make_url) -> None:
        self.reader = reader
        # make_url(url, kind) -> URL Reader siap pakai untuk prompt.
        self.make_url = make_url

    # -- kandidat URL ------------------------------------------------------
    def _section_url(self, activity: Activity) -> str:
        return (
            f"{Config.base_url()}/course/view.php"
            f"?id={activity.course_id}&section={activity.section}"
        )

    def _candidates(self, activity: Activity) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = [(ROLE_PAGE, activity.url)]
        if activity.course_id and activity.section > 0:
            out.append((ROLE_SECTION, self._section_url(activity)))
        return out

    def _thread_urls(self, activity: Activity) -> list[str]:
        """Cari link thread diskusi dari halaman aktivitas.

        `normalize_url` wajib dipakai di sini: Moodle menulis
        `mod/forum/discuss.php?...` relatif terhadap halaman yang sudah berada
        di `/mod/forum/`, sehingga urljoin polos menghasilkan
        `/mod/forum/mod/forum/discuss.php` yang dijawab 404. Padahal post
        pembuka diskusi justru sering jadi sumber soal yang paling kaya.
        """
        urls: list[str] = []
        page = self.reader.fetch(activity.url)
        if page.ok and page.is_html and not page.is_login:
            soup = BeautifulSoup(page.text, "html.parser")
            base = page.final_url or activity.url
            for tag in soup.select("a[href]"):
                href = (tag.get("href") or "").strip()
                if not href or not _THREAD_RE.search(href):
                    continue
                urls.append(normalize_url(base, href).split("#")[0])
        return list(dict.fromkeys(urls))[:2]

    def _attachment_urls(self, activity: Activity) -> list[str]:
        """Kumpulkan URL lampiran dari halaman aktivitas + seksi + thread."""
        found: list[str] = []

        def harvest(html: str, base: str) -> None:
            soup = BeautifulSoup(html or "", "html.parser")
            scopes = soup.select(
                "#introattachments, [id^=assign_files_tree], .assign_files_tree, "
                ".fileuploadsubmission, .attachments, .resourceworkaround, "
                ".activity-altcontent, #intro, .description-inner, .modintro"
            )
            # Tanpa wadah lampiran yang jelas, baru jatuh ke seluruh halaman --
            # dan di situ filter aset tema menjadi penting, kalau tidak logo dan
            # avatar ikut diunduh sebagai "lampiran".
            if not scopes and soup is not None:
                scopes = [soup]
            for scope in scopes:
                for tag in scope.select("a[href], img[src], source[src], [data-src], [data-original]"):
                    for attr in ("href", "src", "data-src", "data-original"):
                        raw = (tag.get(attr) or "").strip()
                        if not raw or raw.startswith(("data:", "javascript:", "#", "mailto:")):
                            continue
                        absolute = normalize_url(base, raw)
                        if _is_asset_url(absolute):
                            continue
                        path = absolute.split("?", 1)[0].lower()
                        if "pluginfile.php" in path or _FILE_EXT_RE.search(path):
                            found.append(absolute)

        page = self.reader.fetch(activity.url)
        if page.ok and page.is_html and not page.is_login:
            harvest(page.text, page.final_url or activity.url)
            # Post pembuka diskusi juga bisa memuat lampiran soal.
            for thread in self._thread_urls(activity)[:1]:
                tpage = self.reader.fetch(thread)
                if tpage.ok and tpage.is_html and not tpage.is_login:
                    harvest(tpage.text, tpage.final_url or thread)

        if activity.course_id and activity.section > 0:
            spage = self.reader.fetch(self._section_url(activity))
            if spage.ok and spage.is_html and not spage.is_login:
                soup = BeautifulSoup(spage.text, "html.parser")
                mod = soup.select_one(
                    f"#module-{activity.id}, [data-id='{activity.id}'][data-for='cmitem']"
                )
                if mod is not None:
                    harvest(str(mod), spage.final_url or self._section_url(activity))

        return list(dict.fromkeys(found))[:12]

    # -- verifikasi --------------------------------------------------------
    def _verify(
        self, url: str, role: str, *, use_cache: bool = True, work_kind: str = ""
    ) -> SourceLink:
        link = SourceLink(url=url, role=role)
        ok, note, fetched = verify_url(
            self.reader, url, kind=role, use_cache=use_cache, work_kind=work_kind
        )
        link.ok = ok
        link.note = note
        link.text_len = _meaningful(fetched)
        # URL Reader hanya dibuat untuk yang lolos: AI tidak boleh mencoba
        # URL yang sudah diketahui tidak berguna.
        link.reader_url = self.make_url(
            url, kind="file" if role == ROLE_ATTACHMENT else role
        )
        return link

    def discover(self, activity: Activity, kind: str, *, attempts: int = 2) -> SoalSource:
        source = SoalSource(item=activity, kind=kind)
        candidates = self._candidates(activity)

        # Verifikasi kandidat utama.
        for role, url in candidates:
            source.links.append(self._verify(url, role, work_kind=kind))

        # Thread diskusi (hanya relevan untuk forum/Diskusi).
        if activity.mod_type == "forum" or "diskus" in activity.title.lower():
            for thread in self._thread_urls(activity):
                source.links.append(self._verify(thread, ROLE_DISCUSSION, work_kind=kind))

        # Lampiran tetap dikumpulkan walau gagal diverifikasi sebagai halaman:
        # agent butuh tahu file apa yang tersedia.
        source.attachments = self._attachment_urls(activity)
        for url in source.attachments:
            if any(link.url == url for link in source.links):
                continue
            source.links.append(self._verify(url, ROLE_ATTACHMENT, work_kind=kind))

        # Retry: jika tak ada satu pun yang lolos, putar ulang TANPA cache
        # supaya perubahan halaman Moodle benar-benar diambil, bukan hasil lama.
        for _ in range(max(0, attempts - 1)):
            if source.ok_links:
                break
            source.attempts += 1
            refreshed = [
                self._verify(url, role, use_cache=False, work_kind=kind)
                for role, url in candidates
            ]
            known = {url for _, url in candidates}
            for thread_url in [
                link.url for link in source.links if link.role == ROLE_DISCUSSION
            ]:
                refreshed.append(
                    self._verify(
                    thread_url, ROLE_DISCUSSION,
                    use_cache=False, work_kind=kind,
                )
                )
                known.add(thread_url)
            for att_url in source.attachments:
                refreshed.append(
                    self._verify(
                    att_url, ROLE_ATTACHMENT,
                    use_cache=False, work_kind=kind,
                )
                )
                known.add(att_url)
            source.links = refreshed + [
                link for link in source.links if link.url not in known
            ]

        self._finalize(source)
        return source

    def _reorder_fresh(self, source: SoalSource) -> list[SourceLink]:
        return sorted(source.links, key=lambda link: (link.priority, not link.ok))

    def _finalize(self, source: SoalSource) -> None:
        ok = source.ok_links
        if ok:
            source.primary_url = ok[0].url
            md, _ = self.reader.render(ok[0].url, kind=source.kind)
            source.soal_text = md
            source.note = source.summary()
        else:
            source.note = _failure_note(source)

    def render_any(self, source: SoalSource) -> str:
        """Markdown gabungan dari semua URL halaman yang terverifikasi.

        Dipakai untuk bagian 'Soal' pada docx dan untuk fallback ketika mode
        `file` diaktifkan.
        """
        parts: list[str] = []
        seen: set[str] = set()
        for link in source.page_links:
            if link.url in seen:
                continue
            seen.add(link.url)
            md, _ = self.reader.render(link.url, kind=source.kind)
            if md.strip():
                parts.append(md)
        if not parts and source.soal_text:
            parts.append(source.soal_text)
        return "\n\n---\n\n".join(parts).strip()


def _meaningful(fetched) -> int:
    from moodle.reader import _meaningful_length  # noqa: PLC0415 - import lokal untuk menghindari siklus

    if not fetched or not fetched.ok or not fetched.is_html:
        return 0
    return _meaningful_length(fetched.text)


def _failure_note(source: SoalSource) -> str:
    if not source.links:
        return "tidak ada kandidat URL sama sekali untuk aktivitas ini"
    reasons = []
    for link in source.failed_links[:4]:
        reasons.append(f"{link.role}: {link.note}")
    login_hint = any("login" in link.note.lower() for link in source.failed_links)
    head = "semua sumber gagal dibaca"
    if login_hint:
        head = (
            "sesi Moodle tampaknya kedaluwarsa (halaman login). Perbarui "
            "MoodleSession di menu Settings lalu ulangi"
        )
    return f"{head} -> {'; '.join(reasons)}"
