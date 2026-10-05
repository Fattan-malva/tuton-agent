'use client';

import { useCallback, useEffect, useState } from 'react';
import Dashboard from '../components/Dashboard';
import Login from '../components/Login';
import type { AppConfig } from '../lib/types';

export default function Home() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    setIsLoggedIn(window.localStorage.getItem('tuton_logged_in') === 'true');
  }, []);

  const handleAuthenticated = useCallback(async (_config: AppConfig) => {
    window.localStorage.setItem('tuton_logged_in', 'true');
    setIsLoggedIn(true);
  }, []);

  const handleLogout = useCallback(() => {
    window.localStorage.removeItem('tuton_logged_in');
    setIsLoggedIn(false);
  }, []);

  if (!isLoggedIn) {
    return <Login onAuthenticated={handleAuthenticated} />;
  }

  return (
    <div className="relative">
      <Dashboard />
      <button onClick={handleLogout} title="Keluar" className="fixed top-3 right-3 z-40 text-slate-400 hover:text-rose-500 text-xs bg-white/80 rounded-full p-2 border border-slate-200">
        <i className="fa-solid fa-arrow-right-from-bracket"></i>
      </button>
    </div>
  );
}
