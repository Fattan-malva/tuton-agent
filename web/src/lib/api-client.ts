import type {
  ActivitiesResponse,
  AppConfig,
  ApiEnvelope,
  Course,
  CourseSection,
  CoursesResponse,
  LoginResponse,
  ModelsResponse,
  ResultCourse,
  ResultsResponse,
  RunOptions,
  RunOutputResponse,
  RunStartResponse,
  RunStatusResponse,
  Section,
  SectionsResponse,
  StatusResponse,
  ResetResponse,
  StopResponse,
} from './types';

const API_BASE = '';

/**
 * Bentuk yang diterima `saveConfig`: kunci datar, bukan `runtime` bersarang.
 * Server membaca kunci datar dan mempertahankan nilai lama untuk field yang
 * tidak dikirim, jadi form boleh mengirim subset saja.
 */
export type SettingsPayload = Partial<AppConfig> & {
  moodle_session?: string;
  // `string` diterima karena `<input type="number">` mengirim teks; server yang
  // mem-parsing dan hanya memakai nilai lama kalau tidak terbaca.
  jobs?: number | string;
  max_pustaka?: number | string;
  transcribe?: string;
  /**
   * Model agen pembantu. Dikirim datar (bukan di `runtime`) karena server
   * menyimpannya ke `.env` sebagai `OPENCODE_MODEL_HELPER`. String kosong
   * berarti "pilih otomatis" -- server sengaja TIDAK mempertahankan nilai
   * lama supaya mode otomatis bisa dipulihkan.
   */
  /**
   * Model vision untuk transkripsi lampiran gambar/PDF scan. Dikirim datar
   * (bukan di `runtime`) karena server menyimpannya ke `.env` sebagai
   * `OPENCODE_MODEL_TRANSCRIBE`. String kosong berarti "pilih otomatis" --
   * sama seperti helper, server sengaja TIDAK mempertahankan nilai lama.
   */
  opencode_model_transcribe?: string;
};

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
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
    if (!isFormData) {
      headers.set('Content-Type', 'application/json');
    }
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

  getModels(options?: { refresh?: boolean }): Promise<ModelsResponse> {
    const query = options?.refresh ? '?refresh=1' : '';
    return request<ModelsResponse>(`/api/models${query}`);
  },

  /**
   * Kirim setelan ke `/api/config`.
   *
   * Body dikirim apa adanya. Server membaca kunci datar (`jobs`,
   * `max_pustaka`, `transcribe`, ...) dan mempertahankan nilai lama untuk
   * field yang tidak dikirim, jadi form boleh mengirim subset saja.
   */
  saveConfig(config: SettingsPayload): Promise<ApiEnvelope<unknown>> {
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

  submitSolve(payload: {
    course_id: number;
    sesi: number;
    kind: 'tugas' | 'diskusi';
    title: string;
    soal_text: string;
    file?: File | null;
    files?: File[];
    /** Contoh format jawaban (.docx). Opsional: dikosongkan berarti pakai template standar. */
    format_file?: File | null;
    /** Keterangan format jawaban bebas. Opsional. */
    format_note?: string;
  }): Promise<RunStartResponse> {
    const form = new FormData();
    form.append('course_id', String(payload.course_id));
    form.append('sesi', String(payload.sesi));
    form.append('kind', payload.kind);
    form.append('title', payload.title);
    form.append('soal_text', payload.soal_text);
    if (payload.file) {
      form.append('file', payload.file);
    }
    for (const extra of payload.files ?? []) {
      form.append('files', extra);
    }
    if (payload.format_file) {
      form.append('format_file', payload.format_file);
    }
    const note = (payload.format_note ?? '').trim();
    if (note) {
      form.append('format_note', note);
    }
    return envelope('/api/solve', { method: 'POST', body: form });
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

  resetResults(keepCache = false): Promise<ResetResponse> {
    return envelope('/api/results/reset', {
      method: 'POST',
      body: JSON.stringify({ keep_cache: keepCache }),
    });
  },
};

export default apiClient;
