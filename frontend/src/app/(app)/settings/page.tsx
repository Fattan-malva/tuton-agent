'use client'

import { useEffect, useState } from 'react'
import useSWR from 'swr'
import { Monitor, Moon, Save, Sun, Unplug } from 'lucide-react'
import { postJSON } from '@/lib/api'
import type { Profil as ProfileInfo, SettingItem } from '@/lib/types'
import { cn } from '@/lib/utils'
import { useTheme, type Theme } from '@/components/theme-provider'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ModelInput } from '@/components/model-input'
import { PageHeader } from '@/components/page-header'

const TEMA: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Terang', icon: Sun },
  { value: 'dark', label: 'Gelap', icon: Moon },
  { value: 'system', label: 'Ikut sistem', icon: Monitor },
]

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
    <Card className='max-w-3xl'>
      <CardHeader>
        <CardTitle className='text-base'>Akun</CardTitle>
        <CardDescription>
          {data?.email || 'Memuat...'} — identitas {terisi}/5 terisi.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='flex flex-wrap items-center gap-2 text-sm'>
          <span className='text-muted-foreground'>Cookie Moodle:</span>
          {data?.cookie_ada ? (
            <Badge variant='secondary'>tersimpan ...{data.cookie_ujung}</Badge>
          ) : (
            <Badge variant='destructive'>belum ada</Badge>
          )}
          {data?.cookie_ada ? (
            <Button
              variant='outline'
              size='sm'
              onClick={putuskan}
              disabled={busy}
            >
              <Unplug /> Putuskan
            </Button>
          ) : null}
        </div>
        <p className='text-xs text-muted-foreground'>
          Cookie Moodle hanya berlaku untuk akun ini dan tidak pernah
          ditampilkan kembali setelah disimpan. Putuskan bila sesi Moodle
          berpindah tangan, lalu tempel cookie baru di tab Konfigurasi.
        </p>
        {msg ? <p className='text-sm text-muted-foreground'>{msg}</p> : null}
      </CardContent>
    </Card>
  )
}

export default function SettingsPage() {
  const { data, isLoading, error, mutate } = useSWR<SettingItem[]>(
    '/api/settings',
  )
  const { data: modelData } = useSWR<{ models: string[] }>('/api/models')
  const { theme, setTheme } = useTheme()
  const [values, setValues] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!data) return
    const next: Record<string, string> = {}
    for (const item of data) next[item.key] = item.rahasia ? '' : item.value
    setValues(next)
  }, [data])

  async function simpan() {
    setBusy(true)
    setMsg('')
    try {
      const r = await postJSON<{
        ok: boolean
        error?: string
        moodle_disegarkan?: boolean
        cache_dibersihkan?: number
      }>('/api/settings', values)
      if (!r.ok) {
        setMsg(r.error || 'Gagal menyimpan.')
        return
      }
      setMsg(
        r.moodle_disegarkan
          ? `Tersimpan. Cache Moodle dibersihkan (${r.cache_dibersihkan || 0} halaman) — memuat ulang...`
          : 'Tersimpan.',
      )
      mutate()
      setTimeout(() => window.location.reload(), r.moodle_disegarkan ? 900 : 600)
    } catch (e) {
      setMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='space-y-6'>
      <PageHeader
        title='Pengaturan'
        description='Identitas dan cookie Moodle tersimpan per akun Clerk di Supabase. Model dan provider berlaku untuk server ini.'
      />

      <AkunCard onChanged={() => mutate()} />

      <Tabs defaultValue='konfigurasi' className='space-y-4'>
        <TabsList>
          <TabsTrigger value='konfigurasi'>Konfigurasi</TabsTrigger>
          <TabsTrigger value='tampilan'>Tampilan</TabsTrigger>
        </TabsList>

        <TabsContent value='konfigurasi' className='space-y-4'>
          <Card className='max-w-3xl'>
            <CardHeader>
              <CardTitle className='text-base'>Variabel .env</CardTitle>
              <CardDescription>
                COOKIE_MOODLE hanya untuk koneksi Moodle, bukan login dashboard.
                Kolom rahasia yang kosong tidak mengubah nilai tersimpan.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              {isLoading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className='space-y-2'>
                    <Skeleton className='h-3.5 w-40' />
                    <Skeleton className='h-9 w-full' />
                  </div>
                ))
              ) : error ? (
                <p className='text-sm text-destructive'>
                  {String((error as Error).message)}
                </p>
              ) : (
                (data || []).map((item) => (
                  <div key={item.key} className='space-y-2'>
                    <Label htmlFor={`set-${item.key}`}>
                      {item.key}
                      {item.rahasia ? (
                        <span className='ms-2 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground'>
                          rahasia
                        </span>
                      ) : null}
                    </Label>
                    {item.key === 'PRIMARY_MODEL' ||
                    item.key === 'VISION_MODEL' ? (
                      <ModelInput
                        id={`set-${item.key}`}
                        value={values[item.key] || ''}
                        onChange={(v) =>
                          setValues((prev) => ({ ...prev, [item.key]: v }))
                        }
                        models={modelData?.models || []}
                      />
                    ) : (
                      <Input
                        id={`set-${item.key}`}
                        type={item.rahasia ? 'password' : 'text'}
                        value={values[item.key] || ''}
                        placeholder={
                          item.key === 'FALLBACK_MODELS'
                            ? 'model cadangan dipisah koma, dicoba bila model utama ditolak provider'
                            : item.rahasia
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
                    )}
                  </div>
                ))
              )}

              <div className='flex flex-wrap items-center gap-3 border-t pt-4'>
                <Button onClick={simpan} disabled={busy || isLoading}>
                  <Save /> {busy ? 'Menyimpan...' : 'Simpan'}
                </Button>
                {msg ? (
                  <p className='text-sm text-muted-foreground'>{msg}</p>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value='tampilan'>
          <Card className='max-w-3xl'>
            <CardHeader>
              <CardTitle className='text-base'>Tema</CardTitle>
              <CardDescription>
                Mode gelap memakai latar hitam dengan permukaan abu. Pilihan
                disimpan di peramban ini.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className='grid gap-2 sm:grid-cols-3'>
                {TEMA.map((item) => (
                  <button
                    key={item.value}
                    type='button'
                    onClick={() => setTheme(item.value)}
                    className={cn(
                      'flex items-center gap-2 rounded-lg border p-3 text-sm transition-colors',
                      theme === item.value
                        ? 'border-foreground/40 bg-accent font-medium'
                        : 'hover:bg-accent/60',
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
      </Tabs>
    </div>
  )
}
