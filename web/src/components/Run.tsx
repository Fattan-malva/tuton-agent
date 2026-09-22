import { CalendarClock, Play, Save, Terminal as TerminalIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import apiClient from '../lib/api-client';
import type { Course, Schedule, ToastType } from '../lib/types';
import Terminal, { type TerminalController } from './Terminal';

interface RunProps {
  courses: Course[];
  schedule: Schedule | null;
  onRefresh: () => Promise<void>;
  onNotify: (message: string, type?: ToastType) => void;
  terminal: TerminalController;
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

export default function Run({ courses, schedule, onRefresh, onNotify, terminal }: RunProps) {
  const [courseId, setCourseId] = useState('');
  const [sesi, setSesi] = useState('');
  const [force, setForce] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [launched, setLaunched] = useState(false);
  const [isSavingSchedule, setIsSavingSchedule] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [day, setDay] = useState<Schedule['day']>('*');
  const [time, setTime] = useState('02:00');

  const isRunning = terminal.snapshot.running;
  const busy = isRunning || isStarting || launched;

  useEffect(() => {
    if (terminal.snapshot.running) setLaunched(false);
  }, [terminal.snapshot.running]);

  useEffect(() => {
    if (!schedule) return;
    setEnabled(!!schedule.enabled);
    setDay(schedule.day === '*' ? '*' : schedule.day);
    setTime(schedule.time || '02:00');
  }, [schedule]);

  const startRun = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;

    const selectedCourse = courseId ? Number(courseId) : undefined;
    const selectedSesi = sesi ? Number(sesi) : undefined;
    const commandLine = [
      'python main.py run',
      selectedCourse ? `--course ${selectedCourse}` : '',
      selectedSesi ? `--sesi ${selectedSesi}` : '',
      force ? '--force' : '',
    ].filter(Boolean).join(' ');

    terminal.setCommand(`user@tuton:~$ ${commandLine}`);
    terminal.reset();
    setIsStarting(true);
    setLaunched(true);

    try {
      const response = await apiClient.startRun({
        course_id: selectedCourse,
        sesi: selectedSesi,
        force,
      });

      if (!response.success) throw new Error(response.error || 'Gagal memulai run.');
      onNotify('Agent mulai dijalankan.', 'success');
    } catch (caught) {
      terminal.setCommand('');
      setLaunched(false);
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
      terminal.onStopRequested();
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

  const nextRun = schedule?.next_run?.replace('T', ' ').replace('+07:00', ' WIB') || '';

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
              <select className="pixel-input" value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={busy}>
                <option value="">Semua mata kuliah</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>{course.name} (ID: {course.id})</option>
                ))}
              </select>
            </label>

            <label className="pixel-field">
              <span className="pixel-label">Filter Sesi</span>
              <input className="pixel-input" type="number" min="1" value={sesi} onChange={(event) => setSesi(event.target.value)} placeholder="Contoh: 3" disabled={busy} />
            </label>

            <label className="pixel-check">
              <input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} disabled={busy} />
              <span>
                <span className="block text-xs font-semibold text-text">Force Run (--force)</span>
                <span className="mt-0.5 block font-terminal text-[9px] uppercase tracking-[0.08em] text-muted">Ulangi item yang sudah selesai</span>
              </span>
            </label>

            <button type="submit" disabled={busy} className="pixel-button pixel-button-primary w-full justify-center">
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

        <Terminal
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