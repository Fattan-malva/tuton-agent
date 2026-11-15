'use client'

import useSWR from 'swr'
import { Bot, Eye, Search, Sparkles } from 'lucide-react'
import type { AgentInfo, Job } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/page-header'

const ICONS = [Search, Sparkles, Eye, Bot]

export default function AgentsPage() {
  const agents = useSWR<AgentInfo[]>('/api/agents')
  const jobs = useSWR<Job[]>('/api/jobs')
  const running = jobs.data?.find(
    (j) => j.status === 'running' || j.status === 'queued',
  )

  return (
    <div className='space-y-6'>
      <PageHeader
        title='Agent Worker'
        description='Agent yang dipanggil pipeline pada tiap sesi. Aktivitas per langkah ada di Log Live.'
      >
        {running ? (
          <Badge>Aktif: {running.id}</Badge>
        ) : (
          <Badge variant='secondary'>Idle</Badge>
        )}
      </PageHeader>

      <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-4'>
        {agents.isLoading
          ? Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <CardHeader>
                  <Skeleton className='size-9 rounded-lg' />
                  <Skeleton className='mt-2 h-4 w-28' />
                </CardHeader>
                <CardContent>
                  <Skeleton className='h-3.5 w-40' />
                </CardContent>
              </Card>
            ))
          : (agents.data || []).map((agent, i) => {
              const Icon = ICONS[i % ICONS.length]
              return (
                <Card key={agent.name}>
                  <CardHeader>
                    <div className='flex size-9 items-center justify-center rounded-lg border bg-muted'>
                      <Icon className='size-4 text-muted-foreground' />
                    </div>
                    <CardTitle className='mt-2 text-base capitalize'>
                      {agent.name}
                    </CardTitle>
                    <CardDescription className='break-all font-mono text-[11px]'>
                      {agent.model || '—'}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Badge variant='outline'>agent {agent.name}</Badge>
                  </CardContent>
                </Card>
              )
            })}
      </div>

      {agents.error ? (
        <p className='text-sm text-destructive'>
          {String((agents.error as Error).message)}
        </p>
      ) : null}
    </div>
  )
}
