'use client'

import Link from 'next/link'
import { NAV_GROUPS } from '@/config/nav'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { NavGroup } from './nav-group'
import { NavUser } from './nav-user'

export function AppSidebar() {
  return (
    <Sidebar collapsible='icon' variant='sidebar'>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size='lg' asChild>
              <Link href='/'>
                {/* Ikon yang sama dengan ikon tab browser (/icon.png). */}
                <img src='/icon.png' alt='' className='aspect-square size-8 rounded-lg' />
                <div className='grid flex-1 text-start text-sm leading-tight'>
                  <span className='truncate font-bold'>Tuton.agent</span>
                  <span className='truncate text-xs text-muted-foreground'>
                    Dashboard Pipeline
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        {NAV_GROUPS.map((group) => (
          <NavGroup key={group.title} {...group} />
        ))}
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
