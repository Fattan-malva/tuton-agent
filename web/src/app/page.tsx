'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import FormSoal from '../components/FormSoal';
import Login from '../components/Login';
import Navigation from '../components/Navigation';
import Results from '../components/Results';
import Run from '../components/Run';
import Settings from '../components/Settings';
import Status from '../components/Status';
import { useTerminalMonitor } from '../hooks/useTerminalMonitor';
import apiClient from '../lib/api-client';
import type {
  AppConfig,
  Course,
  ResultCourse,
  StatusResponse,
  Tab,
  ToastMessage,
  ToastType,
} from '../lib/types';

const emptyStatus: StatusResponse = {
  success: true,
  stats: { done: 0, failed: 0, pending: 0, total: 0 },
  items: [],
};

export default function Home() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('status');
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [statusData, setStatusData] = useState<StatusResponse>(emptyStatus);
  const [results, setResults] = useState<ResultCourse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [command, setCommand] = useState('');
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stopRequestedRef = useRef(false);

  const notify = useCallback((message: string, type: ToastType = 'info') => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ id: Date.now(), message, type });
    toastTimer.current = setTimeout(() => setToast(null), 3200);
  }, []);

  useEffect(() => {
    setIsLoggedIn(window.localStorage.getItem('tuton_logged_in') === 'true');
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      setStatusData(await apiClient.getStatus());
    } catch (caught) {
      notify(caught instanceof Error ? caught.message : 'Gagal memuat status.', 'error');
    }
  }, [notify]);

  const loadResults = useCallback(async () => {
    try {
      setResults(await apiClient.getResults());
    } catch (caught) {
      notify(caught instanceof Error ? caught.message : 'Gagal memuat hasil.', 'error');
    }
  }, [notify]);

  const loadCourses = useCallback(async () => {
    try {
      setCourses(await apiClient.getCourses());
    } catch (caught) {
      setCourses([]);
      notify(caught instanceof Error ? caught.message : 'Gagal memuat mata kuliah.', 'error');
    }
  }, [notify]);

  const refreshAll = useCallback(async () => {
    setIsLoading(true);
    await Promise.allSettled([loadStatus(), loadResults(), loadCourses()]);
    setIsLoading(false);
  }, [loadCourses, loadResults, loadStatus]);

  useEffect(() => {
    if (isLoggedIn) void refreshAll();
  }, [isLoggedIn, refreshAll]);

  const handleTerminalComplete = useCallback(
    async (returncode: number) => {
      const wasStopped = stopRequestedRef.current;
      stopRequestedRef.current = false;
      await refreshAll();
      if (wasStopped) {
        notify('Proses dihentikan oleh pengguna.', 'warning');
      } else if (returncode !== 0) {
        notify(`Proses selesai dengan error (exit ${returncode}).`, 'error');
      } else {
        notify('Proses selesai dieksekusi.', 'success');
      }
    },
    [notify, refreshAll],
  );

  // Terminal dipantau di level aplikasi: polling tetap jalan saat user
  // berpindah menu, sehingga proses run agent / form soal tidak "hilang".
  const { output, snapshot, reset } = useTerminalMonitor(true, handleTerminalComplete);

  const clearTerminal = useCallback(() => {
    reset();
    setCommand('');
  }, [reset]);

  const handleAuthenticated = useCallback(
    async (nextConfig: AppConfig) => {
      setConfig(nextConfig);
      setIsLoggedIn(true);
      setActiveTab('status');
      window.localStorage.setItem('tuton_logged_in', 'true');
      notify(
        nextConfig.has_session ? 'Berhasil login ke sistem.' : 'Login berhasil. Session Moodle belum dikonfigurasi.',
        nextConfig.has_session ? 'success' : 'warning',
      );
      await refreshAll();
    },
    [notify, refreshAll],
  );

  const handleLogout = useCallback(() => {
    window.localStorage.removeItem('tuton_logged_in');
    setIsLoggedIn(false);
    setActiveTab('status');
    notify('Sesi diakhiri.', 'info');
  }, [notify]);

  const switchTab = useCallback(
    (tab: Tab) => {
      setActiveTab(tab);
      if (tab === 'status') void loadStatus();
      if (tab === 'results') void loadResults();
      if (tab === 'run' || tab === 'soal') void loadCourses();
    },
    [loadCourses, loadResults, loadStatus],
  );

  const handleSettingsSaved = useCallback(async () => {
    try {
      setConfig(await apiClient.getConfig());
    } catch (caught) {
      notify(caught instanceof Error ? caught.message : 'Gagal memuat konfigurasi terbaru.', 'error');
    }
  }, [notify]);

  if (!isLoggedIn) {
    return <Login onAuthenticated={handleAuthenticated} />;
  }

  const terminalController = {
    output,
    snapshot,
    command,
    setCommand,
    reset,
    onStopRequested: () => {
      stopRequestedRef.current = true;
    },
    onClearTerminal: clearTerminal,
  };

  return (
    <div className="relative min-h-[100dvh] bg-primary text-text">
      <div className="pixel-world" aria-hidden="true" />
      <Navigation activeTab={activeTab} onSwitch={switchTab} onLogout={handleLogout} />

      <main className="relative z-10 min-h-[100dvh] md:pl-72">
        <div className="mx-auto max-w-[1400px] px-4 pb-28 pt-6 sm:px-6 md:px-8 md:pb-10 md:pt-8">
          {activeTab === 'status' && (
            <Status stats={statusData.stats} items={statusData.items} loading={isLoading} onRefresh={() => void loadStatus()} />
          )}
          {activeTab === 'results' && (
            <Results courses={results} loading={isLoading} onRefresh={() => void loadResults()} onNotify={notify} />
          )}
          {activeTab === 'run' && (
            <Run
              courses={courses}
              onRefresh={refreshAll}
              onNotify={notify}
              terminal={terminalController}
            />
          )}
          {activeTab === 'soal' && (
            <FormSoal
              courses={courses}
              onRefresh={refreshAll}
              onNotify={notify}
              terminal={terminalController}
            />
          )}
          {activeTab === 'settings' && (
            <Settings config={config} onSaved={handleSettingsSaved} onNotify={notify} />
          )}
        </div>
      </main>

      {toast && (
        <div className={`pixel-toast pixel-toast-${toast.type}`} role="status">
          <span className="pixel-toast-marker" aria-hidden="true" />
          <span>{toast.message}</span>
        </div>
      )}
    </div>
  );
}