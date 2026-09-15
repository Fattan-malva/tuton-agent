from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from moodle.auth import MoodleSession
from moodle.scraper import Activity

_PLUGINFILE_RE = re.compile(r"https?://[^\s'\"]*pluginfile\.php[^\s'\"]*")

# Baris "metadata" yang bukan isi soal: Due/extenggat, tanggal, jam, skor.
_NOISE_RE = re.compile(
    r"^(?:due|tenggat|deadline|batas\s*waktu|closing|closes?|open|opens?|"
    r"duration|class\s*(?:starts?|ends?)|graded|worth|points?|maksimum\s*skor|"
    r"max\s*(?:skor|points)|tanggal|jam|waktu)\b",
    re.I,
)
_DAY_RE = re.compile(
    r"\b(?:sunday|monday|tuesday|wednesday|thursday|friday|saturday|"
    r"minggu|senin|selasa|rabu|kamis|jumat|sabtu)\b",
    re.I,
)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_MONTH_RE = re.compile(
    r"\b(?:jan(?:uary)?\.?|feb(?:ruary)?\.?|mar(?:ch)?\.?|apr(?:il)?\.?|may|"
    r"juni?|juli?|aug(?:ust)?\.?|sept?(?:ember)?\.?|okt(?:ober)?\.?|"
    r"nov(?:ember)?\.?|des(?:ember)?\.?|mei|agu(?:stus)?\.?)\b",
    re.I,
)
_TIME_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b|\b\d{1,2}\s*(?:am|pm)\b", re.I)


def _is_noise_line(line: str) -> bool:
    """True kalau baris hanyalah metadata (Due:, tanggal, jam) atau kosong."""
    ln = line.strip()
    if not ln:
        return True
    low = ln.lower()
    if _NOISE_RE.search(low):
        return True
    words = [w for w in ln.split() if w]
    if _DAY_RE.search(ln) and (
        _YEAR_RE.search(ln) or _MONTH_RE.search(ln) or _TIME_RE.search(ln)
    ):
        return True
    if _YEAR_RE.search(ln) and len(words) <= 8 and not ln.rstrip().endswith("?"):
        return True
    if _TIME_RE.search(ln) and len(words) <= 6:
        return True
    return False


def question_body(question: str) -> str:
    """Teks soal yang benar-benar isi, tanpa baris metadata/Due/tanggal."""
    if not question:
        return ""
    kept = [ln for ln in question.splitlines() if not _is_noise_line(ln)]
    return "\n".join(kept).strip()


@dataclass
class ParsedQuestion:
    activity: Activity
    title: str
    question: str = ""
    attachment_urls: list[str] = field(default_factory=list)
    source_url: str = ""


class QuestionParser:
    def __init__(self, session: MoodleSession) -> None:
        self.session = session

    def parse(self, activity: Activity) -> ParsedQuestion:
        if activity.mod_type == "forum":
            return self._parse_forum(activity)
        if activity.mod_type == "assign":
            return self._parse_assign(activity)
        return self._parse_generic(activity)

    # ---- Forum / Diskusi ------------------------------------------------
    def _parse_forum(self, activity: Activity) -> ParsedQuestion:
        q = ParsedQuestion(activity=activity, title=activity.title)

        # Kondisi 1 — LUAR forum: deskripsi aktivitas di halaman section.
        #    Banyak tutor menaruh soal resmi di sana, kadang hanya berupa
        #    gambar inline base64 (data:image/...) yang tidak muncul di body
        #    forum. Kalau dapat soal asli, jangan mencampur konten forum.
        self._parse_section_activity(q, activity)
        if self._real_soal(q):
            q.question = self._clean(q.question)
            return q

        # Kondisi 2 — DALAM forum: deskripsi forum + post pembuka diskusi.
        #    Post pembuka SELALU dicek karena deskripsi forum kadang hanya
        #    berisi "Due: <tanggal>" sementara soal asli (teks/gambar/
        #    lampiran) ada di thread diskusi.
        resp = self.session.get(activity.url)
        soup = BeautifulSoup(resp.text, "html.parser")

        desc_el = soup.select_one(
            ".forumdescription, .forumheaderlist, #forum_intro, "
            "[role=main] .generalbox"
        )
        if desc_el:
            text, atts = self._extract(desc_el, activity.url)
            if text.strip():
                q.question = f"{q.question.strip()}\n\n{text}".strip()
            q.attachment_urls.extend(atts)

        # 3) Thread diskusi pertama: soal resmi ada di post PEMBUKA (starter),
        #    bukan di balasan mahasiswa. Ambil hanya starter-nya.
        for a in soup.select("a[href*='discuss.php']"):
            q.source_url = a["href"].split("#")[0]
            self._extract_starter_post(q, q.source_url)
            break

        # 4) Masih kosong -> ringkasan seksi di halaman course
        #    (soal resmi kadang ditaruh di course/view.php?id=..&section=..)
        if not self._real_soal(q):
            self._parse_section_context(q, activity)

        q.question = self._clean(question_body(q.question))
        return q

    def _real_soal(self, q: ParsedQuestion) -> bool:
        """True kalau soal benar-benar ada: ada lampiran, atau teks yang
        bukan baris metadata (Due:/tanggal/UI forum)."""
        if q.attachment_urls:
            return True
        body = re.sub(r"\s+", " ", question_body(q.question)).strip()
        if not body:
            return False
        words = [w for w in re.split(r"\W+", body) if len(w) > 1]
        return "?" in body or len(words) >= 3

    def _parse_section_activity(self, q: ParsedQuestion, activity: Activity) -> None:
        """Ambil deskripsi aktivitas dari halaman section (area #tabs-tree-start).

        Beberapa matkul menaruh soal resmi di deskripsi aktivitas pada course
        page — sering berupa gambar inline base64 (data:image/...) yang tidak
        muncul di body forum. Hanya elemen milik modul ini yang diambil.
        """
        if not activity.course_id or activity.section <= 0:
            return
        section_url = (
            f"https://elearning.ut.ac.id/course/view.php?id={activity.course_id}"
            f"&section={activity.section}"
        )
        resp = self.session.get(section_url)
        soup = BeautifulSoup(resp.text, "html.parser")

        mod = soup.select_one(
            f"#module-{activity.id}, [data-id='{activity.id}'][data-for='cmitem']"
        )
        if mod is None:
            return

        # Area deskripsi formal aktivitas (jangan ambil badge "Done/View" di
        # .activity-information atau balasan mahasiswa di thread).
        container = (
            mod.select_one(".activity-altcontent .description-inner")
            or mod.select_one(".activity-altcontent")
            or mod.select_one(".description-inner")
        )
        if container is None:
            container = mod
        text, atts = self._extract(container, section_url)
        if text.strip() or atts:
            q.question += text
            q.attachment_urls.extend(atts)
            q.source_url = section_url

    def _extract_starter_post(self, q: ParsedQuestion, disc_link: str) -> None:
        """Ambil isi+lampiran HANYA dari post pembuka diskusi (soal resmi)."""
        dresp = self.session.get(disc_link.split("#")[0])
        dsoup = BeautifulSoup(dresp.text, "html.parser")
        main = dsoup.select_one("[role=main]") or dsoup

        # mb2iq/standard Moodle: setiap post punya id="post-content-<pid>";
        # post pertama dalam DOM = starter diskusi.
        starter = (
            main.select_one("[id^='post-content-']")
            or main.select_one("header.firstpost")
            or main.select_one("article.forum-post, article")
            or main.select_one(".forumpost")
        )
        if starter is None:
            return

        text, atts = self._extract(starter, disc_link)
        if text.strip():
            q.question = f"{q.question.strip()}\n\n{text}".strip()
        q.attachment_urls.extend(atts)

    # ---- Tugas (assignment) ----------------------------------------------
    def _parse_assign(self, activity: Activity) -> ParsedQuestion:
        q = ParsedQuestion(activity=activity, title=activity.title, source_url=activity.url)
        resp = self.session.get(activity.url)
        soup = BeautifulSoup(resp.text, "html.parser")

        container = soup.select_one(
            "#intro, .no-overflow, .activity-information, [role=main]"
        ) or soup
        text, atts = self._extract(container, activity.url)
        q.question = self._clean(text)
        q.attachment_urls.extend(atts)

        if not q.question.strip() and not q.attachment_urls:
            self._parse_section_context(q, activity)
            q.question = self._clean(q.question)

        # Instruksi bisa tersembunyi di popup submission
        for a in soup.select("a[href*='submission']"):
            pass
        return q

    def _parse_generic(self, activity: Activity) -> ParsedQuestion:
        q = ParsedQuestion(activity=activity, title=activity.title, source_url=activity.url)
        resp = self.session.get(activity.url)
        soup = BeautifulSoup(resp.text, "html.parser")
        main = soup.select_one("[role=main]") or soup
        text, atts = self._extract(main, activity.url)
        q.question = self._clean(text)
        q.attachment_urls.extend(atts)

        if not q.question.strip() and not q.attachment_urls:
            self._parse_section_context(q, activity)
            q.question = self._clean(q.question)
        return q

    # ---- Util --------------------------------------------------------------
    def _parse_section_context(self, q: ParsedQuestion, activity: Activity) -> None:
        """Ambil konteks/soal resmi dari ringkasan seksi di halaman course.

        Beberapa matkul menaruh soal di ringkasan seksi (course/view.php?id=..
        &section=..) alih-alih di body forum/aktivitas, jadi parser harus
        beradaptasi agar selalu dapat soal resminya.
        """
        if not activity.course_id or activity.section <= 0:
            return
        section_url = (
            f"https://elearning.ut.ac.id/course/view.php?id={activity.course_id}"
            f"&section={activity.section}"
        )
        resp = self.session.get(section_url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Judul seksi (mis. "Arti dan Sifat Model Regresi Linear Sederhana")
        for cand in soup.select(
            ".course-section-header .sectionname, .section-title, "
            "[data-for=section_title] .sectionname, h3.sectionname"
        ):
            t = cand.get_text(" ", strip=True)
            if t:
                q.question += f"{t}\n\n"
                break

        # Ringkasan/pengantar seksi — tempat tutor menaruh soal resmi
        for el in soup.select(
            ".course-description-item.summarytext, "
            ".summarytext .no-overflow, "
            ".single-section .summarytext, "
            ".section .summary .no-overflow, "
            "#coursecontentcollapse1 .summarytext"
        ):
            text, atts = self._extract(el, section_url)
            if text.strip() or atts:
                q.question += text
                q.attachment_urls.extend(atts)
                q.source_url = section_url
                break

    def _extract(self, el, base_url: str = "") -> tuple[str, list[str]]:
        text = el.get_text("\n", strip=True) if el else ""
        atts: list[str] = []
        if el is not None:
            candidates: list[str] = []
            for tag in el.select("a[href], img[src], source[src], [data-src], [data-original]"):
                for attr in ("href", "src", "data-src", "data-original"):
                    raw = (tag.get(attr) or "").strip()
                    if raw:
                        candidates.append(raw)
            for raw in candidates:
                if raw.startswith("data:image/") and ";base64," in raw:
                    absolute = raw
                elif raw.startswith(("data:", "javascript:", "#")):
                    continue
                else:
                    absolute = urljoin(base_url, raw)
                path = absolute.lower().split("?", 1)[0]
                if (
                    "pluginfile.php" in path
                    or re.search(
                        r"\.(png|jpe?g|gif|bmp|webp|tiff?|pdf|docx?|xlsx?|xlsm|pptx?|txt|csv)(?:$|/)",
                        path,
                    )
                    or absolute.startswith("data:image/")
                ):
                    atts.append(absolute)
            atts = list(dict.fromkeys(atts))
        return text, atts

    @staticmethod
    def _clean(text: str) -> str:
        # buang artefak UI forum yang ikut tersalin
        drop = {"permalink", "reply", "unread", "subscribe", "mark as read"}
        kept = []
        for line in text.splitlines():
            if line.strip().lower() in drop:
                continue
            kept.append(line)
        text = "\n".join(kept)
        # buang duplikat baris berurutan (konten forum/section yang sama)
        dedup: list[str] = []
        prev = None
        for line in text.splitlines():
            s = line.strip()
            if s and s == prev:
                continue
            prev = s
            dedup.append(line)
        text = "\n".join(dedup)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()