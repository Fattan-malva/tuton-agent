// Status Component - Displays current project status
// Part of the 5 required view components

import React from 'react';
import { store } from './store';

const Status = () => {
  const { status, results } = store.getState();

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-white">Status Pekerjaan</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {status.map(item => (
          <div key={item.id} className="p-4 bg-surface/50 rounded-xl border border-white/10">
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <h3 className="font-semibold text-white">{item.title}</h3>
                <p className="text-sm text-gray-400">{item.description}</p>
              </div>
              <div className="text-sm">
                Status: <span className={`${item.status === 'completed' ? 'text-green-400' : item.status === 'in-progress' ? 'text-yellow-400' : 'text-gray-400'}`}>{item.status}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6">
        <h3 className="text-lg font-bold text-white mb-3">Results</h3>
        {results.length > 0 ? (
          <ul className="space-y-2">
            {results.map(r => (
              <li key={r.id} className="p-3 bg-surface/50 rounded-xl border border-white/10">
                <strong className="text-white">{r.title}</strong>
                <p className="text-sm text-gray-300">{r.outcome}</p>
                <time className="text-xs text-gray-500 mt-1">{r.timestamp}</time>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-gray-500 text-sm">No results yet.</p>
        )}
      </div>
    </div>
  );
};

export default Status;
