// Settings Component - Configuration panel for Tuton Agent
// Part of the 5 required view components

import React, { useState, useEffect } from 'react';
import { store } from './store';

const Settings = () => {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [themePreference, setThemePreference] = useState('dark');

  const handleSave = () => {
    store.setState({ theme: themePreference });
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-white">Settings</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-3">
          <label className="text-sm font-medium text-gray-300">Theme</label>
          <select
            value={themePreference}
            onChange={(e) => setThemePreference(e.target.value)}
            className="w-full px-3 py-2 bg-surface/50 border border-white/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <option value="dark">Dark (Pixel Cozy)</option>
            <option value="light">Light</option>
          </select>
        </div>

        <div className="space-y-3">
          <label className="text-sm font-medium text-gray-300">Notification Pref</label>
          <select
            value={showAdvanced ? 'true' : 'false'}
            onChange={(e) => setShowAdvanced(e.target.value === 'true' ? 'true' : 'false')}
            className="w-full px-3 py-2 bg-surface/50 border border-white/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <option value="true">Enable notifications</option>
            <option value="false">Disable notifications</option>
          </select>
        </div>
      </div>

      <div className="mt-6">
        <h3 className="text-lg font-bold text-white mb-3">Configuration</h3>
        <div className="space-y-3">
          <div className="p-4 bg-surface/50 rounded-xl border border-white/10">
            <h4 className="text-sm font-semibold text-gray-300 mb-2">Agent Settings</h4>
            <p className="text-sm text-gray-400">
              Adjust global agent behavior and performance settings.
            </p>
          </div>
          <div className="p-4 bg-surface/50 rounded-xl border border-white/10">
            <h4 className="text-sm font-semibold text-gray-300 mb-2">Database</h4>
            <p className="text-sm text-gray-400">
              Configure storage and persistence for agent state.
            </p>
          </div>
          <div className="p-4 bg-surface/50 rounded-xl border border-white/10">
            <h4 className="text-sm font-semibold text-gray-300 mb-2">API Keys</h4>
            <p className="text-sm text-gray-400">
              Manage authentication credentials securely.
            </p>
          </div>
        </div>

        <div className="pt-4 border-t border-white/5">
          <button
            onClick={handleSave}
            className="btn btn-success w-full py-2 rounded-lg text-sm"
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
};

export default Settings;
