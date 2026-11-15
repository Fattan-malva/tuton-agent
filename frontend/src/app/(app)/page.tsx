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

export default function DashboardPage() {
  const status = useSWR<StatusInfo>('/api/status')
  const jobs = useSWR<Job[]>('/api/jobs')
  const moodle = useSWR<{ masuk: boolean; pesan: string }>('/api/moodle-status')
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
      desc: moodle.isLoading
        ? 'Memeriksa koneksi...'
        : moodle.data?.pesan || 'Status koneksi Moodle',
    },
    {
      title: 'Mata kuliah',
      icon: Users,
      value: courses.data ? String(courses.data.length) : undefined,
      desc: courses.data ? 'terdaftar di akun' : 'Memuat daftar...',
    },
    {
      title: 'Job aktif',
      icon: Terminal,
      value: jobs.data ? String(aktif) : undefined,
      desc: jobs.data
        ? `${jobs.data.length} job tercatat`
        : 'Memuat daftar job...',
    },
    {
      title: 'Job terakhir',
      icon: ListTodo,
      value: last ? JOB_LABEL[last.status] || last.status : '—',
      desc: last ? last.matkul : 'belum ada job',
    },
    {
      title: 'Provider',
      icon: Bot,
      value: status.data?.providers,
      desc: status.data ? `Python ${status.data.python}` : 'Memuat...',
    },
  ]

  return (
    <div className='space-y-6'>
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

      <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-5'>
        {cards.map((card) => (
          <Card key={card.title} className='gap-2'>
            <CardHeader className='flex-row items-center justify-between space-y-0'>
              <CardTitle className='text-sm font-medium text-muted-foreground'>
                {card.title}
              </CardTitle>
              <card.icon className='size-4 text-muted-foreground' />
            </CardHeader>
            <CardContent>
              {card.value === undefined ? (
                <>
                  <Skeleton className='h-8 w-24' />
                  <Skeleton className='mt-2 h-3.5 w-32' />
                </>
              ) : (
                <>
                  <div className='truncate text-2xl font-semibold tracking-tight'>
                    {card.value}
                  </div>
                  <p className='mt-1 line-clamp-2 text-xs text-muted-foreground'>
                    {card.desc || '—'}
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className='grid gap-4 lg:grid-cols-7'>
        <Card className='lg:col-span-4'>
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
              <p className='py-12 text-center text-sm text-destructive'>
                {String((nilai.error as Error).message)}
              </p>
            ) : nilai.data?.error ? (
              <p className='py-12 text-center text-sm text-muted-foreground'>
                {nilai.data.error}
              </p>
            ) : !nilai.data?.courses?.length ? (
              <p className='py-12 text-center text-sm text-muted-foreground'>
                Belum ada nilai Diskusi/Tugas yang bisa diambil.
              </p>
            ) : (
              <NilaiChart data={nilai.data} />
            )}
          </CardContent>
        </Card>

        <Card className='lg:col-span-3'>
          <CardHeader className='flex-row items-start justify-between space-y-0'>
            <div className='space-y-1'>
              <CardTitle>Job terakhir</CardTitle>
              <CardDescription>5 job terbaru di sesi ini.</CardDescription>
            </div>
            <Button asChild size='sm' variant='ghost'>
              <Link href='/log'>
                Semua <ArrowUpRight />
              </Link>
            </Button>
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
              <p className='py-8 text-center text-sm text-muted-foreground'>
                Belum ada job. Mulai dari Kerjakan Tugas.
              </p>
            ) : (
              <ul className='space-y-1'>
                {jobs.data.slice(0, 5).map((job) => (
                  <li key={job.id}>
                    <Link
                      href={`/log/?job=${encodeURIComponent(job.id)}`}
                      className='flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-accent'
                    >
                      <span className='flex size-9 shrink-0 items-center justify-center rounded-lg border bg-muted text-[10px] font-semibold uppercase'>
                        {job.kind === 'manual' ? 'MN' : 'SC'}
                      </span>
                      <span className='min-w-0 flex-1'>
                        <span className='block truncate text-sm font-medium'>
                          {job.matkul}
                          {job.sesi ? ` · sesi ${job.sesi}` : ''}
                        </span>
                        <span className='block truncate text-xs text-muted-foreground'>
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
            className='group rounded-xl border bg-card p-4 transition-colors hover:bg-accent'
          >
            <item.icon className='size-5 text-muted-foreground' />
            <p className='mt-3 text-sm font-medium'>{item.title}</p>
            <p className='mt-1 text-xs text-muted-foreground'>{item.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
