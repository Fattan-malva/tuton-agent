'use client'

import { useEffect, useState } from 'react'
import useSWR from 'swr'
import { Pencil, Trash2, Zap } from 'lucide-react'
import { postJSON } from '@/lib/api'
import type { Provider, ProviderData } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PageHeader } from '@/components/page-header'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { ModelInput } from '@/components/model-input'
import { SaveButton } from '@/components/save-button'

const AGENTS: { name: string; label: string }[] = [
  { name: 'scrapper', label: 'Scrapper (peta soal)' },
  { name: 'research', label: 'Research (daftar pustaka)' },
  { name: 'worker', label: 'Worker (penulis jawaban)' },
  { name: 'vision', label: 'Vision (transkrip gambar)' },
]

const KOSONG = { id: '', name: '', base_url: '', api_key: '', models: '' }

export default function ProvidersPage() {
  const { data, isLoading, mutate } = useSWR<ProviderData>('/api/providers')
  const [form, setForm] = useState(KOSONG)
  const [agents, setAgents] = useState<Record<string, string>>({})
  const [pesan, setPesan] = useState('')
  const [busy, setBusy] = useState(false)
  const [hapus, setHapus] = useState<Provider | null>(null)

  useEffect(() => {
    if (!data) return
    const next: Record<string, string> = {}
    for (const a of AGENTS) next[a.name] = data.agents[a.name] || ''
    setAgents(next)
  }, [data])

  function ubah(p: Provider) {
    setForm({
      id: p.id,
      name: p.name,
      base_url: p.base_url,
      api_key: '',
      models: p.models.join('\n'),
    })
    setPesan('')
  }

  // Aksi simpan mengembalikan pesan sukses; SaveButton hanya menampilkan
  // spinner di tombolnya sendiri, tanpa memuat ulang halaman.
  async function simpan() {
    setBusy(true)
    setPesan('')
    try {
      await postJSON('/api/providers/save', form)
      setForm(KOSONG)
      void mutate()
      return 'Provider tersimpan.'
    } finally {
      setBusy(false)
    }
  }

  async function tes(id = form.id) {
    setBusy(true)
    setPesan('')
    try {
      const r = await postJSON<{ ok: boolean; models?: string[]; error?: string }>(
        '/api/providers/test',
        { id, base_url: form.base_url, api_key: form.api_key },
      )
      if (!r.ok) {
        setPesan(r.error || 'Tes gagal.')
        return
      }
      const daftar = r.models || []
      if (!id || form.id === id) setForm((f) => ({ ...f, models: daftar.join('\n') }))
      setPesan(`${daftar.length} model ditemukan dan dimasukkan ke daftar.`)
    } catch (e) {
      setPesan((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function hapusProvider() {
    if (!hapus) return
    setBusy(true)
    try {
      await postJSON('/api/providers/delete', { id: hapus.id })
      setHapus(null)
      if (form.id === hapus.id) setForm(KOSONG)
      mutate()
    } catch (e) {
      setPesan((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function simpanAgent() {
    try {
      await postJSON('/api/agents/models', { models: agents })
      void mutate()
      return 'Model per agent tersimpan.'
    } finally {
      setPesan('')
    }
  }

  return (
    <div className='flex flex-col gap-4'>
      <PageHeader
        title='Provider'
        description='Endpoint OpenAI-compatible, API key, daftar model, dan model tiap agent. Disimpan di runtime/runtime.json.'
      />

      <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,380px)] xl:items-start'>
        <div className='space-y-4'>
          <Card className='gap-4 py-5'>
            <CardHeader className='px-5'>
              <CardTitle className='text-base'>
                {form.id ? `Ubah ${form.id}` : 'Tambah provider'}
              </CardTitle>
              <CardDescription>
                Base URL harus menunjuk ke akar API, mis.
                <code className='mx-1'>https://provider.example/v1</code>.
                API key dikosongkan saat mengubah berarti nilai lama dipakai.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4 px-5'>
              <div className='grid gap-4 sm:grid-cols-2'>
                <div className='space-y-2'>
                  <Label htmlFor='p-name'>Nama</Label>
                  <Input
                    id='p-name'
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder='9Router'
                  />
                </div>
                <div className='space-y-2'>
                  <Label htmlFor='p-base'>Base URL</Label>
                  <Input
                    id='p-base'
                    value={form.base_url}
                    onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                    placeholder='https://9router.example/v1'
                  />
                </div>
              </div>
              <div className='space-y-2'>
                <Label htmlFor='p-key'>API key</Label>
                <Input
                  id='p-key'
                  type='password'
                  value={form.api_key}
                  onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                  placeholder={form.id ? 'kosongkan = tetap' : 'sk-...'}
                />
              </div>
              <div className='space-y-2'>
                <Label htmlFor='p-models'>Model ID (satu per baris atau pisah koma)</Label>
                <Textarea
                  id='p-models'
                  value={form.models}
                  onChange={(e) => setForm({ ...form, models: e.target.value })}
                  placeholder={'cbai/deepseek-v4.1-flash\ngrok'}
                  className='min-h-24 font-mono text-xs'
                />
              </div>
              <div className='flex flex-wrap items-center gap-2 border-t pt-4'>
                <SaveButton onSave={simpan} disabled={!form.name.trim()} label='Simpan provider' />
                <Button variant='outline' onClick={() => tes()} disabled={busy}>
                  <Zap /> Tes &amp; ambil model
                </Button>
                {form.id ? (
                  <Button variant='ghost' onClick={() => setForm(KOSONG)}>
                    Batal
                  </Button>
                ) : null}
                {pesan ? (
                  <p className='text-muted-foreground text-sm'>{pesan}</p>
                ) : null}
              </div>
            </CardContent>
          </Card>

          <div className='grid gap-4 md:grid-cols-2'>
            {isLoading ? (
              Array.from({ length: 2 }).map((_, i) => (
                <Skeleton key={i} className='h-40 w-full' />
              ))
            ) : (data?.providers || []).length === 0 ? (
              <p className='text-muted-foreground text-sm'>
                Belum ada provider. Tambahkan satu supaya agent bisa jalan.
              </p>
            ) : (
              (data?.providers || []).map((p) => (
                <Card key={p.id} className='gap-3 py-5'>
                  <CardHeader className='px-5'>
                    <CardTitle className='flex items-center justify-between gap-2 text-base'>
                      <span className='truncate'>{p.name}</span>
                      {p.ada_key ? <Badge variant='outline'>key tersimpan</Badge> : null}
                    </CardTitle>
                    <CardDescription className='truncate font-mono text-[11px]'>
                      {p.id} · {p.base_url}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className='space-y-3 px-5'>
                    <div className='flex flex-wrap gap-1'>
                      {p.models.map((m) => (
                        <Badge key={m} variant='secondary' className='font-mono'>
                          {m}
                        </Badge>
                      ))}
                    </div>
                    <div className='flex flex-wrap gap-2'>
                      <Button size='sm' variant='outline' onClick={() => ubah(p)}>
                        <Pencil /> Ubah
                      </Button>
                      <Button size='sm' variant='outline' onClick={() => tes(p.id)} disabled={busy}>
                        <Zap /> Tes
                      </Button>
                      <Button size='sm' variant='ghost' onClick={() => setHapus(p)}>
                        <Trash2 /> Hapus
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </div>

        <Card className='gap-4 py-5'>
          <CardHeader className='px-5'>
            <CardTitle className='text-base'>Model per agent</CardTitle>
            <CardDescription>
              Kosongkan untuk memakai PRIMARY_MODEL/VISION_MODEL. Vision wajib
              model yang bisa membaca gambar.
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-4 px-5'>
            {AGENTS.map((a) => (
              <div key={a.name} className='space-y-2'>
                <Label htmlFor={`agent-${a.name}`}>{a.label}</Label>
                <ModelInput
                  id={`agent-${a.name}`}
                  value={agents[a.name] || ''}
                  onChange={(v) => setAgents((prev) => ({ ...prev, [a.name]: v }))}
                  models={data?.models || []}
                />
              </div>
            ))}
            <div className='flex items-center gap-3 border-t pt-4'>
              <SaveButton onSave={simpanAgent} label='Simpan model agent' />
            </div>
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={hapus !== null}
        onOpenChange={(v) => !v && setHapus(null)}
        title='Hapus provider?'
        message={`Provider ${hapus?.name || ''} beserta model agent yang memakainya akan dilepas dari konfigurasi.`}
        onConfirm={hapusProvider}
        busy={busy}
      />
    </div>
  )
}
