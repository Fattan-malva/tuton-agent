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

const PERAN: Record<string, string> = {
  scrapper: 'Memetakan soal dan menyusun rencana jawaban.',
  research: 'Mencari daftar pustaka pendukung.',
  worker: 'Menulis jawaban akhir per soal.',
  vision: 'Mentranskripsi gambar soal.',
}

export default function AgentsPage() {
  const agents = useSWR<AgentInfo[]>('/api/agents')
  const jobs = useSWR<Job[]>('/api/jobs')
  const running = jobs.data?.find(
    (j) => j.status === 'running' || j.status === 'queued',
  )

  return (
    <div className='flex flex-col gap-4'>
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
              <Card key={i} className='py-5'>
                <CardHeader className='px-5'>
                  <Skeleton className='size-8 rounded-sm' />
                  <Skeleton className='mt-2 h-4 w-28' />
                </CardHeader>
                <CardContent className='px-5'>
                  <Skeleton className='h-3.5 w-40' />
                </CardContent>
              </Card>
            ))
          : (agents.data || []).map((agent, i) => {
              const Icon = ICONS[i % ICONS.length]
              return (
                <Card key={agent.name} className='gap-3 py-5 transition-shadow hover:shadow-md'>
                  <CardHeader className='px-5'>
                    <div className='bg-primary/10 text-primary flex size-8 items-center justify-center rounded-sm'>
                      <Icon className='size-4' />
                    </div>
                    <CardTitle className='mt-2 text-base capitalize'>
                      {agent.name}
                    </CardTitle>
                    <CardDescription className='line-clamp-2 text-xs'>
                      {PERAN[agent.name] || 'Agent pipeline.'}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className='space-y-2 px-5'>
                    <Badge variant='outline' className='font-mono text-[11px]'>
                      {agent.model || 'model bawaan'}
                    </Badge>
                  </CardContent>
                </Card>
              )
            })}
      </div>

      {agents.error ? (
        <p className='text-destructive text-sm'>
          {String((agents.error as Error).message)}
        </p>
      ) : null}
    </div>
  )
}
