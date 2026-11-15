'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Plus } from 'lucide-react'
import { titleFor } from '@/config/nav'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { ThemeToggle } from '@/components/theme-toggle'

export function Header() {
  const pathname = usePathname()
  return (
    <header className='sticky top-0 z-50 flex h-16 shrink-0 items-center gap-3 border-b bg-background/75 px-4 backdrop-blur-md'>
      <SidebarTrigger variant='outline' className='max-md:scale-125' />
      <Separator orientation='vertical' className='h-6' />
      <h1 className='truncate text-sm font-semibold'>{titleFor(pathname)}</h1>
      <div className='ms-auto flex items-center gap-2'>
        <Button asChild size='sm' className='max-sm:hidden'>
          <Link href='/buat'>
            <Plus /> Kerjakan Tugas
          </Link>
        </Button>
        <ThemeToggle />
      </div>
    </header>
  )
}
