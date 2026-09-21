import { CalendarClock, Play, Save, Square, Terminal as TerminalIcon, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTerminalMonitor } from '../hooks/useTerminalMonitor';
import apiClient from '../lib/api-client';
import type { Course, Schedule, ToastType } from '../lib/types';

interface RunProps {
  courses: Course[];
  schedule: Schedule | null;
  onRefresh: () => Promise<void>;
  onNotify: (message: string, type?: ToastType) => void;
}

const dayLabels: Record<Schedule['day'], string> = {
  '*': 'Setiap Hari',
  '0': 'Minggu',
  '1': 'Senin',
  '2': 'Selasa',
  '3': 'Rabu',
  '4': 'Kamis',
  '5': 'Jumat',
  '6': 'Sabtu',
};

function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  const pad = (value: number) => String(value).padStart(2, '0');
  return hours > 0 ? `${pad(hours)}:${pad(minutes)}:${pad(remainder)}` : `${pad(minutes)}:${pad(remainder)}`;
}

function lineTone(line: string): string {
  if (/ERROR|Gagal|✗|exit code/i.test(line)) return 'error';
  if (/✓|Selesai|siap\.$/i.test(line)) return 'success';
  if (/dilewati|timeout|BERHENTI|warning/i.test(line)) return 'warning';
  if (/^user@tuton/.test(line)) return 'cmd';
  return 'info';
}

export default function Run({ courses, schedule, onRefresh, onNotify }: RunProps) {
  const [courseId, setCourseId] = useState('');
  const [sesi, setSesi] = useState('');
  const [force, setForce] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isSavingSchedule, setIsSavingSchedule] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [day, setDay] = useState<Schedule['day']>('*');
  const [time, setTime] = useState('02:00');
  const [command, setCommand] = useState('');
  const [stoppedByUser, setStoppedByUser] = useState(false);
  const stoppedByUserRef = useRef(false);
  const terminalRef = useRef<HTMLDivElement>(null);

  const handleComplete = useCallback(
    (returncode: number) => {
      const wasStopped = stoppedByUserRef.current;
      setIsRunning(false);
      setStoppedByUser(wasStopped);
      stoppedByUserRef.current = false;
      void onRefresh().then(() => {
        if (wasStopped) {
          onNotify('Run dihentikan oleh pengguna.', 'warning');
        } else if (returncode !== 0) {
          onNotify(`Proses selesai dengan error (exit ${returncode}).`, 'error');
        } else {
          onNotify('Run selesai dieksekusi.', 'success');
        }
      });
    },
    [onNotify, onRefresh],
  );

  const { output, snapshot, reset } = useTerminalMonitor(isRunning, handleComplete);

  useEffect(() => {
    const terminal = terminalRef.current;
    if (terminal) terminal.scrollTop = terminal.scrollHeight;
  }, [output]);

  useEffect(() => {
    if (!schedule) return;
    setEnabled(!!schedule.enabled);
    setDay(schedule.day === '*' ? '*' : schedule.day);
    setTime(schedule.time || '02:00');
  }, [schedule]);

  const startRun = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isRunning || isStarting) return;

    const selectedCourse = courseId ? Number(courseId) : undefined;
    const selectedSesi = sesi ? Number(sesi) : undefined;
    const commandLine = [
      'python main.py run',
      selectedCourse ? `--course ${selectedCourse}` : '',
      selectedSesi ? `--sesi ${selectedSesi}` : '',
      force ? '--force' : '',
    ].filter(Boolean).join(' ');

    setCommand(`user@tuton:~$ ${commandLine}`);
    setStoppedByUser(false);
    stoppedByUserRef.current = false;
    reset();
    setIsStarting(true);

    try {
      const response = await apiClient.startRun({
        course_id: selectedCourse,
        sesi: selectedSesi,
        force,
      });

      if (!response.success) throw new Error(response.error || 'Gagal memulai run.');
      setIsRunning(true);
      onNotify('Agent mulai dijalankan.', 'success');
    } catch (caught) {
      setCommand('');
      onNotify(caught instanceof Error ? caught.message : 'Gagal menjalankan agent.', 'error');
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
      stoppedByUserRef.current = true;
      setStoppedByUser(true);
    } catch (caught) {
      onNotify(caught instanceof Error ? caught.message : 'Gagal menghentikan run.', 'error');
    }
  };

  const saveSchedule = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSavingSchedule(true);

    try {
      const response = await apiClient.saveSchedule({ enabled, day, time });
      setEnabled(!!response.enabled);
      setDay(response.day);
      setTime(response.time);
      onNotify(
        response.enabled
          ? `Cronjob dijadwalkan ${dayLabels[response.day]} pukul ${response.time} WIB.`
          : 'Cronjob dinonaktifkan.',
        response.enabled ? 'success' : 'warning',
      );
    } catch (caught) {
      onNotify(caught instanceof Error ? caught.message : 'Gagal menyimpan jadwal.', 'error');
    } finally {
      setIsSavingSchedule(false);
    }
  };

  const clearTerminal = () => {
    setCommand('');
    reset();
    onNotify('Terminal dibersihkan.', 'info');
  };

  const nextRun = schedule?.next_run?.replace('T', ' ').replace('+07:00', ' WIB') || '';
  const progress = snapshot.progress;
  const activeProgress = ['scraping', 'mengerjakan', 'transkripsi', 'opencode', 'docx'].includes(snapshot.step);

  return (
    <section aria-labelledby="run-heading">
      <div className="mb-6 max-w-3xl">
        <div className="font-terminal text-[10px] uppercase tracking-[0.18em] text-accent">Mission Control</div>
        <h1 id="run-heading" className="mt-1 font-display text-2xl leading-snug text-text sm:text-3xl">Agent Runner</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">Eksekusi scrape, transkripsi, OpenCode, dan pembuatan DOCX dari satu panel.</p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
        <div className="pixel-panel p-5 sm:p-6">
          <div className="mb-5 flex items-center gap-2 text-text">
            <TerminalIcon size={18} className="text-accent" aria-hidden="true" />
            <h2 className="font-display text-sm">Parameter Eksekusi</h2>
          </div>

          <form onSubmit={startRun} className="space-y-4">
            <label className="pixel-field">
              <span className="pixel-label">Mata Kuliah dari Scrape</span>
              <select className="pixel-input" value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={isRunning || isStarting}>
                <option value="">Semua mata kuliah</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>{course.name} (ID: {course.id})</option>
                ))}
              </select>
            </label>

            <label className="pixel-field">
              <span className="pixel-label">Filter Sesi</span>
              <input className="pixel-input" type="number" min="1" value={sesi} onChange={(event) => setSesi(event.target.value)} placeholder="Contoh: 3" disabled={isRunning || isStarting} />
            </label>

            <label className="pixel-check">
              <input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} disabled={isRunning || isStarting} />
              <span>
                <span className="block text-xs font-semibold text-text">Force Run (--force)</span>
                <span className="mt-0.5 block font-terminal text-[9px] uppercase tracking-[0.08em] text-muted">Ulangi item yang sudah selesai</span>
              </span>
            </label>

            <button type="submit" disabled={isRunning || isStarting} className="pixel-button pixel-button-primary w-full justify-center">
              {isStarting ? (
                <><span className="pixel-spinner" aria-hidden="true" /><span>Mengeksekusi...</span></>
              ) : (
                <><Play size={17} fill="currentColor" aria-hidden="true" /><span>{isRunning ? 'Running...' : 'Jalankan Sekarang'}</span></>
              )}
            </button>
          </form>

          <div className="pixel-divider my-7">
            <span>Atur Jadwal Otomatis</span>
          </div>

          <form onSubmit={saveSchedule} className="space-y-4">
            <label className="pixel-check pixel-check-between">
              <span className="flex items-center gap-2 text-xs font-semibold text-text">
                <CalendarClock size={15} className="text-accent" aria-hidden="true" />
                Aktifkan Cronjob
              </span>
              <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="pixel-field">
                <span className="pixel-label">Hari</span>
                <select className="pixel-input" value={day} onChange={(event) => setDay(event.target.value as Schedule['day'])}>
                  {Object.entries(dayLabels).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
              <label className="pixel-field">
                <span className="pixel-label">Jam (WIB)</span>
                <input className="pixel-input" type="time" value={time} onChange={(event) => setTime(event.target.value)} />
              </label>
            </div>

            <button type="submit" disabled={isSavingSchedule} className="pixel-button pixel-button-secondary w-full justify-center">
              {isSavingSchedule ? <><span className="pixel-spinner" aria-hidden="true" /><span>Menyimpan...</span></> : <><Save size={16} aria-hidden="true" /><span>Simpan Jadwal</span></>}
            </button>

            {schedule && (
              <p className={`pixel-helper ${schedule.enabled ? 'text-success' : 'text-muted'}`}>
                {schedule.enabled ? `Berikutnya: ${nextRun || 'menghitung...'}` : 'Cronjob nonaktif.'}
              </p>
            )}
          </form>
        </div>

        <div className="pixel-terminal-panel min-h-[340px] overflow-hidden">
          <div className="flex items-center justify-between border-b-2 border-border bg-panel-strong px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="pixel-terminal-dot pixel-terminal-dot-danger" />
              <span className="pixel-terminal-dot pixel-terminal-dot-warning" />
              <span className="pixel-terminal-dot pixel-terminal-dot-success" />
              {isRunning && <span className="pixel-running-label"><span className="pixel-online-dot" /> Running</span>}
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={stopRun} disabled={!isRunning} className="pixel-terminal-action text-danger">
                <Square size={12} fill="currentColor" aria-hidden="true" /> stop
              </button>
              <button type="button" onClick={clearTerminal} className="pixel-terminal-action text-muted hover:text-text">
                <Trash2 size={13} aria-hidden="true" /> clear
              </button>
            </div>
          </div>

          {(isRunning || progress > 0 || command) && (
            <div className="border-b-2 border-border bg-panel px-4 py-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <span className="truncate font-terminal text-[10px] text-text">{snapshot.label}</span>
                <span className="shrink-0 font-terminal text-[10px] text-muted">{snapshot.done}/{snapshot.total || '?'}</span>
              </div>
              <div className="pixel-progress" aria-label={`Progress ${progress}%`}>
                <div className="pixel-progress-fill" style={{ width: `${progress}%` }} />
              </div>
              <div className="mt-2 flex items-center justify-between font-terminal text-[9px] uppercase tracking-[0.1em] text-muted">
                <span>{activeProgress ? snapshot.step : snapshot.step}</span>
                <span>{formatElapsed(snapshot.elapsed)}</span>
              </div>
            </div>
          )}

          <div ref={terminalRef} className="pixel-terminal-scroll" aria-live="polite">
            {command && <div className="pixel-terminal-line pixel-terminal-cmd">{command}</div>}
            {output.length === 0 && !command ? (
              <div className="pixel-terminal-empty">
                <span className="text-success">$</span>
                <span>Sistem siap menerima perintah.</span>
              </div>
            ) : output.map((line, index) => (
              <div key={`${index}-${line}`} className={`pixel-terminal-line pixel-terminal-${lineTone(line)}`}>{line || ' '}</div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
