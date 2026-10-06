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

  if (!isLoggedIn) {
    return <Login onAuthenticated={handleAuthenticated} />;
  }

  return <Dashboard />;
}
