import type {
  ActivitiesResponse,
  AppConfig,
  ApiEnvelope,
  Course,
  CourseSection,
  CoursesResponse,
  LoginResponse,
  ResultCourse,
  ResultsResponse,
  RunOptions,
  RunOutputResponse,
  RunStartResponse,
  RunStatusResponse,
  Schedule,
  Section,
  SectionsResponse,
  StatusResponse,
  StopResponse,
} from './types';

const API_BASE = '';

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  let payload: unknown = null;

  try {
    payload = await response.json();
  } catch {
    payload = { error: `Response tidak valid dari ${endpoint}` };
  }

  if (!response.ok) {
    const envelope = payload as Partial<ApiEnvelope<unknown>>;
    throw new ApiError(
      typeof envelope.error === 'string' ? envelope.error : `HTTP ${response.status}`,
      response.status,
      payload,
    );
  }

  return payload as T;
}

async function envelope<T>(endpoint: string, options?: RequestInit): Promise<ApiEnvelope<T>> {
  return request<ApiEnvelope<T>>(endpoint, options);
}

function coursesFrom(response: CoursesResponse): CoursesResponse {
  return response;
}

function resultsFrom(response: ResultsResponse): ResultsResponse {
  return response;
}

export const apiClient = {
  login(username: string, password: string): Promise<LoginResponse> {
    return envelope<LoginResponse>('/api/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  },

  getConfig(): Promise<AppConfig> {
    return request<AppConfig>('/api/config');
  },

  saveConfig(config: Partial<AppConfig> & { moodle_session?: string }): Promise<ApiEnvelope<unknown>> {
    return envelope('/api/config', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  getCourses(): Promise<Course[]> {
    return request<CoursesResponse>('/api/courses').then((response) => response.courses ?? []);
  },

  getSections(courseId: number): Promise<Section[]> {
    return request<SectionsResponse>(`/api/courses/${courseId}/sections`).then((response) => response.sections ?? []);
  },

  getActivities(courseId: number): Promise<CourseSection[]> {
    return request<ActivitiesResponse>(`/api/courses/${courseId}/activities`).then((response) => response.sections ?? []);
  },

  deleteCourse(folder: string): Promise<ApiEnvelope<unknown>> {
    return envelope(`/api/courses/${encodeURIComponent(folder)}`, { method: 'DELETE' });
  },

  getStatus(): Promise<StatusResponse> {
    return request<StatusResponse>('/api/status');
  },

  getResults(): Promise<ResultCourse[]> {
    return request<ResultsResponse>('/api/results').then((response) => response.courses ?? []);
  },

  download(filepath: string): void {
    window.open(`/api/download/${encodeURI(filepath)}`, '_blank', 'noopener,noreferrer');
  },

  deleteResult(filepath: string): Promise<ApiEnvelope<unknown>> {
    return envelope(`/api/results/${encodeURI(filepath)}`, { method: 'DELETE' });
  },

  startRun(options: RunOptions): Promise<RunStartResponse> {
    return envelope('/api/run', {
      method: 'POST',
      body: JSON.stringify(options),
    });
  },

  getRunOutput(): Promise<RunOutputResponse> {
    return request<RunOutputResponse>('/api/run/output');
  },

  getRunStatus(): Promise<RunStatusResponse> {
    return request<RunStatusResponse>('/api/run/status');
  },

  stopRun(): Promise<StopResponse> {
    return envelope('/api/run/stop', { method: 'POST' });
  },

  getSchedule(): Promise<Schedule> {
    return request<Schedule>('/api/schedule');
  },

  saveSchedule(schedule: { enabled: boolean; day: Schedule['day']; time: string }): Promise<Schedule> {
    return request<Schedule>('/api/schedule', {
      method: 'POST',
      body: JSON.stringify(schedule),
    });
  },
};

export default apiClient;
