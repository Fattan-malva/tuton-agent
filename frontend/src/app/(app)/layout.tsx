'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/react'
import useSWR from 'swr'
import type { SessionInfo } from '@/lib/types'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { Header } from '@/components/layout/header'
import { Skeleton } from '@/components/ui/skeleton'
import { OnboardingModal } from '@/components/onboarding-modal'
import { Toaster } from '@/components/ui/sonner'

function ShellSkeleton() {
  return (
    <div className='flex min-h-svh'>
      <div className='hidden w-64 border-e p-4 md:block'>
        <Skeleton className='h-10 w-full' />
        <div className='mt-6 space-y-2'>
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className='h-8 w-full' />
          ))}
        </div>
      </div>
      <div className='flex-1 p-6'>
        <Skeleton className='h-8 w-48' />
        <div className='mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className='h-32 w-full' />
          ))}
        </div>
      </div>
    </div>
  )
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const { isLoaded, isSignedIn } = useAuth()
  // Server tetap diverifikasi: token bisa saja sudah dicabut di Clerk padahal
  // browser masih menyimpannya.
  const { data, error, mutate } = useSWR<SessionInfo>(
    isSignedIn ? '/api/session' : null,
  )
  const { data: moodleStatus } = useSWR<{ masuk: boolean; pesan: string }>(
    isSignedIn ? '/api/moodle-status' : null,
  )
  const [panduanClosed, setPanduanClosed] = useState(false)

  const panduanAwal = Boolean(data?.panduan_awal)
  const butuhCookie =
    data?.panduan_awal === false &&
    data?.profile?.cookie_ada === false &&
    Boolean(moodleStatus) &&
    moodleStatus?.masuk === false
  const bukaPanduan = !panduanClosed && (panduanAwal || butuhCookie)

  // Panduan awal hanya dipakai sekali per browser tab untuk akun baru.
  useEffect(() => {
    if (panduanAwal) setPanduanClosed(false)
    if (data && !panduanAwal) setPanduanClosed(true)
  }, [data, panduanAwal])

  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace('/login/')
  }, [isLoaded, isSignedIn, router])

  // Panduan awal hanya dipakai sekali per browser tab untuk akun baru.
  useEffect(() => {
    if (data?.panduan_awal) setPanduanClosed(false)
    if (data && !data.panduan_awal) setPanduanClosed(true)
  }, [data])

  // Clerk sudah bilang masuk tapi server belum melihat tokennya (bridge
  // terpasang setelah render ini). Coba lagi, jangan diam di skeleton.
  useEffect(() => {
    if (isSignedIn && data && !data.authenticated) {
      const t = window.setTimeout(() => void mutate(), 400)
      return () => window.clearTimeout(t)
    }
  }, [isSignedIn, data, mutate])

  if (error && isSignedIn) {
    return (
      <div className='flex min-h-svh items-center justify-center p-6'>
        <div className='max-w-md space-y-3 text-center'>
          <h1 className='text-lg font-semibold'>Gagal memuat sesi</h1>
          <p className='text-sm text-muted-foreground'>{(error as Error).message}</p>
          <button
            className='rounded-md border px-3 py-1.5 text-sm hover:bg-muted'
            onClick={() => void mutate()}
          >
            Coba lagi
          </button>
        </div>
      </div>
    )
  }

  if (!isLoaded || !isSignedIn || !data?.authenticated) {
    return <ShellSkeleton />
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className='@container/content min-h-svh'>
        <Header />
        <main className='mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6'>
          {children}
        </main>
        <Toaster position='top-center' />
        <OnboardingModal
          open={bukaPanduan}
          onClose={() => setPanduanClosed(true)}
          initialStep={panduanAwal ? 0 : 1}
        />
      </SidebarInset>
    </SidebarProvider>
  )
}
