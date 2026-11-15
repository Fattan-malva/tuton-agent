'use client'

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DocxPreviewFrame } from '@/components/docx-preview-frame'
import { usePratinjauPdf } from '@/hooks/use-pratinjau-pdf'

// Pratinjau ukuran penuh satu template. Ukuran modal sama dengan pratinjau
// hasil di menu Result. PDF dibuat server saat dibuka dan dihapus saat ditutup.
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
      <DialogContent className='flex h-[92vh] max-h-[92vh] w-[96vw] max-w-[calc(210mm+8rem)] flex-col sm:max-w-[calc(210mm+8rem)]'>
        <DialogHeader>
          <DialogTitle className='truncate'>Pratinjau {label}</DialogTitle>
          <DialogDescription>Contoh tata letak dengan teks lorem ipsum.</DialogDescription>
        </DialogHeader>
        <DocxPreviewFrame url={url} loading={loading} error={error} title={`Pratinjau ${label}`} className='min-h-0 flex-1' />
      </DialogContent>
    </Dialog>
  )
}
