'use client'

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { usePratinjauPdf } from '@/hooks/use-pratinjau-pdf'

// Pratinjau ukuran penuh satu template. PDF dibuat server saat dialog dibuka
// dan dihapus saat dialog ditutup (sumber jadi null, lalu hook membersihkan).
export function TemplatePreviewDialog({
  templateId,
  label,
  onOpenChange,
}: {
  templateId: string
  label: string
  onOpenChange: (open: boolean) => void
}) {
  const { url, loading, error } = usePratinjauPdf({ template_id: templateId })
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className='max-w-[calc(210mm+8rem)] gap-3 p-6'>
        <DialogHeader>
          <DialogTitle>Pratinjau {label}</DialogTitle>
          <DialogDescription>Contoh tata letak dengan teks lorem ipsum.</DialogDescription>
        </DialogHeader>
        <div className='bg-muted h-[75vh] overflow-hidden rounded-md'>
          {url && <iframe title={`Pratinjau ${label}`} src={`${url}#view=FitH`} className='h-full w-full border-0 bg-white' />}
          {loading && <div className='text-muted-foreground flex h-full items-center justify-center text-sm'>Memuat pratinjau…</div>}
          {error && <div className='text-muted-foreground flex h-full items-center justify-center p-4 text-center text-sm'>Pratinjau tidak tersedia untuk template ini.</div>}
        </div>
      </DialogContent>
    </Dialog>
  )
}
