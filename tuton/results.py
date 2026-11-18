"""Penghapusan hasil lokal dan Storage dalam scope akun web aktif."""

import errno
import re
import shutil
from pathlib import Path

from tuton import config, supabase


def _buang(target: Path, stop: Path, berkas: bool) -> None:
    if berkas:
        target.unlink(missing_ok=True)
    elif target.exists():
        shutil.rmtree(target)
    for parent in target.parents:
        if parent == stop:
            break
        try:
            parent.rmdir()
        except FileNotFoundError:
            continue
        except OSError as exc:
            if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                raise
            break


def hapus(slug: str, sesi: str = "", nama: str = "") -> dict:
    user = config.current_user()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", user):
        raise ValueError("Akun tidak sah.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", slug) or slug == "." or ".." in slug:
        raise ValueError("Nama mata kuliah tidak sah.")
    if sesi and not re.fullmatch(r"sesi-\d+", sesi):
        raise ValueError("Nomor sesi tidak sah.")
    if nama and (not sesi or not nama.lower().endswith(".docx") or any(c in nama for c in "/\\\x00")):
        raise ValueError("Path berkas hasil tidak sah.")

    root = config.output_root()
    target = root.joinpath(slug, sesi, nama)
    if target.resolve() != root.parent.resolve() / target.relative_to(root.parent):
        raise ValueError("Path hasil bukan folder milik akun.")

    # Lokal dulu: jika Storage gagal, metadata masih terlihat untuk dicoba lagi.
    _buang(target, root, bool(nama))
    kerja = config.work_dirs(slug)["matkul"]
    _buang(kerja / sesi / nama, kerja, bool(nama))
    supabase.result_delete(user, slug, sesi, nama)
    return {"ok": True, "tingkat": "berkas" if nama else "sesi" if sesi else "matkul",
            "path": target.relative_to(root.parent).as_posix()}
