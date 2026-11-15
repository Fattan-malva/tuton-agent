'use client'

import { useEffect, useState, type DragEvent } from 'react'
import useSWR from 'swr'
import { ArrowDown, ArrowLeft, ArrowUp, Save, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { apiFetch, postJSON } from '@/lib/api'
import { DocxPreviewFrame } from '@/components/docx-preview-frame'
import { usePratinjauPdf } from '@/hooks/use-pratinjau-pdf'

type Nilai = string | number | boolean | string[] | undefined
type Blok = { type: string } & Record<string, Nilai>
type Skema = { font: string; size_pt: number; line: number; after_pt: number; margin_cm: number; blocks: Blok[] }
type Templat = { id: string; name: string; description: string; schema: Skema }

const FONTS = ['Times New Roman', 'Arial', 'Calibri', 'Cambria']
const UNIK = ['title', 'identity', 'soal', 'answer', 'kesimpulan', 'references']

const JENIS: { type: string; label: string }[] = [
  { type: 'title', label: 'Judul' },
  { type: 'identity', label: 'Identitas' },
  { type: 'soal', label: 'Soal (teks atau gambar)' },
  { type: 'heading', label: 'Heading / sub-heading' },
  { type: 'text', label: 'Paragraf' },
  { type: 'bullets', label: 'Poin-poin' },
  { type: 'numbered', label: 'Daftar bernomor' },
  { type: 'table', label: 'Tabel' },
  { type: 'box', label: 'Kotak isian' },
  { type: 'rule', label: 'Garis pemisah' },
  { type: 'answer', label: 'Area jawaban' },
  { type: 'kesimpulan', label: 'Kesimpulan' },
  { type: 'references', label: 'Daftar pustaka (APA 7)' },
]

const BARU: Record<string, Blok> = {
  title: { type: 'title', text: 'Judul tugas', align: 'center', size_pt: 14, bold: true, frame: false },
  identity: { type: 'identity', bordered: false },
  soal: { type: 'soal', min_lines: 4 },
  heading: { type: 'heading', level: 2, text: 'Heading' },
  text: { type: 'text', text: 'Lorem ipsum dolor sit amet.', align: 'justify' },
  bullets: { type: 'bullets', items: ['Lorem ipsum', 'Dolor sit amet'] },
  numbered: { type: 'numbered', items: ['Lorem ipsum', 'Dolor sit amet'] },
  table: { type: 'table', columns: ['Kolom 1', 'Kolom 2'], rows: 3, bordered: true },
  box: { type: 'box', text: 'Lorem ipsum', min_lines: 4 },
  rule: { type: 'rule' },
  answer: { type: 'answer', placeholder: 'Jawaban' },
  kesimpulan: { type: 'kesimpulan' },
  references: { type: 'references' },
}

// Isian per jenis blok. `lines` = satu item per baris.
type Isian = { key: string; label: string; kind: 'text' | 'area' | 'num' | 'bool' | 'lines' | 'select'; opsi?: string[]; angka?: boolean }
const ISIAN: Record<string, Isian[]> = {
  title: [
    { key: 'text', label: 'Teks judul', kind: 'text' },
    { key: 'align', label: 'Perataan', kind: 'select', opsi: ['left', 'center', 'right', 'justify'] },
    { key: 'size_pt', label: 'Ukuran (pt)', kind: 'num' },
    { key: 'bold', label: 'Tebal', kind: 'bool' },
    { key: 'frame', label: 'Berbingkai', kind: 'bool' },
  ],
  identity: [{ key: 'bordered', label: 'Tabel berbingkai', kind: 'bool' }],
  soal: [{ key: 'min_lines', label: 'Tinggi kotak gambar (baris)', kind: 'num' }],
  heading: [
    { key: 'level', label: 'Level', kind: 'select', opsi: ['1', '2', '3'], angka: true },
    { key: 'text', label: 'Teks', kind: 'text' },
  ],
  text: [
    { key: 'text', label: 'Teks', kind: 'area' },
    { key: 'align', label: 'Perataan', kind: 'select', opsi: ['left', 'center', 'right', 'justify'] },
  ],
  bullets: [{ key: 'items', label: 'Item (satu per baris)', kind: 'lines' }],
  numbered: [{ key: 'items', label: 'Item (satu per baris)', kind: 'lines' }],
  table: [
    { key: 'columns', label: 'Kolom (satu per baris)', kind: 'lines' },
    { key: 'rows', label: 'Jumlah baris isi', kind: 'num' },
    { key: 'bordered', label: 'Berbingkai', kind: 'bool' },
  ],
  box: [
    { key: 'text', label: 'Teks contoh', kind: 'area' },
    { key: 'min_lines', label: 'Tinggi (baris)', kind: 'num' },
  ],
  answer: [{ key: 'placeholder', label: 'Teks penanda', kind: 'text' }],
}

const slug = (s: string) => s.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64)
const labelJenis = (t: string) => JENIS.find(j => j.type === t)?.label ?? t

function posisiBaru(blok: Blok[], type: string): number {
  const idx = (t: string) => blok.findIndex(b => b.type === t)
  const akhir = blok.length
  if (type === 'title') return 0
  if (type === 'identity') return idx('title') + 1
  if (type === 'soal') return (idx('identity') >= 0 ? idx('identity') : idx('title')) + 1
  if (type === 'answer') {
    const ke = blok.findIndex(b => b.type === 'kesimpulan' || b.type === 'references')
    return ke >= 0 ? ke : akhir
  }
  if (type === 'kesimpulan') return idx('answer') >= 0 ? idx('answer') + 1 : akhir
  if (type === 'references') return akhir
  return idx('answer') >= 0 ? idx('answer') : akhir
}

function payload(s: Skema): Skema {
  return {
    ...s,
    blocks: s.blocks.map(b => ({
      ...b,
      ...(Array.isArray(b.items) ? { items: b.items.filter(x => x.trim()) } : {}),
      ...(Array.isArray(b.columns) ? { columns: b.columns.filter(x => x.trim()) } : {}),
    })),
  }
}

async function muat(id: string): Promise<Templat> {
  const r = await apiFetch(`/api/templates/${encodeURIComponent(id)}`)
  if (!r.ok) throw new Error('Template tidak bisa dimuat.')
  return (await r.json()).template as Templat
}

export function TemplateEditor({ editId, onBatal, onSimpan }: { editId?: string; onBatal: () => void; onSimpan: () => void }) {
  const { data: daftar } = useSWR<{ templates: { id: string; name: string }[] }>('/api/templates')
  const [nama, setNama] = useState('Template baru')
  const [deskripsi, setDeskripsi] = useState('')
  const [skema, setSkema] = useState<Skema | null>(null)
  const [terpilih, setTerpilih] = useState(0)
  const [pesan, setPesan] = useState('')
  const [menyimpan, setMenyimpan] = useState(false)
  const [pratinjauSkema, setPratinjauSkema] = useState<Skema | null>(null)

  useEffect(() => {
    let batal = false
    muat(editId ?? 'akademik-standar')
      .then(t => {
        if (batal) return
        setSkema(t.schema)
        if (editId) { setNama(t.name); setDeskripsi(t.description) }
      })
      .catch(e => { if (!batal) setPesan((e as Error).message) })
    return () => { batal = true }
  }, [editId])

  // Pratinjau diperbarui 500 ms setelah perubahan terakhir supaya tidak
  // mengonversi PDF di setiap ketukan tombol.
  useEffect(() => {
    if (!skema) return
    const t = setTimeout(() => setPratinjauSkema(skema), 500)
    return () => clearTimeout(t)
  }, [skema])

  const pratinjau = usePratinjauPdf(pratinjauSkema ? { schema: payload(pratinjauSkema) } : null)

  function ubahBlok(fn: (bs: Blok[]) => Blok[]) {
    setSkema(s => (s ? { ...s, blocks: fn(s.blocks) } : s))
  }

  function setField(key: string, value: Nilai) {
    ubahBlok(bs => bs.map((b, i) => (i === terpilih ? { ...b, [key]: value } : b)))
  }

  function tambah(type: string, at?: number) {
    if (!skema) return
    if (UNIK.includes(type) && skema.blocks.some(b => b.type === type)) {
      setPesan(`${labelJenis(type)} hanya boleh satu.`)
      return
    }
    setPesan('')
    const to = at ?? posisiBaru(skema.blocks, type)
    ubahBlok(bs => { const x = [...bs]; x.splice(to, 0, { ...BARU[type] }); return x })
    setTerpilih(to)
  }

  function pindah(from: number, target: number) {
    if (!skema) return
    const to = target > from ? target - 1 : target
    if (to === from) return
    ubahBlok(bs => { const x = [...bs]; const [item] = x.splice(from, 1); x.splice(to, 0, item); return x })
    setTerpilih(to)
  }

  function geser(i: number, arah: -1 | 1) {
    const j = i + arah
    if (!skema || j < 0 || j >= skema.blocks.length) return
    ubahBlok(bs => { const x = [...bs]; [x[i], x[j]] = [x[j], x[i]]; return x })
    setTerpilih(j)
  }

  function hapus(i: number) {
    ubahBlok(bs => bs.filter((_, k) => k !== i))
    setTerpilih(0)
  }

  function dragPalet(e: DragEvent, type: string) {
    e.dataTransfer.setData('text/plain', `baru:${type}`)
    e.dataTransfer.effectAllowed = 'copy'
  }
  function dragBlok(e: DragEvent, i: number) {
    e.dataTransfer.setData('text/plain', `pindah:${i}`)
    e.dataTransfer.effectAllowed = 'move'
  }
  function jatuh(e: DragEvent, target: number) {
    e.preventDefault()
    e.stopPropagation()
    const data = e.dataTransfer.getData('text/plain')
    if (data.startsWith('baru:')) tambah(data.slice(5), target)
    else if (data.startsWith('pindah:')) pindah(Number(data.slice(7)), target)
  }
  function jatuhDiBawah(e: DragEvent) {
    if (skema) jatuh(e, skema.blocks.length)
  }
  function jatuhDiBlok(e: DragEvent, i: number) {
    const r = e.currentTarget.getBoundingClientRect()
    jatuh(e, e.clientY > r.top + r.height / 2 ? i + 1 : i)
  }

  async function pilihMulaiDari(id: string) {
    try {
      const t = await muat(id)
      setSkema(t.schema)
      setTerpilih(0)
      setPesan('')
    } catch (e) { setPesan((e as Error).message) }
  }

  async function simpan() {
    if (!skema) return
    const id = editId ?? slug(nama)
    if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(id)) {
      setPesan('Nama template harus memuat huruf atau angka.')
      return
    }
    setMenyimpan(true)
    setPesan('')
    try {
      await postJSON('/api/templates/save', { id, name: nama.trim() || id, description: deskripsi.trim(), schema: payload(skema) })
      onSimpan()
    } catch (e) {
      setPesan((e as Error).message)
    } finally {
      setMenyimpan(false)
    }
  }

  const sel = skema?.blocks[terpilih]
  const teks = (v: Nilai) => (typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '')
  const fieldKelas = 'h-9 w-full rounded-md border bg-background px-2 text-sm'

  return (
    <div className='flex flex-col gap-4'>
      <div className='flex flex-wrap items-end gap-3'>
        <Button variant='ghost' onClick={onBatal}><ArrowLeft /> Kembali</Button>
        <div className='flex min-w-56 flex-1 flex-col gap-1.5'>
          <Label htmlFor='tpl-nama'>Nama template</Label>
          <Input id='tpl-nama' value={nama} disabled={!!editId} onChange={e => setNama(e.target.value)} />
        </div>
        <div className='flex min-w-56 flex-1 flex-col gap-1.5'>
          <Label htmlFor='tpl-desk'>Deskripsi</Label>
          <Input id='tpl-desk' value={deskripsi} onChange={e => setDeskripsi(e.target.value)} />
        </div>
        <div className='flex w-56 flex-col gap-1.5'>
          <Label>Mulai dari</Label>
          <Select onValueChange={pilihMulaiDari}>
            <SelectTrigger><SelectValue placeholder='Pilih template dasar' /></SelectTrigger>
            <SelectContent>{daftar?.templates.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <Button onClick={simpan} disabled={!skema || menyimpan}><Save /> {menyimpan ? 'Menyimpan…' : 'Simpan template'}</Button>
      </div>
      {pesan && <p role='status' className='text-destructive text-sm'>{pesan}</p>}

      <div className='grid gap-4 lg:grid-cols-[13rem_minmax(0,1fr)_minmax(0,1.1fr)]'>
        <aside className='flex flex-col gap-2 rounded-lg border p-3'>
          <p className='text-sm font-medium'>Blok</p>
          <p className='text-muted-foreground text-xs'>Seret ke kanvas, atau klik untuk menambah.</p>
          {JENIS.map(j => {
            const sudahAda = UNIK.includes(j.type) && !!skema?.blocks.some(b => b.type === j.type)
            return (
              <button
                key={j.type}
                type='button'
                draggable={!sudahAda}
                onDragStart={e => dragPalet(e, j.type)}
                onClick={() => tambah(j.type)}
                disabled={sudahAda}
                className='hover:bg-muted rounded-md border px-2.5 py-2 text-start text-sm disabled:opacity-40'
              >
                {j.label}
              </button>
            )
          })}
        </aside>

        <section className='flex min-w-0 flex-col gap-3'>
          <div
            className='flex min-h-64 flex-col gap-1.5 rounded-lg border p-2'
            onDragOver={e => e.preventDefault()}
            onDrop={jatuhDiBawah}
          >
            {skema?.blocks.map((b, i) => {
              const isi = teks(b.text) || teks(b.placeholder) || ''
              return (
                <div
                  key={i}
                  draggable
                  onDragStart={e => dragBlok(e, i)}
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => jatuhDiBlok(e, i)}
                  onClick={() => setTerpilih(i)}
                  className={`flex cursor-grab items-center gap-2 rounded-md border px-3 py-2 text-sm ${i === terpilih ? 'border-primary bg-muted' : ''}`}
                >
                  <span className='font-medium'>{labelJenis(b.type)}</span>
                  <span className='text-muted-foreground truncate'>{isi.slice(0, 60)}</span>
                </div>
              )
            })}
            {skema && skema.blocks.length === 0 && <p className='text-muted-foreground p-4 text-center text-sm'>Kanvas kosong.</p>}
          </div>

          {sel && (
            <div className='flex flex-col gap-3 rounded-lg border p-3'>
              <div className='flex items-center justify-between'>
                <p className='text-sm font-medium'>{labelJenis(sel.type)}</p>
                <div className='flex gap-1'>
                  <Button size='icon' variant='ghost' aria-label='Naik' onClick={() => geser(terpilih, -1)}><ArrowUp /></Button>
                  <Button size='icon' variant='ghost' aria-label='Turun' onClick={() => geser(terpilih, 1)}><ArrowDown /></Button>
                  <Button size='icon' variant='ghost' aria-label='Hapus blok' onClick={() => hapus(terpilih)}><Trash2 /></Button>
                </div>
              </div>
              {(ISIAN[sel.type] ?? []).map(f => {
                const v = sel[f.key]
                if (f.kind === 'bool') return (
                  <label key={f.key} className='flex items-center gap-2 text-sm'>
                    <input type='checkbox' checked={v === true} onChange={e => setField(f.key, e.target.checked)} />{f.label}
                  </label>
                )
                if (f.kind === 'select') return (
                  <div key={f.key} className='flex flex-col gap-1.5'>
                    <Label>{f.label}</Label>
                    <select className={fieldKelas} value={teks(v)} onChange={e => setField(f.key, f.angka ? Number(e.target.value) : e.target.value)}>
                      {f.opsi?.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </div>
                )
                if (f.kind === 'num') return (
                  <div key={f.key} className='flex flex-col gap-1.5'>
                    <Label>{f.label}</Label>
                    <Input type='number' value={typeof v === 'number' ? v : 0} onChange={e => setField(f.key, Number(e.target.value))} />
                  </div>
                )
                if (f.kind === 'lines') return (
                  <div key={f.key} className='flex flex-col gap-1.5'>
                    <Label>{f.label}</Label>
                    <Textarea rows={4} value={Array.isArray(v) ? v.join('\n') : ''} onChange={e => setField(f.key, e.target.value.split('\n'))} />
                  </div>
                )
                if (f.kind === 'area') return (
                  <div key={f.key} className='flex flex-col gap-1.5'>
                    <Label>{f.label}</Label>
                    <Textarea rows={3} value={teks(v)} onChange={e => setField(f.key, e.target.value)} />
                  </div>
                )
                return (
                  <div key={f.key} className='flex flex-col gap-1.5'>
                    <Label>{f.label}</Label>
                    <Input value={teks(v)} onChange={e => setField(f.key, e.target.value)} />
                  </div>
                )
              })}
              {!ISIAN[sel.type] && <p className='text-muted-foreground text-xs'>Blok ini diisi otomatis oleh pipeline saat tugas dibuat.</p>}
            </div>
          )}

          {skema && (
            <div className='grid grid-cols-2 gap-3 rounded-lg border p-3 sm:grid-cols-5'>
              <div className='flex flex-col gap-1.5'>
                <Label>Font</Label>
                <select className={fieldKelas} value={skema.font} onChange={e => setSkema({ ...skema, font: e.target.value })}>
                  {FONTS.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
              {([['size_pt', 'Ukuran (pt)'], ['line', 'Spasi baris'], ['after_pt', 'Jarak paragraf (pt)'], ['margin_cm', 'Margin (cm)']] as const).map(([k, l]) => (
                <div key={k} className='flex flex-col gap-1.5'>
                  <Label>{l}</Label>
                  <Input type='number' step='0.1' value={skema[k]} onChange={e => setSkema({ ...skema, [k]: Number(e.target.value) })} />
                </div>
              ))}
            </div>
          )}
        </section>

        <section className='bg-muted flex flex-col gap-2 rounded-lg border p-3 lg:sticky lg:top-4 lg:self-start'>
          <p className='text-sm font-medium'>Pratinjau</p>
          <DocxPreviewFrame url={pratinjau.url} loading={pratinjau.loading} error={pratinjau.error} title='Pratinjau template' className='h-[72vh]' />
        </section>
      </div>
    </div>
  )
}
