'use client'

import { useMemo, useState } from 'react'
import useSWR from 'swr'
import { Calculator, Info, RotateCcw } from 'lucide-react'
import type { Course, NilaiTotal } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PageHeader } from '@/components/page-header'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

type Kandidat = {
  metode: string
  nilai: number
  rumus: string
  berlaku: boolean
  alasan: string
}

function angka(nilai: string) {
  if (!nilai.trim()) return null
  const hasil = Number(nilai.replace(',', '.'))
  return Number.isFinite(hasil) ? hasil : null
}

function hitung(uas: number | null, maksimum: number, tuton: number | null, ttm: number | null) {
  if (uas === null || maksimum <= 0 || uas < 0 || uas > maksimum) return null
  const lolosUas = uas >= maksimum * 0.3
  const kandidat: Kandidat[] = [
    { metode: 'UAS murni', nilai: uas, rumus: 'UAS', berlaku: true, alasan: 'Selalu menjadi kandidat.' },
    {
      metode: 'UAS + Tuton',
      nilai: tuton === null ? uas : uas * 0.7 + tuton * 0.3,
      rumus: '(UAS × 70%) + (Tuton × 30%)',
      berlaku: lolosUas && tuton !== null && tuton > uas,
      alasan: !lolosUas ? 'UAS belum mencapai 30% nilai maksimum.' : tuton === null ? 'Nilai Tuton belum diisi.' : tuton <= uas ? 'Tuton tidak lebih tinggi dari UAS.' : 'Memenuhi syarat kontribusi Tuton.',
    },
    {
      metode: 'UAS + TTM/Tuweb',
      nilai: ttm === null ? uas : uas * 0.5 + ttm * 0.5,
      rumus: '(UAS × 50%) + (TTM × 50%)',
      berlaku: lolosUas && ttm !== null && ttm > uas,
      alasan: !lolosUas ? 'UAS belum mencapai 30% nilai maksimum.' : ttm === null ? 'Nilai TTM/Tuweb belum diisi.' : ttm <= uas ? 'TTM/Tuweb tidak lebih tinggi dari UAS.' : 'Memenuhi syarat kontribusi TTM/Tuweb.',
    },
  ]
  const terbaik = kandidat.filter((k) => k.berlaku).reduce((a, b) => (b.nilai > a.nilai ? b : a), kandidat[0])
  return { kandidat, terbaik, lolosUas }
}

export default function CalculatorPage() {
  const { data: courses, isLoading } = useSWR<Course[]>('/api/courses')
  const [courseId, setCourseId] = useState('')
  const total = useSWR<NilaiTotal>(
    courseId ? `/api/courses/${encodeURIComponent(courseId)}/nilai-total` : null,
  )
  const [uas, setUas] = useState('')
  const [maksimum, setMaksimum] = useState('100')
  const [tutonManual, setTutonManual] = useState<string | null>(null)
  const [ttm, setTtm] = useState('')

  const max = angka(maksimum)
  const tuton = tutonManual === null ? total.data?.nilai_total ?? null : angka(tutonManual)
  const hasil = useMemo(() => hitung(angka(uas), max ?? 0, tuton, angka(ttm)), [uas, max, tuton, ttm])
  const invalid = [angka(uas), tuton, angka(ttm)].some((n) => n !== null && (n < 0 || n > (max ?? 0)))

  function reset() {
    setCourseId('')
    setUas('')
    setMaksimum('100')
    setTutonManual(null)
    setTtm('')
  }

  return (
    <div className='flex flex-col gap-4'>
      <PageHeader title='Kalkulator Nilai UT' description='Estimasi nilai akhir mata kuliah reguler berdasarkan UAS dan tutorial.' />

      <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,380px)] xl:items-start'>
        <Card className='gap-4 py-5'>
          <CardHeader className='px-5'>
            <CardTitle className='text-base'>Input nilai</CardTitle>
            <CardDescription>Pilih mata kuliah agar Nilai Tuton terisi dari Nilai Total Moodle.</CardDescription>
          </CardHeader>
          <CardContent className='grid gap-4 px-5 sm:grid-cols-2'>
            <div className='space-y-2 sm:col-span-2'>
              <Label>Mata kuliah</Label>
              {isLoading ? <Skeleton className='h-10 w-full' /> : (
                <Select value={courseId} onValueChange={(v) => { setCourseId(v); setTutonManual(null) }}>
                  <SelectTrigger className='h-10 w-full'><SelectValue placeholder='— pilih mata kuliah —' /></SelectTrigger>
                  <SelectContent>{(courses || []).map((c) => <SelectItem key={c.id} value={c.id}>{c.nama}</SelectItem>)}</SelectContent>
                </Select>
              )}
            </div>
            <Field label='Nilai UAS' value={uas} onChange={setUas} wajib />
            <Field label='Nilai maksimum UAS' value={maksimum} onChange={setMaksimum} />
            <div className='space-y-2'>
              <Label htmlFor='tuton'>Nilai Tuton</Label>
              <Input id='tuton' type='number' min='0' max={maksimum} value={tutonManual ?? (total.data?.nilai_total?.toString() || '')} placeholder={courseId ? 'Memuat Nilai Total Moodle...' : 'Pilih mata kuliah dulu'} onChange={(e) => setTutonManual(e.target.value)} />
              <p className='text-muted-foreground text-xs'>{total.isLoading ? 'Mengambil Nilai Total Moodle...' : total.data?.nilai_total != null ? 'Terisi dari Nilai Total Moodle. Bisa dikoreksi manual.' : 'Opsional.'}</p>
            </div>
            <Field label='Nilai TTM/Tuweb' value={ttm} onChange={setTtm} />
            {invalid ? <p className='text-destructive text-sm sm:col-span-2'>Nilai harus berada antara 0 dan nilai maksimum UAS.</p> : null}
            <div className='flex gap-2 border-t pt-4 sm:col-span-2'>
              <Button disabled={!hasil || invalid}><Calculator /> Hitung</Button>
              <Button variant='outline' onClick={reset}><RotateCcw /> Reset</Button>
            </div>
          </CardContent>
        </Card>

        <Card className='gap-4 py-5'>
          <CardHeader className='px-5'><CardTitle className='text-base'>Nilai akhir</CardTitle></CardHeader>
          <CardContent className='space-y-3 px-5'>
            {!hasil ? <p className='text-muted-foreground text-sm'>Isi Nilai UAS untuk menghitung estimasi.</p> : (
              <>
                <p className={cn('text-5xl font-bold tabular-nums', hasil.terbaik.nilai >= 80 && 'text-emerald-600', hasil.terbaik.nilai >= 60 && hasil.terbaik.nilai < 80 && 'text-amber-500', hasil.terbaik.nilai < 60 && 'text-red-600')}>{hasil.terbaik.nilai.toLocaleString('id-ID', { maximumFractionDigits: 2 })}</p>
                <Badge variant={hasil.lolosUas ? 'secondary' : 'destructive'}>{hasil.lolosUas ? 'Syarat minimum UAS terpenuhi' : 'UAS belum mencapai 30% nilai maksimum'}</Badge>
                <p className='border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400 rounded-md border p-2.5 text-xs leading-relaxed'>Estimasi, bukan nilai resmi. Nilai akhir tetap ditetapkan Universitas Terbuka sesuai hasil dan ketentuan penilaian yang berlaku.</p>
                <p className='text-muted-foreground text-sm'><strong className='text-foreground'>{hasil.terbaik.metode}</strong> dipilih karena menghasilkan kandidat tertinggi yang memenuhi syarat.</p>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {hasil ? <Card className='gap-4 py-5'><CardHeader className='px-5'><CardTitle className='text-base'>Perbandingan metode</CardTitle></CardHeader><CardContent className='overflow-x-auto px-5'><table className='w-full min-w-[620px] text-sm'><thead className='text-muted-foreground border-b text-left'><tr><th className='pb-2'>Metode</th><th className='pb-2'>Rumus</th><th className='pb-2'>Nilai</th><th className='pb-2'>Status</th></tr></thead><tbody>{hasil.kandidat.map((k) => <tr key={k.metode} className='border-b last:border-0'><td className='py-3 font-medium'>{k.metode}</td><td className='py-3 font-mono text-xs'>{k.rumus}</td><td className='py-3 tabular-nums'>{k.nilai.toLocaleString('id-ID', { maximumFractionDigits: 2 })}</td><td className='text-muted-foreground py-3 text-xs'>{k.berlaku ? 'Memenuhi syarat' : k.alasan}</td></tr>)}</tbody></table></CardContent></Card> : null}

      <Card className='border-dashed py-4 shadow-none ring-0'><CardContent className='text-muted-foreground flex items-start gap-2 px-5 text-xs leading-relaxed'><Info className='mt-0.5 size-4 shrink-0' /><p>Untuk mata kuliah reguler. Nilai UAS murni selalu kandidat. Tuton dan TTM/Tuweb tidak dijumlahkan; hanya kandidat tertinggi yang dipilih. Tidak berlaku untuk praktik/praktikum, PKM, TAPS, atau penilaian khusus. <a className='text-primary underline underline-offset-4' href='https://www.ut.ac.id/wp-content/uploads/2026/07/03-PEDOMAN-PENYELENGGARAAN-2026-2027-21-07-2026_22072026.pdf' target='_blank' rel='noreferrer'>Pedoman UT 2026/2027</a>.</p></CardContent></Card>
    </div>
  )
}

function Field({ label, value, onChange, wajib = false }: { label: string; value: string; onChange: (value: string) => void; wajib?: boolean }) {
  return <div className='space-y-2'><Label>{label}{wajib ? ' *' : ''}</Label><Input type='number' min='0' value={value} onChange={(e) => onChange(e.target.value)} /></div>
}
