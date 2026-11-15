'use client'

import { useState, type ReactElement } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { useClerk, useUser } from '@clerk/react'
import { Loader2, LogOut, Mail, Settings, UserRound } from 'lucide-react'
import type { Profil } from '@/lib/types'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Separator } from '@/components/ui/separator'

function inisial(nama: string) {
  const kata = nama.trim().split(/\s+/).filter(Boolean)
  if (!kata.length) return 'TA'
  const huruf =
    kata.length > 1 ? kata[0][0] + kata[kata.length - 1][0] : kata[0].slice(0, 2)
  return huruf.toUpperCase()
}

const IDENTITAS: { kunci: string; label: string }[] = [
  { kunci: 'nama', label: 'Nama' },
  { kunci: 'nim', label: 'NIM' },
  { kunci: 'semester', label: 'Semester' },
  { kunci: 'prodi', label: 'Program studi' },
  { kunci: 'ut_daerah', label: 'UT Daerah' },
]

/**
 * Modal akun: identitas pemilik akun, tautan ke Pengaturan, dan tombol keluar.
 *
 * Sengaja memakai dialog internal, bukan menu Clerk atau tautan keluar milik
 * Clerk, supaya tidak pernah berpindah ke halaman Clerk yang bisa gagal
 * dimuat. Data identitas diambil dari profil Supabase akun ini.
 */
export function AccountDialog({ trigger }: { trigger: ReactElement }) {
  const { user } = useUser()
  const { signOut } = useClerk()
  const [buka, setBuka] = useState(false)
  const [keluar, setKeluar] = useState(false)
  const profil = useSWR<Profil>(buka ? '/api/profil' : null)

  const nama =
    user?.fullName ||
    user?.username ||
    user?.primaryEmailAddress?.emailAddress ||
    'Akun'
  const email = user?.primaryEmailAddress?.emailAddress || ''
  const identitas = profil.data?.identitas || {}
  const nim = String(identitas.nim || '').trim()

  async function logout() {
    setKeluar(true)
    try {
      // `redirectUrl` diarahkan ke halaman login aplikasi sendiri.
      await signOut({ redirectUrl: '/login/' })
    } catch {
      window.location.replace('/login/')
    } finally {
      setKeluar(false)
      setBuka(false)
    }
  }

  return (
    <Dialog open={buka} onOpenChange={setBuka}>
      <DialogTrigger render={trigger} />
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>Akun</DialogTitle>
          <DialogDescription>
            Identitas yang dipakai pipeline dan pencocokan status Diskusi.
          </DialogDescription>
        </DialogHeader>

        <div className='flex items-center gap-3'>
          <Avatar className='size-11'>
            <AvatarImage src={user?.imageUrl} alt={nama} />
            <AvatarFallback>{inisial(nama)}</AvatarFallback>
          </Avatar>
          <div className='min-w-0'>
            <p className='truncate text-sm font-semibold'>{nama}</p>
            <p className='text-muted-foreground flex items-center gap-1.5 truncate text-xs'>
              <Mail className='size-3.5 shrink-0' />
              {email || 'email tidak tersedia'}
            </p>
          </div>
        </div>

        <Separator />

        <dl className='grid gap-2 text-sm'>
          {IDENTITAS.map((item) => {
            const nilai = String(identitas[item.kunci] || '').trim()
            const kosong = !nilai
            return (
              <div key={item.kunci} className='flex items-baseline justify-between gap-3'>
                <dt className='text-muted-foreground shrink-0 text-xs'>{item.label}</dt>
                <dd className={kosong ? 'text-muted-foreground text-xs' : 'truncate text-xs font-medium'}>
                  {kosong ? 'belum diisi' : nilai}
                </dd>
              </div>
            )
          })}
        </dl>

        {!profil.isLoading && !nim ? (
          <div className='bg-tugas-soft/60 border-tugas/30 flex items-start gap-2 rounded-lg border p-2.5 text-xs'>
            <UserRound className='text-tugas mt-0.5 size-3.5 shrink-0' />
            <p className='text-muted-foreground leading-relaxed'>
              NIM belum diisi. Status Diskusi di menu Courses baru bisa
              ditentukan setelah NIM disimpan di Pengaturan.
            </p>
          </div>
        ) : null}

        <DialogFooter className='gap-2 sm:justify-between'>
          <Button asChild variant='outline' onClick={() => setBuka(false)}>
            <Link href='/settings/'>
              <Settings /> Pengaturan
            </Link>
          </Button>
          <div className='flex items-center gap-2'>
            {profil.data?.cookie_ada ? (
              <Badge variant='secondary' className='max-sm:hidden'>
                Moodle tersambung
              </Badge>
            ) : null}
            <Button variant='destructive' onClick={logout} disabled={keluar}>
              {keluar ? <Loader2 className='animate-spin' /> : <LogOut />}
              {keluar ? 'Keluar...' : 'Keluar'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
