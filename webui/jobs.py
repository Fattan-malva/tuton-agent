"""Manajer job: antre, jalankan Pipeline di thread, dan kumpulkan event.

Satu job aktif dalam satu waktu supaya `opencode run` tidak membanjiri mesin.
Tiap event yang dikirim pipeline lewat `reporter` disimpan ke memori (untuk
SSE) dan ke berkas `<job>/events.jsonl` (untuk replay saat halaman disegarkan).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import config
import courses
import moodle
import pipeline


class Job:
    """Satu pekerjaan (scrape atau manual) yang dilacak UI."""

    def __init__(self, id: str, kind: str, params: dict, slug: str, sesi: int) -> None:
        self.id = id
        self.kind = kind  # "scrape" | "manual"
        self.params = params
        self.slug = slug
        self.sesi = sesi
        self.status = "queued"  # queued | running | done | error
        self.events: list[dict] = []
        self.cond = threading.Condition()
        self.finished = False
        self.error = ""
        self.hasil: dict = {}
        self.dibuat = time.time()
        log_dir = config.work_dirs(slug, sesi)["log"]
        log_dir.mkdir(parents=True, exist_ok=True)
        self.event_file = log_dir / f"job-{id}.jsonl"
        self.reporter = self._buat_reporter()

    def _buat_reporter(self) -> "callable[[dict], None]":
        job = self

        def reporter(ev: dict) -> None:
            ev = dict(ev)
            ev["ts"] = time.time()
            ev["job"] = job.id
            with job.cond:
                job.events.append(ev)
                job.cond.notify_all()
            try:
                with open(job.event_file, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            except OSError:
                pass

        return reporter

    def push_status(self, status: str, error: str = "") -> None:
        with self.cond:
            self.status = status
            if error:
                self.error = error
            self.cond.notify_all()


class JobManager:
    """Menyimpan job, mengantre, dan menjalankan lewat thread dispatcher."""

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self._seq = 0
        self._queue: list[str] = []
        self._cv = threading.Condition()
        self._courses_cache: list[dict] | None = None
        self._courses_cache_t = 0.0
        t = threading.Thread(target=self._dispatch, name="jkt-dispatch", daemon=True)
        t.start()

    # ----------------------------------------------------------- pendaftaran

    def submit(self, kind: str, params: dict, slug: str, sesi: int) -> Job:
        with self.lock:
            self._seq += 1
            jid = f"j{self._seq}-{int(time.time()) % 100000:05d}"
            job = Job(jid, kind, params, slug, sesi)
            self.jobs[jid] = job
        with self._cv:
            self._queue.append(jid)
            self._cv.notify()
        return job

    # --------------------------------------------------------------- antrean

    def _dispatch(self) -> None:
        while True:
            with self._cv:
                while not self._queue:
                    self._cv.wait()
                jid = self._queue.pop(0)
            job = self.jobs.get(jid)
            if job is None:
                continue
            job.push_status("running")
            try:
                self._run(job)
            except Exception as exc:  # noqa: BLE001 - laporkan ke UI
                job.reporter({"level": "error", "stage": "", "msg": f"Gagal: {exc}"})
                job.push_status("error", str(exc))
            finally:
                with job.cond:
                    job.finished = True
                    job.cond.notify_all()

    # ----------------------------------------------------------------- run

    @staticmethod
    def _model_utama(params: dict) -> str | None:
        return (
            params.get("model")
            or config.env("PRIMARY_MODEL")
            or config.PRIMARY_MODEL
            or None
        )

    @staticmethod
    def _model_mata(params: dict) -> str | None:
        return (
            params.get("model_mata")
            or config.env("VISION_MODEL")
            or config.VISION_MODEL
            or None
        )

    def _run(self, job: Job) -> None:
        if job.kind == "manual":
            mk = courses.MataKuliah(
                id="manual",
                nama=job.params.get("matkul_nama") or "Manual",
                kode=job.params.get("matkul_kode") or "",
                kelas=job.params.get("matkul_kelas") or "",
                slug=job.slug,
            )
            manual = {
                "question": job.params.get("question", ""),
                "files": job.params.get("files", []),
                "jenis": job.params.get("jenis", "Tugas"),
                "dengan_referensi": bool(job.params.get("dengan_referensi", True)),
            }
            pipe = pipeline.Pipeline(
                mk, int(job.params.get("sesi", 1)),
                model_utama=self._model_utama(job.params),
                model_mata=self._model_mata(job.params),
                dengan_gambar=not job.params.get("tanpa_gambar", False),
                tanpa_docx=bool(job.params.get("tanpa_docx", False)),
                reporter=job.reporter,
                manual=manual,
            )
            hasil = pipe.jalankan()
        else:
            klien = moodle.Moodle()
            daftar = courses.daftar_mata_kuliah_lengkap(klien)
            mk = next(
                (x for x in daftar if x.id == job.params.get("matkul_id")), None
            )
            if mk is None:
                raise pipeline.PipelineGagal("Mata kuliah tidak ditemukan di akun.")
            pipe = pipeline.Pipeline(
                mk, int(job.params.get("sesi")),
                model_utama=self._model_utama(job.params),
                model_mata=self._model_mata(job.params),
                dengan_gambar=not job.params.get("tanpa_gambar", False),
                tanpa_docx=bool(job.params.get("tanpa_docx", False)),
                reporter=job.reporter,
            )
            hasil = pipe.jalankan()
        job.hasil = self._hasil_dict(hasil)
        job.push_status("done")

    @staticmethod
    def _hasil_dict(h) -> dict:
        if h is None:
            return {}
        return {
            "docx": str(h.docx) if h.docx else None,
            "jawaban": str(h.jawaban) if h.jawaban else None,
            "peta": str(h.peta) if h.peta else None,
            "referensi": str(h.referensi) if h.referensi else None,
            "gagal": list(getattr(h, "gagal", []) or []),
            "catatan": list(getattr(h, "catatan", []) or []),
        }

    # ------------------------------------------------------------- courses

    def courses(self) -> list[dict]:
        now = time.time()
        if self._courses_cache and now - self._courses_cache_t < 300:
            return self._courses_cache
        klien = moodle.Moodle()
        daftar = courses.daftar_mata_kuliah_lengkap(klien)
        out = [
            {
                "id": m.id, "nama": m.nama, "kode": m.kode,
                "kelas": m.kelas, "slug": m.slug,
            }
            for m in daftar
        ]
        self._courses_cache = out
        self._courses_cache_t = now
        return out

    def sessions(self, cid: str) -> list[dict]:
        klien = moodle.Moodle()
        daftar = courses.daftar_mata_kuliah_lengkap(klien)
        mk = next((x for x in daftar if x.id == cid), None)
        if mk is None:
            raise pipeline.PipelineGagal("Mata kuliah tidak ditemukan.")
        res = courses.sesi_berisi_soal(klien, mk)
        return [{"sesi": s, "jumlah": n} for s, n in res]
