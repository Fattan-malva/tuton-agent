import { AlertTriangle, BookOpen, Download, Eye, FileText, Inbox, RefreshCw, Trash2, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { ResultCourse, ResultFile } from '../lib/types';
import apiClient from '../lib/api-client';
import type { ToastType } from '../lib/types';

interface ResultsProps {
  courses: ResultCourse[];
  loading: boolean;
  onRefresh: () => void;
  onNotify: (message: string, type?: ToastType) => void;
}

function formatSize(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** index).toFixed(1)} ${units[index]}`;
}

function formatDuration(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '';
  const total = Math.round(seconds);
  if (total < 60) return `${total} dtk`;
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m < 60) return s ? `${m} mnt ${s} dtk` : `${m} mnt`;
  const h = Math.floor(m / 60);
  return `${h} jam ${m % 60} mnt`;
}

function stampFor(file: ResultFile): string {
  return file.finished_at || file.created_at || '';
}

export default function Results({ courses, loading, onRefresh, onNotify }: ResultsProps) {
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [previewLoaded, setPreviewLoaded] = useState(false);

  useEffect(() => {
    if (previewPath === null) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPreviewPath(null);
        setPreviewLoaded(false);
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [previewPath]);

  const openPreview = (path: string) => {
    setPreviewLoaded(false);
    setPreviewPath(path);
  };

  const closePreview = () => {
    setPreviewPath(null);
    setPreviewLoaded(false);
  };

  const handleDeleteResult = async (path: string) => {
    if (!window.confirm('Hapus file DOCX ini?')) return;

    try {
      const response = await apiClient.deleteResult(path);
      if (!response.success) throw new Error(response.error || 'Gagal menghapus file.');
      onNotify('File DOCX berhasil dihapus.', 'success');
      await onRefresh();
    } catch (caught) {
      onNotify(caught instanceof Error ? caught.message : 'Gagal menghapus file.', 'error');
    }
  };

  const handleDeleteCourse = async (folder: string, courseName: string) => {
    if (!window.confirm(`Hapus seluruh folder matkul "${folder}" beserta semua filenya?`)) return;

    try {
      const response = await apiClient.deleteCourse(folder);
      if (!response.success) throw new Error(response.error || 'Gagal menghapus matkul.');
      onNotify(`${courseName} berhasil dihapus.`, 'success');
      await onRefresh();
    } catch (caught) {
      onNotify(caught instanceof Error ? caught.message : 'Gagal menghapus matkul.', 'error');
    }
  };

  const [resetBusy, setResetBusy] = useState(false);

  /**
   * Reset Hasil menghapus SELURUH isi `output/`: jawaban, peta, transkrip,
   * dan cache halaman. Cache ikut dihapus karena sekarang transkrip lampiran
   * ikut dibersihkan dari jawaban mahasiswa lain -- kalau cache-nya masih ada,
   * isi yang bocor itu akan terbaca lagi pada run berikutnya, dan "reset"
   * hanya jadi metade jadi.
   *
   * `keepCache` sengaja menjadi pilihan, bukan default: transkripsi ulang
   * memanggil model vision dan mahal, jadi untuk sekadar mengulang satu
   * worksheet karena soal berubah, cache justru yang ingin disimpan.
   */
  const handleReset = async (keepCache: boolean) => {
    const cacheNote = keepCache
      ? 'Cache halaman dan transkripsi AKAN TETAP ADA.'
      : 'Semua cache halaman dan transkrip juga ikut terhapus.';
    const confirmed = window.confirm(
      'Kosongkan SELURUH folder output/?\n\n'
      + 'Termasuk jawaban, peta soal, transkrip lampiran, dan state.json.\n'
      + `${cacheNote}\n\n`
      + 'Berkas di template/ dan Settings tidak terpengaruh.\n\n'
      + 'Lanjut?',
    );
    if (!confirmed) return;

    setResetBusy(true);
    try {
      const response = await apiClient.resetResults(keepCache);
      const files = response.files ?? 0;
      const items = response.items ?? 0;
      const gagal = response.failed ?? [];
      const ringkas =
        (files ? ` (${files} berkas, ${items} item status)` : '')
        + (gagal.length ? ` — ${gagal.length} GAGAL: ${gagal.join(', ')}` : '');
      if (!response.message && response.error) {
        // Gagal total (mis. masih ada run yang jalan). Tidak ada yang terhapus,
        // jadi cukup tampilkan alasannya.
        throw new Error(response.error);
      }
      onNotify(
        `${response.message ?? 'Output dibersihkan.'}${ringkas}`,
        // `success: false` berarti ada yang tidak terhapus. Menampilkannya
        // sebagai sukses akan membuat pengguna mengira output sudah bersih
        // padahal masih ada folder yang tersisa.
        gagal.length ? 'error' : 'success',
      );
      setPreviewPath(null);
      await onRefresh();
    } catch (caught) {
      onNotify(caught instanceof Error ? caught.message : 'Gagal membersihkan output.', 'error');
    } finally {
      setResetBusy(false);
    }
  };

  return (
    <section aria-labelledby="results-heading">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="font-terminal text-[10px] uppercase tracking-[0.18em] text-accent">Loot Vault</div>
          <h1 id="results-heading" className="mt-1 font-display text-2xl leading-snug text-text sm:text-3xl">Hasil Pekerjaan</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">Unduh file jawaban DOCX yang telah selesai dibuat oleh agent.</p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
          <button type="button" onClick={onRefresh} disabled={loading || resetBusy} className="pixel-button pixel-button-secondary w-full sm:w-auto">
            <RefreshCw className={loading ? 'animate-spin' : ''} size={16} aria-hidden="true" />
            <span>{loading ? 'Memuat...' : 'Refresh Data'}</span>
          </button>
          <div className="pixel-panel flex flex-col gap-2 p-2 sm:flex-row sm:items-center">
            <span className="px-1 font-terminal text-[9px] uppercase tracking-[0.14em] text-muted">
              Reset Hasil
            </span>
            <button
              type="button"
              onClick={() => handleReset(true)}
              disabled={loading || resetBusy}
              className="pixel-button pixel-button-secondary w-full sm:w-auto"
              title="Kosongkan output/, tapi pertahankan cache halaman dan transkrip"
            >
              <RefreshCw size={15} aria-hidden="true" />
              <span>Reset (cache aman)</span>
            </button>
            <button
              type="button"
              onClick={() => handleReset(false)}
              disabled={loading || resetBusy}
              className="pixel-button pixel-button-danger w-full sm:w-auto"
              title="Kosongkan output/ beserta seluruh cache"
            >
              <AlertTriangle size={15} aria-hidden="true" />
              <span>{resetBusy ? 'Membersihkan...' : 'Reset Total'}</span>
            </button>
          </div>
        </div>
      </div>

      {courses.length > 0 ? (
        <div className="pixel-alert pixel-alert-warning mb-6 flex items-start gap-2" role="note">
          <AlertTriangle size={15} className="mt-px shrink-0" aria-hidden="true" />
          <span>
            Reset menghapus isi <code className="pixel-code">output/</code> juga untuk
            mata kuliah yang tidak terlihat di daftar ini, karena yang dihapus adalah
            seluruh foldernya, bukan hanya berkas yang tampil.
          </span>
        </div>
      ) : null}

      {loading && !courses.length ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((item) => <div key={item} className="pixel-skeleton h-52" />)}
        </div>
      ) : courses.length === 0 ? (
        <div className="pixel-empty pixel-empty-large">
          <div className="pixel-empty-icon"><Inbox size={28} aria-hidden="true" /></div>
          <div>
            <h2 className="font-display text-lg text-text">Vault masih kosong</h2>
            <p className="mt-2 max-w-md text-sm leading-relaxed text-muted">Jalankan agent pada tab Run Agent untuk menghasilkan file jawaban pertama.</p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {courses.map((course) => {
            const fileCount = course.files.length;
            return (
              <article key={course.name} className="pixel-card flex min-h-full flex-col">
                <div className="flex items-start justify-between gap-3 border-b-2 border-border px-4 py-4">
                  <div className="min-w-0">
                    <div className="font-terminal text-[9px] uppercase tracking-[0.14em] text-accent">Course</div>
                    <h2 className="mt-1 truncate font-display text-base leading-snug text-text">{course.name}</h2>
                    <p className="mt-1 text-[11px] text-muted">
                      {fileCount ? `${fileCount} file selesai` : 'Belum ada file selesai'}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {course.folder && (
                      <button
                        type="button"
                        onClick={() => void handleDeleteCourse(course.folder!, course.name)}
                        className="pixel-icon-button text-danger"
                        aria-label={`Hapus ${course.name}`}
                        title="Hapus matkul"
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    )}
                    <div className="pixel-course-icon" aria-hidden="true">
                      <BookOpen size={18} />
                    </div>
                  </div>
                </div>

                {fileCount === 0 ? (
                  <div className="flex flex-1 items-center justify-center px-4 py-8 text-center">
                    <p className="font-terminal text-[10px] uppercase tracking-[0.12em] text-muted">No loot yet</p>
                  </div>
                ) : (
                  <ul className="flex-1 space-y-2 p-3">
                    {course.files.map((file) => (
                      <li key={`${file.path}-${file.name}`} className="pixel-file-row">
                        <div className="flex min-w-0 items-center gap-3">
                          <FileText className="shrink-0 text-accent" size={17} aria-hidden="true" />
                          <div className="min-w-0">
                            <div className="truncate text-xs font-semibold text-text">{file.name}</div>
                            <div className="mt-0.5 font-terminal text-[9px] uppercase tracking-[0.08em] text-muted">
                              {file.sesi ? `Sesi ${file.sesi} · ` : ''}{formatSize(file.size)}
                            </div>
                            {stampFor(file) && (
                              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 font-terminal text-[9px] tracking-[0.04em] text-accent">
                                <span title="Waktu selesai pengerjaan (WIB)">{stampFor(file)}</span>
                                {formatDuration(file.duration_sec) && (
                                  <span className="text-muted">· {formatDuration(file.duration_sec)}</span>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <button
                            type="button"
                            onClick={() => openPreview(file.path)}
                            className="pixel-icon-button text-text"
                            aria-label={`Pratinjau ${file.name}`}
                            title="Pratinjau DOCX"
                          >
                            <Eye size={15} aria-hidden="true" />
                          </button>
                          <a
                            href={`/api/download/${encodeURI(file.path)}`}
                            target="_blank"
                            rel="noreferrer"
                            className="pixel-icon-button text-accent"
                            aria-label={`Unduh ${file.name}`}
                            title="Unduh DOCX"
                          >
                            <Download size={15} aria-hidden="true" />
                          </a>
                          <button
                            type="button"
                            onClick={() => void handleDeleteResult(file.path)}
                            className="pixel-icon-button text-danger"
                            aria-label={`Hapus ${file.name}`}
                            title="Hapus DOCX"
                          >
                            <Trash2 size={15} aria-hidden="true" />
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            );
          })}
        </div>
      )}

      {previewPath && (
        <div className="pixel-modal-overlay" role="dialog" aria-modal="true" aria-label="Pratinjau dokumen" onClick={closePreview}>
          <div className="pixel-modal pixel-modal-wide" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between border-b-2 border-border bg-panel-strong px-4 py-3">
              <span className="truncate font-terminal text-[10px] uppercase tracking-[0.12em] text-text">Pratinjau</span>
              <button type="button" onClick={closePreview} className="pixel-icon-button text-muted hover:text-text" aria-label="Tutup pratinjau">
                <X size={17} aria-hidden="true" />
              </button>
            </div>
            <div className="relative h-[70vh]">
              <iframe
                title="Pratinjau DOCX"
                src={`/api/preview/${encodeURI(previewPath)}`}
                onLoad={() => setPreviewLoaded(true)}
                className={`h-full w-full border-0 bg-white transition-opacity duration-150 ${previewLoaded ? 'opacity-100' : 'opacity-0'}`}
              />
              {!previewLoaded && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="flex items-center gap-2 font-terminal text-[10px] uppercase tracking-[0.12em] text-muted">
                    <span className="pixel-spinner" aria-hidden="true" />
                    Memuat pratinjau...
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
