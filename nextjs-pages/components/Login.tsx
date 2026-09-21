// Login Component - Tuton Agent Frontend
// Handles authentication and dashboard access

import React, { useState, useEffect } from 'react';
import { store } from './store';

const Login = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [currentUser, setCurrentUser] = useState(null);

  const handleLogin = async (email: string, password: string) => {
    setIsLoading(true);
    setError('');
    try {
      // In a real implementation, this would call the auth endpoint
      // For now, simulate a successful login
      const user = { id: 1, email, role: 'admin' };
      store.setSetting('current_user', user);
      setCurrentUser(user);
      setIsLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
      setIsLoading(false);
    }
  };

  const handleLogout = () => {
    store.setState({ current_user: null });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface/80">
      <div className="card p-6 rounded-xl shadow-lg">
        <h1 className="text-2xl font-bold text-white mb-4">Tuton Agent</h1>
        {currentUser ? (
          <div className="mb-4">
            <p className="text-gray-300">Welcome, {currentUser.email}</p>
            <p className="text-gray-400">Role: {currentUser.role}</p>
          </div>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); handleLogin(e.currentTarget.email, e.currentTarget.password); }}>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300">Email</label>
                <input
                  type="email"
                  required
                  className="w-full px-3 py-2 bg-surface/50 border border-white/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent"
                  placeholder="your@example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300">Password</label>
                <input
                  type="password"
                  required
                  className="w-full px-3 py-2 bg-surface/50 border border-white/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent"
                  placeholder="••••••••"
                />
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="btn btn-primary w-full py-2 rounded-lg text-sm"
              >
                {isLoading ? 'Logging in...' : 'Login'}
              </button>
            </div>
          </form>
        )}
        <div className="mt-6 text-center">
          <p className="text-sm text-gray-500">No account? Sign up to get started</p>
        </div>
      </div>
    </div>
  );
};

export default Login;
