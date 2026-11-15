'use client'

import { useRef, useState } from 'react'
import useSWR from 'swr'
import { FileUp, Pencil, Save, Trash2 } from 'lucide-react'
import { api, postJSON } from '@/lib/api'
import type { SkillInfo } from '@/lib/types'
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

export default function SkillsPage() {
  const { data, isLoading, mutate } = useSWR<{ skills: SkillInfo[] }>('/api/skills')
  const [nama, setNama] = useState('')
  const [isi, setIsi] = useState('')
  const [pesan, setPesan] = useState('')
  const [busy, setBusy] = useState(false)
  const [hapus, setHapus] = useState<string | null>(null)
  const berkas = useRef<HTMLInputElement>(null)

  async function buka(name: string) {
    setPesan('')
    try {
      const r = await api<{ name: string; content: string }>(`/api/skills/${name}`)
      setNama(r.name)
      setIsi(r.content)
    } catch (e) {
      setPesan((e as Error).message)
    }
  }

  async function unggah(file: File | undefined) {
    if (!file) return
    const teks = await file.text()
    setIsi(teks)
    setNama(
      file.name
        .replace(/\.(md|markdown|txt)$/i, '')
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, '-'),
    )
    setPesan('Isi berkas dimuat. Periksa nama lalu Simpan.')
  }

  async function simpan() {
    setBusy(true)
    setPesan('')
    try {
      await postJSON('/api/skills/save', { name: nama, content: isi })
      setPesan('Skill tersimpan.')
      mutate()
    } catch (e) {
      setPesan((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function hapusSkill() {
    if (!hapus) return
    setBusy(true)
    try {
      await postJSON('/api/skills/delete', { name: hapus })
      if (nama === hapus) {
        setNama('')
        setIsi('')
      }
      setHapus(null)
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
        title='Skill'
        description='Instruksi tambahan yang bisa dimuat agent lewat tool `skill`. Satu folder berisi SKILL.md.'
      />

      <div className='grid gap-4 lg:grid-cols-[280px_1fr]'>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>Daftar skill</CardTitle>
            <CardDescription>Klik untuk mengubah isinya.</CardDescription>
          </CardHeader>
          <CardContent className='space-y-2'>
            {isLoading ? (
              <Skeleton className='h-24 w-full' />
            ) : (
              (data?.skills || []).map((s) => (
                <button
                  key={s.name}
                  type='button'
                  onClick={() => buka(s.name)}
                  className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-sm transition-colors hover:bg-accent/60 ${
                    nama === s.name ? 'border-foreground/40 bg-accent font-medium' : ''
                  }`}
                >
                  <span className='truncate font-mono'>{s.name}</span>
                  <Pencil className='size-3.5 text-muted-foreground' />
                </button>
              ))
            )}
            {!isLoading && !(data?.skills || []).length ? (
              <p className='text-sm text-muted-foreground'>Belum ada skill.</p>
            ) : null}
            <Button
              variant='outline'
              className='w-full'
              onClick={() => berkas.current?.click()}
            >
              <FileUp /> Unggah berkas
            </Button>
            <input
              ref={berkas}
              type='file'
              accept='.md,.markdown,.txt'
              className='hidden'
              onChange={(e) => {
                unggah(e.target.files?.[0])
                e.target.value = ''
              }}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className='text-base'>
              {nama ? `SKILL.md — ${nama}` : 'Skill baru'}
            </CardTitle>
            <CardDescription>
              Nama folder hanya huruf kecil, angka, garis, dan garis bawah.
              Frontmatter `name`/`description` opsional.
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-4'>
            <div className='space-y-2'>
              <Label htmlFor='s-name'>Nama skill</Label>
              <Input
                id='s-name'
                value={nama}
                onChange={(e) => setNama(e.target.value)}
                placeholder='humanizer'
                className='font-mono'
              />
            </div>
            <div className='space-y-2'>
              <Label htmlFor='s-isi'>Isi SKILL.md</Label>
              <Textarea
                id='s-isi'
                value={isi}
                onChange={(e) => setIsi(e.target.value)}
                placeholder='# Nama skill&#10;&#10;Instruksi...'
                className='min-h-[420px] font-mono text-xs'
              />
            </div>
            <div className='flex flex-wrap items-center gap-3 border-t pt-4'>
              <Button onClick={simpan} disabled={busy || !nama || !isi.trim()}>
                <Save /> Simpan
              </Button>
              {nama ? (
                <Button variant='ghost' onClick={() => setHapus(nama)}>
                  <Trash2 /> Hapus
                </Button>
              ) : null}
              {pesan ? <p className='text-sm text-muted-foreground'>{pesan}</p> : null}
            </div>
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={hapus !== null}
        onOpenChange={(v) => !v && setHapus(null)}
        title='Hapus skill?'
        message={`Folder skill ${hapus || ''} akan dihapus.`}
        onConfirm={hapusSkill}
        busy={busy}
      />
    </div>
  )
}
