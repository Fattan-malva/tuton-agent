'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import useSWR from 'swr'
import { Download, Eye, FileText, Search, Trash2 } from 'lucide-react'
import { postJSON, streamUrl } from '@/lib/api'
import { usePratinjauPdf } from '@/hooks/use-pratinjau-pdf'
import type { ResultFile } from '@/lib/types'
import { formatBytes } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { PageHeader } from '@/components/page-header'

function encodeRel(rel: string) {
  return rel.split('/').map(encodeURIComponent).join('/')
}

/** Unduhan tidak bisa membawa header Authorization, jadi token ikut di query. */
function unduh(rel: string) {
  void streamUrl(`/api/download-output/${encodeRel(rel)}`).then((url) => {
    window.location.href = url
  })
}

function namaMatkul(slug: string) {
  return String(slug || 'Lainnya').replace(/-/g, ' ')
}

type Hapus = {
  title: string
  message: string
  body: Record<string, string>
}

export default function ResultsPage() {
  const { data, isLoading, error, mutate } = useSWR<ResultFile[]>('/api/results')
  const [cari, setCari] = useState('')
  const [preview, setPreview] = useState<{ rel: string; nama: string } | null>(null)
  const [hapus, setHapus] = useState<Hapus | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const files = useMemo(() => data || [], [data])
  const tersaring = useMemo(() => {
    const q = cari.trim().toLowerCase()
    if (!q) return files
    return files.filter((f) =>
      [f.nama, f.slug, f.sesi, namaMatkul(f.slug)]
        .join(' ')
        .toLowerCase()
        .includes(q),
    )
  }, [files, cari])

  async function konfirmasiHapus() {
    if (!hapus) return
    setBusy(true)
    setMsg('')
    try {
      await postJSON('/api/results/delete', hapus.body)
      setHapus(null)
      await mutate()
    } catch (e) {
      setMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='flex flex-col gap-4'>
      <PageHeader
        title='Result'
        description='Dokumen DOCX hasil pipeline. Klik nama berkas untuk pratinjau.'
      >
        <Badge variant='secondary'>{files.length} DOCX</Badge>
      </PageHeader>

      {msg ? <p className='text-destructive text-sm'>{msg}</p> : null}

      <Card className='gap-4 py-5'>
        <CardHeader className='px-5'>
          <CardTitle className='text-base'>Berkas hasil</CardTitle>
          <CardDescription>
            Pratinjau, unduh, atau hapus dokumen yang sudah jadi.
          </CardDescription>
          <CardAction>
            <div className='relative w-full sm:w-72'>
              <Search className='text-muted-foreground pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2' />
              <Input
                value={cari}
                onChange={(e) => setCari(e.target.value)}
                placeholder='Cari berkas, mata kuliah, sesi...'
                className='ps-8'
                aria-label='Cari berkas hasil'
              />
            </div>
          </CardAction>
        </CardHeader>
        <CardContent className='px-5'>
          {isLoading ? (
            <div className='space-y-2'>
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className='h-11 w-full' />
              ))}
            </div>
          ) : error ? (
            <p className='text-destructive py-10 text-center text-sm'>
              {String((error as Error).message)}
            </p>
          ) : !files.length ? (
            <div className='flex flex-col items-center justify-center py-16 text-center'>
              <span className='bg-primary/10 text-primary mb-4 flex size-11 items-center justify-center rounded-md'>
                <FileText className='size-5' />
              </span>
              <h2 className='text-base font-semibold'>Belum ada hasil</h2>
              <p className='text-muted-foreground mt-1 max-w-xs text-sm'>
                Dokumen DOCX dari tugas yang selesai akan muncul di sini.
              </p>
            </div>
          ) : !tersaring.length ? (
            <p className='text-muted-foreground py-10 text-center text-sm'>
              Tidak ada berkas yang cocok dengan “{cari}”.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Berkas</TableHead>
                  <TableHead className='max-md:hidden'>Mata kuliah</TableHead>
                  <TableHead className='max-sm:hidden'>Sesi</TableHead>
                  <TableHead className='max-sm:hidden'>Ukuran</TableHead>
                  <TableHead className='max-lg:hidden'>Tanggal</TableHead>
                  <TableHead className='w-28 text-end'>Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tersaring.map((f) => {
                  const rel = `${f.slug}/${f.sesi}/${f.nama}`
                  const tanggal = f.waktu
                    ? new Date(Number(f.waktu) * 1000).toLocaleDateString('id-ID', {
                        day: '2-digit',
                        month: 'short',
                        year: 'numeric',
                      })
                    : '—'
                  return (
                    <TableRow key={rel}>
                      <TableCell className='max-w-[360px]'>
                        <button
                          type='button'
                          className='flex items-center gap-2 text-start font-medium underline-offset-4 hover:underline'
                          onClick={() => setPreview({ rel, nama: f.nama })}
                          title={`Pratinjau ${f.nama}`}
                        >
                          <FileText className='text-muted-foreground size-4 shrink-0' />
                          <span className='truncate'>{f.nama}</span>
                        </button>
                      </TableCell>
                      <TableCell className='max-md:hidden'>
                        <span className='capitalize'>{namaMatkul(f.slug)}</span>
                      </TableCell>
                      <TableCell className='max-sm:hidden'>
                        {String(f.sesi || '').replace('sesi-', 'S')}
                      </TableCell>
                      <TableCell className='text-muted-foreground max-sm:hidden'>
                        {formatBytes(f.ukuran)}
                      </TableCell>
                      <TableCell className='text-muted-foreground max-lg:hidden'>
                        {tanggal}
                      </TableCell>
                      <TableCell className='text-end'>
                        <div className='flex justify-end gap-0.5'>
                          <Button
                            size='icon-sm'
                            variant='ghost'
                            title={`Pratinjau ${f.nama}`}
                            onClick={() => setPreview({ rel, nama: f.nama })}
                          >
                            <Eye />
                          </Button>
                          <Button
                            size='icon-sm'
                            variant='ghost'
                            title={`Unduh ${f.nama}`}
                            onClick={() => unduh(rel)}
                          >
                            <Download />
                          </Button>
                          <Button
                            size='icon-sm'
                            variant='ghost'
                            title={`Hapus ${f.nama}`}
                            onClick={() =>
                              setHapus({
                                title: 'Hapus berkas ini?',
                                message: `${f.nama} akan dihapus permanen dari penyimpanan. Berkas lain di sesi ini tidak ikut terhapus.`,
                                body: { slug: f.slug, sesi: f.sesi, nama: f.nama },
                              })
                            }
                          >
                            <Trash2 className='text-destructive' />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {files.length ? (
        <Card className='border-dashed py-4 shadow-none ring-0'>
          <CardContent className='flex flex-wrap items-center gap-2 px-5 text-xs'>
            <span className='text-muted-foreground'>
              Hapus seluruh hasil satu mata kuliah:
            </span>
            {[...new Set(files.map((f) => f.slug))].map((slug) => (
              <Button
                key={slug}
                size='sm'
                variant='outline'
                className='h-7 capitalize'
                onClick={() =>
                  setHapus({
                    title: `Hapus semua hasil ${namaMatkul(slug)}?`,
                    message: `Seluruh hasil ${namaMatkul(slug)} beserta semua DOCX di dalamnya dihapus permanen. Tidak bisa dibatalkan.`,
                    body: { slug },
                  })
                }
              >
                <Trash2 className='text-destructive' /> {namaMatkul(slug)}
              </Button>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <PreviewDialog preview={preview} onClose={() => setPreview(null)} />

      <ConfirmDialog
        open={Boolean(hapus)}
        onOpenChange={(open) => !open && setHapus(null)}
        title={hapus?.title || ''}
        message={hapus?.message || ''}
        onConfirm={konfirmasiHapus}
        busy={busy}
      />
    </div>
  )
}

function PreviewDialog({
  preview,
  onClose,
}: {
  preview: { rel: string; nama: string } | null
  onClose: () => void
}) {
  // PDF pratinjau dibuat server dari DOCX dan dihapus saat pratinjau ditutup.
  const { url, loading, error } = usePratinjauPdf(preview ? { rel: preview.rel } : null)

  return (
    <Dialog open={Boolean(preview)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className='flex h-[92vh] max-h-[92vh] w-[96vw] max-w-[calc(210mm+8rem)] flex-col sm:max-w-[calc(210mm+8rem)]'>
        <DialogHeader>
          <DialogTitle className='truncate'>{preview?.nama}</DialogTitle>
          <DialogDescription>Pratinjau dokumen DOCX</DialogDescription>
        </DialogHeader>
        <div className='bg-slate-100 min-h-0 flex-1 overflow-hidden rounded-md border'>
          {loading && (
            <div className='space-y-2 p-6'>
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className='h-4 w-full' />
              ))}
            </div>
          )}
          {error && <p className='text-destructive p-6 text-sm'>{error}</p>}
          {url && (
            <iframe
              title={preview?.nama ?? 'Pratinjau'}
              src={`${url}#view=FitH`}
              className='h-full w-full border-0 bg-slate-100'
            />
          )}
        </div>
        <div className='flex justify-end gap-2'>
          <Button
            variant='outline'
            disabled={!preview}
            onClick={() => preview && unduh(preview.rel)}
          >
            <Download /> Unduh
          </Button>
          <Button onClick={onClose}>Tutup</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
