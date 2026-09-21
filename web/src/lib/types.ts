export type Tab = 'status' | 'results' | 'run' | 'settings';

export type StatusValue = 'done' | 'failed' | 'pending' | 'unknown';

export interface StatusStats {
  done: number;
  failed: number;
  pending: number;
  total: number;
}

export interface StatusItem {
  key: string;
  status: StatusValue;
  matkul: string;
  sesi?: number | string | null;
  kind?: string;
  index?: number;
  desc: string;
  outputs: string[];
}

export interface StatusResponse {
  success: boolean;
  stats: StatusStats;
  items: StatusItem[];
  error?: string;
}

export interface Course {
  id: number;
  name: string;
  folder_name: string;
}

export interface Section {
  number: number;
  title: string;
}

export interface Activity {
  id: number;
  title: string;
  mod_type: string;
}

export interface CourseSection {
  section: number;
  section_title: string;
  diskusi: Activity[];
  tugas: Activity[];
  lain: Activity[];
}

export interface CoursesResponse {
  success: boolean;
  courses: Course[];
  error?: string;
}

export interface SectionsResponse {
  success: boolean;
  sections: Section[];
  error?: string;
}

export interface ActivitiesResponse {
  success: boolean;
  course: string;
  sections: CourseSection[];
  error?: string;
}

export interface ResultFile {
  name: string;
  path: string;
  size: number;
  modified: number;
  kind?: string;
  index?: number;
  sesi?: number | string | null;
}

export interface ResultCourse {
  name: string;
  files: ResultFile[];
  has_errors?: boolean;
  folder?: string;
}

export interface ResultsResponse {
  success: boolean;
  courses: ResultCourse[];
  error?: string;
}

export interface AppConfig {
  nama: string;
  nim: string;
  prodi: string;
  model: string;
  base_url: string;
  has_session: boolean;
  output_dir: string;
}

export interface Schedule {
  enabled: boolean;
  day: '*' | '0' | '1' | '2' | '3' | '4' | '5' | '6';
  time: string;
  timezone: string;
  last_run: string | null;
  next_run: string | null;
  last_status: string | null;
  updated_at: string | null;
  success?: boolean;
  error?: string;
}

export interface RunOptions {
  course_id?: number;
  sesi?: number;
  force?: boolean;
}

export interface RunStartResponse {
  success: boolean;
  message?: string;
  error?: string;
}

export interface RunOutputResponse {
  output: string[];
  running: boolean;
  returncode: number | null;
}

export interface RunStatusResponse {
  success: boolean;
  running: boolean;
  returncode: number | null;
  elapsed: number;
  line_count: number;
  last_output: string | null;
}

export interface StopResponse {
  success: boolean;
  message?: string;
  error?: string;
}

export interface LoginResponse {
  success: boolean;
  message?: string;
  error?: string;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export type ToastType = 'info' | 'success' | 'warning' | 'error';

export interface ToastMessage {
  id: number;
  message: string;
  type: ToastType;
}
