'use client'

import { useUser } from '@clerk/react'
import { ChevronsUpDown } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import { displayName, initials } from '@/lib/user'
import { AccountDialog } from './account-dialog'

export function NavUser() {
  const { user } = useUser()
  const nama = displayName(user)
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
              <Avatar className='size-8'>
                <AvatarImage src={user?.imageUrl} alt={nama} />
                <AvatarFallback>{initials(nama)}</AvatarFallback>
              </Avatar>
              <div className='grid flex-1 text-start text-sm leading-tight group-data-[collapsible=icon]:hidden'>
                <span className='truncate font-semibold'>{nama}</span>
                <span className='truncate text-xs text-muted-foreground'>
                  {email || 'tuton.agent'}
                </span>
              </div>
              <ChevronsUpDown className='ms-auto size-4 group-data-[collapsible=icon]:hidden' />
            </SidebarMenuButton>
          }
        />
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
