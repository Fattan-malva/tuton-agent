'use client'

import { useEffect, useState } from 'react'
import { apiFetch, postJSON } from '@/lib/api'

export type SumberPratinjau = { rel: string } | { template_id: string } | { schema: object }

// Pratinjau DOCX: server mengonversi berkas ke PDF sementara dengan
// LibreOffice. PDF itu dihapus di server begitu sumbernya berganti atau
// komponen dilepas (pratinjau ditutup), dan blob-nya dilepas dari memori.
export function usePratinjauPdf(sumber: SumberPratinjau | null) {
  const kunci = sumber ? JSON.stringify(sumber) : ''
  const [url, setUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sumber) {
      setUrl(null)
      setLoading(false)
      setError(null)
      return
    }
    let batal = false
    let id: string | null = null
    let blobUrl: string | null = null
    setLoading(true)
    setError(null)
    setUrl(null)

    const hapusDiServer = (sesi: string) => {
      void postJSON('/api/preview/hapus', { id: sesi }).catch(() => {})
    }

    ;(async () => {
      try {
        const { id: sesi } = await postJSON<{ id: string }>('/api/preview/create', sumber)
        id = sesi
        // Pratinjau sudah ditutup selagi konversi berjalan: hapus sekarang.
        if (batal) return hapusDiServer(sesi)
        const r = await apiFetch(`/api/preview/pdf/${sesi}`)
        if (!r.ok) throw new Error('PDF pratinjau tidak bisa dimuat.')
        const blob = await r.blob()
        if (batal) return
        blobUrl = URL.createObjectURL(blob)
        setUrl(blobUrl)
      } catch (e) {
        if (!batal) setError(e instanceof Error ? e.message : 'Pratinjau gagal dibuat.')
      } finally {
        if (!batal) setLoading(false)
      }
    })()

    return () => {
      batal = true
      if (blobUrl) URL.revokeObjectURL(blobUrl)
      if (id) hapusDiServer(id)
    }
    // `sumber` diwakili oleh `kunci`; objek baru dengan isi sama tidak perlu memicu ulang.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kunci])

  return { url, loading, error }
}
