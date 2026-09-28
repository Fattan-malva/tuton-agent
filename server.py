from __future__ import annotations

import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests

from flask import Flask, jsonify, request, send_from_directory

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
from flask_cors import CORS

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config, OUTPUT_DIR, stamp_display
from generator import state
from moodle.auth import MoodleSession
from moodle.discovery import SourceDiscovery
from moodle.downloader import AttachmentDownloader
from moodle.parser import QuestionParser
from moodle.reader import MoodleReader
from moodle.reader_server import ensure_reader, handle_file, handle_soal, soalu
from moodle.scraper import Activity, CourseScraper

app = Flask(__name__, static_folder="frontend", static_url_path="")
CORS(app)

# Soal sering dilampirkan sebagai PDF/gambar besar. Batas default Flask tak ada,
# tapi nginx di depannya membatasi 1MB -> unggah besar ditolak 413.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024

# Model bawaan opencode. Dipakai kalau .env belum menyebut OPENCODE_MODEL,
# dan jadi nilai yang dikembalikan dropdown Settings sebagai pilihan awal.
DEFAULT_MODEL = "opencode/big-pickle"
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

# Global state for running processes
running_process: subprocess.Popen | None = None
process_output: list[str] = []
process_lock = threading.Lock()
_process_start_time: float = 0.0


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _kill_proc_tree(proc: subprocess.Popen) -> None:
    """Kill sebuah proses beserta seluruh anaknya. Di Windows pakai
    taskkill /T sehingga opencode/node yang dibesarkan ikut mati (tidak orphan)."""
    if os.name != "nt":
        proc.kill()
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _read_process_output(proc: subprocess.Popen):
    """Stream stdout proses anak secara real-time (Linux + Windows).

    Baca dalam mode binary chunk kecil (bukan TextIOWrapper): TextIOWrapper
    buffer 8KB bikin isi pipe baru terbaca setelah EOF di Windows sehingga
    log di UI muncul baru di akhir run. Binary + read chunk mengalir begitu
    data tersedia di kedua OS. Spinner/progress (bare \\r) dipecah manual
    supaya tetap keluar sebagai baris ke UI."""
    global process_output
    # read1 -> BufferedReader (mengembalikan chunk begitu ada data);
    # read -> FileIO/_WindowsPipeIO (raw pipe, bufsize=0).
    read = getattr(proc.stdout, "read1", proc.stdout.read)
    buf = b""
    try:
        while True:
            chunk = read(4096)
            if not chunk:
                break
            buf += bytes(chunk)
            while True:
                nl = buf.find(b"\n")
                cr = buf.find(b"\r")
                if nl == -1 and cr == -1:
                    break
                sep = nl if (nl != -1 and (cr == -1 or nl < cr)) else cr
                line = _strip_ansi(
                    buf[:sep].decode("utf-8", errors="replace")
                ).rstrip("\r")
                buf = buf[sep + 1:]
                if line:
                    with process_lock:
                        process_output.append(line)
        line = _strip_ansi(buf.decode("utf-8", errors="replace")).rstrip("\r\n")
        if line:
            with process_lock:
                process_output.append(line)
    except Exception as e:
        with process_lock:
            process_output.append(f"ERROR: {e}")
    finally:
        proc.wait()


def run_command_async(cmd: list[str], cwd: Path | None = None) -> dict:
    """Run a command asynchronously and return process info."""
    global running_process, process_output, _process_start_time

    with process_lock:
        if running_process and running_process.poll() is None:
            return {"success": False, "error": "Another process is already running"}

        process_output = []
        _process_start_time = time.time()

        kwargs: dict[str, Any] = dict(
            cwd=str(cwd or Path(__file__).parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # Binary + bufsize=0: tanpa TextIOWrapper/WH bundling sehingga
            # pembacaan stdout realtime di Linux maupun Windows.
            bufsize=0,
        )
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        running_process = subprocess.Popen(cmd, **kwargs)

    thread = threading.Thread(target=_read_process_output, args=(running_process,), daemon=True)
    thread.start()

    return {"success": True, "message": "Process started"}


@app.errorhandler(413)
def upload_too_large(_exc):
    limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
    return jsonify({
        "success": False,
        "error": f"Ukuran unggahan melebihi {limit_mb} MB. Kompres file atau tulis soal di kolom teks.",
    }), 413


@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tuton-agent"})


@app.route("/api/login", methods=["POST"])
def login():
    """Authenticate against app credentials from .env."""
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()

    if username == Config.APP_USERNAME and password == Config.APP_PASSWORD:
        return jsonify({"success": True, "message": "Login berhasil"})

    return jsonify({
        "success": False,
        "error": "Username atau password tidak valid"
    }), 401


def _positive_int(value, fallback: int, *, maximum: int = 100) -> int:
    """Terima hanya bilangan bulat positif dalam batas; selain itu pakai fallback."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    if number < 1:
        return fallback
    return min(number, maximum)


def _enum_value(value, allowed: tuple[str, ...], fallback: str) -> str:
    """Terima hanya nilai dari daftar yang diizinkan (kecil-kecil)."""
    text = str(value or "").strip().lower()
    return text if text in allowed else fallback


@app.route("/api/models")
def get_models():
    """Daftar semua model opencode untuk dropdown di Settings.

    Dikelompokkan per provider supaya daftar 400+ model masih bisa dibaca.
    Model yang sedang dipakai ditandai `current`, jadi UI tidak perlu
    membandingkan sendiri. Model aktif juga selalu ikut dikirim walau opencode
    tidak melaporkannya, supaya pilihan di Settings tidak pernah "hilang".
    """
    try:
        from generator.opencode_runner import list_models

        refresh = request.args.get("refresh") == "1"
        ids = list_models(use_cache=not refresh)
        current = (Config.OPENCODE_MODEL or "").strip()

        groups: dict[str, list[dict]] = {}
        for model_id in ids:
            provider, _, name = model_id.partition("/")
            groups.setdefault(provider or "(lainnya)", []).append(
                {"id": model_id, "name": name or model_id, "current": model_id == current}
            )
        ordered = [
            {"provider": provider, "models": models}
            for provider, models in sorted(groups.items())
        ]
        if current and not any(m["current"] for g in ordered for m in g["models"]):
            provider, _, name = current.partition("/")
            ordered.append({
                "provider": provider or "(lainnya)",
                "models": [{"id": current, "name": name or current, "current": True}],
            })
        return jsonify({
            "success": True,
            "current": current,
            "default": DEFAULT_MODEL,
            "total": len(ids),
            "groups": ordered,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/config")
def get_config():
    """Get current configuration (without sensitive data)."""
    return jsonify({
        "nama": Config.NAMA,
        "nim": Config.NIM,
        "prodi": Config.PRODI,
        "model": Config.OPENCODE_MODEL or DEFAULT_MODEL,
        "default_model": DEFAULT_MODEL,
        "base_url": Config.MOODLE_BASE_URL,
        "has_session": bool(Config.moodle_session()),
        "output_dir": str(OUTPUT_DIR),
        "runtime": {
            "jobs": Config.TUTON_JOBS,
            "soal_mode": Config.TUTON_SOAL_MODE,
            "timeout": Config.TUTON_TIMEOUT,
            "retries": Config.TUTON_RETRIES,
            "transcribe": Config.TUTON_TRANSCRIBE,
            "vision_tries": Config.OPENCODE_VISION_TRIES,
        },
    })


@app.route("/api/config", methods=["POST"])
def save_config():
    """Save configuration. Session Moodle ke file JSON, sisanya ke .env."""
    data = request.get_json() or {}

    # Moodle session disimpan ke JSON agar bisa di-update kapan saja
    # tanpa menyentuh .env (dan tidak terekpos sebagai variabel env).
    if data.get("moodle_session"):
        Config.save_moodle_session(str(data["moodle_session"]))

    env_path = Path(__file__).parent / ".env"
    env_lines = []

    # Read existing .env
    if env_path.exists():
        env_lines = env_path.read_text(encoding="utf-8").splitlines()

    # Update or add keys (MOODLE_SESSION sengaja tidak dimasukkan ke .env)
    # Base URL: field kosong TIDAK boleh menimpa nilai yang sekarang, kalau tidak
    # .env bisa tersimpan dengan MOODLE_BASE_URL= dan semua request jadi URL relatif.
    moodle_url = str(data.get("moodle_url") or "").strip() or Config.MOODLE_BASE_URL
    updates = {
        "NAMA": data.get("nama", ""),
        "NIM": data.get("nim", ""),
        "PRODI": data.get("prodi", ""),
        "MOODLE_BASE_URL": moodle_url,
        "OPENCODE_MODEL": str(data.get("opencode_model") or "").strip()
        or Config.OPENCODE_MODEL
        or DEFAULT_MODEL,
    }

    # Setelan kecepatan pipeline. Kalau form tidak mengirim field, nilai saat
    # ini yang dipertahankan (bukan default), jadi menyimpan dari Settings
    # tidak diam-diam mengubah perilaku run berikutnya.
    updates.update(
        {
            "TUTON_JOBS": _positive_int(data.get("jobs"), Config.TUTON_JOBS, maximum=8),
            "TUTON_SOAL_MODE": _enum_value(
                data.get("soal_mode"), ("url", "file"), Config.TUTON_SOAL_MODE
            ),
            "TUTON_TRANSCRIBE": _enum_value(
                data.get("transcribe"), ("auto", "always", "never"), Config.TUTON_TRANSCRIBE
            ),
        }
    )
    
    # Process existing lines
    new_lines = []
    seen_keys = set()
    for line in env_lines:
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=")[0].strip()
            if key == "MOODLE_SESSION":
                continue  # dipindah ke moodle_credentials.json
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                seen_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # Add missing keys
    for key, value in updates.items():
        if key not in seen_keys and value:
            new_lines.append(f"{key}={value}")
    
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    
    # Reload config
    from importlib import reload
    import config
    refreshed_config = reload(config)
    globals()["Config"] = refreshed_config.Config
    globals()["OUTPUT_DIR"] = refreshed_config.OUTPUT_DIR
    
    return jsonify({"success": True, "message": "Configuration saved"})


@app.route("/api/courses")
def get_courses():
    """Get list of courses from Moodle."""
    try:
        Config.require()
        session = MoodleSession()
        session.check_login()
        scraper = CourseScraper(session)
        courses = scraper.get_courses()
        
        return jsonify({
            "success": True,
            "courses": [
                {"id": c.id, "name": c.name, "folder_name": c.folder_name}
                for c in courses
            ]
        })
    except requests.TooManyRedirects:
        return jsonify({
            "success": False,
            "error": "Session Moodle tidak valid atau sudah kedaluwarsa. Perbarui MOODLE_COOKIE (MoodleSession) di Settings.",
        }), 401
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/courses/<int:course_id>/sections")
def get_course_sections(course_id: int):
    """Get available sections for a course."""
    try:
        Config.require()
        session = MoodleSession()
        session.check_login()
        scraper = CourseScraper(session)
        sections = scraper.get_available_sections(course_id)
        
        return jsonify({
            "success": True,
            "sections": [
                {"number": s.number, "title": s.title}
                for s in sections
            ]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/courses/<int:course_id>/activities")
def get_course_activities(course_id: int):
    """Get all activities for a course (scrape view)."""
    try:
        Config.require()
        session = MoodleSession()
        session.check_login()
        scraper = CourseScraper(session)
        
        courses = scraper.get_courses()
        course = next((c for c in courses if c.id == course_id), None)
        if not course:
            return jsonify({"success": False, "error": "Course not found"}), 404
        
        sections = scraper.get_available_sections(course_id)
        result = []
        
        for sec in sections:
            diskusi, tugas, lain = scraper.split_assignable(sec.activities)
            result.append({
                "section": sec.number,
                "section_title": sec.title,
                "diskusi": [{"id": d.id, "title": d.title, "mod_type": d.mod_type} for d in diskusi],
                "tugas": [{"id": t.id, "title": t.title, "mod_type": t.mod_type} for t in tugas],
                "lain": [{"id": x.id, "title": x.title, "mod_type": x.mod_type} for x in lain],
            })
        
        return jsonify({"success": True, "course": course.name, "sections": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/status")
def get_status():
    """Get current work status from state.json."""
    try:
        st = state._load()
        items = st.get("items", {})
        
        result = []
        for k, v in sorted(items.items()):
            result.append({
                "key": k,
                "status": v.get("status", "unknown"),
                "matkul": v.get("matkul", "?"),
                "sesi": v.get("sesi"),
                "kind": v.get("kind"),
                "index": v.get("index"),
                "desc": v.get("desc", "?"),
                "created_at": stamp_display(v.get("created_at", "")),
                "finished_at": stamp_display(v.get("finished_at", "")),
                "duration_sec": v.get("duration_sec"),
                "reason": v.get("reason"),
                "urls": v.get("urls", []),
                "outputs": v.get("outputs", []),
            })
        
        # Calculate stats
        done = sum(1 for r in result if r["status"] == "done")
        failed = sum(1 for r in result if r["status"] == "failed")
        pending = len(result) - done - failed
        
        return jsonify({
            "success": True,
            "stats": {"done": done, "failed": failed, "pending": pending, "total": len(result)},
            "items": result
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/results")
def get_results():
    """Get completed results with file info."""
    try:
        st = state._load()
        items = st.get("items", {})
        
        # Group by course
        courses_map: dict[str, dict] = {}
        
        for k, v in sorted(items.items()):
            if v.get("status") != "done":
                continue
            
            course_name = v.get("matkul", "Unknown")
            if course_name not in courses_map:
                courses_map[course_name] = {
                    "name": course_name,
                    "files": [],
                    "has_errors": False
                }
            
            for output_path in v.get("outputs", []):
                p = Path(output_path)
                if p.exists():
                    try:
                        rel = p.resolve().relative_to(OUTPUT_DIR.resolve())
                    except ValueError:
                        rel = None
                    if rel and rel.parts and not courses_map[course_name].get("folder"):
                        courses_map[course_name]["folder"] = rel.parts[0]
                if p.suffix.lower() != ".docx":
                    continue
                if p.exists():
                    stat = p.stat()
                    try:
                        rel_path = "/".join(p.resolve().relative_to(OUTPUT_DIR.resolve()).parts)
                    except ValueError:
                        rel_path = p.name
                    courses_map[course_name]["files"].append({
                        "name": p.name,
                        "path": rel_path,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "created_at": stamp_display(v.get("created_at", "")),
                        "finished_at": stamp_display(v.get("finished_at", "")),
                        "duration_sec": v.get("duration_sec"),
                        "kind": v.get("kind"),
                        "index": v.get("index"),
                        "sesi": v.get("sesi"),
                        "urls": v.get("urls", []),
                    })
        
        # Convert to list
        courses_list = list(courses_map.values())
        
        return jsonify({"success": True, "courses": courses_list})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/download/<path:filepath>")
def download_file(filepath: str):
    """Download a generated file."""
    try:
        # Security: ensure file is within OUTPUT_DIR
        full_path = _resolve_output_file(filepath)
        if full_path is None:
            return jsonify({"success": False, "error": "Access denied"}), 403
        
        if not full_path.exists():
            return jsonify({"success": False, "error": "File not found"}), 404
        
        resp = send_from_directory(full_path.parent, full_path.name, as_attachment=True)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _resolve_output_file(filepath: str) -> Path | None:
    """Resolve a result path while preventing access outside output/."""
    candidate = Path(filepath)
    full_path = candidate.resolve() if candidate.is_absolute() else (OUTPUT_DIR / candidate).resolve()
    output_root = OUTPUT_DIR.resolve()
    try:
        full_path.relative_to(output_root)
    except ValueError:
        return None
    return full_path


@app.route("/api/results/<path:filepath>", methods=["DELETE"])
def delete_result(filepath: str):
    """Delete a generated DOCX result file."""
    try:
        full_path = _resolve_output_file(filepath)
        if full_path is None:
            return jsonify({"success": False, "error": "Access denied"}), 403
        if full_path.suffix.lower() != ".docx":
            return jsonify({"success": False, "error": "Only DOCX results can be deleted"}), 400
        if not full_path.exists():
            return jsonify({"success": False, "error": "File not found"}), 404

        full_path.unlink()
        return jsonify({"success": True, "message": f"{full_path.name} dihapus"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/courses/<path:folder>", methods=["DELETE"])
def delete_course(folder: str):
    """Hapus seluruh folder matkul di bawah output/ beserta riwayatnya di state."""
    try:
        if not folder or ".." in Path(folder).parts:
            return jsonify({"success": False, "error": "Access denied"}), 403
        course_dir = (OUTPUT_DIR / folder).resolve()
        output_root = OUTPUT_DIR.resolve()
        try:
            course_dir.relative_to(output_root)
        except ValueError:
            return jsonify({"success": False, "error": "Access denied"}), 403
        if not course_dir.is_dir():
            return jsonify({"success": False, "error": f"Folder matkul '{folder}' tidak ditemukan"}), 404

        shutil.rmtree(course_dir)

        prefix = str(course_dir)
        st = state._load()
        items = st.get("items", {})
        removed = 0
        for k in list(items.keys()):
            outs = items[k].get("outputs") or []
            if any(str(o).startswith(prefix + os.sep) or str(o) == prefix for o in outs):
                del items[k]
                removed += 1
        state.save()

        return jsonify({
            "success": True,
            "message": f"{folder} dihapus",
            "removed": removed,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/run", methods=["POST"])
def run_agent():
    """Run the tuton agent."""
    data = request.get_json() or {}
    course_id = data.get("course_id")
    sesi = data.get("sesi")
    force = data.get("force", False)
    kind = str(data.get("kind") or "all").strip().lower()
    if kind not in ("all", "tugas", "diskusi"):
        kind = "all"
    # Pipel ini boleh paralel: tiap item = 1 proses opencode run, jumlah
    # keseluruhan tetap dikendalikan --jobs.
    try:
        jobs = max(1, min(int(data.get("jobs") or 0) or Config.TUTON_JOBS, 8))
    except (TypeError, ValueError):
        jobs = max(1, Config.TUTON_JOBS)

    # Unbuffered stdout is required so main.py/OpenCode logs reach the UI live.
    cmd = [sys.executable, "-u", "main.py", "run"]
    if course_id:
        cmd.extend(["--course", str(course_id)])
    if sesi:
        cmd.extend(["--sesi", str(sesi)])
    cmd.extend(["--kind", kind, "--jobs", str(jobs)])
    if force:
        cmd.append("--force")
    
    result = run_command_async(cmd)
    return jsonify(result)


# ---------------------------------------------------------------------------
# Reader Lokal: hasilkan & sajikan URL yang dibaca agent `tuton`.
# Endpoint ini membuat UI bisa menampilkan "apa yang sebenarnya dilihat AI"
# tanpa harus menjalankan pipeline.
# ---------------------------------------------------------------------------
@app.route("/api/reader/health")
def reader_health():
    """Status Reader Lokal + apakah ia sedang hidup."""
    base = ensure_reader()
    return jsonify({
        "success": True,
        "base_url": base,
        "active": bool(base),
        "note": (
            "Reader hanya hidup selama proses main.py berjalan. Untuk pratinjau "
            "on-demand, endpoint /api/reader/preview tetap bisa dipakai."
        ),
    })


@app.route("/api/reader/preview")
def reader_preview():
    """Pratinjau persis isi yang akan dibaca AI dari satu URL Moodle."""
    url = (request.args.get("u") or "").strip()
    kind = (request.args.get("k") or "generic").strip()
    if not url:
        return jsonify({"success": False, "error": "Parameter u wajib diisi."}), 400
    try:
        Config.require()
        status, ctype, body = handle_soal(url, kind)
        return jsonify({
            "success": status == 200,
            "http_status": status,
            "content_type": ctype,
            "body": body,
            "chars": len(body),
        }), (200 if status == 200 else status)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/reader/urls")
def reader_urls():
    """Daftar URL sumber yang terverifikasi untuk satu course/sesi/jenis.

    Dipakai UI untuk menampilkan tombol "lihat sumber" sebelum menjalankan
    pipeline, sehingga user bisa memastikan soal-nya memang ketemu.
    """
    try:
        course_id = request.args.get("course_id", type=int)
        if not course_id:
            return jsonify({"success": False, "error": "course_id wajib diisi."}), 400
        sesi = request.args.get("sesi", type=int)
        kind = (request.args.get("kind") or "all").strip().lower()
        if kind not in ("all", "tugas", "diskusi"):
            kind = "all"
        Config.require()
        session = MoodleSession()
        session.check_login()
        scraper = CourseScraper(session)
        reader = MoodleReader()
        base = ensure_reader()

        courses = scraper.get_courses()
        course = next((c for c in courses if c.id == course_id), None)
        if course is None:
            return jsonify({"success": False, "error": "Course not found"}), 404

        discovery = SourceDiscovery(reader, make_url=soalu)
        sections = scraper.get_available_sections(course_id)
        out = []
        for sec in sections:
            if sesi and sec.number != sesi:
                continue
            diskusi, tugas, _ = scraper.split_assignable(sec.activities)
            picks = []
            if kind in ("all", "diskusi"):
                picks += [(d, "diskusi") for d in diskusi]
            if kind in ("all", "tugas"):
                picks += [(t, "tugas") for t in tugas]
            for activity, item_kind in picks:
                source = discovery.discover(activity, item_kind)
                out.append({
                    "section": sec.number,
                    "kind": item_kind,
                    "title": activity.title,
                    "summary": source.summary(),
                    "note": source.note,
                    "primary_url": source.primary_url,
                    "reader_url": (
                        source.reader_urls()[0] if source.reader_urls() else ""
                    ),
                    "links": [link.to_dict() for link in source.links],
                })
        return jsonify({
            "success": True,
            "course": course.name,
            "reader_base": base,
            "items": out,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/reader/file")
def reader_file():
    """Unduh lampiran lewat Reader (bisa dibuka langsung di browser)."""
    url = (request.args.get("u") or "").strip()
    if not url:
        return jsonify({"success": False, "error": "Parameter u wajib diisi."}), 400
    try:
        status, ctype, body = handle_file(url)
        if status != 200:
            return jsonify({
                "success": False,
                "http_status": status,
                "error": body.decode("utf-8", "replace"),
            }), status
        resp = app.response_class(body, mimetype=ctype)
        resp.headers["Cache-Control"] = "no-store"
        return resp
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/solve", methods=["POST"])
def solve_soal():
    """Run agent untuk soal custom dari form (teks atau file upload)."""
    data = dict(request.form or {})
    if request.is_json:
        data.update(request.get_json(silent=True) or {})

    course_id = str(data.get("course_id", "") or "").strip()
    sesi = str(data.get("sesi", "") or "").strip()
    kind = str(data.get("kind", "") or "").strip().lower()
    title = str(data.get("title", "") or "").strip()
    soal_text = str(data.get("soal_text", "") or "").strip()

    if not course_id.isdigit() or not sesi.isdigit():
        return jsonify({"success": False, "error": "Matkul dan sesi wajib diisi."}), 400
    if kind not in ("tugas", "diskusi"):
        return jsonify({"success": False, "error": "Jenis harus tugas atau diskusi."}), 400

    jobs_dir = OUTPUT_DIR / ".jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    stamp = int(time.time() * 1000)
    text_path = None
    if soal_text:
        text_path = jobs_dir / f"solve_{stamp}.md"
        text_path.write_text(soal_text, encoding="utf-8")

    file_paths: list[str] = []
    # `file` (tunggal, backward-compatible) + `files` (multi dari form baru).
    uploads = [f for f in request.files.getlist("file") if f and f.filename]
    uploads += [f for f in request.files.getlist("files") if f and f.filename]
    for idx, upload in enumerate(uploads):
        fname = os.path.basename(upload.filename or "") or f"lampiran{idx}"
        dest = jobs_dir / (f"solve_{stamp}_{fname}" if idx == 0 else f"solve_{stamp}_{idx}_{fname}")
        upload.save(str(dest))
        file_paths.append(str(dest))

    if text_path is None and not file_paths:
        return jsonify({
            "success": False,
            "error": "Isi teks soal atau unggah file soal terlebih dahulu.",
        }), 400

    cmd = [
        sys.executable, "-u", "main.py", "solve",
        "--course", course_id,
        "--sesi", sesi,
        "--kind", kind,
        "--title", title or f"{kind} {sesi}",
    ]
    if text_path is not None:
        cmd += ["--text", str(text_path)]
    for path in file_paths:
        cmd += ["--file", path]

    result = run_command_async(cmd)
    if not result.get("success"):
        # Proses tidak jalan (mis. masih ada proses lain) → bersihkan file temp.
        if text_path is not None:
            text_path.unlink(missing_ok=True)
        for path in file_paths:
            Path(path).unlink(missing_ok=True)
    return jsonify(result)


@app.route("/api/preview/<path:filepath>")
def preview_file(filepath: str):
    """Preview isi .docx hasil agent sebagai HTML (equation jadi MathML)."""
    try:
        full_path = _resolve_output_file(filepath)
        if full_path is None:
            return jsonify({"success": False, "error": "Access denied"}), 403
        if full_path.suffix.lower() != ".docx":
            return jsonify({"success": False, "error": "Hanya DOCX yang bisa di-preview"}), 400
        if not full_path.exists():
            return jsonify({"success": False, "error": "File not found"}), 404

        from generator.preview import docx_to_html

        html = docx_to_html(full_path)
        resp = app.response_class(html, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/run/output")
def get_run_output():
    """Get current process output."""
    global process_output
    with process_lock:
        return jsonify({
            "output": process_output.copy(),
            "running": bool(running_process and running_process.poll() is None),
            "returncode": running_process.poll() if running_process else None,
        })


@app.route("/api/run/status")
def get_run_status():
    """Get status of the running process (for the UI to detect stuck vs alive)."""
    global running_process, _process_start_time
    with process_lock:
        running = bool(running_process and running_process.poll() is None)
        elapsed = 0.0
        last_output = None
        out_len = len(process_output)
        if running:
            elapsed = time.time() - _process_start_time
            last_output = process_output[-1] if out_len else None
        return jsonify({
            "success": True,
            "running": running,
            "returncode": running_process.poll() if running_process else None,
            "elapsed": round(elapsed, 1),
            "line_count": out_len,
            "last_output": last_output,
        })


@app.route("/api/run/stop", methods=["POST"])
def stop_run():
    """Stop the running process."""
    global running_process
    with process_lock:
        if running_process and running_process.poll() is None:
            _kill_proc_tree(running_process)
            some_ref = running_process
            process_output.append("user@tuton:~$ Proses dihentikan oleh pengguna")
            # Tunggu di luar lock supaya thread pembaca bisa flush hasil akhir.
            try:
                some_ref.wait(timeout=10)
            except subprocess.TimeoutExpired:
                some_ref.kill()
            return jsonify({"success": True, "message": "Process stopped"})
        return jsonify({"success": False, "error": "No process running"})


def _cleanup_stale_jobs(max_age_hours: float = 24.0) -> int:
    """Hapus file temporary form soal yang tertinggal (mis. run crash/berhenti).

    Tanpa ini upload menggantung menumpuk di output/.jobs selamanya karena file
    hanya dihapus setelah `main.py solve` memindahkannya ke folder lampiran."""
    jobs_dir = OUTPUT_DIR / ".jobs"
    if not jobs_dir.is_dir():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for path in jobs_dir.glob("solve_*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


if __name__ == "__main__":
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Starting Tuton Agent Web Server...")
    print(f"Output directory: {OUTPUT_DIR}")
    stale = _cleanup_stale_jobs()
    if stale:
        print(f"Cleaned {stale} stale file(s) in {OUTPUT_DIR / '.jobs'}")
    # use_reloader=False: watchdog reloader di Windows mematikan proses run
    # yang sedang berjalan (state process ada di memori). Dev tetap dapat
    # traceback (debug), hanya saja tidak auto-restart di tengah run.
    # PORT dari env dipakai launcher (run-server.bat) supaya bisa tes/port lain
    # tanpa mengubah kode.
    port = int(os.environ.get("PORT") or 5000)
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)