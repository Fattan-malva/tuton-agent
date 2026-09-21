import { Activity, Cpu, FolderCheck, LogOut, Settings, Terminal } from 'lucide-react';
import type { Tab } from '../lib/types';

interface NavigationProps {
  activeTab: Tab;
  onSwitch: (tab: Tab) => void;
  onLogout: () => void;
}

const items: Array<{ id: Tab; label: string; icon: typeof Activity }> = [
  { id: 'status', label: 'Status Pekerjaan', icon: Activity },
  { id: 'results', label: 'Result', icon: FolderCheck },
  { id: 'run', label: 'Run Agent', icon: Terminal },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export default function Navigation({ activeTab, onSwitch, onLogout }: NavigationProps) {
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

      <header className="flex h-16 items-center justify-between border-b-2 border-border bg-surface/95 px-4 md:hidden">
        <div className="flex items-center gap-3">
          <div className="pixel-logo" aria-hidden="true">
            <Cpu size={20} strokeWidth={2.5} />
          </div>
          <span className="font-display text-sm text-text">Tuton Agent</span>
        </div>
        <button type="button" onClick={onLogout} className="pixel-icon-button text-danger" aria-label="Logout">
          <LogOut size={18} aria-hidden="true" />
        </button>
      </header>

      <nav className="fixed bottom-0 left-0 right-0 z-30 border-t-2 border-border bg-surface/95 px-2 pb-2 pt-2 md:hidden" aria-label="Navigasi mobile">
        <div className="grid grid-cols-4 gap-1">
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
                <span>{label === 'Status Pekerjaan' ? 'Status' : label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </>
  );
}
