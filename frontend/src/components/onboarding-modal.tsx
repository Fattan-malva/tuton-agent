'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Check, ChevronLeft, ChevronRight, Info, Loader2 } from 'lucide-react'
import useSWR from 'swr'
import { postJSON, api } from '@/lib/api'
import type { SettingItem } from '@/lib/types'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import { COOKIE_LANGKAH, CookiePanduan } from '@/components/cookie-panduan'

const STEPS = [
  { id: 'identitas', judul: 'Identitas mahasiswa' },
  { id: 'cookie', judul: 'Cookie Moodle' },
  { id: 'provider', judul: 'Provider AI' },
] as const

const IDENTITAS: { key: string; label: string }[] = [
  { key: 'NAMA', label: 'Nama' },
  { key: 'NIM', label: 'NIM' },
  { key: 'SEMESTER', label: 'Semester' },
  { key: 'UT_DAERAH', label: 'UT Daerah' },
  { key: 'PRODI', label: 'Program studi' },
]

export function OnboardingModal({
  open,
  onClose,
  initialStep = 0,
  cookieOnly = false,
}: {
  open: boolean
  onClose: () => void
  initialStep?: number
  /** Dibuka karena cookie Moodle mati, bukan karena akun baru. */
  cookieOnly?: boolean
}) {
  const router = useRouter()
  const [step, setStep] = useState(initialStep)
  const [cookie, setCookie] = useState('')
  const [busy, setBusy] = useState(false)
  const [galat, setGalat] = useState<string | null>(null)
  const [identitas, setIdentitas] = useState<Record<string, string>>({})
  const [panduanOpen, setPanduanOpen] = useState(false)
  const { data: settings } = useSWR<SettingItem[]>('/api/settings')

  useEffect(() => {
    if (open) {
      setStep(initialStep)
      setGalat(null)
    }
  }, [open, initialStep])

  const nilai = Object.fromEntries((settings || []).map((s) => [s.key, s.value]))
  const identitasAktif: Record<string, string> = {
    NAMA: identitas.NAMA ?? nilai.NAMA ?? '',
    NIM: identitas.NIM ?? nilai.NIM ?? '',
    SEMESTER: identitas.SEMESTER ?? nilai.SEMESTER ?? '',
    UT_DAERAH: identitas.UT_DAERAH ?? nilai.UT_DAERAH ?? '',
    PRODI: identitas.PRODI ?? nilai.PRODI ?? '',
  }

  function tutup() {
    setStep(0)
    setPanduanOpen(false)
    onClose()
  }

  async function simpanIdentitas() {
    setBusy(true)
    try {
      await postJSON('/api/settings', identitasAktif)
      setStep(1)
    } catch {
      // Kesalahan disalahkan ke halaman Pengaturan; jangan menutup.
    } finally {
      setBusy(false)
    }
  }

  async function simpanCookie() {
    setBusy(true)
    setGalat(null)
    try {
      const r = await postJSON<{ ok: boolean }>('/api/settings', { COOKIE_MOODLE: cookie })
      if (!r.ok) return
      if (!cookieOnly) {
        setStep(2)
        return
      }
      // Cookie mati: uji langsung supaya salah tempel tidak lewat diam-diam.
      const status = await api<{ masuk: boolean; pesan: string }>('/api/moodle-status')
      if (status.masuk) tutup()
      else setGalat(status.pesan || 'Cookie masih belum berlaku.')
    } catch (e) {
      setGalat(e instanceof Error ? e.message : 'Cookie gagal disimpan.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && tutup()}>
      <DialogContent className='max-h-[85vh] overflow-auto sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            {cookieOnly ? 'Cookie Moodle kedaluwarsa' : 'Panduan awal akun'}
          </DialogTitle>
          <DialogDescription>
            {cookieOnly
              ? 'Cookie Moodle tidak berlaku lagi. Tempel nilai MoodleSession yang baru agar pipeline bisa membaca soal dan menilai tugas.'
              : 'Langkah langsung ke konfigurasi akun: identitas, cookie Moodle, lalu provider AI.'}
          </DialogDescription>
        </DialogHeader>

        <div className='flex flex-col items-center gap-2'>
          <ol className='flex items-center justify-center gap-2'>
            {STEPS.map((s, i) => {
              const aktif = i === step
              const selesai = i < step
              return (
                <li key={s.id} className='flex items-center gap-2'>
                  <span
                    aria-current={aktif ? 'step' : undefined}
                    className={`flex size-8 shrink-0 items-center justify-center rounded-full border text-xs font-semibold transition-colors ${
                      selesai
                        ? 'bg-primary text-primary-foreground border-primary'
                        : aktif
                          ? 'border-primary text-primary ring-2 ring-primary/20'
                          : 'bg-muted text-muted-foreground border-border'
                    }`}
                  >
                    {selesai ? <Check className='size-4' /> : i + 1}
                  </span>
                  {i < STEPS.length - 1 ? (
                    <span
                      className={`h-0.5 w-10 rounded-full ${i < step ? 'bg-primary/60' : 'bg-border'}`}
                    />
                  ) : null}
                </li>
              )
            })}
          </ol>
          <p className='text-sm font-medium'>
            {STEPS[step].judul}{' '}
            <span className='text-muted-foreground font-normal'>
              — langkah {step + 1} dari {STEPS.length}
            </span>
          </p>
        </div>

        <Card className='gap-4 py-5'>
          <CardContent className='space-y-3 px-5'>
            {step === 0 ? (
              <>
                <p className='text-muted-foreground text-sm'>
                  Isi identitas mahasiswa agar pipeline bisa membaca soal dan
                  mencocokkan status Diskusi.
                </p>
                <div className='grid gap-3 sm:grid-cols-2'>
                  {IDENTITAS.map((f) => (
                    <div key={f.key} className='space-y-2'>
                      <Label htmlFor={`or-${f.key}`}>{f.label}</Label>
                      <Input
                        id={`or-${f.key}`}
                        value={identitasAktif[f.key] || ''}
                        onChange={(e) =>
                          setIdentitas((prev) => ({ ...prev, [f.key]: e.target.value }))
                        }
                      />
                    </div>
                  ))}
                </div>
              </>
            ) : null}

            {step === 1 ? (
              <>
                <div className='space-y-2'>
                  <Label htmlFor='or-cookie'>Cookie Moodle</Label>
                  <Input
                    id='or-cookie'
                    type='password'
                    value={cookie}
                    onChange={(e) => setCookie(e.target.value)}
                    placeholder='MoodleSession=... atau nilai token-nya'
                    autoComplete='off'
                  />
                  <p className='text-muted-foreground text-xs leading-relaxed'>
                    Cookie diambil dari browser setelah login ke elearning UT.
                  </p>
                  <button
                    type='button'
                    className='text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs underline-offset-4 hover:underline'
                    onClick={() => setPanduanOpen(true)}
                  >
                    <Info className='size-3.5' /> Cara ambil cookie Moodle
                  </button>
                  {galat ? (
                    <p role='alert' className='text-destructive text-xs leading-relaxed'>
                      {galat}
                    </p>
                  ) : null}
                </div>
              </>
            ) : null}

            {step === 2 ? (
              <p className='text-muted-foreground text-sm'>
                Provider AI (OpenAI-compatible) memakai API key milik akunmu.
                Bisa diisi nanti dari menu Provider.
              </p>
            ) : null}
          </CardContent>
        </Card>

        <DialogFooter className='justify-between gap-2'>
          {step > 0 && !cookieOnly ? (
            <Button variant='outline' onClick={() => setStep((s) => Math.max(0, s - 1))}>
              <ChevronLeft className='size-4' /> Kembali
            </Button>
          ) : null}
          <div className='flex items-center gap-2'>
            {step === 0 ? (
              <>
                <Button variant='outline' onClick={tutup}>
                  Lewati
                </Button>
                <Button onClick={() => void simpanIdentitas()} disabled={busy}>
                  {busy ? <Loader2 className='animate-spin' /> : null} Simpan &amp; lanjut
                </Button>
              </>
            ) : null}
            {step === 1 ? (
              <>
                <Button
                  variant='outline'
                  onClick={() => (cookieOnly ? tutup() : setStep(2))}
                  disabled={busy}
                >
                  {cookieOnly ? 'Tutup' : 'Lewati'}
                </Button>
                <Button
                  onClick={() => void simpanCookie()}
                  disabled={busy || !cookie.trim()}
                >
                  {busy ? <Loader2 className='animate-spin' /> : null} Simpan cookie &amp; lanjut
                </Button>
              </>
            ) : null}
            {step === 2 ? (
              <Button
                onClick={() => {
                  tutup()
                  router.push('/providers/')
                }}
              >
                Buka menu Provider <ChevronRight className='size-4' />
              </Button>
            ) : null}
          </div>
        </DialogFooter>
      </DialogContent>

      <CookiePanduan open={panduanOpen} onOpenChange={setPanduanOpen} />
    </Dialog>
  )
}
