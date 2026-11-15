'use client'

import { useRef, useState } from 'react'
import useSWR from 'swr'
import { FileUp, Pencil, Trash2 } from 'lucide-react'
import { api, postJSON } from '@/lib/api'
import type { SkillInfo } from '@/lib/types'
import { cn } from '@/lib/utils'
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
import { SaveButton } from '@/components/save-button'
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
    await postJSON('/api/skills/save', { name: nama, content: isi })
    void mutate()
    return 'Skill tersimpan.'
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
      void mutate()
    } catch (e) {
      setPesan((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='flex flex-col gap-4'>
      <PageHeader
        title='Skill'
        description='Instruksi tambahan yang bisa dimuat agent lewat tool `skill`. Satu folder berisi SKILL.md.'
      />

      <div className='grid gap-4 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)] lg:items-start'>
        <Card className='gap-3 py-5 lg:sticky lg:top-[calc(var(--header-h)+1rem)] lg:max-h-[calc(100svh-var(--header-h)-2rem)] lg:overflow-y-auto'>
          <CardHeader className='px-4'>
            <CardTitle className='text-sm'>Daftar skill</CardTitle>
            <CardDescription className='text-xs'>
              Klik untuk mengubah isinya.
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-1 px-2'>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className='h-9 w-full' />
              ))
            ) : (
              (data?.skills || []).map((s) => (
                <button
                  key={s.name}
                  type='button'
                  onClick={() => buka(s.name)}
                  aria-pressed={nama === s.name}
                  className={cn(
                    'hover:bg-accent/60 flex w-full items-center justify-between gap-2 rounded-md px-2 py-2 text-start text-sm transition-colors',
                    nama === s.name && 'bg-accent font-medium',
                  )}
                >
                  <span className='truncate font-mono text-xs'>{s.name}</span>
                  <Pencil className='text-muted-foreground size-3.5 shrink-0' />
                </button>
              ))
            )}
            {!isLoading && !(data?.skills || []).length ? (
              <p className='text-muted-foreground px-2 py-3 text-sm'>Belum ada skill.</p>
            ) : null}
            <div className='px-2 pt-2'>
              <Button
                variant='outline'
                size='sm'
                className='w-full'
                onClick={() => berkas.current?.click()}
              >
                <FileUp /> Unggah berkas
              </Button>
            </div>
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

        <Card className='gap-4 py-5'>
          <CardHeader className='px-5'>
            <CardTitle className='text-base'>
              {nama ? `SKILL.md — ${nama}` : 'Skill baru'}
            </CardTitle>
            <CardDescription>
              Nama folder hanya huruf kecil, angka, garis, dan garis bawah.
              Frontmatter `name`/`description` opsional.
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-4 px-5'>
            <div className='grid gap-4 sm:grid-cols-2'>
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
                <p className='text-muted-foreground flex h-9 items-center text-xs'>
                  Dimuat agent lewat tool <code className='mx-1'>skill</code>.
                  Frontmatter opsional.
                </p>
              </div>
            </div>
            <Textarea
              id='s-isi'
              value={isi}
              onChange={(e) => setIsi(e.target.value)}
              placeholder='# Nama skill&#10;&#10;Instruksi...'
              className='min-h-[440px] font-mono text-xs'
            />
            <div className='flex flex-wrap items-center gap-2 border-t pt-4'>
              <SaveButton
                onSave={simpan}
                disabled={!nama || !isi.trim()}
                label='Simpan skill'
              />
              {nama ? (
                <Button variant='ghost' onClick={() => setHapus(nama)}>
                  <Trash2 /> Hapus
                </Button>
              ) : null}
              {pesan ? <p className='text-muted-foreground text-sm'>{pesan}</p> : null}
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
