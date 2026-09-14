from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from config import PROJECT_ROOT

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


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
        if os.name == "nt" and not which.lower().endswith((".exe", ".cmd", ".bat")):
            return [which]
        return [which]
    raise RuntimeError(
        "Tidak menemukan executable opencode. Set OPENCODE_BIN di .env jika perlu."
    )


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
    import time

    timeout = timeout or int(os.getenv("TUTON_TIMEOUT", "900"))
    cmd = _build_cmd(
        prompt,
        agent=agent,
        extra_attach=attach,
        model=model,
        variant=variant,
    )
    exe = cmd[0].split(os.sep)[-1]
    print(f"  → {exe} run ... (output live di bawah, mohon tunggu)")
    print(f"    ┌─{'─' * 60}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    if proc.stdin is not None:
        proc.stdin.write(prompt)
        proc.stdin.close()
    out_lines: list[str] = []
    start = time.time()
    assert proc.stdout is not None
    try:
        while True:
            line = proc.stdout.readline()
            if line:
                clean = _ANSI_RE.sub("", line).rstrip()
                out_lines.append(clean)
                if clean:
                    print(f"    │ {clean}")
            elif proc.poll() is not None:
                break
            else:
                if time.time() - start > timeout:
                    proc.kill()
                    proc.wait()
                    print("    └─" + "─" * 60)
                    raise TimeoutError(
                        f"opencode melebihi batas {timeout}s dan dihentikan."
                    )
                time.sleep(0.1)
    finally:
        proc.stdout.close()
    proc.wait()
    print("    └" + "─" * 60)
    return type("RunResult", (), {
        "returncode": proc.returncode,
        "stdout": "\n".join(out_lines),
        "stderr": "",
    })()