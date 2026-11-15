'use client'

import { useEffect, useRef } from 'react'
import { renderAsync } from 'docx-preview'
import { apiFetch } from '@/lib/api'

// Lebar kertas A4 pada 96 dpi (210 mm). Pratinjau memakai ukuran ini supaya
// tampilannya sama dengan halaman Word, bukan tiruan dengan CSS.
export const A4_PX = 794

// Thumbnail DOCX asli. Isinya dirender di dalam Shadow DOM supaya gaya
// `docx-preview` dari satu template tidak bocor ke template lain di halaman
// yang sama. Halaman pertama diskalakan agar pas dengan kotak.
export function DocxThumb({ url, label }: { url: string; label: string }) {
  const hostRef = useRef<HTMLDivElement>(null)

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
    apiFetch(url)
      .then((r) => {
        if (!r.ok) throw new Error('Template tidak bisa dimuat.')
        return r.arrayBuffer()
      })
      .then((buffer) => {
        if (!batal) return renderAsync(buffer, isi, gaya, { inWrapper: false, breakPages: true })
      })
      .catch(() => {
        // Pesan galat harus ditulis ke shadow root: host yang punya shadow
        // root tidak menampilkan light DOM-nya, jadi teks di luar shadow
        // akan tersembunyi dan kotaknya tampak kosong.
        if (batal) return
        const pesan = document.createElement('div')
        pesan.textContent = 'Pratinjau tidak tersedia untuk template ini.'
        pesan.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:16px;text-align:center;font:12px system-ui,sans-serif;color:#6b7280;'
        shadow.replaceChildren(pesan)
      })

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
    </div>
  )
}
