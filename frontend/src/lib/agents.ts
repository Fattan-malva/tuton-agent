'use client'

import { BookOpen, Bot, Eye, Search } from 'lucide-react'

export type AgentInfoLocal = {
  name: string
  label: string
  peran: string
  Icon: typeof Search
}

/**
 * Master daftar agent: label untuk konfigurasi, deskripsi untuk kartu, dan
 * ikon untuk tampilan. Semua halaman yang membicarakan agent harus lewat sini
 * supaya daftar agent tidak boleh hidup di dua tempat.
 */
export const AGENTS: AgentInfoLocal[] = [
  {
    name: 'scrapper',
    label: 'Scrapper (peta soal)',
    peran: 'Memetakan soal dan menyusun rencana jawaban.',
    Icon: Search,
  },
  {
    name: 'research',
    label: 'Research (daftar pustaka)',
    peran: 'Mencari daftar pustaka pendukung.',
    Icon: BookOpen,
  },
  {
    name: 'worker',
    label: 'Worker (penulisan jawaban)',
    peran: 'Menulis jawaban akhir per soal.',
    Icon: Bot,
  },
  {
    name: 'vision',
    label: 'Vision (transkripsi gambar)',
    peran: 'Mentranskripsi gambar soal.',
    Icon: Eye,
  },
]

export const AGENT_BY_NAME: Record<string, AgentInfoLocal> = Object.fromEntries(
  AGENTS.map((a) => [a.name, a]),
)
