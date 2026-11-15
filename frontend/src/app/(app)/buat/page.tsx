'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { Play, RefreshCw } from 'lucide-react'
import { api, postForm, postJSON } from '@/lib/api'
import type { Course, CourseSession } from '@/lib/types'
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
import { Card, CardContent } from '@/components/ui/card'
import { PageHeader } from '@/components/page-header'
import { ModelInput } from '@/components/model-input'

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

  const galatMatkul = coursesError
    ? (coursesError as Error).message
    : ''

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
    <div className='space-y-6'>
      <PageHeader
        title='Kerjakan Tugas'
        description='Ambil soal dari Moodle atau tempel/unggah soal sendiri.'
      />

      <Tabs defaultValue='scrape' className='space-y-4'>
        <TabsList>
          <TabsTrigger value='scrape'>Dari Moodle</TabsTrigger>
          <TabsTrigger value='manual'>Input Manual</TabsTrigger>
        </TabsList>

        <TabsContent value='scrape' className='space-y-4'>
          <Card>
            <CardContent className='space-y-4 pt-6'>
        <p className='text-sm text-muted-foreground'>
          Pilih mata kuliah &amp; sesi yang sudah di-scrape dari akun Moodle
          Anda (memakai cookie di .env).
        </p>
        <div className='grid gap-4 sm:grid-cols-3'>
          <div className='space-y-2'>
            <Label>Mata kuliah</Label>
            {coursesLoading ? (
              <Skeleton className='h-9 w-full' />
            ) : (
              <Select value={matkul} onValueChange={setMatkul}>
                <SelectTrigger>
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
                size='icon'
                variant='ghost'
                className='size-6'
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
                <SelectTrigger disabled={!sesiList.length}>
                  <SelectValue
                    placeholder={
                      !matkul
                        ? 'Pilih mata kuliah dulu'
                        : sesiList.length
                          ? '— pilih sesi —'
                          : 'tidak ada sesi dengan soal'
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

          <div className='space-y-2'>
            <Label>Jenis soal</Label>
            <Select value={jenis} onValueChange={setJenis}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='auto'>Otomatis (ikut sesi)</SelectItem>
                <SelectItem value='Tugas'>Tugas saja</SelectItem>
                <SelectItem value='Diskusi'>Diskusi saja</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <p className='text-xs text-muted-foreground'>
          &quot;Otomatis&quot; mengerjakan semua soal yang ada di sesi itu.
          Memilih Tugas atau Diskusi menyaring soalnya.
        </p>

        <div className='flex flex-wrap gap-4'>
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox
              checked={tanpaDocx}
              onCheckedChange={(v) => setTanpaDocx(Boolean(v))}
            />
            Tanpa buat DOCX (hanya .md)
          </label>
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox
              checked={tanpaGambar}
              onCheckedChange={(v) => setTanpaGambar(Boolean(v))}
            />
            Lewati transkripsi gambar
          </label>
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

        <div className='space-y-2'>
          <Button onClick={submitScrape} disabled={scrapeBusy}>
            <Play /> {scrapeBusy ? 'Mengantrekan job...' : 'Mulai dari Moodle'}
          </Button>
          {scrapeMsg || galatMatkul || sesiError ? (
            <p className='text-sm text-destructive'>
              {scrapeMsg || galatMatkul || sesiError}
            </p>
          ) : null}
        </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value='manual' className='space-y-4'>
          <Card>
            <CardContent className='space-y-4 pt-6'>
              <div className='grid gap-4 sm:grid-cols-3'>
          <div className='space-y-2'>
            <Label>Mata kuliah</Label>
            {coursesLoading ? (
              <Skeleton className='h-9 w-full' />
            ) : (
              <Select value={mnMatkul} onValueChange={setMnMatkul}>
                <SelectTrigger>
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
          <div className='space-y-2'>
            <Label>Jenis</Label>
            <Select value={mnJenis} onValueChange={setMnJenis}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='Tugas'>Tugas</SelectItem>
                <SelectItem value='Diskusi'>Diskusi</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {mnCourse ? (
          <p className='text-xs text-muted-foreground'>
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
            className='min-h-28'
          />
        </div>

        <div className='space-y-2'>
          <Label htmlFor='mn-files'>
            Unggah berkas soal (doc, pdf, gambar, dll) — bisa banyak
          </Label>
          <Input
            id='mn-files'
            type='file'
            multiple
            onChange={(e) => setMnFiles(e.target.files)}
          />
          <p className='text-xs text-muted-foreground'>
            {mnFiles?.length ? `${mnFiles.length} berkas dipilih` : ''}
          </p>
        </div>

        <div className='flex flex-wrap gap-4'>
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox
              checked={mnGambar}
              onCheckedChange={(v) => setMnGambar(Boolean(v))}
            />
            Transkripsi gambar dengan vision
          </label>
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox
              checked={mnRef}
              onCheckedChange={(v) => setMnRef(Boolean(v))}
            />
            Cari daftar pustaka (research)
          </label>
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox
              checked={mnTanpaDocx}
              onCheckedChange={(v) => setMnTanpaDocx(Boolean(v))}
            />
            Tanpa buat DOCX
          </label>
        </div>

        <div className='grid gap-4 sm:grid-cols-2'>
          <div className='space-y-2'>
            <Label htmlFor='mn-model'>Model utama (opsional)</Label>
            <ModelInput
              id='mn-model'
              value={mnModel}
              onChange={setMnModel}
              models={models}
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='mn-model-mata'>Model vision (opsional)</Label>
            <ModelInput
              id='mn-model-mata'
              value={mnModelMata}
              onChange={setMnModelMata}
              models={models}
            />
          </div>
        </div>

        <div className='space-y-2'>
          <Button onClick={submitManual} disabled={mnBusy}>
            <Play /> {mnBusy ? 'Mengantrekan job...' : 'Mulai Manual'}
          </Button>
          {mnMsg || galatMatkul ? (
            <p className='text-sm text-destructive'>{mnMsg || galatMatkul}</p>
          ) : null}
        </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
