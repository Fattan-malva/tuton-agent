import { CheckCircle2, Clock3, RefreshCw, XCircle } from 'lucide-react';
import type { StatusItem, StatusStats } from '../lib/types';

interface StatusProps {
  stats: StatusStats | null;
  items: StatusItem[];
  loading: boolean;
  onRefresh: () => void;
}

const stats = [
  { label: 'Pekerjaan Selesai', value: 'done', icon: CheckCircle2, tone: 'success' },
  { label: 'Pekerjaan Gagal', value: 'failed', icon: XCircle, tone: 'danger' },
  { label: 'Dalam Antrean', value: 'pending', icon: Clock3, tone: 'accent' },
] as const;

function StatusBadge({ status }: { status: StatusItem['status'] }) {
  const config: Record<StatusItem['status'], { label: string; className: string }> = {
    done: { label: 'DONE', className: 'pixel-badge-success' },
    failed: { label: 'FAIL', className: 'pixel-badge-danger' },
    pending: { label: 'PENDING', className: 'pixel-badge-warning' },
    unknown: { label: 'UNKNOWN', className: 'pixel-badge-muted' },
  };

  return <span className={`pixel-badge ${config[status]?.className ?? config.unknown.className}`}>{config[status]?.label ?? status}</span>;
}

export default function Status({ stats: currentStats, items, loading, onRefresh }: StatusProps) {
  return (
    <section aria-labelledby="status-heading">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="font-terminal text-[10px] uppercase tracking-[0.18em] text-accent">Quest Log</div>
          <h1 id="status-heading" className="mt-1 font-display text-2xl leading-snug text-text sm:text-3xl">Status Pekerjaan</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            Laporan langsung dari <span className="pixel-code">state.json</span> untuk seluruh mata kuliah.
          </p>
        </div>
        <button type="button" onClick={onRefresh} disabled={loading} className="pixel-button pixel-button-secondary w-full sm:w-auto">
          <RefreshCw className={loading ? 'animate-spin' : ''} size={16} aria-hidden="true" />
          <span>{loading ? 'Memuat...' : 'Refresh Data'}</span>
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {stats.map(({ label, value, icon: Icon, tone }) => {
          const count = currentStats?.[value] ?? 0;
          return (
            <div key={value} className={`pixel-stat pixel-stat-${tone}`}>
              <div className={`pixel-stat-icon pixel-stat-icon-${tone}`}>
                <Icon size={23} strokeWidth={2.3} aria-hidden="true" />
              </div>
              <div>
                <div className="font-terminal text-[9px] uppercase tracking-[0.14em] text-muted">{label}</div>
                <div className="mt-1 font-display text-3xl leading-none text-text">{count}</div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="pixel-panel mt-6 overflow-hidden">
        <div className="flex items-center justify-between border-b-2 border-border px-4 py-3 sm:px-5">
          <div>
            <h2 className="font-display text-sm text-text">Detail Status per Item</h2>
            <p className="mt-1 text-[11px] text-muted">Setiap item disimpan dalam antrian pekerjaan agent.</p>
          </div>
          <span className="pixel-count">{items.length} item</span>
        </div>

        {loading && !items.length ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2].map((row) => (
              <div key={row} className="pixel-skeleton h-11" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="pixel-empty">
            <span className="pixel-empty-icon">0</span>
            <div>
              <h3 className="font-display text-sm text-text">Belum ada pekerjaan</h3>
              <p className="mt-1 text-xs text-muted">Jalankan agent untuk membuat quest pertama.</p>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse">
              <thead>
                <tr className="border-b-2 border-border bg-panel-strong text-left font-terminal text-[9px] uppercase tracking-[0.12em] text-muted">
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Mata Kuliah</th>
                  <th className="px-4 py-3">Sesi</th>
                  <th className="px-4 py-3">Deskripsi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {items.map((item) => (
                  <tr key={item.key} className="pixel-table-row">
                    <td className="px-4 py-3">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-4 py-3 font-semibold text-text">{item.matkul || '-'}</td>
                    <td className="px-4 py-3 font-terminal text-[11px] text-muted">
                      {item.sesi ? `SESI ${item.sesi}` : '-'}
                    </td>
                    <td className="max-w-[32rem] px-4 py-3 text-xs leading-relaxed text-muted">{item.desc || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
