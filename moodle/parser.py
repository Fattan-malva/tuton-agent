from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from moodle.auth import MoodleSession
from moodle.scraper import Activity

_PLUGINFILE_RE = re.compile(r"https?://[^\s'\"]*pluginfile\.php[^\s'\"]*")


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

        # 1) PRIORITAS: deskripsi aktivitas di halaman SECTION
        #    (course/view.php?id=..&section=..#tabs-tree-start).
        #    Banyak tutor menaruh soal resmi di sana — kadang hanya berupa
        #    gambar inline base64 (data:image/...) yang tidak terlihat di
        #    body forum. Kalau dapat, jangan mencampur konten forum.
        self._parse_section_activity(q, activity)
        if q.question.strip() or q.attachment_urls:
            q.question = self._clean(q.question)
            return q

        resp = self.session.get(activity.url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 2) Deskripsi/intro forum (tempat soal resmi biasanya berada).
        #    Hanya elemen intro formal — jangan tampung .no-overflow umum
        #    agar "Permalink/Reply" atau lampiran balasan mahasiswa tak terambil.
        desc_el = soup.select_one(
            ".forumdescription, .forumheaderlist, #forum_intro, "
            "[role=main] .generalbox"
        )
        if desc_el:
            text, atts = self._extract(desc_el, activity.url)
            q.question += text
            q.attachment_urls.extend(atts)

        # 3) Thread diskusi pertama: soal resmi ada di post PEMBUKA (starter),
        #    bukan di balasan mahasiswa. Ambil hanya starter-nya.
        disc_link = None
        for a in soup.select("a[href*='discuss.php']"):
            disc_link = a["href"]
            break
        if disc_link:
            q.source_url = disc_link.split("#")[0]
            if not q.question.strip():
                self._extract_starter_post(q, disc_link)

        # 4) Masih kosong -> ringkasan seksi di halaman course
        #    (soal resmi kadang ditaruh di course/view.php?id=..&section=..)
        if not q.question.strip() and not q.attachment_urls:
            self._parse_section_context(q, activity)

        q.question = self._clean(q.question)
        return q

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
        starter = main.select_one("[id^='post-content-']")
        if starter is None:
            starter = main.select_one(".forumpost, article")
        if starter is None:
            return

        text, atts = self._extract(starter, disc_link)
        q.question += text
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
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()