// Result Component - Displays project results
// Part of the 5 required view components

import React from 'react';
import { store } from './store';

const Results = () => {
  const { results, addResult } = store;

  const handleAddResult = () => {
    const newResult = {
      id: Date.now(),
      title: `Result ${results.length + 1}`,
      outcome: 'Success',
      timestamp: new Date().toISOString(),
    };
    addResult(newResult);
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-white">Results</h2>
      
      {results.length > 0 ? (
        <div className="space-y-3">
          {results.map(r => (
            <div key={r.id} className="p-4 bg-surface/50 rounded-xl border border-white/10">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-white">{r.title}</h3>
                  <p className="text-sm text-gray-400">{r.outcome}</p>
                </div>
                <span className={`text-xs font-medium ${r.outcome === 'Success' ? 'text-green-400' : 'text-yellow-400'}`}>
                  {r.outcome}
                </span>
              </div>
              <time className="text-xs text-gray-500">{new Date(r.timestamp).toLocaleString()}</time>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-gray-500 text-sm">No results yet. Generate some to see the results panel.</p>
      )}

      <div className="mt-6 pt-4 border-t border-white/5">
        <button
          onClick={handleAddResult}
          className="btn btn-success w-full py-2 rounded-lg text-sm"
        >
          Add Result
        </button>
      </div>
    </div>
  );
};

export default Results;
