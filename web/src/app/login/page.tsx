'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { BookOpen, Loader2, LockKeyhole, User } from 'lucide-react'
import { postJSON, type ApiError } from '@/lib/api'
import type { SessionInfo } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export default function LoginPage() {
  const router = useRouter()
  const { data, mutate } = useSWR<SessionInfo>('/api/session')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (data?.authenticated) router.replace('/')
  }, [data, router])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const r = await postJSON<{ ok: boolean; error?: string }>('/api/login', {
        username,
        password,
        remember,
      })
      if (!r.ok) {
        setError(r.error || 'Gagal masuk.')
        return
      }
      await mutate()
      router.replace('/')
    } catch (err) {
      setError((err as ApiError).message || 'Server tidak dapat dihubungi.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className='grid min-h-svh lg:grid-cols-2'>
      <div className='relative hidden flex-col justify-between bg-zinc-950 p-10 text-zinc-100 lg:flex'>
        <div className='flex items-center gap-2 text-sm font-semibold'>
          <span className='flex size-8 items-center justify-center rounded-lg bg-zinc-100 text-zinc-950'>
            <BookOpen className='size-4' />
          </span>
          Tuton.agent
        </div>
        <div className='max-w-md space-y-4'>
          <h1 className='text-3xl font-semibold tracking-tight'>
            Dashboard pipeline tutor UT.
          </h1>
          <p className='text-sm leading-relaxed text-zinc-400'>
            Scrape soal Moodle, jalankan agent, pantau log langsung, lalu
            unduh jawaban dalam DOCX. Semua dari satu tempat.
          </p>
          <div className='grid grid-cols-3 gap-3 text-center text-xs text-zinc-400'>
            {['Scrape', 'Agent', 'DOCX'].map((step, i) => (
              <div key={step} className='rounded-lg border border-zinc-800 p-3'>
                <div className='text-lg font-semibold text-zinc-100'>
                  0{i + 1}
                </div>
                {step}
              </div>
            ))}
          </div>
        </div>
        <p className='text-xs text-zinc-500'>
          Akses terbatas untuk pemilik akun.
        </p>
      </div>

      <div className='flex items-center justify-center p-6'>
        <div className='w-full max-w-sm space-y-6'>
          <div className='space-y-1 text-center lg:text-start'>
            <div className='mb-4 flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground lg:hidden'>
              <BookOpen className='size-5' />
            </div>
            <h2 className='text-2xl font-semibold tracking-tight'>Masuk</h2>
            <p className='text-sm text-muted-foreground'>
              Gunakan kredensial dashboard untuk melanjutkan.
            </p>
          </div>

          <form onSubmit={submit} className='space-y-4'>
            <div className='space-y-2'>
              <Label htmlFor='user'>Nama pengguna</Label>
              <div className='relative'>
                <User className='pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground' />
                <Input
                  id='user'
                  autoComplete='username'
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className='ps-8'
                />
              </div>
            </div>
            <div className='space-y-2'>
              <Label htmlFor='pass'>Kata sandi</Label>
              <div className='relative'>
                <LockKeyhole className='pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground' />
                <Input
                  id='pass'
                  type='password'
                  autoComplete='current-password'
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className='ps-8'
                />
              </div>
            </div>
            <label className='flex items-center gap-2 text-sm text-muted-foreground'>
              <input
                type='checkbox'
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className='size-4 rounded border-input accent-foreground'
              />
              Ingat saya di peramban ini
            </label>
            {error ? (
              <p className='text-sm text-destructive' role='alert'>
                {error}
              </p>
            ) : null}
            <Button type='submit' className='w-full' disabled={loading}>
              {loading ? <Loader2 className='animate-spin' /> : null}
              {loading ? 'Memeriksa...' : 'Masuk'}
            </Button>
          </form>

          <p className='text-center text-xs text-muted-foreground'>
            Cookie Moodle dan model diatur di halaman Pengaturan setelah masuk.
          </p>
        </div>
      </div>
    </div>
  )
}
