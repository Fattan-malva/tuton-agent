from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from config import PROJECT_ROOT

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

_WRAP_EXTS = {".cmd", ".bat"} if os.name == "nt" else set()


def _resolve_opencode() -> list[str]:
    """Kembalikan perintah yang valid untuk memanggil opencode lintas-OS."""
    # 1) env override
    exe = os.getenv("OPENCODE_BIN", "").strip()
    if exe:
        return [exe]

    # 2) Windows: prefer executable npm asli
    if os.name == "nt":
        appdata = os.getenv("APPDATA", "")
        basis = Path(appdata) / "npm"
        if basis.is_dir():
            direct = basis / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
            candidates = [direct, *(basis / "node_modules").glob("*opencode*/bin/opencode.exe")]
            for cand in candidates:
                if cand.is_file():
                    return [str(cand)]
            cmd = shutil.which("opencode")
            if cmd:
                return [cmd]

    # 3) tersedia di PATH
    which = shutil.which("opencode")
    if which:
        # Windows: .cmd/.bat shim dibungkus cmd.exe /c saat dijalankan
        return [which]
    raise RuntimeError(
        "Tidak menemukan executable opencode. Set OPENCODE_BIN di .env jika perlu."
    )


def _spawn_cmd(cmd: list[str], cwd: str, env: dict | None = None) -> subprocess.Popen:
    """Popen cross-OS. Di Windows, shim .cmd/.bat perlu cmd.exe /c supaya
    stdin/stdout pipe tidak hang dan proses bisa di-kill dengan benar."""
    spawn_cmd = list(cmd)
    kwargs: dict = dict(
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if os.name == "nt":
        first = (spawn_cmd[0] if spawn_cmd else "").lower()
        if first.endswith(tuple(_WRAP_EXTS)):
            spawn_cmd = ["cmd.exe", "/c", *spawn_cmd]
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    return subprocess.Popen(spawn_cmd, **kwargs)


def _build_cmd(
    prompt: str,
    *,
    agent: str,
    extra_attach: list[str] | None = None,
    model: str | None = None,
    variant: str | None = None,
) -> list[str]:
    cmd = _resolve_opencode()
    cmd += ["run", "-", "--agent", agent, "--title", "tuton-job"]
    model = model or os.getenv("OPENCODE_MODEL", "").strip()
    if model:
        cmd += ["--model", model]
    if variant:
        cmd += ["--variant", variant]
    for f in extra_attach or []:
        cmd += ["--file", f]
    return cmd


def _display_name(cmd: list[str]) -> str:
    """Nama yang ditampilkan: opencode, bukan cmd.exe/cmd-wrap di Windows."""
    base = Path(cmd[0]).name
    if base.lower() == "cmd.exe" and len(cmd) > 2:
        base = Path(cmd[2]).name
    return base


def _cap_line(line: str, limit: int = 120) -> str:
    """Potong baris sangat panjang (>limit) agar log web tetap rapi tanpa
    menimbulkan baris meluber. Hanya untuk tampilan; konten asli tetap utuh."""
    line = line.strip()
    return line if len(line) <= limit else line[: limit - 3] + "..."


def _kill_proc_tree(proc: subprocess.Popen) -> None:
    """Kill proses + semua anaknya. Windows: taskkill /T supaya node/opencode
    anak ikut mati saat timeout."""
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


def run_opencode(
    prompt: str,
    *,
    agent: str = "tuton",
    attach: list[str] | None = None,
    timeout: int | None = None,
    model: str | None = None,
    variant: str | None = None,
):
    """Jalankan opencode non-interaktif, tampilkan outputnya live.

    Mengembalikan objek dengan atribut: returncode, stdout, stderr.
    """
    timeout = timeout or int(os.getenv("TUTON_TIMEOUT", "900"))
    cmd = _build_cmd(
        prompt,
        agent=agent,
        extra_attach=attach,
        model=model,
        variant=variant,
    )
    env = dict(os.environ)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("NO_COLOR", "1")

    exe = _display_name(cmd)
    print(f"  → {exe} run ... (output live di bawah, mohon tunggu)", flush=True)
    proc = _spawn_cmd(cmd, cwd=str(PROJECT_ROOT), env=env)
    out_lines: list[str] = []
    start = time.time()

    # Tulis prompt via thread agar tidak deadlock untuk prompt besar
    if proc.stdin is not None:
        def _feed():
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        threading.Thread(target=_feed, daemon=True).start()

    assert proc.stdout is not None
    buf = ""
    # Windows: `pipe.read(n)` memblokir sampai EOF → output opencode tidak
    # stream trus-menerus dan watchdog timeout tidak pernah jalan. Jadi
    # set pipe non-blocking supaya tiap chunk yang sudah tersedia langsung
    # dibaca, dan loop bisa dicek per iterasi.
    if os.name == "nt":
        try:
            os.set_blocking(proc.stdout.fileno(), False)
        except OSError:
            pass

    try:
        while True:
            try:
                chunk = proc.stdout.read(4096)
            except (BlockingIOError, ValueError):
                chunk = ""
            if chunk:
                buf += chunk
                while True:
                    sep = -1
                    if "\n" in buf:
                        idx_n = buf.index("\n")
                        if "\r" in buf:
                            idx_r = buf.index("\r")
                            sep = idx_n if idx_n < idx_r else idx_r
                        else:
                            sep = idx_n
                    elif "\r" in buf:
                        sep = buf.index("\r")
                    else:
                        break
                    clean = _ANSI_RE.sub("", buf[:sep]).rstrip("\r")
                    if clean:
                        out_lines.append(clean)
                        print(f"  · {_cap_line(clean)}", flush=True)
                    buf = buf[sep + 1:]
            elif proc.poll() is not None:
                clean = _ANSI_RE.sub("", buf).rstrip("\r")
                if clean:
                    out_lines.append(clean)
                    print(f"  · {_cap_line(clean)}", flush=True)
                break
            else:
                if time.time() - start > timeout:
                    _kill_proc_tree(proc)
                    proc.wait()
                    raise TimeoutError(
                        f"opencode melebihi batas {timeout}s dan dihentikan."
                    )
                time.sleep(0.05)
    finally:
        try:
            proc.stdout.close()
        except OSError:
            pass
    proc.wait()
    return type("RunResult", (), {
        "returncode": proc.returncode,
        "stdout": "\n".join(out_lines),
        "stderr": "",
    })()