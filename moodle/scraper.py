from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from moodle.auth import MoodleSession

_COURSE_RE = re.compile(r"/course/view\.php\?id=(\d+)")
_ACTIVITY_RE = re.compile(
    r"https://elearning\.ut\.ac\.id/mod/(\w+)/view\.php\?id=(\d+)"
)

# Item global / sidebar yang bukan konten sesi.
_GLOBAL_KEYWORDS = (
    "perkenalan",
    "announcement",
    "jadwal",
    "panduan",
    "rat",
    "tata tertib",
    "kendala",
    "saran",
    "video dan panduan",
    "site announcements",
)


@dataclass
class Course:
    id: int
    name: str

    @property
    def folder_name(self) -> str:
        safe = re.sub(r"[^\w\s-]", "", self.name)
        return re.sub(r"[\s-]+", "_", safe).strip("_") or str(self.id)


@dataclass
class Activity:
    mod_type: str  # forum | assign | lesson | resource | page | url | folder
    id: int
    title: str
    section: int = 0
    course_id: int = 0

    @property
    def url(self) -> str:
        return (
            f"https://elearning.ut.ac.id/mod/{self.mod_type}/view.php?id={self.id}"
        )


@dataclass
class SectionInfo:
    number: int
    title: str
    activities: list[Activity] = field(default_factory=list)


class CourseScraper:
    def __init__(self, session: MoodleSession) -> None:
        self.session = session

    # ---- Daftar kursus ---------------------------------------------------
    def get_courses(self) -> list[Course]:
        resp = self.session.get("/my/courses.php")
        soup = BeautifulSoup(resp.text, "html.parser")
        courses: dict[int, str] = {}
        for a in soup.select("a[href*='/course/view.php']"):
            m = _COURSE_RE.search(a.get("href", ""))
            if not m:
                continue
            text = a.get_text(strip=True)
            if not text:
                continue
            cid = int(m.group(1))
            courses.setdefault(cid, text)
        return [
            Course(id=cid, name=name)
            for cid, name in sorted(courses.items(), key=lambda x: x[1].lower())
        ]

    # ---- Sesi yang tersedia ----------------------------------------------
    def get_available_sections(self, course_id: int) -> list[SectionInfo]:
        """Ambil section yang saat ini tersedia (tiap Senin bertambah)."""
        resp = self.session.get("/course/view.php", params={"id": course_id})
        soup = BeautifulSoup(resp.text, "html.parser")

        numbers: set[int] = set()
        for a in soup.select("a[href*='section='], a[data-*='section']"):
            href = a.get("href") or a.get("data-target") or ""
            m = re.search(r"section=(\d+)", href)
            if m:
                numbers.add(int(m.group(1)))
        # Sesi pertama/halaman juga didapat via #sectionmenu select
        sel = soup.select_one("#sectionmenu")
        if sel:
            for opt in sel.select("option"):
                m = re.search(r"section=(\d+)", opt.get("value", ""))
                if m:
                    numbers.add(int(m.group(1)))

        if not numbers:
            numbers = {0}
        sections: list[SectionInfo] = []
        for num in sorted(n for n in numbers if n > 0):
            info = self._scrape_section(course_id, num)
            if info.activities:
                sections.append(info)
        return sections

    def _scrape_section(self, course_id: int, num: int) -> SectionInfo:
        resp = self.session.get(
            "/course/view.php", params={"id": course_id, "section": num}
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        title = ""
        crumb = soup.select_one("ol.breadcrumb .breadcrumb-item:last-child")
        if crumb:
            t = crumb.get_text(strip=True)
            if t and t not in ("Dashboard",):
                title = t
        if not title:
            float_title = ""
            for cand in soup.select(".sectionname, .sectiontitle, h3, .sectionname span"):
                t = cand.get_text(strip=True)
                if t and len(t) < 120 and not float_title:
                    float_title = t
            # preferensi: judul di dalam tautan nav sesi
            for a in soup.select('a.nav-link[href*="section"]'):
                t = a.get_text(strip=True)
                if t and len(t) < 120 and any(
                    kw in t.lower() for kw in ("sesi", "pendahuluan", "aktivitas")
                ):
                    title = t
                    break
        if not title:
            title = float_title or f"Sesi {num}"

        activities: list[Activity] = []
        seen: set[tuple[str, int]] = set()
        for a in soup.select("a[href]", href=True):
            m = _ACTIVITY_RE.search(a["href"])
            if not m:
                continue
            mod_type, mod_id = m.group(1), int(m.group(2))
            text = a.get_text(strip=True)
            if not text:
                continue
            key = (mod_type, mod_id)
            if key in seen:
                continue
            seen.add(key)
            if self._is_global(text):
                continue
            activities.append(
                Activity(
                    mod_type=mod_type,
                    id=mod_id,
                    title=text,
                    section=num,
                    course_id=course_id,
                )
            )

        return SectionInfo(number=num, title=title, activities=activities)

    @staticmethod
    def _is_global(text: str) -> bool:
        low = text.lower()
        return any(k in low for k in _GLOBAL_KEYWORDS)

    # ---- Pengelompokan aktivitas kerja -------------------------------------
    @staticmethod
    def split_assignable(activities: list[Activity]):
        """Pisah jadi (diskusi, tugas, lainnya)."""
        diskusi, tugas, lain = [], [], []
        for act in activities:
            low = act.title.lower()
            if act.mod_type == "forum" and ("diskusi" in low or "diskus" in low):
                diskusi.append(act)
            elif act.mod_type == "assign" or (
                act.mod_type == "forum" and "tugas" in low
            ):
                tugas.append(act)
            elif "tugas" in low:
                tugas.append(act)
            else:
                lain.append(act)
        return diskusi, tugas, lain