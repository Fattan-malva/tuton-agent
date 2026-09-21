import { BookOpen, Download, FileText, Inbox, RefreshCw, Trash2 } from 'lucide-react';
import type { ResultCourse } from '../lib/types';
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

export default function Results({ courses, loading, onRefresh, onNotify }: ResultsProps) {
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

  return (
    <section aria-labelledby="results-heading">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="font-terminal text-[10px] uppercase tracking-[0.18em] text-accent">Loot Vault</div>
          <h1 id="results-heading" className="mt-1 font-display text-2xl leading-snug text-text sm:text-3xl">Hasil Pekerjaan</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">Unduh file jawaban DOCX yang telah selesai dibuat oleh agent.</p>
        </div>
        <button type="button" onClick={onRefresh} disabled={loading} className="pixel-button pixel-button-secondary w-full sm:w-auto">
          <RefreshCw className={loading ? 'animate-spin' : ''} size={16} aria-hidden="true" />
          <span>{loading ? 'Memuat...' : 'Refresh Data'}</span>
        </button>
      </div>

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
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
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
    </section>
  );
}
