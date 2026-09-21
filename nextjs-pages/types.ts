// Type definitions for Tuton Agent - Black Pixel Cozy Theme
// Separates concerns: shared types, API clients, data formats, state management

export type Tab = 'status' | 'results' | 'run' | 'settings';

export interface StatusItem {
  id: number;
  title: string;
  description: string;
  status: 'completed' | 'in-progress' | 'pending';
}

export interface ResultItem {
  id: number;
  title: string;
  outcome: string;
  timestamp: string;
}

export interface RunConfig {
  target: string;
  iterations: number;
  threshold: number;
}

export interface StoreState {
  status: StatusItem[];
  results: ResultItem[];
  runs: RunConfig[];
  settings: Record<string, string>;
}

export type Action = 'load-status' | 'load-results' | 'load-run' | 'save-config' | 'reset';

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error?: string;
}
