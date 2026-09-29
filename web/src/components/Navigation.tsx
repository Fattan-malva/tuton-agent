import { Activity, ClipboardList, Cpu, FolderCheck, LogOut, Settings, Terminal } from 'lucide-react';
import type { Tab } from '../lib/types';

interface NavigationProps {
  activeTab: Tab;
  onSwitch: (tab: Tab) => void;
  onLogout: () => void;
  /**
   * Nama untuk header mobile. Opsional supaya komponen ini tidak pecah saat
   * `/api/config` belum selesai dimuat atau `.env` masih kosong -- pemanggil
   * cukup mengosongkannya dan `initials` jatuh ke inisial bawaan.
   */
  nama?: string;
}

const items: Array<{ id: Tab; label: string; icon: typeof Activity }> = [
  { id: 'status', label: 'Status Pekerjaan', icon: Activity },
  { id: 'results', label: 'Result', icon: FolderCheck },
  { id: 'run', label: 'Run Agent', icon: Terminal },
  { id: 'soal', label: 'Form Soal', icon: ClipboardList },
  { id: 'settings', label: 'Settings', icon: Settings },
];

/**
 * Inisial untuk avatar profil.
 *
 * Desktop memakai inisial statis "AD", jadi versi mobile mengikuti bentuk yang
 * sama: dua huruf, dan tetap tampil walau nama kosong -- header tidak boleh
 * berubah tinggi hanya karena `.env` belum diisi.
 */
function initials(name?: string): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'AD';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function Navigation({ activeTab, onSwitch, onLogout, nama }: NavigationProps) {
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 flex-col border-r-2 border-border bg-surface/95 md:flex">
        <div className="flex h-20 items-center gap-3 border-b-2 border-border px-5">
          <div className="pixel-logo" aria-hidden="true">
            <Cpu size={22} strokeWidth={2.5} />
          </div>
          <div className="min-w-0">
            <div className="font-display text-[13px] leading-none text-text">Tuton Agent</div>
            <div className="mt-1 font-terminal text-[9px] uppercase tracking-[0.16em] text-accent">CLI Web UI</div>
          </div>
        </div>

        <nav className="flex-1 space-y-2 overflow-y-auto px-4 py-5" aria-label="Navigasi utama">
          <div className="px-2 pb-1 font-terminal text-[9px] uppercase tracking-[0.18em] text-muted">Main Menu</div>
          {items.map(({ id, label, icon: Icon }) => {
            const active = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => onSwitch(id)}
                aria-current={active ? 'page' : undefined}
                className={`pixel-nav-button w-full ${active ? 'pixel-nav-button-active' : ''}`}
              >
                <Icon size={18} strokeWidth={2.2} aria-hidden="true" />
                <span>{label}</span>
              </button>
            );
          })}
        </nav>

        <div className="border-t-2 border-border p-4">
          <div className="pixel-panel-strong flex items-center justify-between gap-3 p-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="pixel-avatar" aria-hidden="true">AD</div>
              <div className="min-w-0">
                <div className="truncate text-xs font-semibold text-text">Admin Moodle</div>
                <div className="mt-0.5 flex items-center gap-1.5">
                  <span className="pixel-online-dot" />
                  <span className="font-terminal text-[9px] uppercase text-success">Online</span>
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={onLogout}
              className="pixel-icon-button text-danger"
              aria-label="Logout"
              title="Logout"
            >
              <LogOut size={16} aria-hidden="true" />
            </button>
          </div>
        </div>
      </aside>

      {/* Header mobile. Di desktop profil sudah ada di sidebar, jadi panel itu
          tidak diubah -- yang ditambah hanya versi mobile-nya.

          Profil (avatar + nama) dan logout SELALU tampil di semua lebar layar,
          tanpa breakpoint. Versi sebelumnya menyembunyikan nama di bawah 640px
          supaya tidak berdesakan, tapi akibatnya di HP 375-430px yang paling
          umum dipakai, yang terlihat cuma avatar kecil -- dan itu dilaporkan
          sebagai "profilnya tidak ada". Sekarang keduanya diprioritaskan: judul aplikasi
          yang memotong diri (`truncate`), nama profil ikut memotong, dan logout
          dapat target sentuh 44px.

          Kedua teks diberi `max-w` eksplisit. Tanpa itu, flex menyusut secara
          PROPORSIONAL terhadap lebar dasar, dan karena nama ("Muhammad Fattan
          Malva Al Dowi") jauh lebih lebar dari judul ("Tuton Agent"),
          justru profil-lah yang pertama terpotong -- kebalikan dari yang
          diinginkan. Dengan batas tetap, lebar leftover bisa diprediksi dan
          tidak pernah berubah-ubah.

          `fixed ... z-30` itu WAJIB, bukan gaya, dan polanya sengaja dibuat
          sama persis dengan nav bawah. `.pixel-world` di `page.tsx` adalah
          `position: fixed; z-index: 0` dengan background OPAQUE, dan dalam
          urutan paint CSS setiap elemen *positioned* menggambar DI ATAS elemen
          in-flow yang statis. Tanpa `z-30`, header ini terkubur di balik
          lapisan background itu: tidak terlihat sama sekali, dan karena
          `pixel-world` juga `pointer-events: none`, tombol logout-nya tidak
          bisa diklik. `aside` dan `nav` bawah sudah z-30 karena itu -- header
          biasanya terlewat karena satu-satunya chrome tanpa positioning.

          Karena posisinya `fixed`, konten `<main>` diberi padding atas sebesar
          `--app-header-h` (lihat globals.css) supaya tidak tertutup header. */}
      <header
        className="fixed top-0 left-0 right-0 z-30 flex items-center justify-between gap-2 border-b-2 border-border bg-surface/95 px-3 pb-2 md:hidden"
        style={{
          height: 'var(--app-header-h)',
          paddingTop: 'env(safe-area-inset-top, 0px)',
        }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <div className="pixel-logo shrink-0" aria-hidden="true">
            <Cpu size={20} strokeWidth={2.5} />
          </div>
          <span className="min-w-0 max-w-[5.5rem] truncate font-display text-sm text-text">
            Tuton Agent
          </span>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <div className="pixel-avatar shrink-0" aria-hidden="true">{initials(nama)}</div>
          <span className="min-w-0 max-w-[7rem] truncate font-terminal text-[10px] uppercase tracking-[0.08em] text-muted">
            {nama?.trim() || 'Admin Moodle'}
          </span>
          <button
            type="button"
            onClick={onLogout}
            className="pixel-icon-button-lg text-danger"
            aria-label="Logout"
            title="Logout"
          >
            <LogOut size={19} aria-hidden="true" />
          </button>
        </div>
      </header>

      <nav className="fixed bottom-0 left-0 right-0 z-30 border-t-2 border-border bg-surface/95 px-2 pb-2 pt-2 md:hidden" aria-label="Navigasi mobile">
        <div className="grid grid-cols-5 gap-1">
          {items.map(({ id, label, icon: Icon }) => {
            const active = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => onSwitch(id)}
                aria-current={active ? 'page' : undefined}
                className={`flex min-h-14 flex-col items-center justify-center gap-1 border-2 px-1 py-2 font-terminal text-[9px] uppercase ${
                  active
                    ? 'border-accent bg-accent/10 text-accent'
                    : 'border-transparent text-muted hover:border-border hover:text-text'
                }`}
              >
                <Icon size={17} strokeWidth={2.2} aria-hidden="true" />
                <span>{label === 'Status Pekerjaan' ? 'Status' : label === 'Form Soal' ? 'Soal' : label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </>
  );
}
