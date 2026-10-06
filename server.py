"""Server Web UI: menjembatani frontend (frontend/) ke backend baru (backend/).

Kontrak endpoint sengaja sama dengan legacy/server.py supaya frontend Next.js
tidak perlu diubah. Pipeline dijalankan lewat subprocess
`python -u -m backend.main ...` supaya lognya bisa distream ke UI.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend import config as cfg  # noqa: E402
from backend import courses, moodle  # noqa: E402

app = Flask(__name__, static_folder="frontend", static_url_path="")
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

STATE_FILE = cfg.OUTPUT_DIR / "state.json"
STAMP = "%Y-%m-%d %H:%M:%S"

# --------------------------------------------------------------- state JSON


def _state_load() -> dict:
    try:
        import json

        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"items": {}}


def _state_save(data: dict) -> None:
    import json

    cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _state_set(key: str, **fields: Any) -> None:
    data = _state_load()
    item = data.setdefault("items", {}).setdefault(key, {})
    item.update(fields)
    _state_save(data)


def _stamp_display(value: str) -> str:
    return value or ""


# ------------------------------------------------------- proses berjalan

running_process: subprocess.Popen | None = None
process_output: list[str] = []
process_lock = threading.Lock()
_process_start_time: float = 0.0
_current_state_key: str | None = None

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _kill_tree(proc: subprocess.Popen) -> int:
    killed = 0
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        killed += 1
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            killed += 1
        except (ProcessLookupError, PermissionError):
            pass
    return killed


def _read_output(proc: subprocess.Popen, state_key: str | None, matkul: str, sesi: Any) -> None:
    global running_process, _process_start_time, _current_state_key, process_output
    try:
        while True:
            chunk = proc.stdout.read1(4096) if proc.stdout else b""
            if not chunk:
                break
            for line in chunk.decode("utf-8", "replace").replace("\r", "\n").splitlines():
                line = _ANSI_RE.sub("", line).rstrip()
                if line:
                    process_output.append(line)
                    if len(process_output) > 5000:
                        del process_output[: len(process_output) - 5000]
        proc.wait()
    finally:
        rc = proc.returncode
        finished = time.strftime(STAMP)
        duration = round(time.time() - _process_start_time, 1)
        outputs: list[str] = []
        if state_key:
            mk_dirs = sorted(cfg.OUTPUT_DIR.glob("*/sesi-*"))
            for d in cfg.OUTPUT_DIR.glob("*"):
                sd = d / f"sesi-{sesi}"
                if sd.is_dir():
                    outputs.extend(str(p) for p in sorted(sd.glob("*.docx")))
            if rc == 0:
                _state_set(
                    state_key,
                    status="done" if outputs else "failed",
                    matkul=matkul,
                    sesi=sesi,
                    kind="all",
                    index=sesi,
                    desc=f"Sesi {sesi}",
                    finished_at=finished,
                    duration_sec=duration,
                    outputs=outputs,
                    reason="" if outputs else "Tidak ada .docx yang dihasilkan",
                )
            else:
                _state_set(
                    state_key,
                    status="failed",
                    matkul=matkul,
                    sesi=sesi,
                    kind="all",
                    index=sesi,
                    desc=f"Sesi {sesi}",
                    finished_at=finished,
                    duration_sec=duration,
                    outputs=outputs,
                    reason=f"Exit code {rc}",
                )
        with process_lock:
            running_process = None
            _process_start_time = 0.0
            _current_state_key = None


def run_command_async(cmd: list[str], cwd: str | None, state_key: str | None, matkul: str, sesi: Any) -> dict:
    global running_process, process_output, _process_start_time, _current_state_key
    with process_lock:
        if running_process is not None and running_process.poll() is None:
            return {"success": False, "error": "Another process is already running"}
        process_output = []
        running_process = subprocess.Popen(
            cmd,
            cwd=cwd or str(cfg.BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=8192,
            start_new_session=True,
        )
        _process_start_time = time.time()
        _current_state_key = state_key
    if state_key:
        _state_set(
            state_key,
            status="pending",
            matkul=matkul,
            sesi=sesi,
            kind="all",
            index=sesi,
            desc=f"Sesi {sesi}",
            created_at=time.strftime(STAMP),
            outputs=[],
        )
    threading.Thread(target=_read_output, args=(running_process, state_key, matkul, sesi), daemon=True).start()
    return {"success": True, "message": "Process started"}


# ---------------------------------------------------------------- util data

_courses_cache: tuple[float, list[dict]] | None = None


def _list_matkul(refresh: bool = False) -> list[dict]:
    global _courses_cache
    now = time.time()
    if not refresh and _courses_cache and now - _courses_cache[0] < 300:
        return _courses_cache[1]
    klien = moodle.Moodle()
    daftar = courses.daftar_mata_kuliah_lengkap(klien)
    hasil = [{"id": int(m.id) if str(m.id).isdigit() else m.id, "name": m.nama, "folder_name": m.slug, "kode": m.kode, "_obj": m} for m in daftar]
    _courses_cache = (now, hasil)
    return hasil


# ------------------------------------------------------------------- routes


@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tuton-agent"})


@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if username and username == os.environ.get("APP_USERNAME", "") and password == os.environ.get("APP_PASSWORD", ""):
        return jsonify({"success": True, "message": "Login berhasil"})
    return jsonify({"success": False, "error": "Username atau password tidak valid"}), 401


@app.route("/api/models")
def get_models():
    try:
        result = subprocess.run(
            [cfg.cari_opencode(), "models"],
            capture_output=True, text=True, errors="replace", timeout=45, cwd=str(cfg.BASE_DIR),
        )
        ids = []
        for raw in ((result.stdout or "") + "\n" + (result.stderr or "")).splitlines():
            line = raw.strip()
            if not line or line.startswith(("-", "DESCRIPTION", "USAGE", "FLAGS", "GLOBAL", "ERROR")):
                continue
            if "/" in line and " " not in line.split("/", 1)[0]:
                ids.append(line.split()[0])
        current = cfg.PRIMARY_MODEL
        groups: dict[str, list[dict]] = {}
        for model_id in ids:
            provider, _, name = model_id.partition("/")
            groups.setdefault(provider or "(lainnya)", []).append({"id": model_id, "name": name or model_id, "current": model_id == current})
        ordered = [{"provider": p, "models": m} for p, m in sorted(groups.items())]
        if current:
            ordered_provider, _, ordered_name = current.partition("/")
            if not any(x["current"] for g in ordered for x in g["models"]):
                ordered.append({"provider": ordered_provider or "(lainnya)", "models": [{"id": current, "name": ordered_name or current, "current": True}]})
        return jsonify({"success": True, "current": current, "default": current, "total": len(ids), "groups": ordered})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/config")
def get_config():
    return jsonify({
        "nama": os.environ.get("NAMA", ""),
        "nim": os.environ.get("NIM", ""),
        "prodi": os.environ.get("PRODI", ""),
        "semester": os.environ.get("SEMESTER", ""),
        "ut_daerah": os.environ.get("UT_DAERAH", ""),
        "model": cfg.PRIMARY_MODEL,
        "default_model": cfg.PRIMARY_MODEL,
        "base_url": cfg.URL_MOODLE,
        "has_session": bool(cfg.COOKIE_MOODLE),
        "output_dir": str(cfg.OUTPUT_DIR),
        "runtime": {
            "jobs": 4, "timeout": cfg.TIMEOUT_AGENT_DETIK, "retries": cfg.MAX_Coba_AGENT,
            "transcribe": "auto", "vision_tries": 2, "max_pustaka": cfg.MAX_REFERENSI,
        },
        "transcribe_model_configured": cfg.VISION_MODEL,
    })


def _env_upsert(updates: dict[str, str]) -> None:
    env_path = cfg.BASE_DIR / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen: set[str] = set()
    for i, line in enumerate(lines):
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in updates:
            key = m.group(1)
            lines[i] = f"{key}={updates[key]}"
            seen.add(key)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key, value in updates.items():
        os.environ[key] = value


@app.route("/api/config", methods=["POST"])
def save_config():
    body = request.get_json(silent=True) or {}
    updates: dict[str, str] = {}
    if body.get("moodle_session"):
        updates["COOKIE_MOODLE"] = str(body["moodle_session"]).strip().removeprefix("MoodleSession=")
    for key, env_key in (("nama", "NAMA"), ("nim", "NIM"), ("prodi", "PRODI"), ("semester", "SEMESTER"), ("ut_daerah", "UT_DAERAH")):
        if key in body:
            updates[env_key] = str(body[key]).strip()
    if body.get("moodle_url"):
        updates["URL_MOODLE"] = str(body["moodle_url"]).strip().rstrip("/")
    if body.get("opencode_model"):
        updates["PRIMARY_MODEL"] = str(body["opencode_model"]).strip()
    if body.get("opencode_model_transcribe"):
        updates["VISION_MODEL"] = str(body["opencode_model_transcribe"]).strip()
    try:
        _env_upsert(updates)
        # Muat ulang konstanta config untuk request berikutnya.
        cfg.URL_MOODLE = os.environ.get("URL_MOODLE", "").rstrip("/")
        cfg.COOKIE_MOODLE = os.environ.get("COOKIE_MOODLE", "")
        cfg.PRIMARY_MODEL = os.environ.get("PRIMARY_MODEL", cfg.PRIMARY_MODEL)
        cfg.VISION_MODEL = os.environ.get("VISION_MODEL", cfg.VISION_MODEL)
        return jsonify({"success": True, "message": "Configuration saved"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/courses")
def get_courses():
    try:
        daftar = _list_matkul()
        return jsonify({"success": True, "courses": [{"id": m["id"], "name": m["name"], "folder_name": m["folder_name"]} for m in daftar]})
    except moodle.LoginMati:
        return jsonify({"success": False, "error": "Sesi Moodle kedaluwarsa. Perbarui cookie di Settings."}), 401
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _matkul_by_id(course_id: int):
    for m in _list_matkul():
        if str(m["id"]) == str(course_id):
            return m
    raise LookupError(f"Mata kuliah {course_id} tidak ditemukan")


@app.route("/api/courses/<int:course_id>/sections")
def get_sections(course_id: int):
    try:
        m = _matkul_by_id(course_id)
        klien = moodle.Moodle()
        sesi = courses.daftar_section(klien, m["_obj"])
        return jsonify({"success": True, "sections": [{"number": n, "title": f"Sesi {n}"} for n in sesi]})
    except LookupError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/courses/<int:course_id>/activities")
def get_activities(course_id: int):
    try:
        m = _matkul_by_id(course_id)
        klien = moodle.Moodle()
        klien.cek_login()
        per_section: dict[int, dict] = {}
        for n in courses.daftar_section(klien, m["_obj"]):
            per_section[n] = {"section": n, "section_title": f"Sesi {n}", "diskusi": [], "tugas": [], "lain": []}
        for a in _daftar_aktivitas_semua(klien, m["_obj"]):
            target = None
            if a.modtype in ("forum",):
                target = "diskusi"
            elif a.modtype in ("assign", "quiz"):
                target = "tugas"
            per_section.setdefault(a.section, {"section": a.section, "section_title": f"Sesi {a.section}", "diskusi": [], "tugas": [], "lain": []})
            if target:
                per_section[a.section][target].append({"id": a.id, "title": a.nama, "mod_type": a.modtype})
            else:
                per_section[a.section]["lain"].append({"id": a.id, "title": a.nama, "mod_type": a.modtype})
        return jsonify({"success": True, "course": m["name"], "sections": list(per_section.values())})
    except LookupError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _daftar_aktivitas_semua(klien, matkul):
    hasil = []
    for s in courses.daftar_section(klien, matkul):
        try:
            hasil.extend(courses.daftar_aktivitas(klien, matkul, s))
        except Exception:
            continue
    return hasil


@app.route("/api/status")
def get_status():
    try:
        st = _state_load()
        items = st.get("items", {})
        done = sum(1 for v in items.values() if v.get("status") == "done")
        failed = sum(1 for v in items.values() if v.get("status") == "failed")
        pending = sum(1 for v in items.values() if v.get("status") == "pending")
        out_items = []
        for k, v in sorted(items.items()):
            out_items.append({
                "key": k,
                "status": v.get("status", "unknown"),
                "matkul": v.get("matkul", ""),
                "sesi": v.get("sesi"),
                "kind": v.get("kind"),
                "index": v.get("index"),
                "desc": v.get("desc", ""),
                "created_at": _stamp_display(v.get("created_at", "")),
                "finished_at": _stamp_display(v.get("finished_at", "")),
                "duration_sec": v.get("duration_sec"),
                "reason": v.get("reason"),
                "urls": v.get("urls", []),
                "outputs": v.get("outputs", []),
            })
        return jsonify({"success": True, "stats": {"done": done, "failed": failed, "pending": pending, "total": len(items)}, "items": out_items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/results")
def get_results():
    try:
        st = _state_load()
        items = st.get("items", {})
        courses_map: dict[str, dict] = {}

        def _push(course_name: str, docx: Path, v: dict | None = None) -> None:
            v = v or {}
            try:
                rel_path = "/".join(docx.resolve().relative_to(cfg.OUTPUT_DIR.resolve()).parts)
            except ValueError:
                rel_path = docx.name
            stat = docx.stat()
            cm = courses_map.setdefault(course_name, {"name": course_name, "files": [], "has_errors": False})
            if rel_path.split("/")[0] and not cm.get("folder"):
                cm["folder"] = rel_path.split("/")[0]
            cm["files"].append({
                "name": docx.name, "path": rel_path, "size": stat.st_size, "modified": stat.st_mtime,
                "created_at": _stamp_display(v.get("created_at", "")),
                "finished_at": _stamp_display(v.get("finished_at", "")),
                "duration_sec": v.get("duration_sec"),
                "kind": v.get("kind"), "index": v.get("index"), "sesi": v.get("sesi"),
                "urls": v.get("urls", []),
            })

        for k, v in sorted(items.items()):
            if v.get("status") != "done":
                continue
            for out in v.get("outputs", []):
                p = Path(out)
                if p.suffix.lower() == ".docx" and p.exists():
                    _push(v.get("matkul", "Unknown"), p, v)

        known = {f["path"] for c in courses_map.values() for f in c["files"]}
        for docx in sorted(cfg.OUTPUT_DIR.glob("**/*.docx")):
            try:
                rel = "/".join(docx.resolve().relative_to(cfg.OUTPUT_DIR.resolve()).parts)
            except ValueError:
                continue
            if rel not in known:
                _push(docx.parent.parent.name if docx.parent.name.startswith("sesi-") else docx.parent.name, docx)
        return jsonify({"success": True, "courses": list(courses_map.values())})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/download/<path:filepath>")
def download_file(filepath: str):
    try:
        root = cfg.OUTPUT_DIR.resolve()
        full = (root / filepath).resolve()
        if not str(full).startswith(str(root)):
            return jsonify({"success": False, "error": "Access denied"}), 403
        if not full.is_file():
            return jsonify({"success": False, "error": "File not found"}), 404
        return send_from_directory(str(root), filepath, as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/results/<path:filepath>", methods=["DELETE"])
def delete_result(filepath: str):
    try:
        root = cfg.OUTPUT_DIR.resolve()
        full = (root / filepath).resolve()
        if not str(full).startswith(str(root)) or full.suffix.lower() != ".docx":
            return jsonify({"success": False, "error": "Access denied"}), 403
        if not full.exists():
            return jsonify({"success": False, "error": "File not found"}), 404
        full.unlink()
        data = _state_load()
        for v in data.get("items", {}).values():
            v["outputs"] = [o for o in v.get("outputs", []) if Path(o).resolve() != full]
        _state_save(data)
        return jsonify({"success": True, "message": f"{full.name} dihapus"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/courses/<path:folder>", methods=["DELETE"])
def delete_course(folder: str):
    try:
        root = cfg.OUTPUT_DIR.resolve()
        target = (root / folder).resolve()
        if not str(target).startswith(str(root)) or target == root:
            return jsonify({"success": False, "error": "Access denied"}), 403
        if not target.is_dir():
            return jsonify({"success": False, "error": "Folder not found"}), 404
        shutil.rmtree(target)
        data = _state_load()
        keys = [k for k, v in data.get("items", {}).items() if any(Path(o).resolve().is_relative_to(target) for o in v.get("outputs", []))] if hasattr(Path, "is_relative_to") else []
        if not keys:
            keys = [k for k, v in data.get("items", {}).items() if v.get("matkul") and folder in str(v.get("outputs", ""))]
        for k in keys:
            del data["items"][k]
        _state_save(data)
        return jsonify({"success": True, "message": f"{folder} dihapus", "removed": len(keys)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/results/reset", methods=["POST"])
def reset_results():
    body = request.get_json(silent=True) or {}
    keep_cache = bool(body.get("keep_cache"))
    with process_lock:
        if running_process is not None and running_process.poll() is None:
            return jsonify({"success": False, "error": "Proses masih berjalan"}), 409
    deleted = files = nbytes = 0
    for p in list(cfg.OUTPUT_DIR.iterdir()) if cfg.OUTPUT_DIR.exists() else []:
        if p.name == ".cache" and keep_cache:
            continue
        if p.is_dir():
            deleted += 1
            for f in p.rglob("*"):
                if f.is_file():
                    files += 1
                    nbytes += f.stat().st_size
            shutil.rmtree(p, ignore_errors=True)
        else:
            if p.name == "state.json":
                continue
            deleted += 1
            files += 1
            nbytes += p.stat().st_size
            p.unlink(missing_ok=True)
    _state_save({"items": {}})
    return jsonify({"success": True, "message": "Reset selesai", "deleted": deleted, "files": files, "bytes": nbytes, "items": 0, "failed": []})


@app.route("/api/run", methods=["POST"])
def run_agent():
    body = request.get_json(silent=True) or {}
    course_id = body.get("course_id")
    sesi = body.get("sesi")
    try:
        course_id_int = int(course_id) if course_id is not None else None
        sesi_int = int(sesi) if sesi is not None else None
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "course_id dan sesi harus angka"}), 400
    if course_id_int is None or sesi_int is None:
        return jsonify({"success": False, "error": "course_id dan sesi wajib diisi"}), 400
    try:
        m = _matkul_by_id(course_id_int)
    except LookupError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    state_key = f"{course_id_int}:sesi-{sesi_int}"
    cmd = [sys.executable, "-u", "-m", "backend.main", "--matkul", m["name"], "--sesi", str(sesi_int)]
    result = run_command_async(cmd, cwd=str(cfg.BASE_DIR), state_key=state_key, matkul=m["name"], sesi=sesi_int)
    return jsonify(result)


@app.route("/api/solve", methods=["POST"])
def solve():
    if request.content_type and "multipart/form-data" in request.content_type:
        data = request.form
        files = request.files
    else:
        data = request.get_json(silent=True) or {}
        files = {}
    try:
        sesi = int(data.get("sesi") or 0)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "sesi harus angka"}), 400
    title = (data.get("title") or "").strip() or f"Tugas {sesi or ''}"
    soal_text = (data.get("soal_text") or "").strip()
    uploaded = None
    for field in ("file", "files"):
        f = files.get(field) if hasattr(files, "get") else None
        if f and f.filename:
            uploaded = f
            break
    if uploaded is not None:
        tmp = cfg.OUTPUT_DIR / ".jobs"
        tmp.mkdir(parents=True, exist_ok=True)
        dest = tmp / f"solve_{int(time.time())}_{uploaded.filename}"
        uploaded.save(dest)
        try:
            from backend.attachments import teks_dari_berkas

            teks = teks_dari_berkas(dest)
            if teks.strip():
                soal_text = (soal_text + "\n\n" + teks).strip()
        except Exception:
            pass
    if not soal_text:
        return jsonify({"success": False, "error": "teks soal kosong"}), 400
    if running_process is not None and running_process.poll() is None:
        return jsonify({"success": False, "error": "Another process is already running"})

    ts = int(time.time())
    state_key = f"solve:{ts}"
    cmd = [sys.executable, "-u", "-m", "backend.solve", "--title", title, "--sesi", str(sesi), "--soal", soal_text, "--state-key", state_key]
    result = run_command_async(cmd, cwd=str(cfg.BASE_DIR), state_key=state_key, matkul=title, sesi=sesi)
    return jsonify(result)


@app.route("/api/preview/<path:filepath>")
def preview_file(filepath: str):
    try:
        root = cfg.OUTPUT_DIR.resolve()
        full = (root / filepath).resolve()
        if not str(full).startswith(str(root)):
            return jsonify({"success": False, "error": "Access denied"}), 403
        if full.suffix.lower() != ".docx":
            return jsonify({"success": False, "error": "Hanya DOCX yang bisa di-preview"}), 400
        if not full.exists():
            return jsonify({"success": False, "error": "File not found"}), 404

        spec = importlib.util.spec_from_file_location("legacy_preview", cfg.BASE_DIR / "legacy" / "generator" / "preview.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        html = mod.docx_to_html(str(full))
        return app.response_class(html, mimetype="text/html")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/run/output")
def run_output():
    with process_lock:
        running = running_process is not None and running_process.poll() is None
        rc = running_process.returncode if running_process is not None else None
    return jsonify({"output": process_output, "running": running, "returncode": rc})


@app.route("/api/run/status")
def run_status():
    with process_lock:
        running = running_process is not None and running_process.poll() is None
        rc = running_process.returncode if running_process is not None else None
        elapsed = time.time() - _process_start_time if _process_start_time else 0.0
    return jsonify({
        "success": True, "running": running, "returncode": rc,
        "elapsed": elapsed, "line_count": len(process_output),
        "last_output": process_output[-1] if process_output else None,
    })


@app.route("/api/run/stop", methods=["POST"])
def run_stop():
    with process_lock:
        proc = running_process
    if proc is None or proc.poll() is not None:
        return jsonify({"success": False, "error": "Tidak ada proses yang sedang berjalan.", "killed": 0})
    killed = _kill_tree(proc)
    return jsonify({"success": True, "message": "Proses dihentikan", "killed": killed})


@app.errorhandler(413)
def too_large(e):
    return jsonify({"success": False, "error": "Ukuran unggahan melebihi 64 MB."}), 413


if __name__ == "__main__":
    cfg.ensure_dirs()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT") or 5000), debug=True, use_reloader=False)
