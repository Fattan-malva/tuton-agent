'use client'

import { SignIn } from '@clerk/react'
import { ArrowRight, BookOpen, CheckCircle2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function LoginPage() {
  return (
    <main className='bg-muted/30 grid min-h-svh lg:grid-cols-[minmax(0,1fr)_minmax(420px,560px)]'>
      <section className='bg-primary text-primary-foreground relative hidden overflow-hidden p-10 lg:flex lg:flex-col lg:justify-between'>
        <div className='bg-primary-foreground/10 absolute -top-32 -right-24 size-96 rounded-full blur-3xl' />
        <div className='relative flex items-center gap-3 text-sm font-semibold'>
          <span className='bg-primary-foreground text-primary flex size-9 items-center justify-center rounded-md'>
            <BookOpen className='size-4' />
          </span>
          Tuton.agent
        </div>
        <div className='relative max-w-xl space-y-7'>
          <div className='space-y-3'>
            <p className='text-primary-foreground/70 text-sm font-medium'>Dashboard pipeline tutor UT</p>
            <h1 className='max-w-lg text-4xl leading-tight font-semibold tracking-tight xl:text-5xl'>
              Kerjakan tugas lebih cepat, tetap terpantau.
            </h1>
            <p className='text-primary-foreground/70 max-w-lg text-sm leading-6'>
              Scrape soal Moodle, jalankan agent, pantau log langsung, lalu unduh jawaban dalam DOCX.
            </p>
          </div>
          <div className='grid max-w-lg gap-3 sm:grid-cols-3'>
            {['Scrape Moodle', 'Agent worker', 'Hasil DOCX'].map((step) => (
              <div key={step} className='border-primary-foreground/15 bg-primary-foreground/10 rounded-lg border p-3'>
                <CheckCircle2 className='mb-3 size-4' />
                <span className='text-xs font-medium'>{step}</span>
              </div>
            ))}
          </div>
        </div>
        <p className='text-primary-foreground/50 relative text-xs'>Akses terbatas untuk pemilik akun.</p>
      </section>

      <section className='flex items-center justify-center p-4 sm:p-8'>
        <Card className='w-full max-w-md gap-6 py-7 shadow-lg shadow-black/5'>
          <CardHeader className='gap-2 px-6'>
            <div className='flex items-center gap-2 text-sm font-semibold lg:hidden'>
              <span className='bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-md'>
                <BookOpen className='size-4' />
              </span>
              Tuton.agent
            </div>
            <CardTitle className='text-2xl'>Selamat datang kembali</CardTitle>
            <CardDescription>Masuk untuk membuka dashboard pipeline Anda.</CardDescription>
          </CardHeader>
          <CardContent className='px-6'>
            <SignIn
              routing='hash'
              signUpUrl='/login/'
              appearance={{
                elements: {
                  rootBox: 'w-full',
                  card: 'w-full shadow-none p-0',
                  headerTitle: 'hidden',
                  headerSubtitle: 'hidden',
                },
              }}
            />
            <p className='text-muted-foreground mt-5 flex items-center justify-center gap-1 text-center text-xs'>
              Aman dan terisolasi per akun <ArrowRight className='size-3' />
            </p>
          </CardContent>
        </Card>
      </section>
    </main>
  )
}
