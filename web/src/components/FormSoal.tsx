import { ClipboardList, FileUp, LayoutTemplate, Play } from 'lucide-react';
import { useEffect, useState } from 'react';
import apiClient from '../lib/api-client';
import type { Course, Section, ToastType, WorkKind } from '../lib/types';
import Terminal, { type TerminalController } from './Terminal';

interface FormSoalProps {
  courses: Course[];
  onRefresh: () => Promise<void>;
  onNotify: (message: string, type?: ToastType) => void;
  terminal: TerminalController;
}

export default function FormSoal({ courses, onRefresh, onNotify, terminal }: FormSoalProps) {
  const [courseId, setCourseId] = useState('');
  const [sections, setSections] = useState<Section[]>([]);
  const [sectionsLoading, setSectionsLoading] = useState(false);
  const [sesi, setSesi] = useState('');
  const [kind, setKind] = useState<WorkKind>('tugas');
  const [title, setTitle] = useState('');
  const [soalText, setSoalText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [formatFile, setFormatFile] = useState<File | null>(null);
  const [formatNote, setFormatNote] = useState('');
  const [isStarting, setIsStarting] = useState(false);
  const [launched, setLaunched] = useState(false);

  const fileName = files.map((f) => f.name).join(', ');
  const hasFile = files.length > 0;
  const hasFormat = Boolean(formatFile) || formatNote.trim().length > 0;

  const isRunning = terminal.snapshot.running;
  const busy = isRunning || isStarting || launched;

  useEffect(() => {
    if (terminal.snapshot.running) setLaunched(false);
  }, [terminal.snapshot.running]);

  useEffect(() => {
    if (!courseId) {
      setSections([]);
      setSesi('');
      return;
    }
    let cancelled = false;
    setSectionsLoading(true);
    setSesi('');
    apiClient
      .getSections(Number(courseId))
      .then((result) => {
        if (!cancelled) setSections(result);
      })
      .catch((caught) => {
        if (!cancelled) {
          setSections([]);
          onNotify(caught instanceof Error ? caught.message : 'Gagal memuat daftar sesi.', 'error');
        }
      })
      .finally(() => {
        if (!cancelled) setSectionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [courseId, onNotify]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    setFiles(selected);
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    if (!courseId || !sesi) {
      onNotify('Pilih mata kuliah dan sesi terlebih dahulu.', 'warning');
      return;
    }
    if (!soalText.trim() && !hasFile) {
      onNotify('Isi teks soal atau unggah file soal terlebih dahulu.', 'warning');
      return;
    }

    const commandLine = [
      'python main.py solve',
      `--course ${courseId}`,
      `--sesi ${sesi}`,
      `--kind ${kind}`,
      title ? `--title "${title}"` : '',
      hasFile ? `--file "${files.map((f) => f.name).join('", "')}"` : '',
      formatFile ? `--format "${formatFile.name}"` : '',
      formatNote.trim() ? '--format-note "..."' : '',
    ].filter(Boolean).join(' ');

    terminal.setCommand(`user@tuton:~$ ${commandLine}`);
    terminal.reset();
    setIsStarting(true);
    setLaunched(true);

    try {
      const response = await apiClient.submitSolve({
        course_id: Number(courseId),
        sesi: Number(sesi),
        kind,
        title,
        soal_text: soalText,
        file: files[0] ?? null,
        files: files.slice(1),
        format_file: formatFile,
        format_note: formatNote.trim(),
      });

      if (!response.success) throw new Error(response.error || 'Gagal memulai pengerjaan soal.');
      onNotify('Pengerjaan soal dimulai.', 'success');
      void onRefresh();
    } catch (caught) {
      terminal.setCommand('');
      setLaunched(false);
      onNotify(caught instanceof Error ? caught.message : 'Gagal menjalankan form soal.', 'error');
    } finally {
      setIsStarting(false);
    }
  };

  const stopRun = async () => {
    try {
      const response = await apiClient.stopRun();
      if (!response.success) {
        onNotify(response.error || 'Proses sudah berhenti.', 'warning');
        return;
      }
      terminal.onStopRequested();
    } catch (caught) {
      onNotify(caught instanceof Error ? caught.message : 'Gagal menghentikan proses.', 'error');
    }
  };

  return (
    <section aria-labelledby="soal-heading">
      <div className="mb-6 max-w-3xl">
        <div className="font-terminal text-[10px] uppercase tracking-[0.18em] text-accent">Custom Mission</div>
        <h1 id="soal-heading" className="mt-1 font-display text-2xl leading-snug text-text sm:text-3xl">Kerjakan Soal (Form Soal)</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          Masukkan soal sendiri (teks atau file) untuk dikerjakan agent, hasilnya disimpan ke folder mata kuliah &amp; sesi yang dipilih.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
        <div className="pixel-panel p-5 sm:p-6">
          <div className="mb-5 flex items-center gap-2 text-text">
            <ClipboardList size={18} className="text-accent" aria-hidden="true" />
            <h2 className="font-display text-sm">Input Soal &amp; Target Output</h2>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <label className="pixel-field">
              <span className="pixel-label">Mata Kuliah (hasil dari Scrape)</span>
              <select className="pixel-input" value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={busy}>
                <option value="">Pilih mata kuliah...</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>{course.name} (ID: {course.id})</option>
                ))}
              </select>
            </label>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="pixel-field">
                <span className="pixel-label">Sesi</span>
                <select className="pixel-input" value={sesi} onChange={(event) => setSesi(event.target.value)} disabled={busy || !courseId || sectionsLoading}>
                  <option value="">
                    {sectionsLoading ? 'Memuat sesi...' : sections.length ? 'Pilih sesi...' : 'Pilih matkul dahulu'}
                  </option>
                  {sections.map((section) => (
                    <option key={section.number} value={section.number}>
                      Sesi {section.number} — {section.title || `Sesi ${section.number}`}
                    </option>
                  ))}
                </select>
              </label>

              <label className="pixel-field">
                <span className="pixel-label">Jenis Pekerjaan</span>
                <select className="pixel-input" value={kind} onChange={(event) => setKind(event.target.value as WorkKind)} disabled={busy}>
                  <option value="tugas">Tugas</option>
                  <option value="diskusi">Diskusi</option>
                </select>
              </label>
            </div>

            <label className="pixel-field">
              <span className="pixel-label">Judul Aktivitas (opsional)</span>
              <input className="pixel-input" type="text" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="contoh: Diskusi 1 / Tugas 2" disabled={busy} />
              <span className="pixel-helper mt-1 text-muted">
                Angka di judul (mis. Tugas 2) dipakai untuk nama file output. Kosongkan untuk default.
              </span>
            </label>

            <label className="pixel-field">
              <span className="pixel-label">Soal (teks)</span>
              <textarea className="pixel-input pixel-textarea" value={soalText} onChange={(event) => setSoalText(event.target.value)} placeholder="Tulis soal yang ingin dikerjakan di sini..." disabled={busy} />
            </label>

            <div className="pixel-field">
              <div className="flex items-center justify-between gap-2">
                <span className="pixel-label">Atau unggah file soal</span>
                {hasFile && (
                  <button
                    type="button"
                    onClick={() => setFiles([])}
                    disabled={busy}
                    className="font-terminal text-[10px] uppercase tracking-[0.1em] text-accent hover:underline disabled:opacity-50"
                  >
                    Hapus
                  </button>
                )}
              </div>
              <label className={`pixel-file-drop ${busy ? 'opacity-50' : 'cursor-pointer'}`}>
                <FileUp size={20} className="text-accent" aria-hidden="true" />
                {hasFile ? (
                  <span className="truncate text-xs font-semibold text-text" title={fileName}>{fileName}</span>
                ) : (
                  <span className="font-terminal text-[10px] uppercase tracking-[0.1em] text-muted">
                    Klik untuk memilih file (PDF, gambar, DOCX, XLSX, PPTX, TXT) — bisa pilih beberapa
                  </span>
                )}
                <input type="file" multiple onChange={handleFileChange} disabled={busy} className="sr-only" />
              </label>
            </div>

            {/* Field opsional. Kosong berarti dokumen hasilnya mengikuti template
                standar; diisi berarti dokumen contoh milik pengguna yang jadi
                acuan. Pakai <fieldset> supaya satu blok terbaca sebagai satu
                grup, bukan empat kontrol terpisah. */}
            <fieldset className="space-y-3 border border-dashed border-line/40 px-3 py-4" disabled={busy}>
              <legend className="flex items-center gap-2 px-1 font-terminal text-[10px] uppercase tracking-[0.14em] text-muted">
                <LayoutTemplate size={13} className="text-accent" aria-hidden="true" />
                Format Jawaban (opsional)
              </legend>

              <div className="flex items-start justify-between gap-2">
                <p className="pixel-helper text-muted">
                  Kosongkan kalau tidak ada bagian. Isi bagian ini kalau jawabanmu
                  punya bentuk khusus, lalu unggah satu file .docx berisi contoh
                  jawaban yang benar. Dokumen hasil akan mengikuti file itu.
                </p>
                {hasFormat && (
                  <button
                    type="button"
                    onClick={() => { setFormatFile(null); setFormatNote(''); }}
                    className="shrink-0 font-terminal text-[10px] uppercase tracking-[0.1em] text-accent hover:underline"
                  >
                    Hapus
                  </button>
                )}
              </div>

              <div className="pixel-field">
                <span className="pixel-label">Contoh format (.docx, opsional)</span>
                <label className={`pixel-file-drop ${busy ? 'opacity-50' : 'cursor-pointer'}`}>
                  <FileUp size={18} className="text-accent" aria-hidden="true" />
                  {formatFile ? (
                    <span className="truncate text-xs font-semibold text-text" title={formatFile.name}>{formatFile.name}</span>
                  ) : (
                    <span className="font-terminal text-[10px] uppercase tracking-[0.1em] text-muted">
                      Klik untuk memilih satu file .docx
                    </span>
                  )}
                  <input
                    type="file"
                    accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    onChange={(event) => setFormatFile(event.target.files?.[0] ?? null)}
                    className="sr-only"
                  />
                </label>
              </div>

              <label className="pixel-field">
                <span className="pixel-label">Keterangan format (opsional)</span>
                <textarea
                  className="pixel-input pixel-textarea-sm"
                  value={formatNote}
                  onChange={(event) => setFormatNote(event.target.value)}
                  placeholder="contoh: isomorphic dengan judul 'ABSTRAK' dan kata kunci, gunakan heading 1 untuk sub-bagian, jangan gunakan tabel"
                  disabled={busy}
                />
              </label>
            </fieldset>

            <button type="submit" disabled={busy} className="pixel-button pixel-button-primary w-full justify-center">
              {isStarting ? (
                <><span className="pixel-spinner" aria-hidden="true" /><span>Mengeksekusi...</span></>
              ) : (
                <><Play size={17} fill="currentColor" aria-hidden="true" /><span>{isRunning ? 'Running...' : 'Kerjakan Soal Sekarang'}</span></>
              )}
            </button>
          </form>
        </div>        <Terminal
          output={terminal.output}
          snapshot={terminal.snapshot}
          command={terminal.command}
          onStop={() => void stopRun()}
          onClear={terminal.onClearTerminal}
          busy={busy}
        />
      </div>
    </section>
  );
}