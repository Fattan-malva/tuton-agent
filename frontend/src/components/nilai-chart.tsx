'use client'

import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { NilaiData } from '@/lib/types'
import { cn } from '@/lib/utils'

const COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  '#f43f5e',
  '#eab308',
  '#84cc16',
]

type Filter = 'Semua' | 'Diskusi' | 'Tugas'

export function NilaiChart({ data }: { data: NilaiData }) {
  const [filter, setFilter] = useState<Filter>('Semua')
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  const rows = useMemo(
    () =>
      data.sesi.map((s) => {
        const row: Record<string, number | string> = { sesi: `S${s}` }
        for (const c of data.courses) {
          const t = c.titik.find((x) => x.sesi === s)
          const v =
            filter === 'Diskusi'
              ? t?.Diskusi
              : filter === 'Tugas'
                ? t?.Tugas
                : (t?.Diskusi ?? t?.Tugas)
          if (v !== null && v !== undefined) row[c.id] = v
        }
        return row
      }),
    [data, filter],
  )

  function toggle(id: string) {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className='space-y-4'>
      <div className='inline-flex rounded-lg border bg-muted/40 p-0.5'>
        {(['Semua', 'Diskusi', 'Tugas'] as Filter[]).map((f) => (
          <button
            key={f}
            type='button'
            onClick={() => setFilter(f)}
            className={cn(
              'rounded-md px-3 py-1 text-xs font-medium transition-colors',
              filter === f
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {f}
          </button>
        ))}
      </div>

      <div className='h-[320px] w-full'>
        <ResponsiveContainer width='100%' height='100%'>
          <LineChart
            data={rows}
            margin={{ top: 8, right: 12, bottom: 0, left: -18 }}
          >
            <CartesianGrid
              strokeDasharray='4 4'
              stroke='var(--border)'
              vertical={false}
            />
            <XAxis
              dataKey='sesi'
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
              dy={6}
            />
            <YAxis
              domain={[0, 100]}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
            />
            <Tooltip
              cursor={{ stroke: 'var(--border)' }}
              contentStyle={{
                background: 'var(--popover)',
                border: '1px solid var(--border)',
                borderRadius: 10,
                color: 'var(--popover-foreground)',
                fontSize: 12,
                boxShadow: '0 8px 24px rgb(0 0 0 / 0.12)',
              }}
              labelStyle={{ fontWeight: 600, marginBottom: 4 }}
            />
            {data.courses.map((c, i) => (
              <Line
                key={c.id}
                type='monotone'
                dataKey={c.id}
                name={c.nama}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={{ r: 2.5, strokeWidth: 0, fill: COLORS[i % COLORS.length] }}
                activeDot={{ r: 5 }}
                connectNulls
                hide={hidden.has(c.id)}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className='flex flex-wrap gap-1.5'>
        {data.courses.map((c, i) => {
          const off = hidden.has(c.id)
          return (
            <button
              key={c.id}
              type='button'
              onClick={() => toggle(c.id)}
              aria-pressed={!off}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors',
                off
                  ? 'text-muted-foreground opacity-50'
                  : 'text-foreground hover:bg-accent',
              )}
            >
              <span
                className='size-2 rounded-full'
                style={{ background: COLORS[i % COLORS.length] }}
              />
              <span className='max-w-44 truncate'>{c.nama}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
