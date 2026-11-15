'use client'

import { useEffect, useRef, useState } from 'react'
import { renderAsync } from 'docx-preview'

// Lebar kertas A4 pada 96 dpi (210 mm). Pratinjau memakai ukuran ini supaya
// tampilannya sama dengan halaman Word, bukan tiruan dengan CSS.
export const A4_PX = 794

// Thumbnail DOCX asli. Isinya dirender di dalam Shadow DOM supaya gaya
// `docx-preview` dari satu template tidak bocor ke template lain di halaman
// yang sama. Halaman pertama diskalakan agar pas dengan kotak.
export function DocxThumb({ url, label }: { url: string; label: string }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [gagal, setGagal] = useState(false)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const shadow = host.shadowRoot ?? host.attachShadow({ mode: 'open' })
    const kertas = document.createElement('div')
    kertas.style.width = `${A4_PX}px`
    kertas.style.transformOrigin = 'top left'
    const gaya = document.createElement('div')
    const isi = document.createElement('div')
    kertas.append(gaya, isi)
    shadow.replaceChildren(kertas)

    const ukur = () => {
      kertas.style.transform = `scale(${host.clientWidth / A4_PX})`
    }
    ukur()
    const ro = new ResizeObserver(ukur)
    ro.observe(host)

    let batal = false
    setGagal(false)
    fetch(url, { cache: 'no-store' })
      .then((r) => {
        if (!r.ok) throw new Error('Template tidak bisa dimuat.')
        return r.arrayBuffer()
      })
      .then((buffer) => {
        if (!batal) return renderAsync(buffer, isi, gaya, { inWrapper: false, breakPages: true })
      })
      .catch(() => { if (!batal) setGagal(true) })

    return () => {
      batal = true
      ro.disconnect()
      shadow.replaceChildren()
    }
  }, [url])

  return (
    <div
      ref={hostRef}
      role='img'
      aria-label={`Pratinjau template ${label}`}
      className='bg-muted relative w-full overflow-hidden'
      style={{ aspectRatio: '210 / 297' }}
    >
      {gagal && (
        <div className='text-muted-foreground absolute inset-0 flex items-center justify-center p-4 text-center text-xs'>
          Pratinjau tidak tersedia untuk template ini.
        </div>
      )}
    </div>
  )
}
