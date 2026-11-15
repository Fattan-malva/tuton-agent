'use client'

/** Label + varian badge status job, satu sumber untuk seluruh UI. */

export const JOB_LABEL: Record<string, string> = {
  queued: 'antre',
  running: 'berjalan',
  stopping: 'menghentikan',
  done: 'selesai',
  error: 'gagal',
  stopped: 'dihentikan',
}

export const JOB_VARIANT: Record<
  string,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  running: 'default',
  queued: 'secondary',
  stopping: 'outline',
  done: 'secondary',
  error: 'destructive',
  stopped: 'outline',
}

export const STATUS_LABEL: Record<string, string> = JOB_LABEL

/** Status yang masih butuh perhatian (ada progres yang berjalan). */
export const STATUS_HIDUP = new Set(['queued', 'running', 'stopping'])

export function isLive(status: string): boolean {
  return STATUS_HIDUP.has(status)
}
