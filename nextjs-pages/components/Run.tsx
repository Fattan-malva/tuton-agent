// Run Component - Controls the run agent simulation
// Part of the 5 required view components

import React, { useState, useEffect } from 'react';
import { store } from './store';

const Run = () => {
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [config, setConfig] = useState({
    target: 'demo',
    iterations: 10,
    threshold: 50,
  });

  const handleStartRun = () => {
    setIsRunning(true);
    setProgress(0);
  };

  const handleStopRun = () => {
    setIsRunning(false);
  };

  const handleConfigChange = (field: keyof typeof config, value: string) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const simulateProgress = () => {
    if (!isRunning) return;
    setProgress(prev => {
      const newProgress = Math.min(prev + 5, 100);
      setProgress(newProgress);
      if (newProgress >= 100) {
        setIsRunning(false);
        return newProgress;
      }
      return newProgress;
    });
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-white">Run Agent</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-sm text-gray-300">Target</label>
            <select
              value={config.target}
              onChange={(e) => handleConfigChange('target', e.target.value)}
              className="w-full px-3 py-2 bg-surface/50 border border-white/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent"
            >
              <option value="demo">Demo Target</option>
              <option value="production">Production Target</option>
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-sm text-gray-300">Iterations</label>
            <input
              type="number"
              value={config.iterations}
              onChange={(e) => handleConfigChange('iterations', e.target.value)}
              min="1"
              className="w-full px-3 py-2 bg-surface/50 border border-white/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-sm text-gray-300">Threshold %</label>
            <input
              type="range"
              min="0"
              max="100"
              value={config.threshold}
              onChange={(e) => handleConfigChange('threshold', e.target.value)}
              className="w-full"
            />
            <span className="text-sm text-gray-400">{config.threshold}%</span>
          </div>
        </div>
        
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-sm text-gray-300">Status</label>
            <span className={`${isRunning ? 'text-green-400' : 'text-gray-400'}`}>{isRunning ? 'Running...' : 'Idle'}</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleStartRun}
              disabled={isRunning}
              className="btn btn-primary w-full py-2 rounded-lg text-sm"
            >
              Start Run
            </button>
            <button
              onClick={handleStopRun}
              disabled={!isRunning}
              className="btn btn-danger w-full py-2 rounded-lg text-sm"
            >
              Stop
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6">
        <div className="h-4 bg-surface/50 rounded-lg overflow-hidden">
          <div className="h-full bg-gradient-to-br from-accent to-purple-500 transition-all duration-500" style={
            progress > 0 && progress < 100
              ? `width: ${progress}%`
              : progress === 100
              ? 'bg-green-500'
              : 'bg-red-500'
          }></div>
        </div>
        <p className="text-xs text-gray-500 mt-2">Progress: {progress}%</p>
      </div>
    </div>
  );
};

export default Run;
