'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import apiClient from '../lib/api-client';
import type { AppConfig, Course, ModelsResponse, ResultCourse, StatusResponse } from '../lib/types';

type TabId = 'status' | 'result' | 'run' | 'form' | 'settings';

const TITLES: Record<TabId, string> = {
  status: 'Status Pekerjaan',
  result: 'Result Dokumen',
  run: 'Agent Runner',
  form: 'Form Soal',
  settings: 'Settings Sistem',
};

interface ToastState {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info';
}

export default function Dashboard() {
  const [tab, setTab] = useState<TabId>('run');
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [statusData, setStatusData] = useState<StatusResponse | null>(null);
  const [results, setResults] = useState<ResultCourse[]>([]);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);

  // Run state
  const [running, setRunning] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [progressText, setProgressText] = useState('SIAP');

  const [search, setSearch] = useState('');
  const [previewPath, setPreviewPath] = useState<string | null>(null);

  // Form state
  const [formCourse, setFormCourse] = useState('');
  const [formSesi, setFormSesi] = useState('');
  const [formKind, setFormKind] = useState<'tugas' | 'diskusi'>('tugas');
  const [formTitle, setFormTitle] = useState('');
  const [formText, setFormText] = useState('');
  const [formFile, setFormFile] = useState<File | null>(null);
  const [formSending, setFormSending] = useState(false);

  // Run form
  const [runCourse, setRunCourse] = useState('');
  const [runSesi, setRunSesi] = useState('');
  const [runKind, setRunKind] = useState('all');

  // Settings form
  const [setForm, setSetForm] = useState<AppConfig | null>(null);
  const [setCookie, setSetCookie] = useState('');
  const [savedMsg, setSavedMsg] = useState('');

  const poller = useRef<ReturnType<typeof setInterval> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const notify = useCallback((message: string, type: ToastState['type'] = 'info') => {
    setToast({ id: Date.now(), message, type });
    setTimeout(() => setToast(null), 3200);
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const [cfg, cs, st, rs, ms] = await Promise.all([
        apiClient.getConfig(),
        apiClient.getCourses(),
        apiClient.getStatus(),
        apiClient.getResults(),
        apiClient.getModels().catch(() => null),
      ]);
      setConfig(cfg);
      setSetForm(cfg);
      setCourses(cs);
      setStatusData(st);
      setResults(rs);
      setModels(ms);
      if (cs.length > 0 && !runCourse) {
        setRunCourse(String(cs[0].id));
        setFormCourse(String(cs[0].id));
      }
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Gagal memuat data', 'error');
    }
  }, [notify, runCourse]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!running) return;
    poller.current = setInterval(async () => {
      try {
        const out = await apiClient.getRunOutput();
        const st = await apiClient.getRunStatus();
        setLines(out.output.slice(-500));
        setElapsed(Math.floor(st.elapsed));
        if (!out.running) {
          setRunning(false);
          setProgressText(out.returncode === 0 ? 'SELESAI' : 'GAGAL');
          if (poller.current) clearInterval(poller.current);
          const st2 = await apiClient.getStatus();
          setStatusData(st2);
          const rs = await apiClient.getResults();
          setResults(rs);
        }
      } catch {
        /* ignore */
      }
    }, 1000);
    return () => {
      if (poller.current) clearInterval(poller.current);
    };
  }, [running]);

  useEffect(() => {
    if (containerRef.current) containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [lines]);

  const startRun = async () => {
    if (!runCourse || !runSesi) {
      notify('Pilih mata kuliah dan isi sesi', 'error');
      return;
    }
    try {
      const res = await apiClient.startRun({
        course_id: (runCourse === 'all' ? ('all' as unknown as number) : Number(runCourse)),
        sesi: Number(runSesi),
        kind: runKind as 'all' | 'tugas' | 'diskusi',
      });
      if (!res.success) {
        notify(res.error || 'Gagal memulai', 'error');
        return;
      }
      setLines([]);
      setRunning(true);
      setProgressText('BERJALAN');
      notify('Proses dimulai', 'success');
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Gagal', 'error');
    }
  };

  const stopRun = async () => {
    const res = await apiClient.stopRun();
    notify(res.success ? 'Dihentikan' : res.error || 'Tidak ada proses', 'info');
  };

  const submitForm = async () => {
    if (!formCourse || !formSesi || !formText.trim()) {
      notify('Mata kuliah, sesi, dan teks soal wajib', 'error');
      return;
    }
    setFormSending(true);
    try {
      const res = await apiClient.submitSolve({
        course_id: Number(formCourse),
        sesi: Number(formSesi),
        kind: formKind,
        title: formTitle || config?.nama || '',
        soal_text: formText,
        file: formFile,
      });
      if (!res.success) notify(res.error || 'Gagal mengirim', 'error');
      else {
        notify('Soal dikirim ke agent', 'success');
        setFormText('');
        setFormTitle('');
        setFormFile(null);
      }
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Gagal', 'error');
    } finally {
      setFormSending(false);
    }
  };

  const saveSettings = async () => {
    if (!setForm) return;
    try {
      const payload: Record<string, unknown> = {
        nama: setForm.nama,
        nim: setForm.nim,
        prodi: setForm.prodi,
        semester: setForm.semester,
        ut_daerah: setForm.ut_daerah,
        moodle_url: setForm.base_url,
        opencode_model: setForm.model,
        opencode_model_transcribe: setForm.transcribe_model_configured ?? '',
      };
      if (setCookie.trim()) payload.moodle_session = setCookie.trim();
      const res = await apiClient.saveConfig(payload);
      if (res.success) {
        setSavedMsg('Tersimpan');
        notify('Pengaturan disimpan', 'success');
      } else notify(res.error || 'Gagal', 'error');
    } catch (e) {
      notify(e instanceof Error ? e.message : 'Gagal', 'error');
    }
  };

  const filtered = results
    .map((c) => ({
      ...c,
      files: c.files.filter((f) => f.name.toLowerCase().includes(search.toLowerCase())),
    }))
    .filter((c) => c.files.length > 0);

  return (
    <div className="bg-brandBg text-slate-700 font-sans min-h-screen md:h-screen flex flex-col md:overflow-hidden select-none">
      {/* Mobile nav: tombol di bawah layar */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 flex overflow-x-auto bg-sidebarBg border-t border-cardBorder text-xs font-semibold shadow-lg">
        {(['status', 'result', 'run', 'form', 'settings'] as TabId[]).map((id) => (
          <button key={id} onClick={() => setTab(id)} className={`flex-1 min-w-[64px] flex flex-col items-center gap-1 px-3 py-2.5 whitespace-nowrap ${tab === id ? 'text-amber-600 border-t-2 border-amber-500' : 'text-slate-500'}`}>
            <i className={`fa-solid ${id === 'status' ? 'fa-chart-pie' : id === 'result' ? 'fa-folder-open' : id === 'run' ? 'fa-play' : id === 'form' ? 'fa-file-pen' : 'fa-sliders'}`}></i>
            <span className="text-[10px]">{TITLES[id].replace(' Pekerjaan', '').replace(' Dokumen', '').replace(' Sistem', '')}</span>
          </button>
        ))}
      </nav>

      <div className="flex flex-1 overflow-hidden pb-[52px] md:pb-0">
        {/* Sidebar */}
        <aside className="hidden md:flex w-72 bg-sidebarBg border-r border-cardBorder flex-col justify-between shrink-0 shadow-sm z-20">
          <div>
            <div className="p-6 flex items-center space-x-3.5 border-b border-cardBorder">
              <div className="w-10 h-10 rounded-2xl bg-accentLight text-amber-600 flex items-center justify-center font-bold text-lg shadow-sm border border-accentPrimary/20">
                <i className="fa-solid fa-cube"></i>
              </div>
              <div>
                <h1 className="font-bold tracking-tight text-slate-900 text-base">Tuton Agent</h1>
                <span className="text-[10px] font-semibold text-amber-600 bg-accentLight px-2 py-0.5 rounded-full inline-block mt-0.5 uppercase tracking-wider">Light Web UI</span>
              </div>
            </div>
            <div className="p-4">
              <p className="px-3 text-[11px] font-semibold tracking-wider text-slate-400 uppercase mb-3">Main Menu</p>
              <nav className="space-y-1.5 font-medium text-sm">
                {(['status', 'result', 'run', 'form', 'settings'] as TabId[]).map((id) => (
                  <button key={id} onClick={() => setTab(id)} className={`w-full flex items-center space-x-3 px-4 py-3 rounded-2xl transition-all text-left ${tab === id ? 'bg-accentLight text-amber-600 font-semibold shadow-sm border border-accentPrimary/20' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}>
                    <i className={`fa-solid ${id === 'status' ? 'fa-chart-pie' : id === 'result' ? 'fa-folder-open' : id === 'run' ? 'fa-play' : id === 'form' ? 'fa-file-pen' : 'fa-sliders'} w-5 text-center`}></i>
                    <span>{TITLES[id]}</span>
                  </button>
                ))}
              </nav>
            </div>
          </div>
          <div className="p-4 border-t border-cardBorder">
            <div className="w-full bg-cardBg border border-cardBorder rounded-2xl p-3.5 flex items-center space-x-3 shadow-sm">
              <div className="w-9 h-9 rounded-2xl bg-amber-500 text-white font-bold text-xs flex items-center justify-center shrink-0 shadow-sm">AD</div>
              <div className="truncate">
                <p className="text-xs font-bold text-slate-900 truncate">{config?.nama || 'Moodle'}</p>
                <div className="flex items-center space-x-1.5 mt-0.5">
                  <span className={`w-2 h-2 rounded-full ${config?.has_session ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`}></span>
                  <span className={`text-[10px] font-medium uppercase tracking-wide ${config?.has_session ? 'text-emerald-600' : 'text-rose-600'}`}>{config?.has_session ? 'Terhubung' : 'Tidak ada sesi'}</span>
                </div>
              </div>
            </div>
          </div>
        </aside>

        <main className="flex-1 flex flex-col overflow-hidden">
          <header className="px-4 md:px-8 py-4 border-b border-cardBorder bg-sidebarBg flex items-center justify-between shrink-0 shadow-xs">
            <div>
              <p className="text-[10px] md:text-xs font-semibold text-amber-600 uppercase tracking-wider mb-0.5">Mission Control Center</p>
              <h2 className="text-lg md:text-2xl font-bold tracking-tight text-slate-900">{TITLES[tab]}</h2>
            </div>
            <div className="flex items-center space-x-3 text-sm">
              <span className="hidden sm:flex px-3.5 py-1.5 bg-cardBg border border-cardBorder text-slate-600 rounded-2xl font-medium text-xs items-center space-x-2 shadow-xs">
                <i className="fa-regular fa-clock text-amber-600"></i><span>{new Date().toTimeString().slice(0, 8)}</span>
              </span>
              <button onClick={() => { setTab('run'); }} className="px-3 md:px-4 py-2 md:py-2.5 bg-amber-500 hover:bg-amber-600 text-white font-bold rounded-2xl transition shadow-md shadow-amber-500/20 flex items-center space-x-2 text-xs">
                <i className="fa-solid fa-bolt"></i><span>Quick Run</span>
              </button>
            </div>
          </header>

          <div className="flex-1 overflow-y-auto p-4 md:p-8 relative">
            {/* RUN */}
            {tab === 'run' && (
              <section className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-5 bg-cardBg border border-cardBorder rounded-3xl p-6 flex flex-col justify-between shadow-sm">
                  <div className="space-y-5">
                    <div className="flex items-center space-x-2.5 border-b border-cardBorder pb-3">
                      <i className="fa-solid fa-sliders text-amber-600 text-base"></i>
                      <h3 className="font-bold text-base text-slate-900 tracking-wide">Parameter Eksekusi</h3>
                    </div>
                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Mata Kuliah</label>
                      <select value={runCourse} onChange={(e) => setRunCourse(e.target.value)} className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3 text-sm text-slate-800 appearance-none focus:outline-none focus:border-amber-500 shadow-inner">
                        <option value="">Pilih mata kuliah...</option>
                        <option value="all">Semua Mata Kuliah</option>
                        {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </div>
                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Sesi</label>
                      <input type="number" value={runSesi} onChange={(e) => setRunSesi(e.target.value)} placeholder="Contoh: 3" className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3 text-sm text-slate-800 focus:outline-none focus:border-amber-500 shadow-inner" />
                    </div>
                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Jenis Pekerjaan</label>
                      <select value={runKind} onChange={(e) => setRunKind(e.target.value)} className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3 text-sm text-slate-800 appearance-none focus:outline-none focus:border-amber-500 shadow-inner">
                        <option value="all">Tugas &amp; Diskusi</option>
                        <option value="diskusi">Diskusi Saja</option>
                        <option value="tugas">Tugas Saja</option>
                      </select>
                    </div>
                  </div>
                  <div className="pt-6">
                    <button onClick={startRun} disabled={running} className="w-full py-4 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white font-bold rounded-2xl transition shadow-md shadow-amber-500/20 flex items-center justify-center space-x-2 text-sm tracking-wide">
                      <i className={`fa-solid ${running ? 'fa-spinner animate-spin' : 'fa-play'}`}></i>
                      <span>{running ? 'Sedang Berjalan...' : 'Jalankan Sekarang'}</span>
                    </button>
                  </div>
                </div>

                <div className="lg:col-span-7 bg-terminalBg border border-slate-800 rounded-3xl flex flex-col shadow-xl overflow-hidden font-mono text-xs text-slate-200 min-h-[420px]">
                  <div className="bg-slate-900 px-5 py-3.5 border-b border-slate-800 flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className="w-3 h-3 rounded-full bg-rose-500 inline-block"></span>
                      <span className="w-3 h-3 rounded-full bg-amber-400 inline-block"></span>
                      <span className="w-3 h-3 rounded-full bg-emerald-400 inline-block"></span>
                      <span className="text-slate-200 ml-3 text-xs font-bold tracking-wide">TERMINAL</span>
                    </div>
                    <div className="flex items-center space-x-4 text-xs">
                      <span className="text-slate-400">{elapsed}s</span>
                      <button onClick={stopRun} className="text-slate-400 hover:text-rose-400 transition flex items-center space-x-1"><i className="fa-solid fa-stop"></i><span className="hidden sm:inline">STOP</span></button>
                      <button onClick={() => setLines([])} className="text-slate-400 hover:text-amber-400 transition flex items-center space-x-1"><i className="fa-solid fa-trash-can"></i><span className="hidden sm:inline">CLEAR</span></button>
                    </div>
                  </div>
                  <div className="px-5 py-3 bg-slate-900/50 border-b border-slate-800 space-y-2">
                    <div className="flex justify-between text-xs text-slate-400">
                      <span className="font-semibold text-terminalGreen">{progressText}</span>
                      <span>{elapsed}s</span>
                    </div>
                    <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800">
                      <div className={`bg-amber-500 h-full transition-all duration-300 ${running ? 'w-2/3 animate-pulse' : progressText === 'SELESAI' ? 'w-full' : 'w-0'}`}></div>
                    </div>
                  </div>
                  <div ref={containerRef} className="flex-1 p-5 overflow-y-auto space-y-1.5 text-slate-300 text-[11px] leading-relaxed">
                    {lines.length === 0 ? <p className="text-slate-500">[siap] Pilih mata kuliah dan sesi, lalu Jalankan Sekarang.</p> : lines.map((l, i) => <p key={i} className={l.startsWith('[OK]') || /berhasil|SELESAI/i.test(l) ? 'text-terminalGreen' : 'text-slate-300'}>{l}</p>)}
                  </div>
                </div>
              </section>
            )}

            {/* STATUS */}
            {tab === 'status' && (
              <section className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xl font-bold text-slate-900">Status Pekerjaan</h3>
                    <p className="text-xs text-slate-500">Monitor pekerjaan agent secara real-time.</p>
                  </div>
                  <button onClick={loadAll} className="px-4 py-2 bg-cardBg border border-cardBorder hover:bg-slate-100 text-xs font-semibold rounded-2xl transition flex items-center space-x-2 text-slate-700 shadow-xs">
                    <i className="fa-solid fa-rotate mr-1 text-amber-600"></i> Refresh
                  </button>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { label: 'Selesai', value: statusData?.stats.done ?? 0, color: 'text-emerald-600' },
                    { label: 'Pending', value: statusData?.stats.pending ?? 0, color: 'text-amber-600' },
                    { label: 'Gagal', value: statusData?.stats.failed ?? 0, color: 'text-rose-500' },
                    { label: 'Total', value: statusData?.stats.total ?? 0, color: 'text-slate-900' },
                  ].map((s) => (
                    <div key={s.label} className="bg-cardBg border border-cardBorder rounded-3xl p-6 shadow-sm">
                      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{s.label}</p>
                      <h4 className={`text-3xl font-bold mt-2 ${s.color}`}>{s.value}</h4>
                    </div>
                  ))}
                </div>
                <div className="bg-cardBg border border-cardBorder rounded-3xl overflow-hidden shadow-sm">
                  <div className="p-5 border-b border-cardBorder font-bold text-slate-900 text-sm">Riwayat</div>
                  <div className="divide-y divide-cardBorder text-sm">
                    {(!statusData || statusData.items.length === 0) && <p className="p-5 text-xs text-slate-400">Belum ada riwayat.</p>}
                    {statusData?.items.map((it) => (
                      <div key={it.key} className="p-5 flex items-center justify-between hover:bg-slate-50 transition">
                        <div className="flex items-center space-x-3.5">
                          <span className={`w-3 h-3 rounded-full ${it.status === 'done' ? 'bg-emerald-500' : it.status === 'failed' ? 'bg-rose-500' : 'bg-amber-400 animate-pulse'}`}></span>
                          <div>
                            <p className="font-bold text-slate-900">{it.matkul} - Sesi {it.sesi ?? '-'}</p>
                            <p className="text-xs text-slate-500 mt-0.5">{it.created_at}{it.duration_sec ? ` • ${it.duration_sec}s` : ''}</p>
                          </div>
                        </div>
                        <span className={`px-3 py-1 font-semibold rounded-full text-xs border uppercase ${it.status === 'done' ? 'bg-emerald-50 text-emerald-600 border-emerald-200' : it.status === 'failed' ? 'bg-rose-50 text-rose-600 border-rose-200' : 'bg-amber-50 text-amber-600 border-amber-200'}`}>{it.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            )}

            {/* RESULT */}
            {tab === 'result' && (
              <section className="space-y-6">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h3 className="text-xl font-bold text-slate-900">Hasil Dokumen per Mata Kuliah</h3>
                    <p className="text-xs text-slate-500">Kelola file jawaban: preview, unduh, atau hapus.</p>
                  </div>
                  <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cari file dokumen..." className="bg-cardBg border border-cardBorder rounded-2xl px-4 py-2.5 text-xs text-slate-800 focus:outline-none focus:border-amber-500 shadow-inner w-full md:w-64" />
                </div>
                <div className="space-y-6">
                  {filtered.length === 0 && <p className="text-xs text-slate-400">Belum ada dokumen.</p>}
                  {filtered.map((course) => (
                    <div key={course.name} className="bg-cardBg border border-cardBorder rounded-3xl p-6 shadow-sm space-y-4">
                      <div className="flex items-center justify-between border-b border-cardBorder pb-4">
                        <div>
                          <h4 className="font-bold text-slate-900 text-base">{course.name}</h4>
                          <span className="text-xs text-slate-500">{course.files.length} file • {course.folder || ''}</span>
                        </div>
                        {course.folder && (
                          <button onClick={async () => { if (confirm('Hapus folder?')) { await apiClient.deleteCourse(course.folder!); loadAll(); } }} className="px-4 py-2 bg-rose-50 hover:bg-rose-100 text-rose-600 border border-rose-200 text-xs font-semibold rounded-2xl transition">Hapus Mata Kuliah</button>
                        )}
                      </div>
                      <div className="space-y-3">
                        {course.files.map((f) => (
                          <div key={f.path} className="bg-slate-50 border border-cardBorder rounded-2xl p-4 flex items-center justify-between hover:border-amber-400 transition">
                            <div className="flex items-center space-x-3.5 overflow-hidden">
                              <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center text-base border border-blue-200"><i className="fa-solid fa-file-word"></i></div>
                              <div className="overflow-hidden">
                                <h5 className="text-sm font-bold text-slate-900 truncate">{f.name}</h5>
                                <p className="text-xs text-slate-400">{(f.size / 1024).toFixed(1)} KB{f.sesi ? ` • Sesi ${f.sesi}` : ''}{f.finished_at ? ` • ${f.finished_at}` : ''}</p>
                              </div>
                            </div>
                            <div className="flex items-center space-x-2">
                              <button onClick={() => setPreviewPath(f.path)} title="Preview" className="p-2.5 bg-white border border-cardBorder hover:bg-slate-100 text-slate-600 rounded-xl transition shadow-xs"><i className="fa-solid fa-eye text-xs"></i></button>
                              <button onClick={() => apiClient.download(f.path)} title="Download" className="p-2.5 bg-white border border-cardBorder hover:bg-amber-500 hover:text-white text-slate-600 rounded-xl transition shadow-xs"><i className="fa-solid fa-download text-xs"></i></button>
                              <button onClick={async () => { if (confirm('Hapus file?')) { await apiClient.deleteResult(f.path); loadAll(); } }} title="Hapus" className="p-2.5 bg-white border border-cardBorder hover:bg-rose-500 hover:text-white text-slate-400 rounded-xl transition shadow-xs"><i className="fa-solid fa-trash text-xs"></i></button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* FORM */}
            {tab === 'form' && (
              <section className="space-y-6 max-w-4xl mx-auto">
                <div className="border-b border-cardBorder pb-4">
                  <h3 className="text-xl font-bold text-slate-900">Kerjakan Soal</h3>
                  <p className="text-xs text-slate-500 mt-1">Masukkan soal sendiri (teks atau file) untuk dikerjakan agent.</p>
                </div>
                <div className="bg-cardBg border border-cardBorder rounded-3xl p-6 md:p-8 space-y-6 shadow-sm text-sm">
                  <div className="space-y-1.5">
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Mata Kuliah</label>
                    <select value={formCourse} onChange={(e) => setFormCourse(e.target.value)} className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3 text-slate-800 focus:outline-none focus:border-amber-500 shadow-inner">
                      <option value="">Pilih...</option>
                      {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Sesi</label>
                      <input type="number" value={formSesi} onChange={(e) => setFormSesi(e.target.value)} placeholder="Contoh: 3" className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3 text-slate-800 focus:outline-none focus:border-amber-500 shadow-inner" />
                    </div>
                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Jenis Pekerjaan</label>
                      <select value={formKind} onChange={(e) => setFormKind(e.target.value as 'tugas' | 'diskusi')} className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3 text-slate-800 focus:outline-none focus:border-amber-500 shadow-inner">
                        <option value="tugas">Tugas</option>
                        <option value="diskusi">Diskusi</option>
                      </select>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Judul Aktivitas (Opsional)</label>
                    <input value={formTitle} onChange={(e) => setFormTitle(e.target.value)} placeholder="Contoh: Diskusi 1 / Tugas 2" className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3 text-slate-800 focus:outline-none focus:border-amber-500 shadow-inner" />
                  </div>
                  <div className="space-y-1.5">
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Soal (Teks)</label>
                    <textarea rows={4} value={formText} onChange={(e) => setFormText(e.target.value)} placeholder="Tulis soal..." className="w-full bg-slate-50 border border-cardBorder rounded-2xl p-4 text-slate-800 focus:outline-none focus:border-amber-500 leading-relaxed shadow-inner" />
                  </div>
                  <div className="space-y-1.5">
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Unggah File Soal</label>
                    <div className="border-2 border-dashed border-cardBorder hover:border-amber-500 rounded-3xl p-6 text-center cursor-pointer bg-slate-50 transition" onClick={() => document.getElementById('dash-form-file')?.click()}>
                      <input id="dash-form-file" type="file" className="hidden" onChange={(e) => setFormFile(e.target.files?.[0] ?? null)} />
                      <i className="fa-solid fa-cloud-arrow-up text-2xl text-amber-500 mb-2"></i>
                      <p className="text-xs font-bold text-slate-800">KLIK UNTUK MEMILIH FILE</p>
                      {formFile && <div className="mt-3 text-xs text-emerald-600 font-medium">{formFile.name}</div>}
                    </div>
                  </div>
                  <div className="pt-4">
                    <button onClick={submitForm} disabled={formSending} className="w-full py-4 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white font-bold rounded-2xl transition shadow-md shadow-amber-500/20 flex items-center justify-center space-x-2 text-sm tracking-wide">
                      <i className="fa-solid fa-bolt"></i><span>{formSending ? 'Mengirim...' : 'Kerjakan Soal Sekarang'}</span>
                    </button>
                  </div>
                </div>
              </section>
            )}

            {/* SETTINGS */}
            {tab === 'settings' && (
              <section className="space-y-6 max-w-4xl mx-auto">
                <div className="border-b border-cardBorder pb-4">
                  <h3 className="text-xl font-bold text-slate-900">Control Room — Settings</h3>
                  <p className="text-xs text-slate-500 mt-1">Atur identitas mahasiswa, sesi Moodle, dan model OpenCode.</p>
                </div>
                <div className="bg-cardBg border border-cardBorder rounded-3xl p-6 md:p-8 space-y-8 shadow-sm text-sm">
                  {setForm && (
                    <>
                      <div className="space-y-4">
                        <h4 className="font-bold text-slate-900 border-b border-cardBorder pb-2">Data Mahasiswa</h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <input value={setForm.nama} onChange={(e) => setSetForm({ ...setForm, nama: e.target.value })} placeholder="Nama Lengkap" className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3" />
                          <input value={setForm.nim} onChange={(e) => setSetForm({ ...setForm, nim: e.target.value })} placeholder="NIM" className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3" />
                          <input value={setForm.prodi} onChange={(e) => setSetForm({ ...setForm, prodi: e.target.value })} placeholder="Prodi" className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3" />
                          <input value={setForm.semester} onChange={(e) => setSetForm({ ...setForm, semester: e.target.value })} placeholder="Semester" className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3" />
                        </div>
                        <input value={setForm.ut_daerah} onChange={(e) => setSetForm({ ...setForm, ut_daerah: e.target.value })} placeholder="UT Daerah" className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3" />
                      </div>
                      <div className="space-y-4">
                        <h4 className="font-bold text-slate-900 border-b border-cardBorder pb-2">Kredensial Moodle</h4>
                        <input value={setCookie} onChange={(e) => setSetCookie(e.target.value)} type="password" placeholder="MoodleSession=..." className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3" />
                        <input value={setForm.base_url} onChange={(e) => setSetForm({ ...setForm, base_url: e.target.value })} placeholder="https://elearning.ut.ac.id" className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3" />
                      </div>
                      <div className="space-y-4">
                        <h4 className="font-bold text-slate-900 border-b border-cardBorder pb-2">Model Configuration</h4>
                        <div className="space-y-1.5">
                          <label className="block text-xs font-semibold text-slate-500 uppercase">Model OpenCode (Utama)</label>
                          <select value={setForm.model} onChange={(e) => setSetForm({ ...setForm, model: e.target.value })} className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3">
                            <option value={setForm.model}>{setForm.model}</option>
                            {models?.groups?.map((g) => (
                              <optgroup key={g.provider} label={g.provider}>
                                {g.models.map((m) => <option key={m.id} value={m.id}>{m.id}</option>)}
                              </optgroup>
                            ))}
                          </select>
                        </div>
                        <div className="space-y-1.5">
                          <label className="block text-xs font-semibold text-slate-500 uppercase">Model Vision (Transkripsi Lampiran)</label>
                          <select value={setForm.transcribe_model_configured ?? ''} onChange={(e) => setSetForm({ ...setForm, transcribe_model_configured: e.target.value })} className="w-full bg-slate-50 border border-cardBorder rounded-2xl px-4 py-3">
                            <option value="">Pilih otomatis (vision)</option>
                            {models?.groups?.map((g) => (
                              <optgroup key={g.provider} label={g.provider}>
                                {g.models.map((m) => <option key={m.id} value={m.id}>{m.id}</option>)}
                              </optgroup>
                            ))}
                          </select>
                        </div>
                      </div>
                      <div className="flex justify-end pt-4 space-x-3">
                        <button onClick={() => { window.localStorage.removeItem('tuton_logged_in'); window.location.reload(); }} className="px-6 py-3.5 bg-rose-50 hover:bg-rose-100 text-rose-600 border border-rose-200 font-bold rounded-2xl transition text-sm tracking-wide flex items-center space-x-2">
                          <i className="fa-solid fa-arrow-right-from-bracket"></i><span>Keluar</span>
                        </button>
                        <button onClick={saveSettings} className="px-6 py-3.5 bg-amber-500 hover:bg-amber-600 text-white font-bold rounded-2xl transition shadow-md shadow-amber-500/20 flex items-center space-x-2 text-sm tracking-wide">
                          <i className="fa-solid fa-floppy-disk"></i><span>Simpan Settings</span>
                        </button>
                      </div>
                      {savedMsg && <p className="text-xs text-emerald-600 text-right">{savedMsg}</p>}
                    </>
                  )}
                </div>
              </section>
            )}
          </div>
        </main>
      </div>

      {/* Preview Modal */}
      {previewPath && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-center justify-center p-4" onClick={() => setPreviewPath(null)}>
          <div className="bg-cardBg border border-cardBorder w-full max-w-4xl rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]" onClick={(e) => e.stopPropagation()}>
            <div className="px-6 py-4 bg-slate-100 border-b border-cardBorder flex items-center justify-between">
              <h4 className="font-bold text-slate-900 text-sm">{previewPath.split('/').pop()}</h4>
              <button onClick={() => setPreviewPath(null)} className="text-slate-400 hover:text-slate-700 p-2 rounded-2xl hover:bg-slate-200 transition"><i className="fa-solid fa-xmark text-base"></i></button>
            </div>
            <iframe src={`/api/preview/${encodeURI(previewPath)}`} className="flex-1 min-h-[60vh] bg-white" />
          </div>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 bg-slate-900 border border-slate-800 text-white px-5 py-3.5 rounded-2xl shadow-xl flex items-center space-x-3 z-50 text-xs font-medium">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></div>
          <span>{toast.message}</span>
        </div>
      )}
    </div>
  );
}
