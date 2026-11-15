'use client'

import { SWRConfig } from 'swr'
import { fetcher } from '@/lib/api'

export function SWRProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        fetcher,
        revalidateOnFocus: false,
        keepPreviousData: true,
        dedupingInterval: 15000,
        errorRetryCount: 1,
      }}
    >
      {children}
    </SWRConfig>
  )
}
