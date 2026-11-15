import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatBytes(bytes: number) {
  return `${(Number(bytes || 0) / 1048576).toFixed(2)} MB`
}

export function formatTime(ts?: number) {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleTimeString('id-ID', { hour12: false })
}
