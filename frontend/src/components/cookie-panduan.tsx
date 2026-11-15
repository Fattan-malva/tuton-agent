'use client'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

/** Langkah-langkah mengambil cookie Moodle, dipakai modal onboarding & halaman Pengaturan. */
export const COOKIE_LANGKAH = [
  'Buka https://elearning.ut.ac.id lalu login dengan akun mahasiswa.',
  'Buka Developer Tools browser (F12) — tab Application (Chrome) / tab Storage (Firefox).',
  'Pilih cookies, lalu cari kunci bernama MoodleSession pada domain elearning.ut.ac.id.',
  'Salin nilainya — bentuk token (mis. tanpa akhiran `MoodleSession=`).',
  'Tempel nilainya di kolom Cookie Moodle pada menu Pengaturan.',
]

/** Modal penjelas cara mengambil cookie Moodle. */
export function CookiePanduan({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>Cara ambil cookie Moodle</DialogTitle>
          <DialogDescription>
            Cookie MoodleSession dipakai pipeline untuk membaca soal dan
            mencatat penilaian mahasiswa. Salin di browser setelah login.
          </DialogDescription>
        </DialogHeader>
        <ol className='flex flex-col gap-2'>
          {COOKIE_LANGKAH.map((n, i) => (
            <li
              key={i}
              className='text-muted-foreground flex items-start gap-2.5 rounded-md border bg-muted/40 p-2.5 text-sm leading-relaxed'
            >
              <span className='bg-primary text-primary-foreground mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold'>
                {i + 1}
              </span>
              {n}
            </li>
          ))}
        </ol>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Baik, saya sudah tahu</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
