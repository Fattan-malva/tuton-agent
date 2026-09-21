// State management for Tuton Agent - Black Pixel Cozy Theme
// Centralized state for status, results, runs, and settings

import { StoreState, Action } from './types';

class Store {
  private state: StoreState;

  constructor(initialState: StoreState = {}) {
    this.state = { ...initialState };
  }

  getState(): StoreState {
    return this.state;
  }

  setState(newState: Partial<StoreState>): void {
    this.state = { ...this.state, ...newState };
  }

  // Status updates
  setStatusItem(id: number, item: StatusItem): void {
    this.setState(prev => ({
      ...prev,
      status: prev.status.map((s, i) => i === id ? item : s),
    }));
  }

  addStatusItem(item: StatusItem): void {
    this.setState(prev => ({
      ...prev,
      status: [...prev.status, item],
    }));
  }

  removeStatusItem(id: number): void {
    this.setState(prev => ({
      ...prev,
      status: prev.status.filter(s => s.id !== id),
    }));
  }

  // Results updates
  addResult(result: ResultItem): void {
    this.setState(prev => ({
      ...prev,
      results: [...prev.results, result],
    }));
  }

  setResults(items: ResultItem[]): void {
    this.setState({ results: items });
  }

  // Run configurations
  setRunConfig(config: RunConfig): void {
    this.setState(prev => ({
      ...prev,
      runs: [...prev.runs, config],
    }));
  }

  getAllRuns(): RunConfig[] {
    return this.state.runs;
  }

  // Settings
  setSetting(key: string, value: string): void {
    this.setState(prev => ({
      ...prev,
      settings: { ...prev.settings, [key]: value },
    }));
  }

  getSettings(): Record<string, string> {
    return this.state.settings;
  }

  // Actions
  async loadStatus(): Promise<void> {
    const data = await apiClient.getStatus();
    if (data.success && data.data) {
      this.addStatusItem(data.data[0]);
    }
  }

  async loadResults(): Promise<void> {
    const data = await apiClient.getResults();
    if (data.success && data.data) {
      this.addResult(data.data[0]);
    }
  }

  async saveConfig(config: Record<string, string>): Promise<void> {
    await apiClient.saveConfig(config);
  }
}

// Singleton instance
const store = new Store();

export default store;
