'use client'

import { useEffect, useState } from 'react'
import useSWR from 'swr'
import { Pencil, Plug, Trash2, Zap } from 'lucide-react'
import { postJSON } from '@/lib/api'
import type { McpServer } from '@/lib/types'
import { cn } from '@/lib/utils'
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
import { SaveButton } from '@/components/save-button'

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
    await postJSON('/api/mcp/save', {
      ...form,
      headers: teksKeHeader(form.headers),
      tools: form.tools
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    })
    setForm(KOSONG)
    void mutate()
    return 'Server MCP tersimpan.'
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
    <div className='flex flex-col gap-4'>
      <PageHeader
        title='MCP'
        description='Server MCP remote (streamable HTTP) yang boleh dipakai agent. InstaBox contohnya: URL https://api.instabox.sh/mcp dengan header X-API-Key.'
      />

      <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,380px)] xl:items-start'>
        <Card className='gap-4 py-5'>
          <CardHeader className='px-5'>
            <CardTitle className='text-base'>
              {form.id ? `Ubah ${form.id}` : 'Tambah server MCP'}
            </CardTitle>
            <CardDescription>
              Header ditulis satu per baris, mis. <code>X-API-Key: ibk_...</code>.
              Saat mengubah, nilai header yang dikosongkan tetap memakai nilai lama.
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-4 px-5'>
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
            <div className='grid gap-4 sm:grid-cols-2'>
              <div className='space-y-2'>
                <Label htmlFor='m-tools'>Batasi tool (opsional)</Label>
                <Input
                  id='m-tools'
                  value={form.tools}
                  onChange={(e) => setForm({ ...form, tools: e.target.value })}
                  placeholder='kosong = semua tool'
                />
              </div>
              <div className='space-y-2'>
                <Label>Status</Label>
                <label className='flex h-9 items-center gap-2 rounded-md border px-3 text-sm'>
                  <Checkbox
                    checked={form.enabled}
                    onCheckedChange={(v) => setForm({ ...form, enabled: Boolean(v) })}
                  />
                  Aktif
                </label>
              </div>
            </div>
            <div className='space-y-2'>
              <Label>Dipakai oleh agent</Label>
              <div className='flex flex-wrap gap-2'>
                {AGENTS.map((a) => {
                  const aktif = form.agents.includes(a)
                  return (
                    <label
                      key={a}
                      className={cn(
                        'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors',
                        aktif ? 'border-primary/40 bg-accent font-medium' : 'hover:bg-accent/60',
                      )}
                    >
                      <Checkbox
                        checked={aktif}
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
                  )
                })}
              </div>
            </div>
            <div className='flex flex-wrap items-center gap-2 border-t pt-4'>
              <SaveButton
                onSave={simpan}
                disabled={!form.name.trim() || !form.url.trim()}
                label='Simpan server'
              />
              <Button variant='outline' onClick={() => tes()} disabled={busy}>
                <Zap /> Tes &amp; daftar tool
              </Button>
              {form.id ? (
                <Button variant='ghost' onClick={() => setForm(KOSONG)}>
                  Batal
                </Button>
              ) : null}
              {pesan ? <p className='text-muted-foreground text-sm'>{pesan}</p> : null}
            </div>
          </CardContent>
        </Card>

        <div className='grid gap-4'>
          {isLoading ? (
            Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className='h-36 w-full' />
            ))
          ) : (data?.servers || []).length === 0 ? (
            <Card>
              <CardContent className='text-muted-foreground py-8 text-center text-sm'>
                Belum ada server MCP.
              </CardContent>
            </Card>
          ) : (
            (data?.servers || []).map((s) => (
              <Card key={s.id} className='gap-3 py-5'>
                <CardHeader className='px-5'>
                  <CardTitle className='flex items-center justify-between gap-2 text-base'>
                    <span className='flex min-w-0 items-center gap-2'>
                      <Plug className='size-4 shrink-0' />
                      <span className='truncate'>{s.name}</span>
                    </span>
                    <Badge variant={s.enabled ? 'secondary' : 'outline'}>
                      {s.enabled ? 'aktif' : 'nonaktif'}
                    </Badge>
                  </CardTitle>
                  <CardDescription className='truncate font-mono text-[11px]'>
                    {s.url}
                  </CardDescription>
                </CardHeader>
                <CardContent className='space-y-3 px-5'>
                  <p className='text-muted-foreground text-xs'>
                    Agent: {s.agents.join(', ') || '—'}
                  </p>
                  <div className='flex flex-wrap gap-1'>
                    {(tools[s.id] || s.tools).map((t) => (
                      <Badge key={t} variant='outline' className='font-mono'>
                        {t}
                      </Badge>
                    ))}
                    {!s.tools.length && !(tools[s.id] || []).length ? (
                      <span className='text-muted-foreground text-xs'>
                        Tekan Tes untuk melihat daftar tool.
                      </span>
                    ) : null}
                  </div>
                  <div className='flex flex-wrap gap-2'>
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
