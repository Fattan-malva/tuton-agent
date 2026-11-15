'use client'

import { useEffect, useRef } from 'react'
import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { Plus } from 'lucide-react'
import { NAV_GROUPS } from '@/config/nav'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { ModeToggle } from '@/components/theme-toggle'
import { ProfileDropdown } from './profile-dropdown'

/** Nama tampilan untuk tiap segmen URL, memakai judul menu bila ada. */
function labelFor(pathname: string) {
  const clean = pathname.replace(/\/+$/, '') || '/'
  for (const group of NAV_GROUPS) {
    for (const item of group.items) {
      if (item.url === clean) return item.title
    }
  }
  const segmen = clean.split('/').filter(Boolean).pop() || 'Dashboard'
  return segmen.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function Header() {
  const pathname = usePathname()
  const ref = useRef<HTMLElement>(null)
  const clean = pathname.replace(/\/+$/, '') || '/'

  // Tinggi header disimpan sebagai variabel CSS: dipakai header halaman yang
  // sticky dan panel samping supaya keduanya berhenti tepat di bawahnya.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const akar = document.documentElement
    const ukur = () => {
      akar.style.setProperty('--header-h', `${Math.round(el.offsetHeight)}px`)
    }
    ukur()
    if (typeof ResizeObserver === 'undefined') return () => {}
    const pengamat = new ResizeObserver(ukur)
    pengamat.observe(el)
    return () => pengamat.disconnect()
  }, [])

  return (
    <header
      ref={ref}
      className='bg-card/95 supports-[backdrop-filter]:bg-card/80 sticky top-0 z-40 border-b backdrop-blur-md'
    >
      <div className='mx-auto flex w-full max-w-[1600px] items-center justify-between gap-6 px-4 py-2 sm:px-6'>
        <div className='flex min-w-0 items-center gap-3'>
          <SidebarTrigger className='[&_svg]:size-5!' />
          <Separator
            orientation='vertical'
            className='data-vertical:self-center hidden h-4! sm:block'
          />
          <Breadcrumb className='hidden min-w-0 sm:block'>
            <BreadcrumbList>
              <BreadcrumbItem>
                {/* Next Link, bukan <a href>: tanpa ini klik breadcrumb
                    memuat ulang seluruh halaman. */}
                <Link href='/' className='hover:text-foreground transition-colors'>
                  Dashboard
                </Link>
              </BreadcrumbItem>
              {clean !== '/' ? (
                <>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>{labelFor(clean)}</BreadcrumbPage>
                  </BreadcrumbItem>
                </>
              ) : null}
            </BreadcrumbList>
          </Breadcrumb>
        </div>

        <div className='flex items-center gap-1.5'>
          <Button asChild size='sm' className='max-sm:hidden'>
            <Link href='/buat'>
              <Plus /> Kerjakan Tugas
            </Link>
          </Button>
          <ModeToggle />
          <ProfileDropdown />
        </div>
      </div>
    </header>
  )
}
