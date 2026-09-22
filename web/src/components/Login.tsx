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
    <main className="relative flex min-h-[100dvh] items-center justify-center overflow-hidden bg-primary px-4 py-10">
      <div className="pixel-world" aria-hidden="true" />
      <div className="relative z-10 w-full max-w-md">
        <div className="pixel-panel-strong px-6 py-8 sm:px-9 sm:py-10">
          <div className="mb-8 text-center">
            <div className="pixel-logo-large mx-auto mb-5" aria-hidden="true">
              <Cpu size={34} strokeWidth={2.4} />
            </div>
            <h1 className="font-display text-xl leading-snug text-text sm:text-2xl">Tuton Agent</h1>
            <p className="mt-2 font-terminal text-[10px] uppercase tracking-[0.16em] text-accent">
              Auto-Grader &amp; Submission Controller
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="username" className="pixel-label">Username Moodle / Admin</label>
              <div className="relative">
                <User className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" size={17} aria-hidden="true" />
                <input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="Masukkan username"
                  className="pixel-input pixel-input-icon w-full"
                  disabled={isLoading}
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="pixel-label">Kata Sandi</label>
              <div className="relative">
                <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" size={17} aria-hidden="true" />
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Masukkan kata sandi"
                  className="pixel-input pixel-input-icon w-full"
                  disabled={isLoading}
                />
              </div>
            </div>

            {error && (
              <div className="pixel-alert pixel-alert-error" role="alert">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="pixel-button pixel-button-primary w-full justify-center"
            >
              {isLoading ? (
                <>
                  <LoaderCircle className="animate-spin" size={18} aria-hidden="true" />
                  <span>Memverifikasi...</span>
                </>
              ) : (
                <>
                  <span>Akses Sistem</span>
                  <ArrowRight size={18} aria-hidden="true" />
                </>
              )}
            </button>
          </form>

          <div className="mt-7 border-t-2 border-border pt-4 text-center">
            <p className="font-terminal text-[9px] uppercase tracking-[0.14em] text-muted">Secure local controller</p>
          </div>
        </div>
      </div>
    </main>
  );
}
