'use client'

import { useEffect, useState } from 'react'
import useSWR from 'swr'
import { Pencil, Plug, Save, Trash2, Zap } from 'lucide-react'
import { postJSON } from '@/lib/api'
import type { McpServer } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PageHeader } from '@/components/page-header'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'

const AGENTS = ['scrapper', 'research', 'worker', 'vision']
const KOSONG = {
  id: '',
  name: '',
  url: '',
  headers: '',
  agents: [] as string[],
  tools: '',
  enabled: true,
}

function teksKeHeader(teks: string) {
  const out: Record<string, string> = {}
  for (const baris of teks.split('\n')) {
    const i = baris.indexOf(':')
    if (i <= 0) continue
    const k = baris.slice(0, i).trim()
    const v = baris.slice(i + 1).trim()
    if (k && v) out[k] = v
  }
  return out
}

export default function McpPage() {
  const { data, isLoading, mutate } = useSWR<{ servers: McpServer[] }>('/api/mcp')
  const [form, setForm] = useState(KOSONG)
  const [pesan, setPesan] = useState('')
  const [busy, setBusy] = useState(false)
  const [hapus, setHapus] = useState<McpServer | null>(null)
  const [tools, setTools] = useState<Record<string, string[]>>({})

  useEffect(() => {
    if (!data) return
    const a: Record<string, string[]> = {}
    for (const s of data.servers) a[s.id] = s.tools || []
    setTools(a)
  }, [data])

  function ubah(s: McpServer) {
    setForm({
      id: s.id,
      name: s.name,
      url: s.url,
      headers: s.headers.map((h) => `${h}: `).join('\n'),
      agents: s.agents,
      tools: s.tools.join(', '),
      enabled: s.enabled,
    })
    setPesan('')
  }

  async function simpan() {
    setBusy(true)
    setPesan('')
    try {
      await postJSON('/api/mcp/save', {
        ...form,
        headers: teksKeHeader(form.headers),
        tools: form.tools
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      })
      setForm(KOSONG)
      setPesan('Server MCP tersimpan.')
      mutate()
    } catch (e) {
      setPesan((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function tes(id = form.id) {
    setBusy(true)
    setPesan('')
    try {
      const r = await postJSON<{
        ok: boolean
        tools?: { name: string; description: string }[]
        error?: string
      }>('/api/mcp/test', {
        id,
        url: form.url,
        headers: teksKeHeader(form.headers),
      })
      if (!r.ok) {
        setPesan(r.error || 'Tes gagal.')
        return
      }
      const daftar = r.tools || []
      setTools((prev) => ({ ...prev, [id]: daftar.map((t) => t.name) }))
      setPesan(`${daftar.length} tool ditemukan: ${daftar.map((t) => t.name).join(', ')}`)
    } catch (e) {
      setPesan((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function hapusServer() {
    if (!hapus) return
    setBusy(true)
    try {
      await postJSON('/api/mcp/delete', { id: hapus.id })
      setHapus(null)
      if (form.id === hapus.id) setForm(KOSONG)
      mutate()
    } catch (e) {
      setPesan((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='space-y-6'>
      <PageHeader
        title='MCP'
        description='Server MCP remote (streamable HTTP) yang boleh dipakai agent. InstaBox contohnya: URL https://api.instabox.sh/mcp dengan header X-API-Key.'
      />

      <Card className='max-w-3xl'>
        <CardHeader>
          <CardTitle className='text-base'>
            {form.id ? `Ubah ${form.id}` : 'Tambah server MCP'}
          </CardTitle>
          <CardDescription>
            Header ditulis satu per baris, mis. <code>X-API-Key: ibk_...</code>.
            Saat mengubah, nilai header yang dikosongkan tetap memakai nilai lama.
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-4'>
          <div className='grid gap-4 sm:grid-cols-2'>
            <div className='space-y-2'>
              <Label htmlFor='m-name'>Nama</Label>
              <Input
                id='m-name'
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder='InstaBox'
              />
            </div>
            <div className='space-y-2'>
              <Label htmlFor='m-url'>URL MCP</Label>
              <Input
                id='m-url'
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder='https://api.instabox.sh/mcp'
              />
            </div>
          </div>
          <div className='space-y-2'>
            <Label htmlFor='m-headers'>Header</Label>
            <Textarea
              id='m-headers'
              value={form.headers}
              onChange={(e) => setForm({ ...form, headers: e.target.value })}
              placeholder='X-API-Key: ibk_...'
              className='min-h-20 font-mono text-xs'
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='m-tools'>Batasi tool (opsional, pisah koma)</Label>
            <Input
              id='m-tools'
              value={form.tools}
              onChange={(e) => setForm({ ...form, tools: e.target.value })}
              placeholder='kosong = semua tool'
            />
          </div>
          <div className='space-y-2'>
            <Label>Dipakai oleh agent</Label>
            <div className='flex flex-wrap gap-4'>
              {AGENTS.map((a) => (
                <label key={a} className='flex items-center gap-2 text-sm'>
                  <Checkbox
                    checked={form.agents.includes(a)}
                    onCheckedChange={(v) =>
                      setForm((f) => ({
                        ...f,
                        agents: v
                          ? [...f.agents, a]
                          : f.agents.filter((x) => x !== a),
                      }))
                    }
                  />
                  {a}
                </label>
              ))}
            </div>
          </div>
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox
              checked={form.enabled}
              onCheckedChange={(v) => setForm({ ...form, enabled: Boolean(v) })}
            />
            Aktif
          </label>
          <div className='flex flex-wrap items-center gap-3 border-t pt-4'>
            <Button onClick={simpan} disabled={busy}>
              <Save /> Simpan
            </Button>
            <Button variant='outline' onClick={() => tes()} disabled={busy}>
              <Zap /> Tes &amp; daftar tool
            </Button>
            {form.id ? (
              <Button variant='ghost' onClick={() => setForm(KOSONG)}>
                Batal
              </Button>
            ) : null}
            {pesan ? <p className='text-sm text-muted-foreground'>{pesan}</p> : null}
          </div>
        </CardContent>
      </Card>

      <div className='grid gap-4 lg:grid-cols-2'>
        {isLoading ? (
          Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className='h-36 w-full' />
          ))
        ) : (data?.servers || []).length === 0 ? (
          <p className='text-sm text-muted-foreground'>Belum ada server MCP.</p>
        ) : (
          (data?.servers || []).map((s) => (
            <Card key={s.id}>
              <CardHeader>
                <CardTitle className='flex items-center justify-between gap-2 text-base'>
                  <span className='flex items-center gap-2'>
                    <Plug className='size-4' /> {s.name}
                  </span>
                  <Badge variant={s.enabled ? 'secondary' : 'outline'}>
                    {s.enabled ? 'aktif' : 'nonaktif'}
                  </Badge>
                </CardTitle>
                <CardDescription className='break-all font-mono text-[11px]'>
                  {s.url}
                </CardDescription>
              </CardHeader>
              <CardContent className='space-y-3'>
                <p className='text-xs text-muted-foreground'>
                  Agent: {s.agents.join(', ') || '—'}
                </p>
                <div className='flex flex-wrap gap-1'>
                  {(tools[s.id] || s.tools).map((t) => (
                    <Badge key={t} variant='outline' className='font-mono'>
                      {t}
                    </Badge>
                  ))}
                  {!s.tools.length && !(tools[s.id] || []).length ? (
                    <span className='text-xs text-muted-foreground'>
                      Tekan Tes untuk melihat daftar tool.
                    </span>
                  ) : null}
                </div>
                <div className='flex gap-2'>
                  <Button size='sm' variant='outline' onClick={() => ubah(s)}>
                    <Pencil /> Ubah
                  </Button>
                  <Button size='sm' variant='outline' onClick={() => tes(s.id)} disabled={busy}>
                    <Zap /> Tes
                  </Button>
                  <Button size='sm' variant='ghost' onClick={() => setHapus(s)}>
                    <Trash2 /> Hapus
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      <ConfirmDialog
        open={hapus !== null}
        onOpenChange={(v) => !v && setHapus(null)}
        title='Hapus server MCP?'
        message={`Server ${hapus?.name || ''} tidak akan diberikan ke agent lagi.`}
        onConfirm={hapusServer}
        busy={busy}
      />
    </div>
  )
}
