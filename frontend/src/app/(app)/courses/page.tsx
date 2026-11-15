'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { BookOpen, CalendarDays, X } from 'lucide-react'
import type { Course, CourseSession, JadwalItem } from '@/lib/types'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { JadwalCalendar } from '@/components/jadwal-calendar'
import { PageHeader } from '@/components/page-header'
import { cn } from '@/lib/utils'

function statusBadge(item: JadwalItem) {
  if (item.status_pengumpulan === 'submitted')
    return <Badge variant='secondary'>sudah dikumpulkan</Badge>
  if (item.status_pengumpulan === 'not_submitted')
    return <Badge variant='destructive'>belum dikumpulkan</Badge>
  return <Badge variant='outline'>tidak diketahui</Badge>
}

export default function CoursesPage() {
  const { data: courses, isLoading, error } = useSWR<Course[]>('/api/courses')
  const [selected, setSelected] = useState<string | null>(null)

  const sesi = useSWR<CourseSession[]>(
    selected ? `/api/courses/${encodeURIComponent(selected)}/sessions` : null,
  )
  const jadwal = useSWR<{ items: JadwalItem[]; error?: string }>(
    selected ? `/api/jadwal/${encodeURIComponent(selected)}` : null,
  )

  const course = (courses || []).find((c) => c.id === selected)
  const items = jadwal.data?.items || []

  return (
    <div className='flex flex-col gap-4'>
      <PageHeader
        title='Courses'
        description='Daftar mata kuliah Moodle, sesi dengan soal, jadwal, dan status pengumpulan.'
      >
        <Badge variant='secondary'>{courses?.length ?? 0} mata kuliah</Badge>
      </PageHeader>

      {error ? (
        <p className='text-destructive text-sm'>
          {String((error as Error).message)}
        </p>
      ) : null}

      <div className='grid gap-4 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)] lg:items-start'>
        <Card className='gap-2 py-4 lg:sticky lg:top-[calc(var(--header-h)+1rem)] lg:max-h-[calc(100svh-var(--header-h)-2rem)] lg:overflow-y-auto'>
          <CardHeader className='px-4'>
            <CardTitle className='text-sm'>Mata kuliah</CardTitle>
            <CardDescription className='text-xs'>
              Pilih untuk melihat sesi dan jadwal.
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-1 px-2'>
            {isLoading
              ? Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className='h-14 w-full' />
                ))
              : (courses || []).map((c) => (
                  <button
                    key={c.id}
                    type='button'
                    onClick={() => setSelected(c.id)}
                    aria-pressed={selected === c.id}
                    className={cn(
                      'hover:bg-accent/60 flex w-full items-start gap-3 rounded-md px-2 py-2.5 text-start transition-colors',
                      selected === c.id && 'bg-accent',
                    )}
                  >
                    <span className='bg-primary/10 text-primary mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-sm'>
                      <BookOpen className='size-3.5' />
                    </span>
                    <span className='min-w-0 flex-1'>
                      <span className='block truncate text-sm font-medium'>
                        {c.nama}
                      </span>
                      <span className='text-muted-foreground mt-0.5 flex flex-wrap gap-1.5 text-[11px]'>
                        {c.kode ? <span>{c.kode}</span> : null}
                        {c.kelas ? <span>· kelas {c.kelas}</span> : null}
                      </span>
                    </span>
                    <CalendarDays className='text-muted-foreground mt-1 size-3.5 shrink-0' />
                  </button>
                ))}

            {!isLoading && !courses?.length ? (
              <p className='text-muted-foreground px-2 py-4 text-sm'>
                Tidak ada mata kuliah (cek cookie Moodle).
              </p>
            ) : null}
          </CardContent>
        </Card>

        <div className='min-w-0 space-y-4'>
          {!selected ? (
            <Card className='border-dashed shadow-none ring-0'>
              <CardContent className='flex flex-col items-center justify-center py-20 text-center'>
                <span className='bg-primary/10 text-primary mb-4 flex size-11 items-center justify-center rounded-md'>
                  <BookOpen className='size-5' />
                </span>
                <p className='text-base font-semibold'>Pilih mata kuliah</p>
                <p className='text-muted-foreground mt-1 max-w-xs text-sm'>
                  Sesi dengan soal, jadwal Diskusi/Tugas, dan status pengumpulan
                  muncul di sini.
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              <Card className='gap-4 py-5'>
                <CardHeader className='gap-2 px-5'>
                  <CardTitle className='text-lg'>{course?.nama || 'Mata kuliah'}</CardTitle>
                  <div className='flex flex-wrap gap-1.5'>
                    {course?.kode ? <Badge variant='outline'>{course.kode}</Badge> : null}
                    {course?.kelas ? (
                      <Badge variant='secondary'>Kelas {course.kelas}</Badge>
                    ) : null}
                    <Badge variant='outline'>{items.length} aktivitas</Badge>
                  </div>
                  <CardAction>
                    <Button size='sm' variant='ghost' onClick={() => setSelected(null)}>
                      <X /> Tutup
                    </Button>
                  </CardAction>
                </CardHeader>
                <CardContent className='px-5'>
                  <h3 className='text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase'>
                    Sesi dengan soal
                  </h3>
                  {sesi.isLoading ? (
                    <div className='flex flex-wrap gap-2'>
                      {Array.from({ length: 4 }).map((_, i) => (
                        <Skeleton key={i} className='h-6 w-28' />
                      ))}
                    </div>
                  ) : sesi.error ? (
                    <p className='text-destructive text-sm'>
                      {String((sesi.error as Error).message)}
                    </p>
                  ) : sesi.data?.length ? (
                    <div className='flex flex-wrap gap-2'>
                      {sesi.data.map((s) => (
                        <Badge key={s.sesi} variant='secondary'>
                          Sesi {s.sesi} — {s.jumlah ?? 0} soal
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className='text-muted-foreground text-sm'>tidak ada</p>
                  )}
                </CardContent>
              </Card>

              {jadwal.isLoading ? (
                <Skeleton className='h-[360px] w-full' />
              ) : jadwal.error ? (
                <p className='text-destructive text-sm'>
                  {String((jadwal.error as Error).message)}
                </p>
              ) : jadwal.data?.error ? (
                <p className='text-muted-foreground text-sm'>
                  Jadwal tidak bisa dimuat: {jadwal.data.error}
                </p>
              ) : !items.filter((i) => i.tenggat).length ? (
                <Card>
                  <CardContent className='text-muted-foreground py-10 text-center text-sm'>
                    Belum ada Diskusi/Tugas dengan tenggat di course ini.
                  </CardContent>
                </Card>
              ) : (
                <JadwalCalendar items={items.filter((i) => i.tenggat)} />
              )}

              <Card className='gap-4 py-5'>
                <CardHeader className='px-5'>
                  <CardTitle className='text-base'>Status Tugas &amp; Diskusi</CardTitle>
                  <CardDescription>
                    Klik nama aktivitas untuk membuka tautannya di Moodle.
                  </CardDescription>
                </CardHeader>
                <CardContent className='px-5'>
                  {jadwal.isLoading ? (
                    <div className='space-y-2'>
                      {Array.from({ length: 5 }).map((_, i) => (
                        <Skeleton key={i} className='h-9 w-full' />
                      ))}
                    </div>
                  ) : !items.length ? (
                    <p className='text-muted-foreground text-sm'>
                      Belum ada Tugas/Diskusi di course ini.
                    </p>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Aktivitas</TableHead>
                          <TableHead>Tenggat</TableHead>
                          <TableHead>Nilai</TableHead>
                          <TableHead className='max-lg:hidden'>Feedback</TableHead>
                          <TableHead>Status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {items.map((item) => (
                          <TableRow key={`${item.url}-${item.sesi}-${item.nomor}`}>
                            <TableCell>
                              <a
                                href={item.url}
                                target='_blank'
                                rel='noopener noreferrer'
                                className='font-medium underline-offset-4 hover:underline'
                              >
                                {item.nama}
                              </a>
                              <div className='text-muted-foreground text-xs'>
                                <span
                                  className={cn(
                                    'font-medium',
                                    item.jenis.toLowerCase() === 'tugas'
                                      ? 'text-tugas'
                                      : 'text-diskusi',
                                  )}
                                >
                                  {item.jenis}
                                </span>{' '}
                                {item.nomor} · Sesi {item.sesi}
                              </div>
                            </TableCell>
                            <TableCell className='whitespace-nowrap text-sm'>
                              {item.tenggat || '—'}
                            </TableCell>
                            <TableCell>{item.nilai ?? '—'}</TableCell>
                            <TableCell className='max-w-[420px] align-top max-lg:hidden'>
                              {item.feedback ? (
                                <details>
                                  <summary className='text-muted-foreground hover:text-foreground cursor-pointer text-xs font-medium'>
                                    Lihat feedback
                                  </summary>
                                  <p className='mt-1 text-xs leading-relaxed whitespace-pre-line'>
                                    {item.feedback}
                                  </p>
                                </details>
                              ) : (
                                <span className='text-muted-foreground text-xs'>—</span>
                              )}
                            </TableCell>
                            <TableCell>{statusBadge(item)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
