from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from flask import Flask, jsonify, request, send_from_directory

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
from flask_cors import CORS

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config, OUTPUT_DIR
from generator import state
from moodle.auth import MoodleSession
from moodle.downloader import AttachmentDownloader
from moodle.parser import QuestionParser
from moodle.scraper import CourseScraper

app = Flask(__name__, static_folder="frontend", static_url_path="")
CORS(app)

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
    """Stream stdout proses anak secara real-time.

    Di Windows, `pipe.read(n)` memblokir sampai EOF → semua baris baru muncul
    di akhir run. Jadi di Windows pakai readline() (streaming per baris) lalu
    pecah ulang per \\r supaya spinner/progress (bare \\r) tetap terlihat.
    Di Linux, chunk read baku sudah streaming per potongan."""
    global process_output
    try:
        if os.name == "nt":
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                for piece in line.split("\r"):
                    piece = _strip_ansi(piece).strip()
                    if piece:
                        with process_lock:
                            process_output.append(piece)
        else:
            buf = ""
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                buf += chunk
                while True:
                    sep = -1
                    if "\n" in buf:
                        sep = buf.index("\n")
                    if "\r" in buf and (sep == -1 or buf.index("\r") < sep):
                        sep = buf.index("\r")
                    if sep == -1:
                        break
                    line = _strip_ansi(buf[:sep]).rstrip("\r")
                    if line:
                        with process_lock:
                            process_output.append(line)
                    buf = buf[sep + 1:]
            line = _strip_ansi(buf).rstrip("\r")
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
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        running_process = subprocess.Popen(cmd, **kwargs)

    thread = threading.Thread(target=_read_process_output, args=(running_process,), daemon=True)
    thread.start()

    return {"success": True, "message": "Process started"}


# === Cronjob scheduler =====================================================
# Jadwal tersimpan di cronjob.json (project root) supaya persisten dan bisa
# di-update dari web UI. Scheduler berjalan sebagai background thread di
# dalam server (bukan cron OS) sehingga hidup selama container berjalan.
# Eksekusi memakai `python main.py run` TANPA --force dan TANPA --course:
# semua matkul dikerjakan, item yang sudah selesai otomatis dilewati lewat
# output/state.json.

CRON_FILE = Path(__file__).parent / "cronjob.json"
CRON_LOG = Path(__file__).parent / "cron.log"
_CRON_TZ = None

CRON_POLL_SECONDS = 30
CRON_GRACE_SECONDS = 3 * 60 * 60  # catch-up 3 jam bila server sempat mati/sibuk

_CRON_VALID_DAYS = ("*", "0", "1", "2", "3", "4", "5", "6")


def _cron_tz() -> ZoneInfo:
    """Timezone jadwal. Fallback ke timezone sistem bila Asia/Jakarta
    tidak tersedia (mis. tzdata belum terpasang)."""
    global _CRON_TZ
    if _CRON_TZ is None:
        try:
            _CRON_TZ = ZoneInfo("Asia/Jakarta")
        except Exception:  # noqa: BLE001 - ZoneInfoNotFoundError dkk.
            _CRON_TZ = datetime.now().astimezone().tzinfo
    return _CRON_TZ


def _cron_now() -> datetime:
    return datetime.now(_cron_tz())


def _default_cron_config() -> dict:
    return {
        "enabled": False,
        "day": "*",
        "time": "02:00",
        "timezone": "Asia/Jakarta",
        "last_run": None,
        "next_run": None,
        "last_status": None,
        "updated_at": None,
    }


def _load_cron_config() -> dict:
    try:
        data = json.loads(CRON_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    cfg = {**_default_cron_config(), **data}
    cfg["enabled"] = bool(cfg.get("enabled"))
    day = str(cfg.get("day", "*"))
    cfg["day"] = day if day in _CRON_VALID_DAYS else "*"
    time_str = str(cfg.get("time", "02:00"))
    cfg["time"] = time_str if re.fullmatch(r"\d{2}:\d{2}", time_str) else "02:00"
    return cfg


def _save_cron_config(cfg: dict) -> None:
    CRON_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _cron_next_time(cfg: dict, after: datetime) -> datetime | None:
    """Waktu kemunculan jadwal berikutnya yang (ketat) setelah `after`."""
    hh, mm = (int(x) for x in cfg["time"].split(":"))
    day_str = cfg["day"]
    target = after + timedelta(minutes=1)
    for day_offset in range(8):
        d = target.date() + timedelta(days=day_offset)
        cron_wd = (d.weekday() + 1) % 7  # Python: Mon=0..Sun=6 -> cron: Sun=0
        if day_str != "*" and cron_wd != int(day_str):
            continue
        cand = datetime.combine(d, dtime(hh, mm), tzinfo=_cron_tz())
        if cand >= target:
            return cand
    return None


def _cron_log(message: str) -> None:
    try:
        with CRON_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"[{_cron_now().isoformat(timespec='seconds')}] {message}\n")
    except OSError:
        pass


def _cron_run_cmd() -> list[str]:
    # Semua matkul, tanpa --force: hanya item yang belum selesai yang dikerjakan.
    return [sys.executable, "-u", "main.py", "run"]


def _cron_fire(cfg: dict, nxt: datetime) -> str:
    """Eksekusi pekerjaan terjadwal. Return status: started/skipped_busy/failed."""
    with process_lock:
        busy = bool(running_process and running_process.poll() is None)
    if busy:
        return "skipped_busy"
    res = run_command_async(_cron_run_cmd())
    if not res.get("success"):
        return "failed"
    with process_lock:
        process_output.insert(0, "user@tuton:~$ [cron] " + " ".join(_cron_run_cmd()))
    _cron_log(f"run otomatis dimulai (jadwal {nxt.isoformat(timespec='minutes')})")
    return "started"


def _cron_check() -> None:
    cfg = _load_cron_config()
    now = _cron_now()
    if not cfg.get("enabled"):
        if cfg.get("next_run") is not None:
            cfg["next_run"] = None
            _save_cron_config(cfg)
        return

    nxt_saved = cfg.get("next_run")
    if nxt_saved:
        try:
            nxt = datetime.fromisoformat(nxt_saved)
        except (TypeError, ValueError):
            nxt = None
    else:
        nxt = None
    if nxt is None:
        nxt = _cron_next_time(cfg, now)
        cfg["next_run"] = nxt.isoformat() if nxt else None
        _save_cron_config(cfg)
        return

    if now < nxt:
        return
    if (now - nxt).total_seconds() > CRON_GRACE_SECONDS:
        cfg["next_run"] = _cron_next_time(cfg, now).isoformat()
        _save_cron_config(cfg)
        return

    status = _cron_fire(cfg, nxt)
    cfg["last_run"] = now.isoformat(timespec="seconds")
    cfg["last_status"] = status
    cfg["next_run"] = _cron_next_time(cfg, now).isoformat()
    _save_cron_config(cfg)


def _start_cron_scheduler() -> None:
    """Background thread: cek jadwal tiap CRON_POLL_SECONDS detik."""

    def _loop():
        while True:
            try:
                _cron_check()
            except Exception as exc:  # noqa: BLE001
                _cron_log(f"ERROR scheduler: {exc}")
            time.sleep(CRON_POLL_SECONDS)

    threading.Thread(target=_loop, name="cron-scheduler", daemon=True).start()


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


@app.route("/api/config")
def get_config():
    """Get current configuration (without sensitive data)."""
    return jsonify({
        "nama": Config.NAMA,
        "nim": Config.NIM,
        "prodi": Config.PRODI,
        "model": Config.OPENCODE_MODEL or "(default)",
        "base_url": Config.MOODLE_BASE_URL,
        "has_session": bool(Config.moodle_session()),
        "output_dir": str(OUTPUT_DIR),
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
    updates = {
        "NAMA": data.get("nama", ""),
        "NIM": data.get("nim", ""),
        "PRODI": data.get("prodi", ""),
        "MOODLE_BASE_URL": data.get("moodle_url", ""),
        "OPENCODE_MODEL": data.get("opencode_model") or Config.OPENCODE_MODEL,
    }
    
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
                        "kind": v.get("kind"),
                        "index": v.get("index"),
                        "sesi": v.get("sesi"),
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
        
        return send_from_directory(full_path.parent, full_path.name, as_attachment=True)
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
    
    # Unbuffered stdout is required so main.py/OpenCode logs reach the UI live.
    cmd = [sys.executable, "-u", "main.py", "run"]
    if course_id:
        cmd.extend(["--course", str(course_id)])
    if sesi:
        cmd.extend(["--sesi", str(sesi)])
    if force:
        cmd.append("--force")
    
    result = run_command_async(cmd)
    return jsonify(result)


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


@app.route("/api/schedule", methods=["GET"])
def get_schedule():
    """Kembalikan config cron saat ini (untuk mengisi form UI)."""
    cfg = _load_cron_config()
    nxt = cfg.get("next_run")
    if cfg["enabled"] and not nxt:
        nxt_time = _cron_next_time(cfg, _cron_now())
        if nxt_time:
            cfg["next_run"] = nxt_time.isoformat()
            _save_cron_config(cfg)
    return jsonify({"success": True, **cfg})


@app.route("/api/schedule", methods=["POST"])
def save_schedule():
    """Simpan config cron baru dan hitung jadwal berikutnya."""
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", False))
    day = str(data.get("day", "*"))
    time_str = str(data.get("time", "02:00"))
    if day not in _CRON_VALID_DAYS or not re.fullmatch(r"\d{2}:\d{2}", time_str):
        return jsonify({"success": False, "error": "day/time tidak valid"}), 400
    cfg = _load_cron_config()
    cfg.update(enabled=enabled, day=day, time=time_str, updated_at=_cron_now().isoformat(timespec="seconds"))
    cfg["last_status"] = None
    cfg["next_run"] = _cron_next_time(cfg, _cron_now()).isoformat() if enabled else None
    _save_cron_config(cfg)
    _cron_log(f"config: enabled={enabled} day={day} time={time_str}")
    return jsonify({"success": True, **cfg})


if __name__ == "__main__":
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Mulai scheduler cron (background thread).
    # Berjalan selama server hidup, cek tiap 30 detik apakah waktunya
    # menjalankan `python main.py run` (tanpa --force, semua matkul).
    _start_cron_scheduler()
    _cron_log("server started, cron scheduler active")

    print("Starting Tuton Agent Web Server...")
    print(f"Output directory: {OUTPUT_DIR}")
    # use_reloader=False: watchdog reloader di Windows mematikan proses run
    # yang sedang berjalan (state process ada di memori). Dev tetap dapat
    # traceback (debug), hanya saja tidak auto-restart di tengah run.
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)