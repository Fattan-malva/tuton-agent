'use client'

import Link from 'next/link'
import useSWR from 'swr'
import {
  ArrowUpRight,
  BookOpen,
  Bot,
  FileText,
  ListTodo,
  Plus,
  Terminal,
  Users,
  Wrench,
} from 'lucide-react'
import type { Course, Job, NilaiData, StatusInfo } from '@/lib/types'
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
import { Skeleton } from '@/components/ui/skeleton'
import { NilaiChart } from '@/components/nilai-chart'
import { PageHeader } from '@/components/page-header'

const JOB_LABEL: Record<string, string> = {
  queued: 'antre',
  running: 'berjalan',
  stopping: 'menghentikan',
  done: 'selesai',
  error: 'gagal',
  stopped: 'dihentikan',
}

const JOB_VARIANT: Record<
  string,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  running: 'default',
  queued: 'secondary',
  stopping: 'outline',
  done: 'secondary',
  error: 'destructive',
  stopped: 'outline',
}

/** Kartu statistik gaya template: chip ikon, angka besar, judul, keterangan. */
function StatCard({
  icon: Icon,
  value,
  title,
  hint,
}: {
  icon: typeof BookOpen
  value?: string
  title: string
  hint: string
}) {
  return (
    <Card className='gap-4 py-4'>
      <CardHeader className='gap-3'>
        <div className='bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-sm'>
          <Icon className='size-4' />
        </div>
        {value === undefined ? (
          <Skeleton className='h-7 w-20' />
        ) : (
          <span className='text-2xl font-semibold tracking-tight'>{value}</span>
        )}
      </CardHeader>
      <CardContent className='flex flex-col gap-1'>
        <span className='text-sm font-medium'>{title}</span>
        <span className='text-muted-foreground line-clamp-2 text-xs'>
          {hint || '—'}
        </span>
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const jobs = useSWR<Job[]>('/api/jobs')
  const moodle = useSWR<{ masuk: boolean; pesan: string }>('/api/moodle/status')
  const status = useSWR<StatusInfo>('/api/status')
  const courses = useSWR<Course[]>('/api/courses')
  const nilai = useSWR<NilaiData>('/api/nilai')

  const last = jobs.data?.[0]
  const aktif = jobs.data?.filter(
    (j) => j.status === 'running' || j.status === 'queued',
  ).length

  const cards = [
    {
      title: 'Moodle',
      icon: BookOpen,
      value: moodle.isLoading
        ? undefined
        : moodle.data?.masuk
          ? 'Masuk'
          : 'Belum',
      hint: moodle.isLoading
        ? 'Memeriksa koneksi...'
        : moodle.data?.pesan || 'Status koneksi Moodle',
    },
    {
      title: 'Mata kuliah',
      icon: Users,
      value: courses.data ? String(courses.data.length) : undefined,
      hint: courses.data ? 'terdaftar di akun' : 'Memuat daftar...',
    },
    {
      title: 'Job aktif',
      icon: Terminal,
      value: jobs.data ? String(aktif) : undefined,
      hint: jobs.data
        ? `${jobs.data.length} job tercatat`
        : 'Memuat daftar job...',
    },
    {
      title: 'Job terakhir',
      icon: ListTodo,
      value: last ? JOB_LABEL[last.status] || last.status : '—',
      hint: last ? last.matkul : 'belum ada job',
    },
    {
      title: 'Provider',
      icon: Bot,
      value: status.data?.providers,
      hint: status.data ? `Python ${status.data.python}` : 'Memuat...',
    },
  ]

  return (
    <div className='flex flex-col gap-4'>
      <PageHeader
        title='Dashboard'
        description='Ringkasan pipeline tutor, nilai, dan job terakhir.'
      >
        <Button asChild size='sm'>
          <Link href='/buat'>
            <Plus /> Kerjakan Tugas
          </Link>
        </Button>
        <Button asChild size='sm' variant='outline'>
          <Link href='/log'>
            <Terminal /> Log Live
          </Link>
        </Button>
      </PageHeader>

      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5'>
        {cards.map((card) => (
          <StatCard
            key={card.title}
            icon={card.icon}
            value={card.value}
            title={card.title}
            hint={card.hint}
          />
        ))}
      </div>

      <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,380px)]'>
        <Card>
          <CardHeader>
            <CardTitle>Nilai per sesi</CardTitle>
            <CardDescription>
              Diskusi &amp; Tugas semua mata kuliah, klik legenda untuk
              menyembunyikan garis.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {nilai.isLoading ? (
              <div className='space-y-3'>
                <Skeleton className='h-8 w-52' />
                <Skeleton className='h-[300px] w-full' />
              </div>
            ) : nilai.error ? (
              <p className='text-destructive py-12 text-center text-sm'>
                {String((nilai.error as Error).message)}
              </p>
            ) : nilai.data?.error ? (
              <p className='text-muted-foreground py-12 text-center text-sm'>
                {nilai.data.error}
              </p>
            ) : !nilai.data?.courses?.length ? (
              <p className='text-muted-foreground py-12 text-center text-sm'>
                Belum ada nilai Diskusi/Tugas yang bisa diambil.
              </p>
            ) : (
              <NilaiChart data={nilai.data} />
            )}
          </CardContent>
        </Card>

        <Card className='gap-3'>
          <CardHeader>
            <CardTitle>Job terakhir</CardTitle>
            <CardDescription>5 job terbaru di sesi ini.</CardDescription>
            <CardAction>
              <Button asChild size='sm' variant='ghost'>
                <Link href='/log'>
                  Semua <ArrowUpRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            {jobs.isLoading ? (
              <div className='space-y-4'>
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className='flex items-center gap-3'>
                    <Skeleton className='size-9 rounded-lg' />
                    <div className='flex-1 space-y-1.5'>
                      <Skeleton className='h-3.5 w-40' />
                      <Skeleton className='h-3 w-24' />
                    </div>
                  </div>
                ))}
              </div>
            ) : !jobs.data?.length ? (
              <p className='text-muted-foreground py-8 text-center text-sm'>
                Belum ada job. Mulai dari Kerjakan Tugas.
              </p>
            ) : (
              <ul className='space-y-1'>
                {jobs.data.slice(0, 5).map((job) => (
                  <li key={job.id}>
                    <Link
                      href={`/log/?job=${encodeURIComponent(job.id)}`}
                      className='hover:bg-accent flex items-center gap-3 rounded-md px-2 py-2 transition-colors'
                    >
                      <span className='bg-muted flex size-9 shrink-0 items-center justify-center rounded-sm text-[10px] font-semibold uppercase'>
                        {job.kind === 'manual' ? 'MN' : 'SC'}
                      </span>
                      <span className='min-w-0 flex-1'>
                        <span className='block truncate text-sm font-medium'>
                          {job.matkul}
                          {job.sesi ? ` · sesi ${job.sesi}` : ''}
                        </span>
                        <span className='text-muted-foreground block truncate text-xs'>
                          {job.id} · {job.jenis || job.kind}
                        </span>
                      </span>
                      <Badge
                        variant={JOB_VARIANT[job.status] || 'outline'}
                        className='shrink-0'
                      >
                        {JOB_LABEL[job.status] || job.status}
                      </Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
        {[
          {
            title: 'Kerjakan dari Moodle',
            desc: 'Scrape soal sesi lalu jalankan agent.',
            href: '/buat',
            icon: ListTodo,
          },
          {
            title: 'Input manual',
            desc: 'Tempel soal atau unggah berkas sendiri.',
            href: '/buat',
            icon: FileText,
          },
          {
            title: 'Lihat hasil DOCX',
            desc: 'Pratinjau dan unduh jawaban jadi.',
            href: '/results',
            icon: FileText,
          },
          {
            title: 'Pengaturan',
            desc: 'Model, cookie Moodle, dan tampilan.',
            href: '/settings',
            icon: Wrench,
          },
        ].map((item) => (
          <Link
            key={item.title}
            href={item.href}
            className='bg-card ring-foreground/10 hover:bg-accent/60 group flex items-start gap-3 rounded-xl p-4 shadow-xs ring-1 transition-colors'
          >
            <span className='bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-sm'>
              <item.icon className='size-4' />
            </span>
            <span className='min-w-0'>
              <span className='block text-sm font-medium'>{item.title}</span>
              <span className='text-muted-foreground mt-1 block text-xs'>
                {item.desc}
              </span>
            </span>
          </Link>
        ))}
      </div>
    </div>
  )
}
