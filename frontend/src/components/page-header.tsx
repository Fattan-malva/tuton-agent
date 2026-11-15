import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * Kepala halaman: judul, deskripsi, dan aksi di sisi kanan.
 * Dipakai semua halaman agar jarak dan tipografinya seragam.
 */
export function PageHeader({
  title,
  description,
  children,
  className,
}: {
  title: string
  description?: string
  children?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-start justify-between gap-4',
        className,
      )}
    >
      <div className='space-y-1'>
        <h1 className='font-heading text-2xl font-semibold tracking-tight'>
          {title}
        </h1>
        {description ? (
          <p className='text-muted-foreground max-w-3xl text-sm'>{description}</p>
        ) : null}
      </div>
      {children ? (
        <div className='flex flex-wrap items-center gap-2'>{children}</div>
      ) : null}
    </div>
  )
}
