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

# opencode >= 2.0 datang sebagai satu binary mandiri. Namanya tetap
# `opencode.exe` bahkan di Linux/macOS (ELF, bukan PE), jadi kedua nama harus
# dicoba di semua OS.
_EXE_NAMES = ("opencode.exe", "opencode", "opencode.cmd", "opencode.bat")


def _global_node_modules_dirs() -> list[Path]:
    """Kandidat direktori `node_modules` global tempat opencode terpasang.

    PENTING: di POSIX `npm root -g` sudah mengembalikan .../lib/node_modules,
    sedangkan di Windows prefix npm adalah %APPDATA%\npm dan paketnya ada satu
    level di bawahnya. Dictionaries harus memakai path yang SUDAH termasuk
    `node_modules`; jangan pernah menambahkannya lagi di sini.
    """
    dirs: list[Path] = []

    # Windows: prefix npm global = %APPDATA%\npm.
    appdata = os.getenv("APPDATA", "").strip()
    if appdata:
        dirs.append(Path(appdata) / "npm" / "node_modules")

    # Prefix npm yang dikonfigurasi manual (npm config set prefix ...).
    for var in ("NPM_CONFIG_PREFIX", "npm_config_prefix"):
        prefix = os.getenv(var, "").strip()
        if prefix:
            base = Path(prefix)
            # Prefix bisa berupa ".../lib" (default) atau ".../npm" (Windows).
            dirs.append(base / "lib" / "node_modules")
            dirs.append(base / "node_modules")

    # POSIX: lokasi standar prefix npm.
    if os.name != "nt":
        dirs += [
            Path("/usr/lib/node_modules"),
            Path("/usr/local/lib/node_modules"),
            Path.home() / ".npm-global" / "lib" / "node_modules",
            Path.home() / ".local" / "lib" / "node_modules",
            Path.home() / ".bun" / "install" / "global" / "node_modules",
        ]

    seen: set[str] = set()
    unique: list[Path] = []
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def _candidate_exes(modules: Path) -> list[Path]:
    """Semua path opencode yang mungkin di dalam satu direktori node_modules."""
    out: list[Path] = []
    # opencode >= 2.0 dipaketkan sebagai `@opencode/cli`; versi lama
    # `opencode-ai`. Keduanya dicoba, nama bin dari `_EXE_NAMES`.
    for pkg in ("@opencode/cli", "opencode-ai"):
        for name in _EXE_NAMES:
            out.append(modules / pkg / "bin" / name)
    # Fallback: nama paket/versi lain yang belum terdaftar di atas.
    for pattern in ("*opencode*/bin/opencode*", "@*/*/bin/opencode*"):
        out += sorted(modules.glob(pattern))
    return out


def _is_runnable(path: Path) -> bool:
    if not path.is_file():
        return False
    # Di POSIX bit+x wajib; di Windows tidak relevan (shim .cmd/.bat).
    if os.name != "nt" and not os.access(path, os.X_OK):
        return False
    return True


def _npm_root_g() -> Path | None:
    """`npm root -g` sebagai sumber terakhir (lambat, jadi paling akhir)."""
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        return None
    try:
        res = subprocess.run(
            [npm, "root", "-g"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    out = (res.stdout or "").strip().splitlines()
    for line in out:
        line = line.strip()
        # Buang pesan error/warning npm yang ikut tercetak ke stdout.
        if line and Path(line).is_dir() and not line.startswith(("npm ", "npm error")):
            return Path(line)
    return None


def _resolve_opencode() -> list[str]:
    """Kembalikan perintah yang valid untuk memanggil opencode lintas-OS."""
    # 1) env override
    exe = os.getenv("OPENCODE_BIN", "").strip()
    if exe:
        return [exe]

    # 2) Cari di global npm dir (lihat catatan path di _global_node_modules_dirs)
    for basis in _global_node_modules_dirs():
        if not basis.is_dir():
            continue
        for cand in _candidate_exes(basis):
            if _is_runnable(cand):
                return [str(cand)]

    # 3) shim `opencode` di PATH
    which = shutil.which("opencode")
    if which:
        return [which]

    # 4) `npm root -g`. Penting untuk container yang hanya me-mount paket
    #    opencode tanpa symlink bin, dan untuk prefix npm yang non-standar.
    root = _npm_root_g()
    if root is not None:
        for cand in _candidate_exes(root):
            if _is_runnable(cand):
                return [str(cand)]

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
    if model is None:
        from config import Config

        model = (Config.OPENCODE_MODEL or os.getenv("OPENCODE_MODEL", "")).strip()
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


# ---------------------------------------------------------------------------
# Daftar model opencode.
#
# Satu sumber kebenaran untuk transkripsi vision maupun dropdown di Settings.
# Di-cache 5 menit karena `opencode models` menelepon server, jadi tidak boleh
# dipanggil setiap kali Settings dibuka.
# ---------------------------------------------------------------------------
_models_cache: tuple[float, list[str]] | None = None
_MODELS_TTL = 300.0

_NOISE_PREFIXES = (
    "opencode.exe", "At line:", "CategoryInfo", "FullyQualified", "+ ", "  ",
)


def list_models(*, timeout: int = 45, use_cache: bool = True) -> list[str]:
    """Semua id model yang tersedia, mis. `opencode/big-pickle`."""
    global _models_cache
    now = time.time()
    if use_cache and _models_cache is not None and now - _models_cache[0] < _MODELS_TTL:
        return list(_models_cache[1])

    ids: list[str] = []
    ok = False
    try:
        result = subprocess.run(
            _resolve_opencode() + ["models"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        data = (result.stdout or "") + (result.stderr or "")
        skip = ("DESCRIPTION", "USAGE", "FLAGS", "GLOBAL FLAGS", "ERROR")
        for raw in data.splitlines():
            line = raw.strip()
            if not line or line.startswith(skip) or line.startswith("-"):
                continue
            if line.startswith(_NOISE_PREFIXES):
                continue
            if "/" not in line or " " in line:
                continue
            ids.append(line)
        ids = list(dict.fromkeys(ids))
        ok = True
    except Exception as exc:  # noqa: BLE001 - UI harus tetap jalan walau CLI gagal
        print(f"  ! gagal membaca daftar model opencode: {exc}")

    # Hanya cache kalau CLI benar-benar dijawab. `opencode models` gagal sesaat
    # right setelah container start (database opencode belum siap), dan cache
    # kosong selama TTL membuat kegagalan sesaat itu terasa seperti "tidak ada
    # model sama sekali" -- termasuk membuat auto-pilih model tidak bisa jalan.
    if use_cache and ok:
        _models_cache = (now, ids)
    return ids


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
    # `pipe.read(n)` di SEMUA OS memblokir sampai buffer penuh atau EOF, bukan
    # sampai baris baru tersedia. Akibatnya output opencode tidak stream
    # trus-menerus dan watchdog timeout tidak pernah sempat dicek.
    # Set pipe non-blocking supaya tiap chunk yang sudah tersedia langsung
    # dibaca, dan loop bisa dicek per iterasi. Linux/perlainan punya masalah
    # yang sama seperti Windows, jadi ini sengaja tidak dibatasi ke `nt`.
    try:
        os.set_blocking(proc.stdout.fileno(), False)
    except (OSError, ValueError):
        # Kalau tidak bisa (mis. handle sudah ditutup), tetap jalan dengan
        # perilaku blocking — lebih lambat, tapi tidak fatal.
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