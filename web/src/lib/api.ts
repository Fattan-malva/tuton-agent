export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: 'no-store', ...init })
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
