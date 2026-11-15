'use client'

import useSWR from 'swr'
import { useState } from 'react'
import { PageHeader } from '@/components/page-header'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { postJSON } from '@/lib/api'

type Template = { id: string; name: string; description: string }
export default function TemplatesPage() {
  const { data, mutate } = useSWR<{ templates: Template[]; default_id: string }>('/api/templates')
  const [message, setMessage] = useState('')
  async function select(id: string) {
    try { await postJSON('/api/templates/default', { id }); await mutate(); setMessage('Template default disimpan.') }
    catch (e) { setMessage((e as Error).message) }
  }
  return <div className='flex flex-col gap-4'><PageHeader title='Template' description='Template bawaan dan milik akun ini.' />
    <Select value={data?.default_id} onValueChange={select}><SelectTrigger className='max-w-sm'><SelectValue placeholder='Pilih template default' /></SelectTrigger><SelectContent>{data?.templates.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent></Select>
    <div className='grid gap-3 sm:grid-cols-2'>{data?.templates.map(t => <article key={t.id} className='rounded-lg border p-4'><h2 className='font-medium'>{t.name}</h2><p className='text-muted-foreground text-sm'>{t.description}</p><p className='mt-2 text-xs'>{t.id === data.default_id ? 'Default' : t.id}</p></article>)}</div>{message && <p role='status'>{message}</p>}</div>
}
