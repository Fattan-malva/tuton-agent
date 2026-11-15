'use client'

import { useMemo, useState, type CSSProperties, type FocusEvent, type MouseEvent, type ReactNode } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight, Flag } from 'lucide-react'
import type { JadwalItem } from '@/lib/types'
import { cn } from '@/lib/utils'
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

const NAMA_HARI = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']
const NAMA_BULAN = [
  'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
  'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember',
]
const LANE_H = 20

type Warna = { ink: string; solid: string }
type Rentang = JadwalItem & { s: Date; e: Date; lane?: number; warna: Warna }
type Tip = { x: number; y: number; flip: boolean; isi: ReactNode }

function awalBulan(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function kunci(d: Date) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

function jenisKelas(jenis: string) {
  return jenis.toLowerCase() === 'tugas' ? 'tugas' : 'diskusi'
}

// Identitas satu aktivitas (jenis + nomor): bilah dan bendera tenggatnya
// memakai warna yang sama, tetapi berbeda antar aktivitas.
function kunciAktivitas(jenis: string, nomor: string) {
  return `${jenisKelas(jenis)}-${String(nomor).trim()}`
}

// Warna deterministik per aktivitas. Indeks dikali sudut emas (137.5°) supaya
// aktivitas yang berurutan berjauhan warnanya. `light-dark()` menjaga teks
// tetap terbaca di tema terang dan gelap tanpa JavaScript.
function warnaAktivitas(indeks: number): Warna {
  const hue = (18 + indeks * 137.508) % 360
  return {
    ink: `light-dark(oklch(0.46 0.13 ${hue}), oklch(0.82 0.11 ${hue}))`,
    solid: `light-dark(oklch(0.56 0.15 ${hue}), oklch(0.5 0.12 ${hue}))`,
  }
}

function tanggal(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('id-ID', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function labelAktivitas(jenis: string, nomor: string) {
  return `${jenisKelas(jenis) === 'tugas' ? 'Tugas' : 'Diskusi'} ${nomor}`
}

export function JadwalCalendar({ items }: { items: JadwalItem[] }) {
  const [tip, setTip] = useState<Tip | null>(null)

  // Tooltip dirender sendiri dengan posisi tetap: muncul seketika saat kursor
  // masuk (tanpa jeda tooltip bawaan browser) dan tidak terpotong kotak kalender.
  function tampilkan(el: HTMLElement, isi: ReactNode) {
    const r = el.getBoundingClientRect()
    const flip = r.bottom > window.innerHeight - 160
    setTip({
      x: Math.min(Math.max(8, r.left), window.innerWidth - 280),
      y: flip ? r.top - 6 : r.bottom + 6,
      flip,
      isi,
    })
  }
  const sembunyikan = () => setTip(null)

  const { rentang, legenda } = useMemo(() => {
    const dipakai = items.filter((it) => it.tenggat)
    // Urutan kunci menentukan indeks warna: jenis dulu, lalu nomor secara
    // numerik supaya Diskusi 2 tidak mendahului Diskusi 10.
    const kunciList = Array.from(
      new Set(dipakai.map((it) => kunciAktivitas(it.jenis, it.nomor))),
    ).sort((a, b) => {
      const [ja, na] = a.split('-')
      const [jb, nb] = b.split('-')
      if (ja !== jb) return ja.localeCompare(jb)
      return Number(na) - Number(nb)
    })
    const petaWarna = new Map(kunciList.map((k, i) => [k, warnaAktivitas(i)] as const))
    const daftar: Rentang[] = dipakai.map((it) => ({
      ...it,
      s: new Date(`${it.mulai}T00:00:00`),
      e: new Date(`${it.tenggat}T00:00:00`),
      warna: petaWarna.get(kunciAktivitas(it.jenis, it.nomor)) || warnaAktivitas(0),
    }))
    return {
      rentang: daftar,
      legenda: kunciList.map((k) => {
        const [jenis, nomor] = k.split('-')
        return { kunci: k, label: labelAktivitas(jenis, nomor), warna: petaWarna.get(k)! }
      }),
    }
  }, [items])

  const hariIni = useMemo(() => new Date(), [])
  const [tampil, setTampil] = useState<Date>(() => {
    if (!rentang.length) return awalBulan(hariIni)
    const akhirBulan = new Date(hariIni.getFullYear(), hariIni.getMonth() + 1, 0)
    const diBulanIni = rentang.some((r) => r.s <= akhirBulan && r.e >= awalBulan(hariIni))
    const berikut = rentang
      .filter((r) => r.e >= hariIni)
      .sort((a, b) => a.e.getTime() - b.e.getTime())[0]
    const rujuk = diBulanIni ? hariIni : berikut?.e || rentang[rentang.length - 1]?.e || hariIni
    return awalBulan(rujuk)
  })

  const y = tampil.getFullYear()
  const m = tampil.getMonth()
  const pertama = new Date(y, m, 1)
  const offset = (pertama.getDay() + 6) % 7
  const gridMulai = new Date(y, m, 1 - offset)
  const bulanAkhir = new Date(y, m + 1, 0)
  const jumlahMinggu = Math.ceil((offset + bulanAkhir.getDate()) / 7)
  const gridAkhir = new Date(gridMulai)
  gridAkhir.setDate(gridMulai.getDate() + jumlahMinggu * 7 - 1)

  const nampak = rentang
    .filter((r) => r.s <= gridAkhir && r.e >= gridMulai)
    .sort((a, b) => a.s.getTime() - b.s.getTime() || a.e.getTime() - b.e.getTime())

  const akhirLane: Date[] = []
  for (const r of nampak) {
    let lane = akhirLane.findIndex((t) => t < r.s)
    if (lane === -1) {
      lane = akhirLane.length
      akhirLane.push(r.e)
    } else {
      akhirLane[lane] = r.e
    }
    r.lane = lane
  }
  const tinggiBaris = Math.max(80, 28 + akhirLane.length * LANE_H + 6)

  const minggu = Array.from({ length: jumlahMinggu }, (_, w) => {
    const awal = new Date(gridMulai)
    awal.setDate(gridMulai.getDate() + w * 7)
    const akhir = new Date(awal)
    akhir.setDate(awal.getDate() + 6)

    // Semua tenggat dalam satu hari dikumpulkan; bendera memakai warna
    // tenggat pertama dan tooltip menampilkan semuanya.
    const tenggatMinggu = new Map<string, { warna: Warna; items: Rentang[] }>()
    for (const r of nampak) {
      if (r.e >= awal && r.e <= akhir) {
        const k = kunci(r.e)
        const ada = tenggatMinggu.get(k)
        if (ada) ada.items.push(r)
        else tenggatMinggu.set(k, { warna: r.warna, items: [r] })
      }
    }

    const hari = Array.from({ length: 7 }, (_, d) => {
      const tgl = new Date(awal)
      tgl.setDate(awal.getDate() + d)
      return {
        tgl,
        luar: tgl.getMonth() !== m,
        ini: kunci(tgl) === kunci(hariIni),
        akhirPekan: d > 4,
        tenggat: tenggatMinggu.get(kunci(tgl)),
      }
    })

    const bars = nampak
      .filter((r) => r.e >= awal && r.s <= akhir)
      .map((r) => {
        const cs = r.s < awal ? 0 : Math.round((r.s.getTime() - awal.getTime()) / 86400000)
        const ce = r.e > akhir ? 6 : Math.round((r.e.getTime() - awal.getTime()) / 86400000)
        const hari0 = Math.max(0, Math.round((r.s.getTime() - gridMulai.getTime()) / 86400000))
        const awalSeg = w === Math.floor(hari0 / 7)
        return { r, left: (cs / 7) * 100, width: ((ce - cs + 1) / 7) * 100, awalSeg }
      })

    return { hari, bars }
  })

  return (
    <Card className='gap-4 py-5'>
      <CardHeader className='gap-3 px-5'>
        <div className='flex flex-wrap items-center gap-2'>
          {legenda.map((item) => (
            <Badge key={item.kunci} variant='outline' className='gap-1.5 font-medium' style={{ color: item.warna.ink }}>
              <span className='size-2 rounded-full' style={{ backgroundColor: item.warna.ink }} />
              {item.label}
            </Badge>
          ))}
          <Badge variant='secondary' className='text-muted-foreground gap-1.5 font-normal'>
            <Flag className='size-3' /> Tenggat
          </Badge>
          <Badge variant='secondary' className='text-muted-foreground gap-1.5 font-normal'>
            <span className='bg-primary size-2 rounded-full' /> Hari ini
          </Badge>
        </div>
        <CardTitle className='flex items-center gap-2 text-base'>
          <CalendarDays className='text-muted-foreground size-4' />
          Jadwal Diskusi &amp; Tugas
        </CardTitle>
        <CardDescription>
          Bilah berwarna menunjukkan rentang pengerjaan. Ikon bendera menandai hari tenggat; arahkan kursor untuk melihat detailnya.
        </CardDescription>
        <CardAction className='flex items-center gap-1.5'>
          <Button size='icon-sm' variant='outline' aria-label='Bulan sebelumnya' onClick={() => setTampil(new Date(y, m - 1, 1))}>
            <ChevronLeft />
          </Button>
          <span className='min-w-32 text-center text-sm font-medium'>{NAMA_BULAN[m]} {y}</span>
          <Button size='icon-sm' variant='outline' aria-label='Bulan berikutnya' onClick={() => setTampil(new Date(y, m + 1, 1))}>
            <ChevronRight />
          </Button>
        </CardAction>
      </CardHeader>

      <CardContent className='px-5'>
        <div className='jad-bulan'>
          <div className='jad-kepala'>
            {NAMA_HARI.map((h) => <div key={h}>{h}</div>)}
          </div>
          {minggu.map((row, w) => (
            <div key={w} className='jad-row' style={{ height: tinggiBaris }}>
              {row.hari.map((h) => (
                <div key={h.tgl.toISOString()} className={cn('jad-hari', h.luar && 'luar', h.akhirPekan && !h.luar && 'akhir-pekan')}>
                  <span>{h.tgl.getDate()}</span>
                  {h.tenggat && (
                    <span
                      tabIndex={0}
                      role='img'
                      aria-label={`Tenggat: ${h.tenggat.items.map((i) => i.nama).join(', ')}`}
                      className='absolute end-1.5 top-1.5 flex size-5 cursor-pointer items-center justify-center rounded-full'
                      style={{ backgroundColor: h.tenggat.warna.solid, color: 'white' }}
                      onMouseEnter={(e) => tampilkan(e.currentTarget, <TenggatIsi items={h.tenggat!.items} />)}
                      onFocus={(e) => tampilkan(e.currentTarget, <TenggatIsi items={h.tenggat!.items} />)}
                      onMouseLeave={sembunyikan}
                      onBlur={sembunyikan}
                    >
                      <Flag className='size-3' />
                    </span>
                  )}
                </div>
              ))}
              {row.bars.map(({ r, left, width, awalSeg }) => (
                <a
                  key={`${r.url}-${r.sesi}-${r.nomor}`}
                  className='jad-bar'
                  href={r.url}
                  target='_blank'
                  rel='noopener noreferrer'
                  onMouseEnter={(e) => tampilkan(e.currentTarget, <BarIsi r={r} />)}
                  onFocus={(e: FocusEvent<HTMLAnchorElement>) => tampilkan(e.currentTarget, <BarIsi r={r} />)}
                  onMouseLeave={sembunyikan}
                  onBlur={sembunyikan}
                  style={
                    {
                      left: `calc(${left}% + 3px)`,
                      width: `calc(${width}% - 3px)`,
                      top: 28 + (r.lane || 0) * LANE_H,
                      backgroundColor: r.warna.solid,
                      color: 'white',
                      '--tw-outline-color': r.warna.solid,
                    } as CSSProperties
                  }
                >
                  {awalSeg ? (
                    <>
                      <span className='truncate'>{r.jenis}</span>
                      <span className='opacity-80'>{r.nomor}</span>
                    </>
                  ) : null}
                </a>
              ))}
            </div>
          ))}
        </div>
      </CardContent>

      {tip && (
        <div
          role='tooltip'
          className='bg-popover text-popover-foreground pointer-events-none fixed z-50 w-max max-w-72 rounded-lg border px-3 py-2 text-xs shadow-lg'
          style={{ left: tip.x, top: tip.y, transform: tip.flip ? 'translateY(-100%)' : undefined }}
        >
          {tip.isi}
        </div>
      )}
    </Card>
  )
}

function BarIsi({ r }: { r: Rentang }) {
  return (
    <div className='flex flex-col gap-1'>
      <span className='font-semibold'>{r.nama}</span>
      <span className='text-muted-foreground'>{labelAktivitas(r.jenis, r.nomor)} · Sesi {r.sesi}</span>
      <span className='text-muted-foreground flex items-center gap-1.5'>
        <CalendarDays className='size-3.5' /> {tanggal(r.mulai)}
        <span aria-hidden>→</span>
        <Flag className='size-3.5' /> {tanggal(r.tenggat)}
      </span>
    </div>
  )
}

function TenggatIsi({ items }: { items: Rentang[] }) {
  return (
    <div className='flex flex-col gap-2'>
      <span className='text-muted-foreground flex items-center gap-1.5 font-medium'>
        <Flag className='size-3.5' /> Tenggat {tanggal(items[0].tenggat)}
      </span>
      {items.map((r) => (
        <div key={`${r.url}-${r.sesi}-${r.nomor}`} className='flex items-start gap-2'>
          <span className='mt-1 size-2 shrink-0 rounded-full' style={{ backgroundColor: r.warna.solid }} />
          <div className='flex flex-col'>
            <span className='font-semibold'>{r.nama}</span>
            <span className='text-muted-foreground'>{labelAktivitas(r.jenis, r.nomor)} · Sesi {r.sesi}</span>
          </div>
        </div>
      ))}
    </div>
  )
}
