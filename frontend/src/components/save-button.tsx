'use client'

import { useState, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type SaveButtonProps = {
  /** Aksi simpan. Boleh mengembalikan pesan sukses untuk ditampilkan. */
  onSave: () => Promise<string | void>
  label?: string
  savingLabel?: string
  disabled?: boolean
  variant?: 'default' | 'outline' | 'secondary' | 'ghost' | 'destructive'
  size?: 'default' | 'sm' | 'lg'
  className?: string
  children?: ReactNode
}

/**
 * Tombol simpan dengan status loading lokal.
 *
 * Selama menyimpan hanya tombol ini yang berubah — tidak ada reload halaman
 * dan tidak ada spinner seluruh layar, sehingga halaman tetap bisa dibaca dan
 * isian tidak hilang.
 */
export function SaveButton({
  onSave,
  label = 'Simpan',
  savingLabel = 'Menyimpan...',
  disabled,
  variant = 'default',
  size = 'default',
  className,
}: SaveButtonProps) {
  const [saving, setSaving] = useState(false)

  async function handle() {
    if (saving) return
    setSaving(true)
    try {
      const pesan = await onSave()
      if (pesan) toast.success(pesan)
    } catch (e) {
      toast.error((e as Error).message || 'Gagal menyimpan.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Button
      onClick={handle}
      disabled={disabled || saving}
      variant={variant}
      size={size}
      className={cn('min-w-28', className)}
      aria-busy={saving}
    >
      {saving ? <Loader2 className='animate-spin' /> : null}
      {saving ? savingLabel : label}
    </Button>
  )
}
