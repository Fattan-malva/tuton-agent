'use client'

import useSWR from 'swr'
import { useState } from 'react'
import { Eye, FileText, Plus } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { postJSON } from '@/lib/api'
import { DocxThumb } from '@/components/docx-thumb'
import { TemplatePreviewDialog } from '@/components/template-preview-dialog'

type Template = { id: string; name: string; description: string }

export default function TemplatesPage() {
  const { data, mutate } = useSWR<{ templates: Template[]; default_id: string }>('/api/templates')
  const [message, setMessage] = useState('')
  const [pratinjau, setPratinjau] = useState<Template | null>(null)
  async function select(id: string) {
    try { await postJSON('/api/templates/default', { id }); await mutate(); setMessage('Template default disimpan.') }
    catch (e) { setMessage((e as Error).message) }
  }
  return <div className='flex flex-col gap-4'>
    <PageHeader title='Template DOCX' description='Pilih model tata letak dokumen jawaban. Template default otomatis dipakai saat membuat tugas.' />
    <div className='flex flex-wrap items-center gap-3 rounded-lg border p-4'>
      <div className='min-w-64 flex-1'><p className='text-sm font-medium'>Template default</p><p className='text-muted-foreground text-xs'>Bisa diganti pada tiap tugas.</p></div>
      <Select value={data?.default_id} onValueChange={select}><SelectTrigger className='w-64'><SelectValue placeholder='Pilih template default' /></SelectTrigger><SelectContent>{data?.templates.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent></Select>
      <Button disabled title='Editor drag-and-drop segera tersedia'><Plus /> Buat template</Button>
    </div>
    <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-3'>{data?.templates.map(t => <article key={t.id} className='overflow-hidden rounded-lg border bg-card'>
      <button type='button' onClick={() => setPratinjau(t)} className='block w-full cursor-zoom-in' aria-label={`Buka pratinjau ${t.name}`}><DocxThumb templateId={t.id} label={t.name} /></button>
      <div className='p-4'>
        <div className='flex items-start gap-2'><FileText className='text-muted-foreground mt-0.5 size-4' /><div><h2 className='font-medium'>{t.name}</h2><p className='text-muted-foreground text-sm'>{t.description}</p></div></div>
        <div className='mt-4 grid grid-cols-2 gap-2'>
          <Button variant='outline' onClick={() => setPratinjau(t)}><Eye /> Pratinjau</Button>
          <Button variant={t.id === data.default_id ? 'secondary' : 'outline'} onClick={() => select(t.id)}>{t.id === data.default_id ? 'Default' : 'Jadikan default'}</Button>
        </div>
      </div>
    </article>)}</div>
    {pratinjau && <TemplatePreviewDialog templateId={pratinjau.id} label={pratinjau.name} onOpenChange={open => { if (!open) setPratinjau(null) }} />}
    {message && <p role='status' className='text-sm'>{message}</p>}
  </div>
}
