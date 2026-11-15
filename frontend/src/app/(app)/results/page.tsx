'use client'

import { useMemo, useState } from 'react'
import useSWR from 'swr'
import { Download, Eye, FileText, Search, Trash2 } from 'lucide-react'
import { postJSON } from '@/lib/api'
import type { ResultFile } from '@/lib/types'
import { formatBytes } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
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

function namaMatkul(slug: string) {
  return String(slug || 'Lainnya').replace(/-/g, ' ')
}

type Hapus = {
  title: string
  message: string
  body: Record<string, string>
}

export default function ResultsPage() {
  const { data, isLoading, error, mutate } = useSWR<ResultFile[]>(
    '/api/results',
  )
  const [cari, setCari] = useState('')
  const [preview, setPreview] = useState<{
    rel: string
    nama: string
  } | null>(null)
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
    <div className='space-y-6'>
      <PageHeader
        title='Result'
        description='Dokumen DOCX hasil pipeline. Klik nama berkas untuk pratinjau.'
      >
        <Badge variant='secondary'>{files.length} DOCX</Badge>
      </PageHeader>

      {msg ? <p className='text-sm text-destructive'>{msg}</p> : null}

      <Card>
        <CardHeader className='flex-row items-center justify-between gap-3 space-y-0'>
          <CardTitle className='text-base'>Berkas hasil</CardTitle>
          <div className='relative w-full max-w-64'>
            <Search className='pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground' />
            <Input
              value={cari}
              onChange={(e) => setCari(e.target.value)}
              placeholder='Cari berkas, mata kuliah, sesi...'
              className='ps-8'
              aria-label='Cari berkas hasil'
            />
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className='space-y-2'>
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className='h-11 w-full' />
              ))}
            </div>
          ) : error ? (
            <p className='py-10 text-center text-sm text-destructive'>
              {String((error as Error).message)}
            </p>
          ) : !files.length ? (
            <div className='flex flex-col items-center justify-center py-14 text-center'>
              <FileText className='mb-3 size-10 text-muted-foreground' />
              <h2 className='text-lg font-semibold'>Belum ada hasil</h2>
              <p className='mt-1 text-sm text-muted-foreground'>
                Dokumen DOCX dari tugas yang selesai akan muncul di sini.
              </p>
            </div>
          ) : !tersaring.length ? (
            <p className='py-10 text-center text-sm text-muted-foreground'>
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
                  <TableHead className='max-md:hidden'>Tanggal</TableHead>
                  <TableHead className='w-28 text-end'>Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tersaring.map((f) => {
                  const rel = `${f.slug}/${f.sesi}/${f.nama}`
                  const tanggal = f.waktu
                    ? new Date(Number(f.waktu) * 1000).toLocaleDateString(
                        'id-ID',
                        { day: '2-digit', month: 'short', year: 'numeric' },
                      )
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
                          <FileText className='size-4 shrink-0 text-muted-foreground' />
                          <span className='truncate'>{f.nama}</span>
                        </button>
                      </TableCell>
                      <TableCell className='max-md:hidden'>
                        <span className='capitalize'>
                          {namaMatkul(f.slug)}
                        </span>
                      </TableCell>
                      <TableCell className='max-sm:hidden'>
                        {String(f.sesi || '').replace('sesi-', 'S')}
                      </TableCell>
                      <TableCell className='max-sm:hidden text-muted-foreground'>
                        {formatBytes(f.ukuran)}
                      </TableCell>
                      <TableCell className='max-md:hidden text-muted-foreground'>
                        {tanggal}
                      </TableCell>
                      <TableCell className='text-end'>
                        <div className='flex justify-end gap-0.5'>
                          <Button
                            size='icon'
                            variant='ghost'
                            className='size-8'
                            title={`Pratinjau ${f.nama}`}
                            onClick={() => setPreview({ rel, nama: f.nama })}
                          >
                            <Eye />
                          </Button>
                          <Button
                            asChild
                            size='icon'
                            variant='ghost'
                            className='size-8'
                          >
                            <a
                              href={`/api/download-output/${encodeRel(rel)}`}
                              title={`Unduh ${f.nama}`}
                            >
                              <Download />
                            </a>
                          </Button>
                          <Button
                            size='icon'
                            variant='ghost'
                            className='size-8'
                            title={`Hapus ${f.nama}`}
                            onClick={() =>
                              setHapus({
                                title: 'Hapus berkas ini?',
                                message: `${f.nama} akan dihapus permanen dari disk. Berkas lain di sesi ini tidak ikut terhapus.`,
                                body: {
                                  slug: f.slug,
                                  sesi: f.sesi,
                                  nama: f.nama,
                                },
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
        <div className='flex flex-wrap items-center gap-2 rounded-xl border border-dashed p-3 text-xs text-muted-foreground'>
          <span>Hapus seluruh hasil satu mata kuliah:</span>
          {[...new Set(files.map((f) => f.slug))].map((slug) => (
            <Button
              key={slug}
              size='sm'
              variant='outline'
              className='h-7 capitalize'
              onClick={() =>
                setHapus({
                  title: `Hapus semua hasil ${namaMatkul(slug)}?`,
                  message: `Seluruh folder output/${namaMatkul(slug)} beserta semua DOCX di dalamnya dihapus permanen. Tidak bisa dibatalkan.`,
                  body: { slug },
                })
              }
            >
              <Trash2 className='text-destructive' /> {namaMatkul(slug)}
            </Button>
          ))}
        </div>
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
  const enc = preview ? encodeRel(preview.rel) : null
  const { data, isLoading, error } = useSWR<{ html: string }>(
    enc ? `/api/results/preview/${enc}` : null,
  )

  return (
    <Dialog open={Boolean(preview)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className='flex max-h-[85vh] max-w-3xl flex-col'>
        <DialogHeader>
          <DialogTitle className='truncate'>{preview?.nama}</DialogTitle>
          <DialogDescription>Pratinjau dokumen DOCX</DialogDescription>
        </DialogHeader>
        <div className='min-h-0 flex-1 overflow-auto rounded-md border p-4'>
          {isLoading ? (
            <div className='space-y-2'>
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className='h-4 w-full' />
              ))}
            </div>
          ) : error ? (
            <p className='text-sm text-destructive'>
              {String((error as Error).message)}
            </p>
          ) : data?.html?.trim() ? (
            <div
              className='prose prose-sm max-w-none dark:prose-invert'
              dangerouslySetInnerHTML={{ __html: data.html }}
            />
          ) : (
            <p className='text-sm text-muted-foreground'>
              Dokumen tidak memiliki teks yang bisa ditampilkan.
            </p>
          )}
        </div>
        <div className='flex justify-end gap-2'>
          <Button asChild variant='outline'>
            <a href={`/api/download-output/${enc}`}>
              <Download /> Unduh
            </a>
          </Button>
          <Button onClick={onClose}>Tutup</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
