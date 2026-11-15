import { useEffect, useRef, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * Kepala halaman: judul, deskripsi, dan aksi di sisi kanan.
 *
 * Kepala ini menempel (sticky) tepat di bawah header aplikasi, jadi judul dan
 * deskripsi tetap terlihat saat isi kartu di bawahnya digulir. Tingginya
 * diukur dan disimpan di `--page-header-h` supaya panel dua kolom yang juga
 * sticky bisa berhenti tepat di bawahnya, berapa pun panjang deskripsinya.
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
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const akar = document.documentElement
    const ukur = () => {
      akar.style.setProperty('--page-header-h', `${Math.round(el.offsetHeight)}px`)
    }
    ukur()
    if (typeof ResizeObserver === 'undefined') return () => {}
    const pengamat = new ResizeObserver(ukur)
    pengamat.observe(el)
    return () => {
      pengamat.disconnect()
      akar.style.removeProperty('--page-header-h')
    }
  }, [])

  return (
    <div
      ref={ref}
      className={cn(
        'sticky top-[var(--header-h)] z-30 -mx-4 flex flex-wrap items-start justify-between gap-3 border-b bg-background/90 px-4 py-3.5 backdrop-blur-md sm:-mx-6 sm:px-6',
        className,
      )}
    >
      <div className='min-w-0 space-y-0.5'>
        <h1 className='font-heading text-xl font-semibold tracking-tight sm:text-2xl'>
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
