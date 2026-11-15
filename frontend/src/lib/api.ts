export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// Clerk menaruh token di sini lewat <TokenBridge /> supaya `fetch` di
// seluruh aplikasi tidak perlu tahu apa pun soal Clerk. Modul (bukan React
// context) dipakai karena `api()` juga dipanggil dari EventSource, SWR, dan
// handler non-komponen.
let tokenGetter: (() => Promise<string | null>) | null = null
let tokenReady: Promise<void> | null = null
let markTokenReady: (() => void) | null = null

function waitForToken() {
  if (!tokenReady) {
    tokenReady = new Promise<void>((resolve) => {
      markTokenReady = resolve
      // Jaring pengaman: kalau Clerk gagal memuat (blokir jaringan, kunci
      // salah), jangan sampai semua request menggantung tanpa akhir. Setelah
      // 4 detik request tetap jalan tanpa token, dan server menjawab 401.
      if (typeof window !== 'undefined') {
        window.setTimeout(() => markTokenReady?.(), 4000)
      }
    })
  }
  return tokenReady
}

export function setTokenGetter(fn: (() => Promise<string | null>) | null) {
  tokenGetter = fn
  // SWR bisa mulai mengambil data pada render yang sama saat Clerk melaporkan
  // `isSignedIn: true`, yaitu SEBELUM efek TokenBridge memasang getter baru.
  // Tanpa penantian ini `/api/session` dijawab `200 {"authenticated": false}`
  // (bukan 401, jadi tidak ada redirect) dan dashboard berhenti di skeleton.
  markTokenReady?.()
  markTokenReady = null
}

async function authHeaders(): Promise<Record<string, string>> {
  await waitForToken()
  if (!tokenGetter) return {}
  try {
    const token = await tokenGetter()
    return token ? { Authorization: `Bearer ${token}` } : {}
  } catch {
    return {}
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    cache: 'no-store',
    ...init,
    headers: { ...(await authHeaders()), ...(init?.headers || {}) },
  })
  const ct = res.headers.get('content-type') || ''
  const data: unknown = ct.includes('application/json')
    ? await res.json()
    : await res.text()

  if (res.status === 401) {
    if (
      typeof window !== 'undefined' &&
      !window.location.pathname.startsWith('/login')
    ) {
      window.location.href = '/login/'
    }
    throw new ApiError('Sesi berakhir. Silakan masuk kembali.', 401)
  }
  if (!res.ok) {
    const pesan =
      data && typeof data === 'object' && 'error' in data
        ? String((data as { error: unknown }).error)
        : `Permintaan gagal (HTTP ${res.status}).`
    throw new ApiError(pesan, res.status)
  }
  return data as T
}

export const api = request
export const fetcher = <T,>(url: string) => request<T>(url)

export function postJSON<T>(path: string, body: unknown) {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function postForm<T>(path: string, body: FormData) {
  return request<T>(path, { method: 'POST', body })
}

/** URL EventSource tidak bisa membawa header, jadi token ikut di query. */
export async function streamUrl(path: string) {
  const token = await authHeaders()
  const auth = token.Authorization
  if (!auth) return path
  const sep = path.includes('?') ? '&' : '?'
  return `${path}${sep}token=${encodeURIComponent(auth.replace('Bearer ', ''))}`
}
