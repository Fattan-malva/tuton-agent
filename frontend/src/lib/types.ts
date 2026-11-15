export type SessionInfo = {
  authenticated: boolean
  user?: { id: string; email: string; name: string }
  profile?: Profil
}

export type Profil = {
  user_id: string
  email: string
  nama_akun: string
  identitas: Record<string, string>
  cookie_ada: boolean
  cookie_ujung: string
  diperbarui?: string | null
}

export type StatusInfo = {
  providers: string
  python: string
  platform: string
  primary_model: string
  vision_model: string
  auth_required: boolean
}

export type AgentInfo = { name: string; model: string }

export type Course = { id: string; nama: string; kode: string; kelas: string }

export type CourseSession = { sesi: number; jumlah?: number }

export type JadwalItem = {
  nama: string
  jenis: string
  nomor: string
  sesi: string
  mulai: string
  tenggat: string
  mulai_turunan?: boolean
  url: string
  status_pengumpulan?: 'submitted' | 'not_submitted' | string
  nilai?: number | string | null
  feedback?: string | null
}

export type NilaiPoint = {
  sesi: number
  Diskusi?: number | null
  Tugas?: number | null
}

export type NilaiCourse = { id: string; nama: string; titik: NilaiPoint[] }

export type NilaiData = { courses: NilaiCourse[]; sesi: number[]; error?: string }

export type ResultFile = {
  slug: string
  sesi: string
  nama: string
  ukuran: number
  waktu: number
}

export type Job = {
  id: string
  kind: string
  status: 'queued' | 'running' | 'stopping' | 'done' | 'error' | 'stopped'
  slug: string
  sesi: number
  matkul: string
  jenis: string
  dibuat: number
  error?: string | null
  hasil?: unknown
}

export type LogEvent = {
  seq?: number
  ts?: number
  level?: 'info' | 'warn' | 'error' | 'ok' | 'stage' | string
  stage?: string
  agent?: string
  msg?: string
}

export type SettingItem = {
  key: string
  value: string
  rahasia: boolean
  ada?: boolean
}

export type Provider = {
  id: string
  name: string
  base_url: string
  models: string[]
  ada_key: boolean
}

export type ProviderData = {
  providers: Provider[]
  agents: Record<string, string>
  models: string[]
  error?: string
}

export type McpServer = {
  id: string
  name: string
  url: string
  headers: string[]
  agents: string[]
  tools: string[]
  enabled: boolean
}

export type SkillInfo = { name: string; ukuran: number; waktu: number }
