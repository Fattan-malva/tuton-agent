'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { CalendarDays, X } from 'lucide-react'
import type { Course, CourseSession, JadwalItem } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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
    <div className='space-y-6'>
      <PageHeader
        title='Courses'
        description='Daftar mata kuliah Moodle, sesi dengan soal, jadwal, dan status pengumpulan.'
      >
        <Badge variant='secondary'>{courses?.length ?? 0} mata kuliah</Badge>
      </PageHeader>

      {error ? (
        <p className='text-sm text-destructive'>
          {String((error as Error).message)}
        </p>
      ) : null}

      <div className='overflow-hidden rounded-lg border'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Mata kuliah</TableHead>
              <TableHead>Kode</TableHead>
              <TableHead>Kelas</TableHead>
              <TableHead className='text-end'>Sesi</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      <Skeleton className='h-4 w-64' />
                    </TableCell>
                    <TableCell>
                      <Skeleton className='h-4 w-16' />
                    </TableCell>
                    <TableCell>
                      <Skeleton className='h-4 w-10' />
                    </TableCell>
                    <TableCell>
                      <Skeleton className='ms-auto h-4 w-20' />
                    </TableCell>
                  </TableRow>
                ))
              : (courses || []).map((c) => (
                  <TableRow
                    key={c.id}
                    className='cursor-pointer'
                    data-state={selected === c.id ? 'selected' : undefined}
                    onClick={() => setSelected(c.id)}
                  >
                    <TableCell className='font-medium'>{c.nama}</TableCell>
                    <TableCell>{c.kode}</TableCell>
                    <TableCell>{c.kelas}</TableCell>
                    <TableCell className='text-end'>
                      <span className='inline-flex items-center gap-1 text-xs text-muted-foreground'>
                        <CalendarDays className='size-3.5' /> lihat sesi
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>

      {!isLoading && !courses?.length ? (
        <p className='text-sm text-muted-foreground'>
          Tidak ada mata kuliah (cek cookie Moodle).
        </p>
      ) : null}

      {selected ? (
        <div className='space-y-4 rounded-xl border bg-card p-4'>
          <div className='flex flex-wrap items-start justify-between gap-2'>
            <div className='space-y-1'>
              <h2 className='text-lg font-semibold tracking-tight'>
                {course?.nama || 'Mata kuliah'}
              </h2>
              <div className='flex flex-wrap gap-1.5'>
                {course?.kode ? (
                  <Badge variant='outline'>{course.kode}</Badge>
                ) : null}
                {course?.kelas ? (
                  <Badge variant='secondary'>Kelas {course.kelas}</Badge>
                ) : null}
                <Badge variant='outline'>{items.length} aktivitas</Badge>
              </div>
            </div>
            <Button
              size='sm'
              variant='ghost'
              onClick={() => setSelected(null)}
            >
              <X /> Tutup
            </Button>
          </div>

          <div>
            <h3 className='mb-2 text-sm font-semibold text-muted-foreground'>
              Sesi dengan soal
            </h3>
            {sesi.isLoading ? (
              <div className='flex gap-2'>
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className='h-6 w-28' />
                ))}
              </div>
            ) : sesi.error ? (
              <p className='text-sm text-destructive'>
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
              <p className='text-sm text-muted-foreground'>tidak ada</p>
            )}
          </div>

          <div>
            <h3 className='mb-2 text-sm font-semibold text-muted-foreground'>
              Jadwal Diskusi &amp; Tugas
            </h3>
            <Card>
              <CardContent>
                {jadwal.isLoading ? (
                  <Skeleton className='h-[300px] w-full' />
                ) : jadwal.error ? (
                  <p className='text-sm text-destructive'>
                    {String((jadwal.error as Error).message)}
                  </p>
                ) : jadwal.data?.error ? (
                  <p className='text-sm text-muted-foreground'>
                    Jadwal tidak bisa dimuat: {jadwal.data.error}
                  </p>
                ) : !items.filter((i) => i.tenggat).length ? (
                  <p className='text-sm text-muted-foreground'>
                    Belum ada Diskusi/Tugas dengan tenggat di course ini.
                  </p>
                ) : (
                  <JadwalCalendar items={items.filter((i) => i.tenggat)} />
                )}
              </CardContent>
            </Card>
          </div>

          <div>
            <h3 className='mb-2 text-sm font-semibold text-muted-foreground'>
              Status Tugas &amp; Diskusi
            </h3>
            <Card>
              <CardContent>
                {jadwal.isLoading ? (
                  <div className='space-y-2'>
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Skeleton key={i} className='h-9 w-full' />
                    ))}
                  </div>
                ) : !items.length ? (
                  <p className='text-sm text-muted-foreground'>
                    Belum ada Tugas/Diskusi di course ini.
                  </p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Aktivitas</TableHead>
                        <TableHead>Tenggat</TableHead>
                        <TableHead>Nilai</TableHead>
                        <TableHead>Feedback</TableHead>
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
                            <div className='text-xs text-muted-foreground'>
                              {item.jenis} {item.nomor} · Sesi {item.sesi}
                            </div>
                          </TableCell>
                          <TableCell>{item.tenggat || '—'}</TableCell>
                          <TableCell>{item.nilai ?? '—'}</TableCell>
                          <TableCell className='max-w-[420px] align-top'>
                            {item.feedback ? (
                              <details>
                                <summary className='cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground'>
                                  Lihat feedback
                                </summary>
                                <p className='mt-1 whitespace-pre-line text-xs leading-relaxed'>
                                  {item.feedback}
                                </p>
                              </details>
                            ) : (
                              <span className='text-xs text-muted-foreground'>
                                —
                              </span>
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
          </div>
        </div>
      ) : null}
    </div>
  )
}
