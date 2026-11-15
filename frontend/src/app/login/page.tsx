'use client'

import { SignIn } from '@clerk/react'
import { BookOpen } from 'lucide-react'

export default function LoginPage() {
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
            unduh jawaban dalam DOCX. Setiap akun memakai sesi Moodle dan
            identitasnya sendiri.
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
        <SignIn
          routing='hash'
          signUpUrl='/login/'
          appearance={{ elements: { rootBox: 'w-full max-w-sm' } }}
        />
      </div>
    </div>
  )
}
