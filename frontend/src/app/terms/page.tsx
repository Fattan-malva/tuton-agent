import type { Metadata } from 'next'
import Link from 'next/link'
import { BookOpen } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Ketentuan Layanan — Tuton.agent',
  description:
    'Ketentuan penggunaan dashboard pipeline tutor online Universitas Terbuka.',
}

const DIPERBARUI = '15 November 2026'

function Legal({ children }: { children: React.ReactNode }) {
  return (
    <div className='min-h-svh bg-background text-foreground'>
      <header className='border-b'>
        <div className='mx-auto flex w-full max-w-3xl items-center justify-between px-6 py-4'>
          <Link href='/' className='flex items-center gap-2 text-sm font-semibold'>
            <span className='flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground'>
              <BookOpen className='size-4' />
            </span>
            Tuton.agent
          </Link>
          <nav className='flex gap-4 text-sm text-muted-foreground'>
            <Link href='/terms/' className='hover:text-foreground'>
              Ketentuan
            </Link>
            <Link href='/privacy/' className='hover:text-foreground'>
              Privasi
            </Link>
          </nav>
        </div>
      </header>
      <main className='mx-auto w-full max-w-3xl px-6 py-10'>
        <p className='text-xs uppercase tracking-wide text-muted-foreground'>
          Diperbarui {DIPERBARUI}
        </p>
        <article className='mt-4 space-y-6 text-sm leading-relaxed'>{children}</article>
        <footer className='mt-12 border-t pt-6 text-xs text-muted-foreground'>
          <Link href='/' className='hover:text-foreground'>
            ← Kembali ke dashboard
          </Link>
        </footer>
      </main>
    </div>
  )
}

export default function TermsPage() {
  return (
    <Legal>
      <h1 className='text-2xl font-semibold tracking-tight'>Ketentuan Layanan</h1>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>1. Layanan</h2>
        <p className='text-muted-foreground'>
          Tuton.agent adalah alat bantu yang mengambil soal dari elearning UT,
          menyusun draf jawaban dengan model bahasa, lalu menghasilkan dokumen
          .docx. Layanan disediakan apa adanya untuk pemakaian pribadi pemilik
          akun.
        </p>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>2. Akun dan kredensial</h2>
        <p className='text-muted-foreground'>
          Kamu masuk memakai akun Clerk milikmu sendiri. Cookie sesi Moodle
          yang kamu tempel adalah kredensial hidup milikmu; kamu bertanggung
          jawab menjaganya dan boleh memutusnya kapan saja dari halaman
          Pengaturan. Jangan memakai akun Moodle milik orang lain tanpa izin.
        </p>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>3. Batasan pemakaian</h2>
        <ul className='list-disc space-y-1 ps-5 text-muted-foreground'>
          <li>Tidak untuk mengakali ujian, kuis terjadwal, atau penilaian resmi.</li>
          <li>Tidak untuk mengirim jawaban atas nama orang lain tanpa sepengetahuannya.</li>
          <li>Tidak untuk membebani server UT di luar pemakaian wajar.</li>
        </ul>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>4. Hasil model bahasa</h2>
        <p className='text-muted-foreground'>
          Jawaban dibuat oleh model bahasa dan bisa salah, tidak lengkap, atau
          mengarang sumber. Periksa selalu isi dokumen sebelum dikumpulkan.
          Kamu bertanggung jawab penuh atas apa yang kamu kirim ke Moodle.
        </p>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>5. Ketersediaan</h2>
        <p className='text-muted-foreground'>
          Layanan bisa berhenti, berubah, atau kehilangan data tanpa pemberitahuan
          sebelumnya, termasuk bila kuota penyedia model habis atau sesi Moodle
          kedaluwarsa. Tidak ada jaminan ketersediaan.
        </p>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>6. Pembatasan tanggung jawab</h2>
        <p className='text-muted-foreground'>
          Pemilik layanan tidak bertanggung jawab atas kerugian yang timbul dari
          pemakaian alat ini, termasuk nilai akademik, sanksi institusi, atau
          kehilangan data.
        </p>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>7. Perubahan ketentuan</h2>
        <p className='text-muted-foreground'>
          Ketentuan ini bisa diperbarui; versi terbaru selalu ada di halaman
          ini. Pemakaian setelah perubahan berarti kamu menyetujui versi baru.
        </p>
      </section>
    </Legal>
  )
}
