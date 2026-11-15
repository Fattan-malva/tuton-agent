'use client'

import { useEffect } from 'react'
import { ClerkProvider, useAuth } from '@clerk/react'
import { setTokenGetter } from '@/lib/api'

const key = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || ''

// Menyalakan getter token global selama aplikasi hidup. Diletakkan tepat di
// dalam ClerkProvider supaya `useAuth()` sudah punya konteks.
function TokenBridge() {
  const { getToken, isLoaded, isSignedIn } = useAuth()

  useEffect(() => {
    if (!isLoaded) return
    setTokenGetter(isSignedIn ? () => getToken() : null)
    return () => setTokenGetter(null)
  }, [getToken, isLoaded, isSignedIn])

  return null
}

export function AppAuthProvider({ children }: { children: React.ReactNode }) {
  if (!key) {
    // Tanpa publishable key Clerk tidak bisa dimuat. Pesan ini lebih berguna
    // daripada layar putih yang tidak menjelaskan apa pun.
    return (
      <div className='flex min-h-svh items-center justify-center p-6'>
        <div className='max-w-lg space-y-2 text-center'>
          <h1 className='text-lg font-semibold'>Clerk belum dikonfigurasi</h1>
          <p className='text-sm text-muted-foreground'>
            Isi <code>NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY</code> saat build (lihat{' '}
            <code>.env.example</code>), lalu build ulang UI.
          </p>
        </div>
      </div>
    )
  }
  return (
    <ClerkProvider publishableKey={key} afterSignOutUrl='/login/'>
      <TokenBridge />
      {children}
    </ClerkProvider>
  )
}
