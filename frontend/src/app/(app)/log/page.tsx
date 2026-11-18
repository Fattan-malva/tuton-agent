'use client'

import { Suspense, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { Copy, Pause, Play, RefreshCw, RotateCcw, Square, Trash2 } from 'lucide-react'
import { api, postJSON, streamUrl } from '@/lib/api'
import type { Job, LogEvent } from '@/lib/types'
import { cn, formatTime } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { PageHeader } from '@/components/page-header'
import { STATUS_LABEL, isLive } from '@/lib/job-status'


function LogSkeleton() {
  return (
    <div className='grid gap-4 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)]'>
      <div className='space-y-2'>
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className='h-14 w-full' />
        ))}
      </div>
      <Skeleton className='h-[60vh] w-full' />
    </div>
  )
}

function LogContent() {
  const router = useRouter()
  const search = useSearchParams()
  const { data: jobs, isLoading, mutate } = useSWR<Job[]>('/api/jobs', {
    refreshInterval: 4000,
  })
  const list = jobs || []
  const dipilih = search.get('job') || list[0]?.id || ''
  const selectedJob = list.find((j) => j.id === dipilih)
  const stoppable = selectedJob ? isLive(selectedJob.status) : false
  const bisaJeda = selectedJob?.status === 'running'
  const bisaLanjut = selectedJob?.status === 'paused'
  const bisaUlang =
    selectedJob?.status === 'error' || selectedJob?.status === 'stopped'

  const [lines, setLines] = useState<LogEvent[]>([])
  const [status, setStatus] = useState('siap')
  const [follow, setFollow] = useState(true)
  const [msg, setMsg] = useState('')
  const [busyStop, setBusyStop] = useState(false)
  const [hapusOpen, setHapusOpen] = useState(false)
  const [busyHapus, setBusyHapus] = useState(false)
  const consoleRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!dipilih) {
      setLines([])
      return
    }
    let cancelled = false
    let es: EventSource | null = null
    setLines([])
    setStatus('menghubungkan')

    ;(async () => {
      try {
        const evs = await api<LogEvent[]>(
          `/api/jobs/${encodeURIComponent(dipilih)}/events`,
        )
        if (cancelled) return
        setLines(Array.isArray(evs) ? evs : [])
        const after = (Array.isArray(evs) ? evs : []).reduce(
          (max, e) => Math.max(max, Number(e.seq) || 0),
          0,
        )
        es = new EventSource(
          await streamUrl(
            `/api/jobs/${encodeURIComponent(dipilih)}/stream?after=${after}`,
          ),
        )
        setStatus('mengalir')
        es.onmessage = (ev) => {
          try {
            setLines((prev) => [...prev, JSON.parse(ev.data) as LogEvent])
          } catch {
            /* abaikan baris rusak */
          }
        }
        es.addEventListener('done', (ev) => {
          let doneStatus = 'done'
          try {
            doneStatus = JSON.parse((ev as MessageEvent).data).status || 'done'
          } catch {
            /* abaikan */
          }
          setStatus(
            doneStatus === 'error'
              ? 'gagal'
              : doneStatus === 'stopped'
                ? 'dihentikan'
                : 'selesai',
          )
          setLines((prev) => [
            ...prev,
            {
              level: 'info',
              msg:
                doneStatus === 'stopped'
                  ? '\n=== job dihentikan ==='
                  : doneStatus === 'error'
                    ? '\n=== job gagal ==='
                    : '\n=== job selesai ===',
            },
          ])
          es?.close()
          mutate()
        })
        es.onerror = () => {
          if (!cancelled) setStatus('mencoba ulang')
        }
      } catch (e) {
        if (!cancelled) {
          setStatus('gagal memuat log')
          setMsg((e as Error).message)
        }
      }
    })()

    return () => {
      cancelled = true
      es?.close()
    }
  }, [dipilih, mutate])

  useEffect(() => {
    if (follow && consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight
    }
  }, [lines, follow])

  async function stopJob() {
    if (!dipilih) return
    setBusyStop(true)
    setMsg('')
    try {
      await postJSON(`/api/jobs/${encodeURIComponent(dipilih)}/stop`, {})
      mutate()
    } catch (e) {
      setMsg((e as Error).message)
    } finally {
      setBusyStop(false)
    }
  }

  async function aksiJob(aksi: 'pause' | 'resume' | 'retry') {
    if (!dipilih) return
    setMsg('')
    try {
      const r = await postJSON<{ job?: string }>(
        `/api/jobs/${encodeURIComponent(dipilih)}/${aksi}`,
        {},
      )
      if (aksi === 'retry' && r?.job) router.replace(`/log/?job=${encodeURIComponent(r.job)}`)
      mutate()
    } catch (e) {
      setMsg((e as Error).message)
    }
  }

  async function clearLog() {
    if (!dipilih) return
    setLines([])
    await api(`/api/jobs/${encodeURIComponent(dipilih)}/clear-log`, {
      method: 'POST',
    }).catch(() => {})
  }

  async function copyLog() {
    if (!consoleRef.current) return
    await navigator.clipboard.writeText(consoleRef.current.innerText).catch(() => {})
  }

  async function hapusJob() {
    if (!dipilih) return
    setBusyHapus(true)
    setMsg('')
    try {
      await postJSON(`/api/jobs/${encodeURIComponent(dipilih)}/delete`, {})
      setHapusOpen(false)
      router.replace('/log/')
      await mutate()
    } catch (e) {
      setMsg((e as Error).message)
    } finally {
      setBusyHapus(false)
    }
  }

  if (isLoading) return <LogSkeleton />

  return (
    <div className='space-y-6'>
      <PageHeader
        title='Log Live'
        description='Pantau job berjalan lewat streaming log. Hentikan atau hapus job dari sini.'
      />
      <div className='grid gap-4 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)] lg:items-start'>
        <aside className='bg-card ring-foreground/10 space-y-2 rounded-xl p-3 shadow-xs ring-1 lg:sticky lg:top-[calc(var(--header-h)+var(--page-header-h,0px)+1rem)] lg:max-h-[calc(100svh-var(--header-h)-var(--page-header-h,0px)-2rem)] lg:overflow-y-auto'>
          <div className='flex items-center justify-between'>
            <strong className='text-sm'>Daftar job</strong>
            <div className='flex items-center gap-1'>
              <Badge variant='secondary'>{list.length}</Badge>
              <Button
                size='icon'
                variant='ghost'
                className='size-7'
                title='Muat ulang daftar job'
                onClick={() => mutate()}
              >
                <RefreshCw />
              </Button>
            </div>
          </div>
          <div className='max-h-[54svh] space-y-1 overflow-y-auto rounded-lg border p-1'>
            {!list.length ? (
              <p className='p-3 text-xs text-muted-foreground'>
                Belum ada job. Jalankan dari menu Kerjakan Tugas.
              </p>
            ) : (
              list.map((job) => (
                <button
                  key={job.id}
                  type='button'
                  onClick={() => router.replace(`/log/?job=${encodeURIComponent(job.id)}`)}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-md px-2 py-2 text-start hover:bg-accent',
                    job.id === dipilih && 'bg-accent',
                  )}
                >
                  <span
                    className={cn(
                      'size-2 shrink-0 rounded-full',
                      job.status === 'running' && 'bg-blue-500',
                      job.status === 'queued' && 'bg-zinc-400',
                      job.status === 'done' && 'bg-green-500',
                      job.status === 'error' && 'bg-red-500',
                      job.status === 'stopped' && 'bg-red-400',
                      job.status === 'stopping' && 'bg-amber-500',
                      job.status === 'paused' && 'bg-amber-400',
                    )}
                  />
                  <span className='min-w-0 flex-1'>
                    <span className='block truncate text-sm font-medium'>
                      {job.matkul || 'manual'}
                      {job.sesi ? ` · sesi ${job.sesi}` : ''}
                    </span>
                    <span className='block truncate text-[11px] text-muted-foreground'>
                      {[job.id, job.jenis, job.kind === 'manual' ? 'manual' : '']
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </span>
                  <Badge variant='outline' className='shrink-0 text-[10px]'>
                    {STATUS_LABEL[job.status] || job.status}
                  </Badge>
                </button>
              ))
            )}
          </div>
        </aside>

        <section className='bg-card ring-foreground/10 min-w-0 space-y-2 rounded-xl p-3 shadow-xs ring-1'>
          <div className='flex flex-wrap items-center gap-2'>
            {bisaJeda ? (
              <Button size='sm' variant='outline' onClick={() => aksiJob('pause')}>
                <Pause /> Jeda job
              </Button>
            ) : null}
            {bisaLanjut ? (
              <Button size='sm' onClick={() => aksiJob('resume')}>
                <Play /> Lanjutkan job
              </Button>
            ) : null}
            {bisaUlang ? (
              <Button size='sm' variant='outline' onClick={() => aksiJob('retry')}>
                <RotateCcw /> Ulangi job
              </Button>
            ) : null}
            {stoppable ? (
              <Button
                size='sm'
                variant='destructive'
                onClick={stopJob}
                disabled={busyStop}
              >
                <Square /> {busyStop ? 'Menghentikan...' : 'Hentikan job'}
              </Button>
            ) : null}
            {selectedJob ? (
              <Button
                size='sm'
                variant='outline'
                onClick={() => setHapusOpen(true)}
              >
                <Trash2 /> Hapus job
              </Button>
            ) : null}
            {dipilih ? <Badge variant='secondary'>job {dipilih}</Badge> : null}
          </div>
          {msg ? <p className='text-sm text-destructive'>{msg}</p> : null}

          <div className='flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs'>
            <span
              className={cn(
                'font-medium',
                status === 'gagal' || status === 'gagal memuat log'
                  ? 'text-destructive'
                  : 'text-muted-foreground',
              )}
            >
              {status}
            </span>
            <span className='flex-1' />
            <Button size='sm' variant='outline' onClick={copyLog}>
              <Copy /> Salin
            </Button>
            <Button size='sm' variant='outline' onClick={clearLog}>
              Bersihkan
            </Button>
            <Button
              size='sm'
              variant={follow ? 'default' : 'outline'}
              onClick={() => setFollow((v) => !v)}
              aria-pressed={follow}
            >
              Gulir otomatis
            </Button>
          </div>

          <div ref={consoleRef} className='console'>
            {!dipilih ? (
              <span className='text-muted-foreground'>
                Belum ada job untuk ditampilkan.
              </span>
            ) : lines.length ? (
              lines.map((e, i) => (
                <span key={i} className={cn('ln', e.level || 'info')}>
                  {e.ts ? <span className='ts'>{formatTime(e.ts)}</span> : null}
                  {e.stage ? `[${e.stage}] ` : ''}
                  {e.agent ? `<${e.agent}> ` : ''}
                  {e.msg || ''}
                </span>
              ))
            ) : (
              <span className='text-muted-foreground'>Menunggu log...</span>
            )}
          </div>
        </section>
      </div>

      <ConfirmDialog
        open={hapusOpen}
        onOpenChange={setHapusOpen}
        title={`Hapus job ${dipilih}?`}
        message='Job beserta folder kerja dan lognya dihapus permanen. Hasil DOCX di tab Result tidak ikut terhapus.'
        onConfirm={hapusJob}
        busy={busyHapus}
      />
    </div>
  )
}

export default function LogPage() {
  return (
    <Suspense fallback={<LogSkeleton />}>
      <LogContent />
    </Suspense>
  )
}
