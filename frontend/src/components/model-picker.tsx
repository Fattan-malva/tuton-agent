'use client'

import { useMemo, useRef, useState } from 'react'
import { Popover } from '@base-ui/react/popover'
import { Check, ChevronsUpDown, Search } from 'lucide-react'
import { cn } from '@/lib/utils'

const MAKS_OPSI = 10

/**
 * Daftar model milik satu provider: hanya 10 baris yang tampil, sisanya
 * dijangkau lewat kotak pencarian di atasnya.
 */
export function ModelList({
  models,
  kosong = 'Belum ada model tersimpan.',
}: {
  models: string[]
  kosong?: string
}) {
  const [cari, setCari] = useState('')

  const { opsi, total } = useMemo(() => {
    const q = cari.trim().toLowerCase()
    const cocok = q ? models.filter((m) => m.toLowerCase().includes(q)) : models
    return { opsi: cocok.slice(0, MAKS_OPSI), total: cocok.length }
  }, [cari, models])

  if (!models.length) {
    return <p className='text-muted-foreground text-xs'>{kosong}</p>
  }

  return (
    <div className='space-y-2'>
      <div className='relative'>
        <Search className='text-muted-foreground pointer-events-none absolute start-2 top-1/2 size-3.5 -translate-y-1/2' />
        <input
          value={cari}
          onChange={(e) => setCari(e.target.value)}
          placeholder={`Cari di ${models.length} model...`}
          autoComplete='off'
          aria-label='Cari model provider'
          className='border-input placeholder:text-muted-foreground h-8 w-full rounded-md border bg-transparent ps-7 pe-2 text-xs outline-none'
        />
      </div>
      <div className='flex flex-wrap gap-1'>
        {opsi.map((m) => (
          <span
            key={m}
            className='bg-secondary text-secondary-foreground max-w-full truncate rounded px-1.5 py-0.5 font-mono text-[11px]'
          >
            {m}
          </span>
        ))}
      </div>
      {total > MAKS_OPSI ? (
        <p className='text-muted-foreground text-[11px]'>
          {MAKS_OPSI} dari {total} model — ketik untuk mempersempit.
        </p>
      ) : null}
    </div>
  )
}

/**
 * Pemilih model bergaya combobox: tombol membuka kotak pencarian, lalu daftar
 * model disaring saat mengetik. Maksimal 10 opsi ditampilkan supaya daftar
 * model provider yang panjang tidak membanjiri layar; sisanya bisa dicapai
 * dengan mencari.
 *
 * Nilai kosong berarti agent itu belum punya model, jadi opsi pertama selalu
 * mengosongkan pilihan.
 */
export function ModelPicker({
  id,
  value,
  onChange,
  models,
  placeholder = 'Pilih model',
  kosongLabel = 'Kosongkan',
  bolehKosong = true,
  className,
}: {
  id?: string
  value: string
  onChange: (value: string) => void
  models: string[]
  placeholder?: string
  kosongLabel?: string
  bolehKosong?: boolean
  className?: string
}) {
  const [buka, setBuka] = useState(false)
  const [cari, setCari] = useState('')
  const [sorot, setSorot] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const { opsi, total } = useMemo(() => {
    const q = cari.trim().toLowerCase()
    const cocok = q ? models.filter((m) => m.toLowerCase().includes(q)) : models
    return { opsi: cocok.slice(0, MAKS_OPSI), total: cocok.length }
  }, [cari, models])

  function pilih(nilai: string) {
    onChange(nilai)
    setBuka(false)
    setCari('')
    setSorot(0)
  }

  function bukaMenu(nilai: boolean) {
    setBuka(nilai)
    if (!nilai) {
      setCari('')
      setSorot(0)
    }
  }

  function tekan(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSorot((i) => Math.min(i + 1, opsi.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSorot((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const target = opsi[sorot]
      if (target) pilih(target)
    }
  }

  return (
    <Popover.Root open={buka} onOpenChange={bukaMenu}>
      <Popover.Trigger
        render={
          <button
            id={id}
            type='button'
            className={cn(
              'border-input focus-visible:border-ring focus-visible:ring-ring/50 flex h-9 w-full min-w-0 items-center justify-between gap-2 rounded-md border bg-transparent px-2.5 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-3',
              className,
            )}
          >
            <span
              className={cn(
                'truncate text-left',
                value ? 'font-mono text-xs' : 'text-muted-foreground',
              )}
            >
              {value || placeholder}
            </span>
            <ChevronsUpDown className='text-muted-foreground size-4 shrink-0' />
          </button>
        }
      />
      <Popover.Portal>
        <Popover.Positioner side='bottom' align='start' sideOffset={4} className='isolate z-50'>
          <Popover.Popup
            data-slot='model-picker'
            initialFocus={inputRef}
            className='bg-popover text-popover-foreground ring-foreground/10 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95 w-[min(92vw,26rem)] origin-(--transform-origin) overflow-hidden rounded-lg shadow-md ring-1 duration-100 outline-none'
          >
            <div className='border-b p-2'>
              <div className='relative'>
                <Search className='text-muted-foreground pointer-events-none absolute start-2 top-1/2 size-3.5 -translate-y-1/2' />
                <input
                  ref={inputRef}
                  value={cari}
                  onChange={(e) => {
                    setCari(e.target.value)
                    setSorot(0)
                  }}
                  onKeyDown={tekan}
                  placeholder='Cari model...'
                  autoComplete='off'
                  className='placeholder:text-muted-foreground h-8 w-full rounded-md bg-transparent ps-7 pe-2 text-sm outline-none'
                />
              </div>
            </div>

            <div className='max-h-72 overflow-y-auto p-1'>
              {bolehKosong && !cari ? (
                <button
                  type='button'
                  onClick={() => pilih('')}
                  className='hover:bg-accent hover:text-accent-foreground flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm'
                >
                  <span className='flex-1 truncate text-muted-foreground'>{kosongLabel}</span>
                  {!value ? <Check className='size-3.5' /> : null}
                </button>
              ) : null}

              {opsi.length === 0 ? (
                <p className='text-muted-foreground px-2 py-3 text-xs'>
                  {models.length === 0
                    ? 'Belum ada model tersimpan. Jalankan “Tes & ambil model” dulu.'
                    : 'Tidak ada model yang cocok.'}
                </p>
              ) : (
                opsi.map((m, i) => (
                  <button
                    key={m}
                    type='button'
                    onMouseEnter={() => setSorot(i)}
                    onClick={() => pilih(m)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left',
                      i === sorot && 'bg-accent text-accent-foreground',
                    )}
                  >
                    <span className='flex-1 truncate font-mono text-xs'>{m}</span>
                    {m === value ? <Check className='size-3.5 shrink-0' /> : null}
                  </button>
                ))
              )}
            </div>

            {total > MAKS_OPSI ? (
              <p className='text-muted-foreground border-t px-3 py-1.5 text-[11px]'>
                Menampilkan {MAKS_OPSI} dari {total} model — ketik untuk mempersempit.
              </p>
            ) : null}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}
