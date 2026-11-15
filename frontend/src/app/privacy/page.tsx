import type { Metadata } from 'next'
import Link from 'next/link'
import { BookOpen } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Kebijakan Privasi — Tuton.agent',
  description:
    'Data apa yang disimpan Tuton.agent, di mana, dan bagaimana menghapusnya.',
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

export default function PrivacyPage() {
  return (
    <Legal>
      <h1 className='text-2xl font-semibold tracking-tight'>Kebijakan Privasi</h1>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>1. Data yang disimpan</h2>
        <ul className='list-disc space-y-1 ps-5 text-muted-foreground'>
          <li>
            <strong>Akun:</strong> id pengguna Clerk, alamat email, dan nama
            tampilan.
          </li>
          <li>
            <strong>Identitas akademik:</strong> nama, NIM, semester, UT-Daerah,
            dan program studi yang kamu isi untuk kop dokumen.
          </li>
          <li>
            <strong>Cookie Moodle:</strong> nilai MoodleSession milikmu, dipakai
            untuk membaca soal atas namamu sendiri.
          </li>
          <li>
            <strong>Hasil kerja:</strong> dokumen .docx, log job, dan berkas
            kerja sementara di server ini.
          </li>
        </ul>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>2. Di mana data disimpan</h2>
        <p className='text-muted-foreground'>
          Akun diverifikasi oleh Clerk (clerk.com). Profil — identitas dan
          cookie Moodle — disimpan di database Supabase milik pemilik layanan,
          dengan akses hanya lewat kunci layanan di server. Dokumen hasil dan
          log tersimpan di disk server tempat aplikasi ini berjalan.
        </p>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>3. Pihak ketiga</h2>
        <ul className='list-disc space-y-1 ps-5 text-muted-foreground'>
          <li>Clerk — autentikasi akun.</li>
          <li>Supabase — penyimpanan profil.</li>
          <li>
            Penyedia model bahasa (OpenAI-compatible, dikonfigurasi pemilik
            server) — menerima teks soal dan bahan ajar yang diperlukan untuk
            menyusun jawaban.
          </li>
          <li>elearning.ut.ac.id — sumber soal, diakses dengan sesimu sendiri.</li>
        </ul>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>4. Yang tidak dilakukan</h2>
        <p className='text-muted-foreground'>
          Data tidak dijual, tidak dipakai untuk iklan, dan tidak dibagikan ke
          pengguna lain. Cookie Moodle tidak pernah dikirim kembali ke browser
          setelah disimpan — halaman Pengaturan hanya menampilkan empat huruf
          terakhir.
        </p>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>5. Masa simpan</h2>
        <p className='text-muted-foreground'>
          Profil disimpan selama akunmu ada. Cookie Moodle dapat diputus kapan
          saja dari halaman Pengaturan. Dokumen hasil dan log job bisa dihapus
          dari halaman Result dan Log, dan folder kerja sementara dibersihkan
          otomatis setelah dokumen selesai dibuat.
        </p>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>6. Hak kamu</h2>
        <p className='text-muted-foreground'>
          Kamu bisa meminta salinan atau penghapusan seluruh data profilmu
          dengan menghubungi pemilik layanan. Menghapus akun Clerk tanpa
          meminta penghapusan data akan menyisakan baris profil di Supabase;
          mintakan keduanya sekaligus.
        </p>
      </section>

      <section className='space-y-2'>
        <h2 className='text-base font-semibold'>7. Keamanan</h2>
        <p className='text-muted-foreground'>
          Kunci layanan hanya ada di server dan tidak pernah dikirim ke browser.
          Meski begitu, tidak ada sistem yang sepenuhnya aman; jangan menaruh
          data yang tidak kamu rela lihat di server pihak ketiga.
        </p>
      </section>
    </Legal>
  )
}
