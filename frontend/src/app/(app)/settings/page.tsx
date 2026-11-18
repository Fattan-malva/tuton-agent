'use client'

import { useEffect, useState } from 'react'
import useSWR from 'swr'
import { Info, Loader2, Monitor, Moon, Sun, Unplug } from 'lucide-react'
import { postJSON } from '@/lib/api'
import type { Profil as ProfileInfo, SettingItem } from '@/lib/types'
import { cn } from '@/lib/utils'
import { useTheme, type Theme } from '@/components/theme-provider'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PageHeader } from '@/components/page-header'
import { SaveButton } from '@/components/save-button'
import { CookiePanduan } from '@/components/cookie-panduan'

const TEMA: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Terang', icon: Sun },
  { value: 'dark', label: 'Gelap', icon: Moon },
  { value: 'system', label: 'Ikut sistem', icon: Monitor },
]

/** Kolom yang isinya panjang ditampilkan selebar kartu, sisanya berjajar. */
const LEBAR_PENUH = new Set(['COOKIE_MOODLE'])

function AkunCard({ onChanged }: { onChanged: () => void }) {
  const { data, mutate } = useSWR<ProfileInfo>('/api/profil')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  async function putuskan() {
    setBusy(true)
    setMsg('')
    try {
      await postJSON('/api/profil', { cookie_moodle: '' })
      await mutate()
      onChanged()
      setMsg('Sesi Moodle akun ini diputus.')
    } catch (e) {
      setMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const ident = data?.identitas || {}
  const terisi = ['nama', 'nim', 'semester', 'ut_daerah', 'prodi'].filter(
    (k) => (ident[k] || '').trim(),
  ).length

  return (
    <Card className='gap-4 py-5'>
      <CardHeader className='px-5'>
        <CardTitle className='text-base'>Akun</CardTitle>
        <CardDescription>
          {data?.email || 'Memuat...'} — identitas {terisi}/5 terisi.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3 px-5'>
        <div className='flex flex-wrap items-center gap-2 text-sm'>
          <span className='text-muted-foreground'>Cookie Moodle:</span>
          {data?.cookie_ada ? (
            <Badge variant='secondary'>tersimpan ...{data.cookie_ujung}</Badge>
          ) : (
            <Badge variant='destructive'>belum ada</Badge>
          )}
          {data?.cookie_ada ? (
            <Button variant='outline' size='sm' onClick={putuskan} disabled={busy}>
              {busy ? <Loader2 className='animate-spin' /> : <Unplug />} Putuskan
            </Button>
          ) : null}
        </div>
        <p className='text-muted-foreground text-xs leading-relaxed'>
          Cookie Moodle hanya berlaku untuk akun ini dan tidak pernah ditampilkan
          kembali setelah disimpan. Putuskan bila sesi Moodle berpindah tangan,
          lalu tempel cookie baru di tab Konfigurasi.
        </p>
        {msg ? <p className='text-muted-foreground text-sm'>{msg}</p> : null}
      </CardContent>
    </Card>
  )
}

export default function SettingsPage() {
  const { data, isLoading, error, mutate } = useSWR<SettingItem[]>('/api/settings')
  const { theme, setTheme } = useTheme()
  const [values, setValues] = useState<Record<string, string>>({})
  const [panduanOpen, setPanduanOpen] = useState(false)

  useEffect(() => {
    if (!data) return
    const next: Record<string, string> = {}
    for (const item of data) next[item.key] = item.rahasia ? '' : item.value
    setValues(next)
  }, [data])

  // Tidak ada reload halaman: cukup segarkan data lewat SWR supaya isian dan
  // posisi scroll pengguna tidak hilang.
  async function simpan() {
    const r = await postJSON<{
      ok: boolean
      error?: string
      moodle_disegarkan?: boolean
      cache_dibersihkan?: number
    }>('/api/settings', values)
    if (!r.ok) throw new Error(r.error || 'Gagal menyimpan.')
    void mutate()
    return r.moodle_disegarkan
      ? `Tersimpan. Cache Moodle dibersihkan (${r.cache_dibersihkan || 0} halaman).`
      : 'Tersimpan.'
  }

  return (
    <div className='flex flex-col gap-4'>
      <PageHeader
        title='Pengaturan'
        description='Identitas dan cookie Moodle tersimpan per akun. Provider dan model per agent diatur di menu Provider.'
      />

      <Tabs defaultValue='konfigurasi' className='gap-4'>
        <TabsList>
          <TabsTrigger value='konfigurasi'>Konfigurasi</TabsTrigger>
          <TabsTrigger value='tampilan'>Tampilan</TabsTrigger>
          <TabsTrigger value='akun'>Akun</TabsTrigger>
        </TabsList>

        <TabsContent value='konfigurasi' className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,340px)] xl:items-start'>
          <Card className='gap-4 py-5'>
            <CardHeader className='px-5'>
              <CardTitle className='text-base'>Variabel .env</CardTitle>
              <CardDescription>
                COOKIE_MOODLE hanya untuk koneksi Moodle, bukan login dashboard.
                Kolom rahasia yang kosong tidak mengubah nilai tersimpan.
              </CardDescription>
              <CardAction>
                <SaveButton
                  onSave={simpan}
                  disabled={isLoading}
                  size='sm'
                  label='Simpan'
                />
              </CardAction>
            </CardHeader>
            <CardContent className='px-5'>
              {isLoading ? (
                <div className='grid gap-4 sm:grid-cols-2'>
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className='space-y-2'>
                      <Skeleton className='h-3.5 w-32' />
                      <Skeleton className='h-9 w-full' />
                    </div>
                  ))}
                </div>
              ) : error ? (
                <p className='text-destructive text-sm'>
                  {String((error as Error).message)}
                </p>
              ) : (
                <div className='grid gap-4 sm:grid-cols-2'>
                  {(data || []).map((item) => (
                    <div
                      key={item.key}
                      className={cn(
                        'space-y-2',
                        LEBAR_PENUH.has(item.key) && 'sm:col-span-2',
                      )}
                    >
                      <Label htmlFor={`set-${item.key}`} className='flex items-center gap-2'>
                        <span className='font-mono text-xs'>{item.key}</span>
                        {item.rahasia ? (
                          <span className='bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px] font-medium'>
                            rahasia
                          </span>
                        ) : null}
                        {item.key === 'COOKIE_MOODLE' ? (
                          <button
                            type='button'
                            onClick={() => setPanduanOpen(true)}
                            className='text-muted-foreground hover:text-foreground -mt-0.5 transition-colors'
                            aria-label='Cara ambil cookie Moodle'
                          >
                            <Info className='size-3.5' />
                          </button>
                        ) : null}
                      </Label>
                      <Input
                        id={`set-${item.key}`}
                        type={item.rahasia ? 'password' : 'text'}
                        value={values[item.key] || ''}
                        className={item.key === 'COOKIE_MOODLE' ? 'font-mono text-xs' : undefined}
                        placeholder={
                          item.rahasia
                            ? item.ada
                              ? 'biarkan kosong = tetap'
                              : 'isi baru'
                            : ''
                        }
                        onChange={(e) =>
                          setValues((prev) => ({
                            ...prev,
                            [item.key]: e.target.value,
                          }))
                        }
                      />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
          <CookiePanduan open={panduanOpen} onOpenChange={setPanduanOpen} />

          <Card className='gap-4 py-5'>
            <CardHeader className='px-5'>
              <CardTitle className='text-base'>Ringkasan</CardTitle>
              <CardDescription>
                Nilai berlaku setelah disimpan. Tidak perlu memuat ulang halaman.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-3 px-5 text-sm'>
              <div className='flex items-center justify-between gap-2'>
                <span className='text-muted-foreground'>Cookie Moodle</span>
                <span className='text-xs'>
                  {values.COOKIE_MOODLE ? 'akan diperbarui' : 'tidak diubah'}
                </span>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value='tampilan'>
          <Card className='max-w-2xl gap-4 py-5'>
            <CardHeader className='px-5'>
              <CardTitle className='text-base'>Tema</CardTitle>
              <CardDescription>
                Pilihan disimpan di peramban ini dan berlaku seketika.
              </CardDescription>
            </CardHeader>
            <CardContent className='px-5'>
              <div className='grid gap-2 sm:grid-cols-3'>
                {TEMA.map((item) => (
                  <button
                    key={item.value}
                    type='button'
                    onClick={() => setTheme(item.value)}
                    className={cn(
                      'hover:bg-accent/60 flex items-center gap-2 rounded-md border p-3 text-sm transition-colors',
                      theme === item.value && 'border-primary/40 bg-accent font-medium',
                    )}
                    aria-pressed={theme === item.value}
                  >
                    <item.icon className='size-4' />
                    {item.label}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value='akun'>
          <AkunCard onChanged={() => void mutate()} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
