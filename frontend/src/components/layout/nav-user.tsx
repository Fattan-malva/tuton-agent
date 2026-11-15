'use client'

import { useState } from 'react'
import { useUser, useClerk } from '@clerk/react'
import { LogOut, ChevronsUpDown } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'

function inisial(nama: string) {
  const kata = nama.trim().split(/\s+/).filter(Boolean)
  if (!kata.length) return 'TA'
  const huruf = kata.length > 1 ? kata[0][0] + kata[kata.length - 1][0] : kata[0].slice(0, 2)
  return huruf.toUpperCase()
}

export function NavUser() {
  const { isMobile } = useSidebar()
  const { user } = useUser()
  const { signOut } = useClerk()
  const [keluar, setKeluar] = useState(false)

  const nama = user?.fullName || user?.username || user?.primaryEmailAddress?.emailAddress || 'Akun'
  const email = user?.primaryEmailAddress?.emailAddress || ''

  async function logout() {
    setKeluar(true)
    // signOut() juga menghapus cache SWR yang menyimpan data akun ini.
    await signOut({ redirectUrl: '/login/' }).catch(() => {
      window.location.href = '/login/'
    })
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size='lg'
              className='data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground'
            >
              <div className='flex size-8 items-center justify-center rounded-lg bg-primary text-xs font-bold text-primary-foreground'>
                {inisial(nama)}
              </div>
              <div className='grid flex-1 text-start text-sm leading-tight'>
                <span className='truncate font-semibold'>{nama}</span>
                <span className='truncate text-xs text-muted-foreground'>
                  {email || 'tuton.agent'}
                </span>
              </div>
              <ChevronsUpDown className='ms-auto size-4' />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className='w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg'
            side={isMobile ? 'bottom' : 'right'}
            align='end'
            sideOffset={4}
          >
            <DropdownMenuLabel className='font-normal'>
              Dashboard pipeline tutor
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant='destructive'
              disabled={keluar}
              onClick={logout}
            >
              <LogOut />
              {keluar ? 'Keluar...' : 'Keluar'}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
