// API Client for Tuton Agent - Black Pixel Cozy Theme
// Handles communication with backend Flask server

import { ApiResponse } from '../types';

class ApiClient {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    this.headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
  }

  async request(endpoint: string, options: Record<string, any> = {}): Promise<ApiResponse<any>> {
    const url = `${this.baseUrl}${endpoint}`;
    const mergedHeaders = { ...this.headers, ...options};

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: mergedHeaders,
        ...options,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('API request failed:', error);
      return { success: false, data: null, error: String(error) };
    }
  }

  async getStatus(): Promise<StatusItem[]> {
    return this.request('/api/status');
  }

  async getResults(): Promise<ResultItem[]> {
    return this.request('/api/results');
  }

  async getRunConfig(): Promise<RunConfig[]> {
    return this.request('/api/runs');
  }

  async saveConfig(config: Record<string, string>): Promise<ApiResponse<any>> {
    return this.request('/api/config', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }
}

// Singleton instance
const apiClient = new ApiClient('http://localhost:8000');

export default apiClient;
