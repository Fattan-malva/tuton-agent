"""Pindahkan hasil kerja lama ke folder milik satu akun Clerk.

Sejak aplikasi jadi multi-user, semua berkas berada di bawah folder per akun:

    output/<clerk_user_id>/<matkul>/sesi-<N>/*.docx
    _kerja/<clerk_user_id>/...
    cache/<clerk_user_id>/*.html

Data lama (sebelum perubahan itu) ada langsung di `output/<matkul>/...` dan
tidak terlihat oleh akun mana pun. Skrip ini memindahkannya ke akun yang
benar, sekali saja.

Pemakaian:

    python tools/migrasi_output.py --daftar
    python tools/migrasi_output.py --user user_3M8qSoSCFW4G3ipmtdDbv15fyfh
    python tools/migrasi_output.py --user user_... --dry-run

Id user Clerk dilihat di dashboard Clerk, atau dari `user` di respons
`/api/session` setelah login.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tuton import config  # noqa: E402

_RE_SESI = re.compile(r"^sesi-\d+$")
# Folder yang bukan milik satu akun: folder per akun selalu berawalan `user_`
# atau id Clerk lain, dan nama matkul tidak pernah mengandung awalan itu.
def _calon_legacy(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    out: list[Path] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        # Folder akun berisi `<slug>/sesi-N/`; folder legacy berisi
        # `sesi-N/` langsung. Bedanya cukup untuk memisahkan keduanya tanpa
        # perlu tahu format id Clerk.
        if any(_RE_SESI.match(x.name) for x in entry.iterdir() if x.is_dir()):
            out.append(entry)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", help="Id user Clerk tujuan.")
    ap.add_argument("--daftar", action="store_true", help="Tampilkan hasil lama lalu berhenti.")
    ap.add_argument("--dry-run", action="store_true", help="Cetak rencana tanpa memindahkan.")
    args = ap.parse_args()

    legacy = _calon_legacy(config.OUTPUT_DIR)
    if not legacy:
        print("Tidak ada hasil lama di output/. Tidak ada yang perlu dipindahkan.")
        return 0

    print(f"Hasil lama ({len(legacy)} mata kuliah):")
    for path in legacy:
        jumlah = len(list(path.glob("*/*.docx")))
        print(f"  {path.name:<50} {jumlah} dokumen")
    if args.daftar:
        return 0

    if not args.user:
        print("\nSebutkan --user <id Clerk>. Lihat daftar id dengan --daftar.", file=sys.stderr)
        return 2
    if not args.user.startswith("user_"):
        print("Id user Clerk biasanya berawalan `user_`. Periksa lagi.", file=sys.stderr)
        return 2

    tujuan = config.OUTPUT_DIR / args.user
    print(f"\nTujuan: {tujuan}")
    if args.dry_run:
        print("(dry-run: tidak ada berkas yang dipindahkan)")
        return 0

    tujuan.mkdir(parents=True, exist_ok=True)
    for path in legacy:
        target = tujuan / path.name
        if target.exists():
            print(f"  ! {path.name} sudah ada di tujuan, dilewati")
            continue
        shutil.move(str(path), str(target))
        print(f"  {path.name} -> {target.relative_to(config.OUTPUT_DIR)}")
    print("\nSelesai. Muat ulang halaman Result.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
