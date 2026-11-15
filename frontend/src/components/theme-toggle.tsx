'use client'

import { MoonStarIcon, SunIcon } from 'lucide-react'
import { useTheme } from '@/components/theme-provider'
import { Button } from '@/components/ui/button'

/** Tombol tema gaya template: dua ikon bertumpuk, berganti tanpa reload. */
export function ModeToggle() {
  const { resolvedTheme, setTheme } = useTheme()

  return (
    <Button
      variant='ghost'
      size='icon'
      className='relative'
      onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
      title='Ubah tema'
    >
      <MoonStarIcon className='scale-100 transition-transform dark:scale-0' />
      <SunIcon className='absolute scale-0 transition-transform dark:scale-100' />
      <span className='sr-only'>Ubah tema</span>
    </Button>
  )
}
