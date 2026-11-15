'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { CheckCircle2, FileUp, ListTodo, Play, RefreshCw, Sparkles } from 'lucide-react'
import { api, postForm, postJSON } from '@/lib/api'
import type { Course, CourseSession } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { PageHeader } from '@/components/page-header'
import { ModelInput } from '@/components/model-input'

/** Baris opsi: kotak centang dengan keterangan singkat di bawahnya. */
function Opsi({
  checked,
  onChange,
  title,
  desc,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  title: string
  desc: string
}) {
  return (
    <label
      className={cn(
        'flex cursor-pointer items-start gap-2.5 rounded-md border p-3 text-sm transition-colors',
        checked ? 'border-primary/40 bg-accent/60' : 'hover:bg-accent/40',
      )}
    >
      <Checkbox
        checked={checked}
        onCheckedChange={(v) => onChange(Boolean(v))}
        className='mt-0.5'
      />
      <span className='min-w-0'>
        <span className='block font-medium'>{title}</span>
        <span className='text-muted-foreground mt-0.5 block text-xs'>{desc}</span>
      </span>
    </label>
  )
}

export default function BuatPage() {
  const router = useRouter()
  const { data: courses, isLoading: coursesLoading, error: coursesError } =
    useSWR<Course[]>('/api/courses')
  const { data: modelData } = useSWR<{ models: string[]; error: string }>(
    '/api/models',
  )
  const models = modelData?.models || []

  const daftar = courses || []

  // ---- form Moodle
  const [matkul, setMatkul] = useState('')
  const [sesi, setSesi] = useState('')
  const [jenis, setJenis] = useState('auto')
  const [tanpaDocx, setTanpaDocx] = useState(false)
  const [tanpaGambar, setTanpaGambar] = useState(false)
  const [model, setModel] = useState('')
  const [modelMata, setModelMata] = useState('')
  const [sesiList, setSesiList] = useState<CourseSession[]>([])
  const [sesiLoading, setSesiLoading] = useState(false)
  const [sesiError, setSesiError] = useState('')
  const [scrapeMsg, setScrapeMsg] = useState('')
  const [scrapeBusy, setScrapeBusy] = useState(false)

  const loadSessions = useCallback(
    async (paksa = false) => {
      if (!matkul) {
        setSesiList([])
        return
      }
      setSesiLoading(true)
      setSesiError('')
      setSesi('')
      try {
        const suffix = paksa ? '?paksa=1' : ''
        const url =
          matkul === 'semua'
            ? `/api/sessions${suffix}`
            : `/api/courses/${encodeURIComponent(matkul)}/sessions${suffix}`
        const list = await api<CourseSession[]>(url)
        setSesiList(
          (Array.isArray(list) ? list : []).filter(
            (s) => s.jumlah === undefined || Number(s.jumlah) > 0,
          ),
        )
      } catch (e) {
        setSesiList([])
        setSesiError((e as Error).message)
      } finally {
        setSesiLoading(false)
      }
    },
    [matkul],
  )

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  // ---- form manual
  const [mnMatkul, setMnMatkul] = useState('')
  const [mnSesi, setMnSesi] = useState('1')
  const [mnJenis, setMnJenis] = useState('Tugas')
  const [mnSoal, setMnSoal] = useState('')
  const [mnFiles, setMnFiles] = useState<FileList | null>(null)
  const [mnGambar, setMnGambar] = useState(true)
  const [mnRef, setMnRef] = useState(true)
  const [mnTanpaDocx, setMnTanpaDocx] = useState(false)
  const [mnModel, setMnModel] = useState('')
  const [mnModelMata, setMnModelMata] = useState('')
  const [mnMsg, setMnMsg] = useState('')
  const [mnBusy, setMnBusy] = useState(false)

  const mnCourse = useMemo(
    () => daftar.find((c) => c.id === mnMatkul),
    [daftar, mnMatkul],
  )

  const galatMatkul = coursesError ? (coursesError as Error).message : ''

  async function submitScrape() {
    if (!matkul) return setScrapeMsg('Pilih mata kuliah.')
    if (matkul === 'semua' && !sesi)
      return setScrapeMsg('Pilih sesi untuk semua mata kuliah.')
    setScrapeBusy(true)
    setScrapeMsg('')
    try {
      const r = await postJSON<{
        jobs: string[]
        skipped?: { matkul: string; alasan: string }[]
      }>('/api/jobs/scrape', {
        matkul_id: matkul,
        sesi: Number(sesi || 0),
        jenis: jenis === 'auto' ? '' : jenis,
        tanpa_docx: tanpaDocx,
        tanpa_gambar: tanpaGambar,
        model,
        model_mata: modelMata,
      })
      router.push(`/log/?job=${encodeURIComponent(r.jobs[0])}`)
    } catch (e) {
      setScrapeMsg((e as Error).message)
      setScrapeBusy(false)
    }
  }

  async function submitManual() {
    if (!mnCourse) return setMnMsg('Pilih mata kuliah.')
    setMnBusy(true)
    setMnMsg('')
    const fd = new FormData()
    fd.append('matkul_nama', mnCourse.nama || '')
    fd.append('matkul_kode', mnCourse.kode || '')
    fd.append('matkul_kelas', mnCourse.kelas || '')
    fd.append('sesi', mnSesi)
    fd.append('jenis', mnJenis)
    fd.append('question', mnSoal)
    fd.append('dengan_gambar', mnGambar ? 'on' : 'off')
    fd.append('dengan_referensi', mnRef ? 'on' : 'off')
    fd.append('tanpa_docx', mnTanpaDocx ? 'on' : 'off')
    fd.append('model', mnModel)
    fd.append('model_mata', mnModelMata)
    if (mnFiles) {
      for (const f of Array.from(mnFiles)) fd.append('file', f, f.name)
    }
    try {
      const r = await postForm<{ jobs: string[] }>('/api/jobs/manual', fd)
      router.push(`/log/?job=${encodeURIComponent(r.jobs[0])}`)
    } catch (e) {
      setMnMsg((e as Error).message)
      setMnBusy(false)
    }
  }

  return (
    <div className='flex flex-col gap-4'>
      <PageHeader
        title='Kerjakan Tugas'
        description='Ambil soal dari Moodle atau tempel/unggah soal sendiri.'
      />

      <Tabs defaultValue='scrape' className='gap-4'>
        <TabsList>
          <TabsTrigger value='scrape'>
            <Sparkles /> Dari Moodle
          </TabsTrigger>
          <TabsTrigger value='manual'>
            <ListTodo /> Input Manual
          </TabsTrigger>
        </TabsList>

        <TabsContent value='scrape'>
          <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,340px)] xl:items-start'>
            <Card className='gap-4 py-5'>
              <CardHeader className='px-5'>
                <CardTitle className='text-base'>Pilih sesi Moodle</CardTitle>
                <CardDescription>
                  Mata kuliah &amp; sesi yang sudah di-scrape dari akun Moodle
                  (memakai cookie di .env).
                </CardDescription>
              </CardHeader>
              <CardContent className='space-y-4 px-5'>
                <div className='grid gap-4 sm:grid-cols-3'>
                  <div className='space-y-2 sm:col-span-2'>
                    <Label>Mata kuliah</Label>
                    {coursesLoading ? (
                      <Skeleton className='h-9 w-full' />
                    ) : (
                      <Select value={matkul} onValueChange={setMatkul}>
                        <SelectTrigger className='w-full'>
                          <SelectValue placeholder='— pilih —' />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value='semua'>Semua mata kuliah</SelectItem>
                          {daftar.map((c) => (
                            <SelectItem key={c.id} value={c.id}>
                              {c.nama}
                              {c.kode ? ` (${c.kode})` : ''}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </div>

                  <div className='space-y-2'>
                    <div className='flex items-center justify-between'>
                      <Label>Sesi</Label>
                      <Button
                        type='button'
                        size='icon-xs'
                        variant='ghost'
                        title='Muat ulang daftar sesi dari Moodle'
                        disabled={!matkul || sesiLoading}
                        onClick={() => loadSessions(true)}
                      >
                        <RefreshCw className={sesiLoading ? 'animate-spin' : ''} />
                      </Button>
                    </div>
                    {sesiLoading ? (
                      <Skeleton className='h-9 w-full' />
                    ) : (
                      <Select value={sesi} onValueChange={setSesi}>
                        <SelectTrigger className='w-full' disabled={!sesiList.length}>
                          <SelectValue
                            placeholder={
                              !matkul
                                ? 'Pilih mata kuliah dulu'
                                : sesiList.length
                                  ? '— pilih sesi —'
                                  : 'tidak ada sesi'
                            }
                          />
                        </SelectTrigger>
                        <SelectContent>
                          {sesiList.map((s) => (
                            <SelectItem key={s.sesi} value={String(s.sesi)}>
                              Sesi {s.sesi}
                              {s.jumlah !== undefined ? ` (${s.jumlah} soal)` : ''}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                </div>

                <div className='grid gap-4 sm:grid-cols-2'>
                  <div className='space-y-2'>
                    <Label>Jenis soal</Label>
                    <Select value={jenis} onValueChange={setJenis}>
                      <SelectTrigger className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='auto'>Otomatis (ikut sesi)</SelectItem>
                        <SelectItem value='Tugas'>Tugas saja</SelectItem>
                        <SelectItem value='Diskusi'>Diskusi saja</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className='text-muted-foreground text-xs'>
                      &quot;Otomatis&quot; mengerjakan semua soal di sesi itu.
                    </p>
                  </div>
                  <div className='grid gap-2'>
                    <Label>Opsi job</Label>
                    <Opsi
                      checked={tanpaDocx}
                      onChange={setTanpaDocx}
                      title='Tanpa DOCX'
                      desc='Hanya menghasilkan .md'
                    />
                    <Opsi
                      checked={tanpaGambar}
                      onChange={setTanpaGambar}
                      title='Lewati gambar'
                      desc='Tidak menjalankan transkripsi vision'
                    />
                  </div>
                </div>

                <div className='grid gap-4 sm:grid-cols-2'>
                  <div className='space-y-2'>
                    <Label htmlFor='sc-model'>Model utama (opsional)</Label>
                    <ModelInput
                      id='sc-model'
                      value={model}
                      onChange={setModel}
                      models={models}
                    />
                  </div>
                  <div className='space-y-2'>
                    <Label htmlFor='sc-model-mata'>Model vision (opsional)</Label>
                    <ModelInput
                      id='sc-model-mata'
                      value={modelMata}
                      onChange={setModelMata}
                      models={models}
                    />
                  </div>
                </div>

                <div className='flex flex-wrap items-center gap-2 border-t pt-4'>
                  <Button onClick={submitScrape} disabled={scrapeBusy}>
                    <Play /> {scrapeBusy ? 'Mengantrekan job...' : 'Mulai dari Moodle'}
                  </Button>
                  {scrapeMsg || galatMatkul || sesiError ? (
                    <p className='text-destructive text-sm'>
                      {scrapeMsg || galatMatkul || sesiError}
                    </p>
                  ) : null}
                </div>
              </CardContent>
            </Card>

            <Card className='gap-4 py-5'>
              <CardHeader className='px-5'>
                <CardTitle className='text-base'>Alur job</CardTitle>
                <CardDescription>
                  Setelah diantrekan, halaman Log Live terbuka otomatis.
                </CardDescription>
              </CardHeader>
              <CardContent className='space-y-3 px-5'>
                {[
                  'Scrape soal dari Moodle sesuai sesi',
                  'Agent menyusun peta soal & referensi',
                  'Worker menulis jawaban',
                  'DOCX dirakit dan bisa diunduh',
                ].map((step, i) => (
                  <div key={step} className='flex items-start gap-2.5'>
                    <span className='bg-primary/10 text-primary flex size-6 shrink-0 items-center justify-center rounded-sm text-[11px] font-semibold'>
                      {i + 1}
                    </span>
                    <span className='text-muted-foreground text-sm'>{step}</span>
                  </div>
                ))}
                <div className='border-t pt-3'>
                  <Badge variant='outline' className='gap-1.5'>
                    <CheckCircle2 className='size-3' /> Isolasi per akun Clerk
                  </Badge>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value='manual'>
          <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,340px)] xl:items-start'>
            <Card className='gap-4 py-5'>
              <CardHeader className='px-5'>
                <CardTitle className='text-base'>Soal manual</CardTitle>
                <CardDescription>
                  Tempel rumusan soal atau unggah berkas (doc, pdf, gambar).
                </CardDescription>
              </CardHeader>
              <CardContent className='space-y-4 px-5'>
                <div className='grid gap-4 sm:grid-cols-3'>
                  <div className='space-y-2 sm:col-span-2'>
                    <Label>Mata kuliah</Label>
                    {coursesLoading ? (
                      <Skeleton className='h-9 w-full' />
                    ) : (
                      <Select value={mnMatkul} onValueChange={setMnMatkul}>
                        <SelectTrigger className='w-full'>
                          <SelectValue placeholder='— pilih —' />
                        </SelectTrigger>
                        <SelectContent>
                          {daftar.map((c) => (
                            <SelectItem key={c.id} value={c.id}>
                              {c.nama}
                              {c.kode ? ` (${c.kode})` : ''}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                  <div className='space-y-2'>
                    <Label htmlFor='mn-sesi'>Sesi</Label>
                    <Input
                      id='mn-sesi'
                      type='number'
                      min={1}
                      value={mnSesi}
                      onChange={(e) => setMnSesi(e.target.value)}
                    />
                  </div>
                </div>

                <div className='grid gap-4 sm:grid-cols-2'>
                  <div className='space-y-2'>
                    <Label>Jenis</Label>
                    <Select value={mnJenis} onValueChange={setMnJenis}>
                      <SelectTrigger className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='Tugas'>Tugas</SelectItem>
                        <SelectItem value='Diskusi'>Diskusi</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className='space-y-2'>
                    <Label htmlFor='mn-files'>Berkas soal</Label>
                    <div className='relative'>
                      <Input
                        id='mn-files'
                        type='file'
                        multiple
                        className='file:me-2'
                        onChange={(e) => setMnFiles(e.target.files)}
                      />
                    </div>
                    <p className='text-muted-foreground text-xs'>
                      {mnFiles?.length
                        ? `${mnFiles.length} berkas dipilih`
                        : 'Bisa lebih dari satu berkas.'}
                    </p>
                  </div>
                </div>

                {mnCourse ? (
                  <p className='text-muted-foreground text-xs'>
                    Kode: {mnCourse.kode || '-'} · Kelas: {mnCourse.kelas || '-'}
                  </p>
                ) : null}

                <div className='space-y-2'>
                  <Label htmlFor='mn-soal'>Soal (tempel teks)</Label>
                  <Textarea
                    id='mn-soal'
                    value={mnSoal}
                    onChange={(e) => setMnSoal(e.target.value)}
                    placeholder='Tempel rumusan soal di sini...'
                    className='min-h-32'
                  />
                </div>

                <div className='flex flex-wrap items-center gap-2 border-t pt-4'>
                  <Button onClick={submitManual} disabled={mnBusy}>
                    <Play /> {mnBusy ? 'Mengantrekan job...' : 'Mulai Manual'}
                  </Button>
                  {mnMsg || galatMatkul ? (
                    <p className='text-destructive text-sm'>{mnMsg || galatMatkul}</p>
                  ) : null}
                </div>
              </CardContent>
            </Card>

            <Card className='gap-4 py-5'>
              <CardHeader className='px-5'>
                <CardTitle className='text-base'>Opsi pengerjaan</CardTitle>
                <CardDescription>
                  Berlaku untuk job manual ini saja.
                </CardDescription>
              </CardHeader>
              <CardContent className='space-y-2 px-5'>
                <Opsi
                  checked={mnGambar}
                  onChange={setMnGambar}
                  title='Transkripsi gambar'
                  desc='Baca gambar dengan model vision'
                />
                <Opsi
                  checked={mnRef}
                  onChange={setMnRef}
                  title='Cari daftar pustaka'
                  desc='Agent research menyusun referensi'
                />
                <Opsi
                  checked={mnTanpaDocx}
                  onChange={setMnTanpaDocx}
                  title='Tanpa DOCX'
                  desc='Hanya menghasilkan .md'
                />
                <div className='grid gap-4 border-t pt-3'>
                  <div className='space-y-2'>
                    <Label htmlFor='mn-model'>Model utama</Label>
                    <ModelInput
                      id='mn-model'
                      value={mnModel}
                      onChange={setMnModel}
                      models={models}
                    />
                  </div>
                  <div className='space-y-2'>
                    <Label htmlFor='mn-model-mata'>Model vision</Label>
                    <ModelInput
                      id='mn-model-mata'
                      value={mnModelMata}
                      onChange={setMnModelMata}
                      models={models}
                    />
                  </div>
                  <p className='text-muted-foreground flex items-center gap-1.5 text-xs'>
                    <FileUp className='size-3.5' /> Kosongkan untuk memakai nilai
                    dari Pengaturan.
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
