// Custom hooks for Tuton Agent - Polling terminal + progress parsing

import { useState, useEffect, useCallback } from 'react';
import apiClient from './api-client';

// Hook for polling terminal output and detecting progress updates
const useTerminalProgress = (intervalMs: number = 2000) => {
  const [progress, setProgress] = useState<number>(0);
  const [lastMessage, setLastMessage] = useState<string>('');

  useEffect(() => {
    const interval = setInterval(() => {
      // In a real implementation, this would read from terminal or API
      // For now, simulate periodic updates
      setProgress(prev => Math.min(prev + 1, 100));
      setLastMessage(`Terminal update at ${Math.floor(progress)}%`);
    }, intervalMs);

    return () => clearInterval(interval);
  }, [intervalMs]);

  return { progress, lastMessage };
};

// Hook for parsing terminal progress markers (e.g., "PROGRESS: 75%")
const useProgressParser = (terminalOutput: string): { percent: number; message: string } => {
  const parse = (output: string): { percent: number; message: string } => {
    // Look for patterns like "PROGRESS: 75%", "COMPLETED", "ERROR", etc.
    const progressMatch = output.match(/PROGRESS:\s*(\d+)%/i);
    if (progressMatch) {
      const percent = parseInt(progressMatch[1], 10);
      return { percent, message: progressMatch[0] };
    }
    // Fallback to extracting percentage-like numbers
    const numMatch = output.match(/(\d+)%/i);
    if (numMatch) {
      return { percent: parseInt(numMatch[1], 10), message: output.trim() };
    }
    return { percent: 0, message: output.trim() };
  };

  return parse(terminalOutput);
};

// Main hook combining terminal monitoring with progress parsing
export const useTerminalMonitor = (intervalMs: number = 2000) => {
  const { progress, lastMessage } = useTerminalProgress(intervalMs);
  const parsed = useProgressParser(lastMessage);

  const updateProgress = useCallback(() => {
    setProgress(parsed.percent);
  }, []);

  return { progress, lastMessage, parsed, updateProgress };
};
