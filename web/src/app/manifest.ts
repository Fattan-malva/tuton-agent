import type { MetadataRoute } from 'next';

/**
 * Manifest untuk "Add to Home Screen" (iOS & Android).
 *
 * `purpose: "any"` saja, bukan `"maskable"`. Ikon ini memakai block shadow
 * keras + border 2px ala pixel; kalau dipakai sebagai maskable, Android akan
 * memotong bagian luar dan bayangan hilang, persis seperti elemen yang
 * jadi "tepi-tepi doang".
 *
 * `background_color` dan `theme_color` diambil dari `--bg-primary` di
 * `globals.css` supaya warna splash screen sama dengan halaman, tidak
 * kedipan putih saat aplikasi dibuka.
 */
export const dynamic = 'force-static';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Tuton Agent',
    short_name: 'Tuton',
    description: 'Auto-Grader and submission controller',
    start_url: '/',
    display: 'standalone',
    orientation: 'portrait',
    background_color: '#07090d',
    theme_color: '#07090d',
    icons: [
      { src: '/icon.png', sizes: '512x512', type: 'image/png' },
      { src: '/apple-icon.png', sizes: '180x180', type: 'image/png' },
    ],
  };
}
