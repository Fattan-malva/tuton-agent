from __future__ import annotations

import json
import mimetypes
import os
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

from config import Config, OUTPUT_DIR
from generator import state
from moodle.auth import MoodleSession
from moodle.downloader import AttachmentDownloader
from moodle.parser import QuestionParser
from moodle.scraper import CourseScraper

app = Flask(__name__, static_folder="frontend", static_url_path="")
CORS(app)

# Global state for running processes
running_process: subprocess.Popen | None = None
process_output: list[str] = []
process_lock = threading.Lock()


def run_command_async(cmd: list[str], cwd: Path | None = None) -> dict:
    """Run a command asynchronously and return process info."""
    global running_process, process_output
    
    with process_lock:
        if running_process and running_process.poll() is None:
            return {"success": False, "error": "Another process is already running"}
        
        process_output = []
        
        def read_output():
            global running_process, process_output
            try:
                running_process = subprocess.Popen(
                    cmd,
                    cwd=cwd or Path(__file__).parent,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                for line in iter(running_process.stdout.readline, ""):
                    if not line:
                        break
                    with process_lock:
                        process_output.append(line.rstrip())
                running_process.wait()
            except Exception as e:
                with process_lock:
                    process_output.append(f"ERROR: {e}")
        
        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()
        
        return {"success": True, "message": "Process started"}


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
        "has_session": bool(Config.MOODLE_SESSION),
        "output_dir": str(OUTPUT_DIR),
    })


@app.route("/api/config", methods=["POST"])
def save_config():
    """Save configuration to .env file."""
    data = request.get_json() or {}
    
    env_path = Path(__file__).parent / ".env"
    env_lines = []
    
    # Read existing .env
    if env_path.exists():
        env_lines = env_path.read_text(encoding="utf-8").splitlines()
    
    # Update or add keys
    updates = {
        "NAMA": data.get("nama", ""),
        "NIM": data.get("nim", ""),
        "PRODI": data.get("prodi", ""),
        "MOODLE_BASE_URL": data.get("moodle_url", ""),
        "MOODLE_SESSION": data.get("moodle_session") or Config.MOODLE_SESSION,
        "OPENCODE_MODEL": data.get("opencode_model") or Config.OPENCODE_MODEL,
    }
    
    # Process existing lines
    new_lines = []
    seen_keys = set()
    for line in env_lines:
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=")[0].strip()
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
            "error": "Session Moodle tidak valid atau sudah kedaluwarsa. Perbarui MOODLE_SESSION di Settings.",
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
                if p.suffix.lower() != ".docx":
                    continue
                if p.exists():
                    stat = p.stat()
                    courses_map[course_name]["files"].append({
                        "name": p.name,
                        "path": str(p),
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
        return jsonify({"output": process_output.copy()})


@app.route("/api/run/stop", methods=["POST"])
def stop_run():
    """Stop the running process."""
    global running_process
    with process_lock:
        if running_process and running_process.poll() is None:
            running_process.terminate()
            try:
                running_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                running_process.kill()
            return jsonify({"success": True, "message": "Process stopped"})
        return jsonify({"success": False, "error": "No process running"})


@app.route("/api/schedule", methods=["POST"])
def save_schedule():
    """Save cron schedule (placeholder - would need system integration)."""
    data = request.get_json() or {}
    enabled = data.get("enabled", False)
    day = data.get("day", "*")
    time_str = data.get("time", "02:00")
    
    # This would typically write to crontab or Windows Task Scheduler
    # For now, just acknowledge
    return jsonify({
        "success": True,
        "message": f"Schedule {'enabled' if enabled else 'disabled'}: {day} at {time_str}"
    })


if __name__ == "__main__":
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("Starting Tuton Agent Web Server...")
    print(f"Output directory: {OUTPUT_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=True)