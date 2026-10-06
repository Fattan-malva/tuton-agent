import { ArrowRight, Cpu, LockKeyhole, LoaderCircle, User } from 'lucide-react';
import { useState } from 'react';
import type { AppConfig } from '../lib/types';
import apiClient from '../lib/api-client';

interface LoginProps {
  onAuthenticated: (config: AppConfig) => Promise<void>;
}

export default function Login({ onAuthenticated }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');

    const cleanUsername = username.trim();
    const cleanPassword = password.trim();

    if (!cleanUsername || !cleanPassword) {
      setError('Username dan kata sandi wajib diisi.');
      return;
    }

    setIsLoading(true);

    try {
      const response = await apiClient.login(cleanUsername, cleanPassword);

      if (!response.success) {
        setError(response.error || 'Login gagal.');
        return;
      }

      const config = await apiClient.getConfig();
      await onAuthenticated(config);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Login gagal.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="relative flex min-h-[100dvh] items-center justify-center overflow-hidden bg-brandBg px-4 py-10">
      <div className="relative z-10 w-full max-w-md">
        <div className="bg-cardBg border border-cardBorder rounded-3xl px-6 py-8 sm:px-9 sm:py-10 shadow-lg">
          <div className="mb-8 text-center">
            <div className="w-12 h-12 rounded-2xl bg-accentLight text-amber-600 flex items-center justify-center font-bold text-xl mx-auto mb-4 border border-accentPrimary/20">
              <Cpu size={26} />
            </div>
            <h1 className="font-bold text-xl text-slate-900">Tuton Agent</h1>
            <p className="mt-2 text-xs font-semibold text-amber-600 uppercase tracking-wider">Auto-Grader &amp; Submission Controller</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="username" className="block text-xs font-semibold text-slate-500 uppercase">Username</label>
              <div className="relative mt-1">
                <User className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Masukkan username"
                  className="w-full bg-slate-50 border border-cardBorder rounded-2xl pl-10 pr-4 py-3 text-slate-800 focus:outline-none focus:border-amber-500 shadow-inner"
                  disabled={isLoading}
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-semibold text-slate-500 uppercase">Kata Sandi</label>
              <div className="relative mt-1">
                <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Masukkan kata sandi"
                  className="w-full bg-slate-50 border border-cardBorder rounded-2xl pl-10 pr-4 py-3 text-slate-800 focus:outline-none focus:border-amber-500 shadow-inner"
                  disabled={isLoading}
                />
              </div>
            </div>

            {error && <div className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded-2xl px-4 py-3">{error}</div>}

            <button type="submit" disabled={isLoading} className="w-full py-3.5 bg-amber-500 hover:bg-amber-600 text-white font-bold rounded-2xl transition shadow-md shadow-amber-500/20 flex items-center justify-center space-x-2">
              {isLoading ? (<><LoaderCircle className="animate-spin" size={18} /><span>Memverifikasi...</span></>) : (<><span>Akses Sistem</span><ArrowRight size={18} /></>)}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
