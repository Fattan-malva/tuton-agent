'use client'

import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { JadwalItem } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

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

type Rentang = JadwalItem & { s: Date; e: Date; lane?: number }

function awalBulan(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function kunci(d: Date) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

export function JadwalCalendar({ items }: { items: JadwalItem[] }) {
  const rentang = useMemo<Rentang[]>(
    () =>
      items
        .filter((it) => it.tenggat)
        .map((it) => ({
          ...it,
          s: new Date(`${it.mulai}T00:00:00`),
          e: new Date(`${it.tenggat}T00:00:00`),
        })),
    [items],
  )

  const hariIni = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])

  const [tampil, setTampil] = useState<Date>(() => {
    const akhirBulan = new Date(
      hariIni.getFullYear(),
      hariIni.getMonth() + 1,
      0,
    )
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

    const tenggatMinggu = new Map<string, string>()
    for (const r of nampak) {
      if (r.e >= awal && r.e <= akhir && !tenggatMinggu.has(kunci(r.e))) {
        tenggatMinggu.set(kunci(r.e), r.jenis.toLowerCase())
      }
    }

    const hari = Array.from({ length: 7 }, (_, d) => {
      const tgl = new Date(awal)
      tgl.setDate(awal.getDate() + d)
      return {
        tgl,
        luar: tgl.getMonth() !== m,
        ini: kunci(tgl) === kunci(hariIni),
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
    <div>
      <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
        <div className='flex items-center gap-2'>
          <Button
            size='icon'
            variant='outline'
            className='size-7'
            aria-label='Bulan sebelumnya'
            onClick={() => setTampil(new Date(y, m - 1, 1))}
          >
            <ChevronLeft />
          </Button>
          <strong className='text-sm'>
            {NAMA_BULAN[m]} {y}
          </strong>
          <Button
            size='icon'
            variant='outline'
            className='size-7'
            aria-label='Bulan berikutnya'
            onClick={() => setTampil(new Date(y, m + 1, 1))}
          >
            <ChevronRight />
          </Button>
        </div>
        <div className='flex flex-wrap gap-3 text-[11px] text-muted-foreground'>
          <span className='flex items-center gap-1'>
            <i className='size-2 rounded-full bg-blue-600' /> Diskusi
          </span>
          <span className='flex items-center gap-1'>
            <i className='size-2 rounded-full bg-amber-600' /> Tugas
          </span>
          <span className='flex items-center gap-1'>
            <i className='h-0.5 w-4 bg-muted-foreground' /> Garis tenggat
          </span>
          <span className='flex items-center gap-1'>
            <i className='size-2 rounded-sm bg-accent ring-1 ring-border' /> Hari
            ini
          </span>
        </div>
      </div>

      <div className='overflow-hidden rounded-lg border'>
        <div className='jad-row bg-muted/40'>
          {NAMA_HARI.map((h) => (
            <div
              key={h}
              className='border-e border-border px-1.5 py-1 text-center text-[11px] font-medium text-muted-foreground last:border-e-0'
            >
              {h}
            </div>
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
                  h.ini && 'ini',
                  h.tenggat && 'tenggat',
                )}
              >
                <span>{h.tgl.getDate()}</span>
              </div>
            ))}
            {row.bars.map(({ r, left, width, awalSeg, ket }) => (
              <a
                key={`${r.url}-${r.sesi}-${r.nomor}`}
                className={cn('jad-bar', r.jenis.toLowerCase())}
                href={r.url}
                target='_blank'
                rel='noopener noreferrer'
                title={ket}
                style={{
                  left: `calc(${left}% + 3px)`,
                  width: `calc(${width}% - 3px)`,
                  top: 24 + (r.lane || 0) * LANE_H,
                }}
              >
                {awalSeg ? `${r.jenis} ${r.nomor}` : ''}
              </a>
            ))}
            {row.hari.map(
              (h, d) =>
                h.tenggat && (
                  <i
                    key={`t-${d}`}
                    className={cn(
                      'pointer-events-none absolute top-0 h-full w-0.5',
                      h.tenggat === 'tugas' ? 'bg-amber-500/70' : 'bg-blue-500/70',
                    )}
                    style={{ left: `calc(${((d + 1) / 7) * 100}% - 1px)` }}
                  />
                ),
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
