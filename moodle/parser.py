from __future__ import annotations

import re
from dataclasses import dataclass, field

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
        resp = self.session.get(activity.url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Deskripsi forum (tempat soal biasanya berada)
        desc_el = soup.select_one(
            ".forumdescription, .forumheaderlist, .no-overflow, "
            "[role=main] .generalbox"
        )
        if desc_el:
            text, atts = self._extract(desc_el)
            q.question += text
            q.attachment_urls.extend(atts)

        # Thread diskusi pertama: soal kadang di post pertama
        disc_link = None
        for a in soup.select("a[href*='discuss.php']"):
            disc_link = a["href"]
            break
        if disc_link and q.question.strip() == "":
            q.source_url = disc_link
            dresp = self.session.get(disc_link.split("#")[0])
            dsoup = BeautifulSoup(dresp.text, "html.parser")
            main = dsoup.select_one("[role=main]") or dsoup
            post = main.select_one(
                ".forumpost, .serforumpost, [data-post], article"
            ) or main
            text, atts = self._extract(post)
            q.question += text
            q.attachment_urls.extend(atts)
        elif disc_link:
            q.source_url = disc_link

        q.question = self._clean(q.question)
        return q

    # ---- Tugas (assignment) ----------------------------------------------
    def _parse_assign(self, activity: Activity) -> ParsedQuestion:
        q = ParsedQuestion(activity=activity, title=activity.title, source_url=activity.url)
        resp = self.session.get(activity.url)
        soup = BeautifulSoup(resp.text, "html.parser")

        container = soup.select_one(
            "#intro, .no-overflow, .activity-information, [role=main]"
        ) or soup
        text, atts = self._extract(container)
        q.question = self._clean(text)
        q.attachment_urls.extend(atts)

        # Instruksi bisa tersembunyi di popup submission
        for a in soup.select("a[href*='submission']"):
            pass
        return q

    def _parse_generic(self, activity: Activity) -> ParsedQuestion:
        q = ParsedQuestion(activity=activity, title=activity.title, source_url=activity.url)
        resp = self.session.get(activity.url)
        soup = BeautifulSoup(resp.text, "html.parser")
        main = soup.select_one("[role=main]") or soup
        text, atts = self._extract(main)
        q.question = self._clean(text)
        q.attachment_urls.extend(atts)
        return q

    # ---- Util --------------------------------------------------------------
    def _extract(self, el) -> tuple[str, list[str]]:
        text = el.get_text("\n", strip=True) if el else ""
        atts: list[str] = []
        html = ""
        if el is not None:
            html = str(el)
            atts = list(
                dict.fromkeys(
                    u
                    for u in re.findall(
                        r'https?://[^\s"\']*pluginfile\.php[^\s"\']*', html
                    )
                )
            )
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