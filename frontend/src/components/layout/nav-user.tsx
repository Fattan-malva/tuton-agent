'use client'

import { useUser } from '@clerk/react'
import { ChevronsUpDown } from 'lucide-react'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import { AccountDialog } from './account-dialog'

function inisial(nama: string) {
  const kata = nama.trim().split(/\s+/).filter(Boolean)
  if (!kata.length) return 'TA'
  const huruf = kata.length > 1 ? kata[0][0] + kata[kata.length - 1][0] : kata[0].slice(0, 2)
  return huruf.toUpperCase()
}

export function NavUser() {
  const { user } = useUser()
  const nama = user?.fullName || user?.username || user?.primaryEmailAddress?.emailAddress || 'Akun'
  const email = user?.primaryEmailAddress?.emailAddress || ''

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <AccountDialog
          trigger={
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
          }
        />
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
