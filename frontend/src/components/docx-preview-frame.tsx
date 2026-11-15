'use client'

import { cn } from '@/lib/utils'

// Animasi loading pratinjau DOCX. Seluruhnya memakai token tema (bg-card,
// bg-muted, text-primary), jadi ikut mode terang dan gelap.
export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        'border-muted-foreground/30 border-t-primary inline-block size-5 animate-spin rounded-full border-2 motion-reduce:animate-none',
        className,
      )}
    />
  )
}

// Kertas A4 yang "sedang dirender": baris teks berdenyut dan kilau melintas.
export function PaperSkeleton() {
  return (
    <div role='status' aria-live='polite' className='flex h-full w-full flex-col items-center justify-center gap-5 p-6'>
      <div
        className='bg-card relative flex h-full max-h-[70vh] w-full max-w-[min(100%,calc(70vh*210/297))] flex-col gap-3 overflow-hidden rounded-sm border p-8 shadow-sm'
        style={{ aspectRatio: '210 / 297' }}
      >
        <div className='bg-muted-foreground/20 h-4 w-1/2 animate-pulse rounded motion-reduce:animate-none' />
        <div className='mt-4 space-y-2.5'>
          {Array.from({ length: 14 }).map((_, i) => (
            <div
              key={i}
              className='bg-muted-foreground/10 h-2.5 animate-pulse rounded motion-reduce:animate-none'
              style={{ width: `${78 + ((i * 37) % 22)}%`, animationDelay: `${i * 80}ms` }}
            />
          ))}
        </div>
        <div className='pointer-events-none absolute inset-y-0 left-0 w-1/2 bg-gradient-to-r from-transparent via-foreground/10 to-transparent motion-reduce:hidden [animation:tuton-shimmer_1.8s_ease-in-out_infinite]' />
      </div>
      <p className='text-muted-foreground flex items-center gap-2 text-sm'>
        <Spinner className='size-4' />
        Menyiapkan pratinjau DOCX…
      </p>
    </div>
  )
}

// Bingkai pratinjau: skeleton saat PDF dibuat server, iframe saat siap,
// pesan galat bila gagal. Dipakai di modal result, modal template, editor.
export function DocxPreviewFrame({
  url,
  loading,
  error,
  title,
  className,
}: {
  url: string | null
  loading: boolean
  error: string | null
  title: string
  className?: string
}) {
  return (
    <div className={cn('bg-muted relative h-full w-full overflow-hidden rounded-md border', className)}>
      {url && <iframe title={title} src={`${url}#view=FitH`} className='h-full w-full border-0 bg-white' />}
      {!url && loading && !error && <PaperSkeleton />}
      {error && <div className='text-destructive absolute inset-0 flex items-center justify-center p-6 text-center text-sm'>{error}</div>}
    </div>
  )
}
