export type Tab = 'status' | 'results' | 'run' | 'soal' | 'settings';

export type WorkKind = 'tugas' | 'diskusi';

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
  created_at?: string;
  finished_at?: string;
  duration_sec?: number | null;
  reason?: string;
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
  created_at?: string;
  finished_at?: string;
  duration_sec?: number | null;
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

export interface RuntimeConfig {
  jobs: number;
  timeout: number;
  retries: number;
  transcribe: string;
  vision_tries: number;
  /** Batas keras jumlah referensi per jawaban. Batas biaya, bukan selera. */
  max_pustaka: number;
}

export interface AppConfig {
  nama: string;
  nim: string;
  prodi: string;
  /** Isi baris "Semester" di tabel identitas dokumen. Boleh kosong. */
  semester: string;
  /** Isi baris "UT Daerah" di tabel identitas dokumen. Boleh kosong. */
  ut_daerah: string;
  model: string;
  default_model?: string;
  base_url: string;
  has_session: boolean;
  output_dir: string;
  runtime?: RuntimeConfig;
  /**
   * Model vision transkripsi yang tersimpan di `.env`
   * (`OPENCODE_MODEL_TRANSCRIBE`). Bedanya dengan mode otomatis: yang ini
   * pilihan manual. Kosong = sistem yang memilih model vision sendiri.
   */
  transcribe_model_configured?: string;
}

export interface ModelOption {
  id: string;
  name: string;
  current: boolean;
}

export interface ModelGroup {
  provider: string;
  models: ModelOption[];
}

export interface ModelsResponse {
  success: boolean;
  current: string;
  default: string;
  total: number;
  groups: ModelGroup[];
  error?: string;
}

export type RunKindFilter = 'all' | 'tugas' | 'diskusi';

export interface RunOptions {
  course_id?: number;
  sesi?: number;
  force?: boolean;
  kind?: RunKindFilter;
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

export interface ResetResponse {
  success: boolean;
  message?: string;
  error?: string;
  /** Jumlah entri di `output/` yang dihapus. */
  deleted?: number;
  /** Jumlah berkas yang hilang, termasuk di dalam folder. */
  files?: number;
  /** Total byte yang dibebaskan. */
  bytes?: number;
  /** Item `state.json` yang dibersihkan karena berkasnya sudah tidak ada. */
  items?: number;
  /** Nama entri yang gagal dihapus. Kosong = tidak ada. */
  failed?: string[];
}

export interface StopResponse {
  success: boolean;
  message?: string;
  error?: string;
  /** Jumlah proses yang benar-benar dibunuh (pipeline + sesi agen). */
  killed?: number;
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
