#!/usr/bin/env python3
"""Generate ikon aplikasi untuk web dan iOS.

Ikon ini sengaja dibangun dari GEOMETRI PERSIS ikon yang sudah dipakai di
sidebar (component `Navigation.tsx` -> `pixel-logo` + lucide `Cpu` v0.525.0),
bukan gambar baru yang terpisah. Kalau logo sidebar berubah, ubah konstanta
warna + skala di sini, lalu jalankan ulang:

    python3 web/scripts/make-icons.py

Menghasilkan:
    web/src/app/icon.svg          -> favicon browser (vektor, tajam di 16px)
    web/public/icon.png           -> 512px, dipakai manifest & shortcut
    web/src/app/apple-icon.png    -> 180px, dipakai iOS "Add to Home Screen"

Kenapa PNG 512 tidak ditaruh di `src/app/`: kalau `icon.png` dan `icon.svg`
sama-sama ada di sana, Next.js hanya mengeluarkan SATU `<link rel="icon">` --
dan yang dipilih PNG. SVG perlu diutamakan supaya favicon tetap tajam di 16px
(tab browser), sedangkan PNG tetap tersedia untuk manifest dan peramban lama.

Kenapa iOS butuh file terpisah: iOS tidak pernah memakai favicon. Home Screen
mengambil `apple-touch-icon` dan memotongnya sendiri dengan rounded-corner
miliknya, jadi file ini HARUS bujur penuh (tanpa sudut membulat buatan sendiri)
dan TANPA area transparan.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Palet: disalin dari `web/src/app/globals.css` (:root).
# Jangan di-hardcode warna lain -- supaya ikon tidak melenceng dari UI.
#
# SENGAJA TIDAK ADA `--bg-primary` (#07090d) lagi. Kotak pixel sekarang mengisi
# SELURUH kanvas, jadi tidak ada lagi bidang hitam di sekelilingnya. Ini bukan
# sekadar selera: iOS mengomposit area transparan pada `apple-touch-icon`
# sebagai HITAM, jadi ikon transparan akan tetap tampil sebagai kotak hitam di
# Home Screen -- hanya lebih kecil. Mengisi kanvas membuang kemungkinan itu.
# ---------------------------------------------------------------------------
BOX_FILL = "#3b2d12"  # --accent-soft
BOX_BORDER = "#ffe29a"  # warna border .pixel-logo
GLYPH = "#fbbf24"  # --accent

APP_DIR = Path(__file__).resolve().parent.parent / "src" / "app"
PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"

# Kanvas ikon 64 unit. Semua koordinat di bawah dalam ruang ini, supaya satu
# skema yang sama bisa dipakai untuk SVG (skala bebas) dan PNG (skala = px/64).
UNIT = 64
# Kotak mengisi kanvas penuh. Block shadow 3px dihapus karena tidak ada lagi
# ruang untuknya -- dan shadow juga tidak ada artinya di ikon Home Screen.
BOX_BORDER_W = 3.0  # 3/64 = 4.7%, sepadan 2px/42px = 4.8% di sidebar

# Peta lucide 24 -> unit 64: tengah ikon (12,12) dipusatkan ke (32,32).
# Glif diskalakan 2.0 sehingga membentang 12..52, di dalam interior 3..61 --
# proporsi yang sama dengan 22px di kotak 42px di sidebar.
GLYPH_SCALE = 2.0
GLYPH_STROKE = 2.0 * GLYPH_SCALE
GLYPH_RX_OUTER = 2.0 * GLYPH_SCALE
GLYPH_RX_INNER = 1.0 * GLYPH_SCALE


def g(value: float) -> float:
    """Koordinat viewport lucide (24 unit) -> ruang kanvas 64 unit."""
    return (value - 12.0) * GLYPH_SCALE + UNIT / 2


# Geometri persis dari `lucide-react@0.525.0` icons/cpu.js, apa adanya supaya
# ikon di home screen sama persis dengan yang di sidebar.
CPU_OUTER_RECT = (4.0, 4.0, 16.0, 16.0)
CPU_INNER_RECT = (8.0, 8.0, 8.0, 8.0)
# (dari, sampai) -- persis urutan path di lucide: 4 pin atas/bawah, 4 kiri/kanan.
CPU_PINS = (
    (12.0, 20.0, 12.0, 22.0),  # bawah tengah
    (12.0, 2.0, 12.0, 4.0),  # atas tengah
    (17.0, 20.0, 17.0, 22.0),
    (17.0, 2.0, 17.0, 4.0),
    (2.0, 12.0, 4.0, 12.0),  # kiri tengah
    (2.0, 17.0, 4.0, 17.0),
    (2.0, 7.0, 4.0, 7.0),
    (20.0, 12.0, 22.0, 12.0),  # kanan tengah
    (20.0, 17.0, 22.0, 17.0),
    (20.0, 7.0, 22.0, 7.0),
    (7.0, 20.0, 7.0, 22.0),
    (7.0, 2.0, 7.0, 4.0),
)


def _stroke_line(draw: ImageDraw.ImageDraw, p0: tuple[float, float], p1: tuple[float, float], width: float, color: str) -> None:
    """Garis dengan ujung bulat, sama seperti `stroke-linecap="round"` lucide."""
    draw.line([p0, p1], fill=color, width=int(round(width)))
    radius = width / 2.0
    for point in (p0, p1):
        x, y = point
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)


def render(size: int, *, supersample: int = 4) -> Image.Image:
    """Render ikon ukuran `size` px.

    Mode `RGB` (bukan RGBA) dengan sudut siku: Home Screen iOS memotong
    rounded-corner-nya sendiri, dan area transparan akan dikomposit jadi hitam.
    Jadi PNG harus bujur penuh 100% opaque -- membiarkan iOS yang memotong.
    """
    scale = size * supersample / UNIT
    big = Image.new("RGB", (size * supersample, size * supersample), BOX_FILL)
    draw = ImageDraw.Draw(big)

    def s(value: float) -> float:
        return value * scale

    def rect(x: float, y: float, w: float, h: float) -> list[float]:
        return [s(x), s(y), s(x + w), s(y + h)]

    # Border digambar sebagai 4 pita tepat di tepi kanvas (0..BOX_BORDER_W),
    # bukan `outline` pada rect bersudut: supaya hasilnya 100% opaque sampai
    # ke tepi dan ketebalan garis tidak ikut terpecah oleh pembulatan piksel.
    bw = s(BOX_BORDER_W)
    edge = size * supersample
    draw.rectangle([0, 0, edge, bw], fill=BOX_BORDER)  # atas
    draw.rectangle([0, edge - bw, edge, edge], fill=BOX_BORDER)  # bawah
    draw.rectangle([0, 0, bw, edge], fill=BOX_BORDER)  # kiri
    draw.rectangle([edge - bw, 0, edge, edge], fill=BOX_BORDER)  # kanan

    # Glif CPU.
    ox, oy, ow, oh = CPU_OUTER_RECT
    draw.rounded_rectangle(
        rect(g(ox), g(oy), ow * GLYPH_SCALE, oh * GLYPH_SCALE),
        radius=s(GLYPH_RX_OUTER),
        outline=GLYPH,
        width=int(round(s(GLYPH_STROKE))),
    )
    ix, iy, iw, ih = CPU_INNER_RECT
    draw.rounded_rectangle(
        rect(g(ix), g(iy), iw * GLYPH_SCALE, ih * GLYPH_SCALE),
        radius=s(GLYPH_RX_INNER),
        outline=GLYPH,
        width=int(round(s(GLYPH_STROKE))),
    )
    for x0, y0, x1, y1 in CPU_PINS:
        _stroke_line(draw, (s(g(x0)), s(g(y0))), (s(g(x1)), s(g(y1))), s(GLYPH_STROKE), GLYPH)

    if supersample == 1:
        return big
    # `BOX` (rata-rata area), BUKAN LANCZOS/BICUBIC.
    #
    # Rasio downsample di sini bilangan bulat, jadi `BOX` justru filter yang
    # benar secara matematis: setiap piksel output = rata-rata persis blok
    # piksel input. LANCZOS dan BICUBIC punya kernel bermultiple lobe sehingga
    # MEMBUNCING (ringing) di tepi kontras tinggi, dan di ikon ini kontrasnya
    # ekstrem: border kream (255,226,154) bersinggungan dengan fill coklat (61,45,18).
    # Akibatnya muncul garis gelap 1px di dalam border -- di sudut bahkan
    # terlihat seperti bintik hitam, padahal tidak ada hitam di desain.
    return big.resize((size, size), Image.Resampling.BOX)


def build_svg() -> str:
    """Favicon vektor. Bentuk sama persis dengan PNG, tapi tajam di 16px."""
    pins = "\n    ".join(
        f'<path d="M{f2(g(x0))} {f2(g(y0))}v{f2(g(y1) - g(y0)) if y1 > y0 else f2(g(y0) - g(y1))}"/>'
        if x0 == x1
        else f'<path d="M{f2(g(x0))} {f2(g(y0))}h{f2(g(x1) - g(x0))}"/>'
        for x0, y0, x1, y1 in CPU_PINS
    )
    outer = (
        f"M{f2(g(CPU_OUTER_RECT[0]))} {f2(g(CPU_OUTER_RECT[1]))}"
        f"h{f2(CPU_OUTER_RECT[2] * GLYPH_SCALE)}v{f2(CPU_OUTER_RECT[3] * GLYPH_SCALE)}"
        f"h-{f2(CPU_OUTER_RECT[2] * GLYPH_SCALE)}z"
    )
    inner = (
        f"M{f2(g(CPU_INNER_RECT[0]))} {f2(g(CPU_INNER_RECT[1]))}"
        f"h{f2(CPU_INNER_RECT[2] * GLYPH_SCALE)}v{f2(CPU_INNER_RECT[3] * GLYPH_SCALE)}"
        f"h-{f2(CPU_INNER_RECT[2] * GLYPH_SCALE)}z"
    )
    # Rect border digeser masuk BOX_BORDER_W/2 supaya garis stroke-nya utuh di
    # dalam kanvas. Kalau rect-nya menempel di 0, setengah stroke terpotong tepi.
    inset = BOX_BORDER_W / 2
    side = UNIT - BOX_BORDER_W
    # Sudut membulat 4 unit (~6%): cukup untuk favicon di tab terlihat rapi,
    # dan iOS tidak pernah memakai file ini (ia memotong sendiri).
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {UNIT} {UNIT}" width="{UNIT}" height="{UNIT}">
  <rect width="{UNIT}" height="{UNIT}" fill="{BOX_FILL}"/>
  <rect x="{f2(inset)}" y="{f2(inset)}" width="{f2(side)}" height="{f2(side)}" rx="{f2(inset * 1.3)}" fill="none" stroke="{BOX_BORDER}" stroke-width="{f2(BOX_BORDER_W)}"/>
  <g fill="none" stroke="{GLYPH}" stroke-width="{f2(GLYPH_STROKE)}" stroke-linecap="round" stroke-linejoin="round">
    <path d="{outer}"/>
    <path d="{inner}"/>
    {pins}
  </g>
</svg>
"""


def f2(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def main() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    (APP_DIR / "icon.svg").write_text(build_svg(), encoding="utf-8")
    print(f"  icon.svg        {APP_DIR / 'icon.svg'}")

    # 512 PNG -> `public/` (ikut ter-export apa adanya, tidak jadi route Next).
    path = PUBLIC_DIR / "icon.png"
    render(512).save(path, format="PNG", optimize=True)
    print(f"  icon.png        512x512  {path}")

    # 180 PNG -> `src/app/` supaya Next mengeluarkan `apple-touch-icon` sendiri.
    path = APP_DIR / "apple-icon.png"
    render(180).save(path, format="PNG", optimize=True)
    print(f"  apple-icon.png  180x180  {path}")


if __name__ == "__main__":
    main()
