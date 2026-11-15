'use client'

import { useMemo, useState, type CSSProperties } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
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
  'Januari',
  'Februari',
  'Maret',
  'April',
  'Mei',
  'Juni',
  'Juli',
  'Agustus',
  'September',
  'Oktober',
  'November',
  'Desember',
]
const LANE_H = 20

type Rentang = JadwalItem & {
  s: Date
  e: Date
  lane?: number
  warna: { soft: string; ink: string }
}

function awalBulan(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function kunci(d: Date) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

function jenisKelas(jenis: string) {
  return jenis.toLowerCase() === 'tugas' ? 'tugas' : 'diskusi'
}

/**
 * Kunci identitas satu aktivitas: jenis + nomor. Dipakai untuk memberi warna
 * yang sama pada bilah, garis tenggat, dan legenda, tetapi berbeda antar
 * aktivitas -- Diskusi 1 tidak lagi berwarna sama dengan Diskusi 2.
 */
function kunciAktivitas(jenis: string, nomor: string) {
  return `${jenisKelas(jenis)}-${String(nomor).trim()}`
}

/**
 * Warna deterministik per aktivitas. Indeks dikali sudut emas (137.5°) supaya
 * aktivitas yang berurutan selalu berjauhan warnanya, bukan sekadar bergeser
 * sedikit. `light-dark()` membuat satu nilai tetap terbaca di tema terang dan
 * gelap tanpa perlu JavaScript.
 */
function warnaAktivitas(indeks: number) {
  const hue = (18 + indeks * 137.508) % 360
  return {
    soft: `light-dark(oklch(0.96 0.035 ${hue}), oklch(0.31 0.055 ${hue}))`,
    ink: `light-dark(oklch(0.44 0.12 ${hue}), oklch(0.86 0.1 ${hue}))`,
  }
}

export function JadwalCalendar({ items }: { items: JadwalItem[] }) {
  const { rentang, legenda } = useMemo(() => {
    const dipakai = items.filter((it) => it.tenggat)
    // Urutan kunci menentukan indeks warna: jenis lebih dulu, lalu nomor
    // secara numerik supaya Diskusi 2 tidak mendahului Diskusi 10.
    const kunci = Array.from(
      new Set(dipakai.map((it) => kunciAktivitas(it.jenis, it.nomor))),
    ).sort((a, b) => {
      const [ja, na] = a.split('-')
      const [jb, nb] = b.split('-')
      if (ja !== jb) return ja.localeCompare(jb)
      return Number(na) - Number(nb)
    })
    const petaWarna = new Map(
      kunci.map((k, i) => [k, warnaAktivitas(i)] as const),
    )
    const daftar: Rentang[] = dipakai.map((it) => ({
      ...it,
      s: new Date(`${it.mulai}T00:00:00`),
      e: new Date(`${it.tenggat}T00:00:00`),
      warna:
        petaWarna.get(kunciAktivitas(it.jenis, it.nomor)) ||
        warnaAktivitas(0),
    }))
    return {
      rentang: daftar,
      legenda: kunci.map((k) => {
        const [jenis, nomor] = k.split('-')
        return {
          kunci: k,
          label: `${jenis === 'tugas' ? 'Tugas' : 'Diskusi'} ${nomor}`,
          warna: petaWarna.get(k)!,
        }
      }),
    }
  }, [items])

  const hariIni = useMemo(() => new Date(), [])
  const [tampil, setTampil] = useState<Date>(() => {
    if (!rentang.length) return awalBulan(hariIni)
    const akhirBulan = new Date(hariIni.getFullYear(), hariIni.getMonth() + 1, 0)
    const diBulanIni = rentang.some(
      (r) => r.s <= akhirBulan && r.e >= awalBulan(hariIni),
    )
    const berikut = rentang
      .filter((r) => r.e >= hariIni)
      .sort((a, b) => a.e.getTime() - b.e.getTime())[0]
    const rujuk = diBulanIni
      ? hariIni
      : berikut?.e || rentang[rentang.length - 1]?.e || hariIni
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
  const tinggiBaris = Math.max(76, 24 + akhirLane.length * LANE_H + 6)

  const minggu = Array.from({ length: jumlahMinggu }, (_, w) => {
    const awal = new Date(gridMulai)
    awal.setDate(gridMulai.getDate() + w * 7)
    const akhir = new Date(awal)
    akhir.setDate(awal.getDate() + 6)

    // Satu hari bisa punya beberapa tenggat; warnanya memakai aktivitas
    // pertama hari itu, sisanya tetap terlihat dari bilah masing-masing.
    const tenggatMinggu = new Map<string, Rentang['warna']>()
    for (const r of nampak) {
      if (r.e >= awal && r.e <= akhir && !tenggatMinggu.has(kunci(r.e))) {
        tenggatMinggu.set(kunci(r.e), r.warna)
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
        const hari0 = Math.max(
          0,
          Math.round((r.s.getTime() - gridMulai.getTime()) / 86400000),
        )
        const awalSeg = w === Math.floor(hari0 / 7)
        const left = (cs / 7) * 100
        const width = ((ce - cs + 1) / 7) * 100
        const ket = `${r.nama} — Sesi ${r.sesi} · ${r.mulai} → ${r.tenggat}`
        return { r, left, width, awalSeg, ket }
      })

    return { hari, bars }
  })

  return (
    <Card className='gap-4 py-5'>
      <CardHeader className='gap-3 px-5'>
        <div className='flex flex-wrap items-center gap-2'>
          {legenda.map((item) => (
            <Badge
              key={item.kunci}
              variant='secondary'
              className='gap-1.5 font-normal'
              style={{ color: item.warna.ink }}
            >
              <span
                className='size-2 rounded-full'
                style={{ backgroundColor: item.warna.ink }}
              />
              {item.label}
            </Badge>
          ))}
          <span className='text-muted-foreground flex items-center gap-1.5 text-xs'>
            <i className='bg-muted-foreground/60 h-0.5 w-4 rounded-full' />
            Garis tenggat
          </span>
          <span className='text-muted-foreground flex items-center gap-1.5 text-xs'>
            <i className='bg-primary size-2 rounded-full' /> Hari ini
          </span>
        </div>
        <CardTitle className='flex items-center gap-2 text-base'>
          <CalendarDays className='text-muted-foreground size-4' />
          Jadwal Diskusi &amp; Tugas
        </CardTitle>
        <CardDescription>
          Bilah menunjukkan rentang pengerjaan; garis tegak menandai tenggat.
        </CardDescription>
        <CardAction className='flex items-center gap-1.5'>
          <Button
            size='icon-sm'
            variant='outline'
            aria-label='Bulan sebelumnya'
            onClick={() => setTampil(new Date(y, m - 1, 1))}
          >
            <ChevronLeft />
          </Button>
          <span className='min-w-32 text-center text-sm font-medium'>
            {NAMA_BULAN[m]} {y}
          </span>
          <Button
            size='icon-sm'
            variant='outline'
            aria-label='Bulan berikutnya'
            onClick={() => setTampil(new Date(y, m + 1, 1))}
          >
            <ChevronRight />
          </Button>
        </CardAction>
      </CardHeader>

      <CardContent className='px-5'>
        <div className='jad-bulan'>
          <div className='jad-kepala'>
            {NAMA_HARI.map((h) => (
              <div key={h}>{h}</div>
            ))}
          </div>
          {minggu.map((row, w) => (
            <div key={w} className='jad-row' style={{ height: tinggiBaris }}>
              {row.hari.map((h) => (
                <div
                  key={h.tgl.toISOString()}
                  className={cn(
                    'jad-hari',
                    h.luar && 'luar',
                    h.akhirPekan && !h.luar && 'akhir-pekan',
                  )}
                >
                  <span>{h.tgl.getDate()}</span>
                </div>
              ))}
              {row.bars.map(({ r, left, width, awalSeg, ket }) => (
                <a
                  key={`${r.url}-${r.sesi}-${r.nomor}`}
                  className='jad-bar'
                  href={r.url}
                  target='_blank'
                  rel='noopener noreferrer'
                  title={ket}
                  style={
                    {
                      left: `calc(${left}% + 3px)`,
                      width: `calc(${width}% - 3px)`,
                      top: 26 + (r.lane || 0) * LANE_H,
                      backgroundColor: r.warna.soft,
                      color: r.warna.ink,
                      '--tw-ring-color': r.warna.ink,
                    } as CSSProperties
                  }
                >
                  {awalSeg ? (
                    <>
                      <span className='truncate'>{r.jenis}</span>
                      <span className='opacity-60'>{r.nomor}</span>
                    </>
                  ) : null}
                </a>
              ))}
              {row.hari.map(
                (h, d) =>
                  h.tenggat && (
                    <i
                      key={`t-${d}`}
                      className='pointer-events-none absolute top-0 h-full w-0.5 rounded-full opacity-70'
                      style={{
                        left: `calc(${((d + 1) / 7) * 100}% - 1px)`,
                        backgroundColor: h.tenggat.ink,
                      }}
                    />
                  ),
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
