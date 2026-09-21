import type { AppConfig, Course, ResultCourse, Schedule, StatusResponse } from './types';

export interface StoreState {
  config: AppConfig | null;
  courses: Course[];
  status: StatusResponse | null;
  results: ResultCourse[];
  schedule: Schedule | null;
  currentTab: 'status' | 'results' | 'run' | 'settings';
  isLoggedIn: boolean;
  isLoading: boolean;
  error: string | null;
}

class Store {
  private state: StoreState = {
    config: null,
    courses: [],
    status: null,
    results: [],
    schedule: null,
    currentTab: 'status',
    isLoggedIn: false,
    isLoading: false,
    error: null,
  };

  getState(): StoreState {
    return this.state;
  }

  setState(updater: Partial<StoreState> | ((previous: StoreState) => Partial<StoreState>)): void {
    const changes = typeof updater === 'function' ? updater(this.state) : updater;
    this.state = { ...this.state, ...changes };
  }
}

const store = new Store();

export default store;
