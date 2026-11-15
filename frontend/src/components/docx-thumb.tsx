'use client'

import { useEffect, useRef, useState } from 'react'
import { Spinner } from '@/components/docx-preview-frame'
import { usePratinjauPdf } from '@/hooks/use-pratinjau-pdf'

// Lebar kertas A4 pada 96 dpi (210 mm). PDF dirender pada lebar ini lalu
// diskalakan supaya pas dengan kotak thumbnail.
export const A4_PX = 794

// Thumbnail halaman pertama template. PDF-nya dibuat server saat kartu
// tampil dan dihapus saat kartu dilepas.
export function DocxThumb({ templateId, label }: { templateId: string; label: string }) {
  const { url, loading, error } = usePratinjauPdf({ template_id: templateId })
  const kotakRef = useRef<HTMLDivElement>(null)
  const [skala, setSkala] = useState(0.4)

  useEffect(() => {
    const kotak = kotakRef.current
    if (!kotak) return
    const ukur = () => setSkala(kotak.clientWidth / A4_PX)
    ukur()
    const ro = new ResizeObserver(ukur)
    ro.observe(kotak)
    return () => ro.disconnect()
  }, [])

  return (
    <div
      ref={kotakRef}
      role='img'
      aria-label={`Pratinjau template ${label}`}
      className='bg-muted relative w-full overflow-hidden'
      style={{ aspectRatio: '210 / 297' }}
    >
      {url && (
        <iframe
          title={`Pratinjau ${label}`}
          src={`${url}#toolbar=0&navpanes=0&scrollbar=0&view=FitH`}
          tabIndex={-1}
          className='pointer-events-none absolute left-0 top-0 border-0 bg-white'
          style={{
            width: A4_PX,
            height: Math.round((A4_PX * 297) / 210),
            transform: `scale(${skala})`,
            transformOrigin: 'top left',
          }}
        />
      )}
      {loading && (
        <div className='bg-muted absolute inset-0 flex items-center justify-center'>
          <Spinner className='size-6' />
        </div>
      )}
      {error && (
        <div className='text-muted-foreground absolute inset-0 flex items-center justify-center p-4 text-center text-xs'>
          Pratinjau tidak tersedia untuk template ini.
        </div>
      )}
    </div>
  )
}
