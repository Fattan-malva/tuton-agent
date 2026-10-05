#!/usr/bin/env bash
# Redeploy tuton-agent secara penuh sekali jalan:
#   1-2. frontend UI statis di frontend/ (index.html), tidak perlu build
#   3. rebuild + restart container (--build: image ikut menangkap perubahan
#      file .py/kode)
#   4. re-attach ke app-network
#   5. cek nginx (TIDAK direstart, lihat catatan di bawah)
#
# Workaround untuk podman 3.4 yang meng-ignore `--network=<name>:alias=...`.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== [1-2/5] Frontend statis (frontend/index.html), build Next.js dilewati ==="

# 3) Rebuild + start container (--build: memuat perubahan Python/kode)
echo "=== [3/5] Rebuilding & starting containers ==="
podman-compose up -d --build

# 4) Re-attach ke app-network (workaround podman 3.4)
echo "=== [4/5] Connecting to app-network ==="
sleep 3
podman network connect app-network tuton-agent 2>/dev/null || true

# 5) JANGAN sentuh nginx di sini.
#
#    nginx melayani banyak project lain (spty-web, 9router, marketplace, dll)
#    dan jadi target utama script ini. Di podman 3.4.4 `podman restart nginx` rapuh:
#    port 80/443 belum dilepas host saat container baru mau bind, sehingga
#    start gagal "address already in use" dan nginx MATI TANPA ERROR yang
#    terlihat (script tetap exit 0). Satu restart salah = semua web down.
#
#    Proxy ke tuton-agent lewat DNS container, jadi container yang baru
#    langsung terlayani tanpa perlu reload nginx. Kalau config nginx memang
#    berubah, restart manual:  podman restart nginx
echo "=== [5/5] nginx dilewati (dijaga tetap hidup) ==="

# Peringatan saja kalau nginx mati, jangan dinyalakan di sini.
if ! podman inspect nginx --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
  echo "  PERINGATAN: container nginx tidak running." >&2
  echo "  Nyalakan manual dengan: podman start nginx" >&2
fi

echo "---"
podman ps --format '{{.Names}} | {{.Status}} | {{.Ports}}' 2>/dev/null | grep -iE 'tuton|nginx' || echo "No containers found"
echo "Redeploy selesai."