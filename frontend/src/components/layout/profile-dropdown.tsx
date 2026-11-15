'use client'

import { useState } from 'react'
import { useClerk, useUser } from '@clerk/react'
import { LogOut, ChevronsUpDown } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import Link from 'next/link'

function initials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean)
  return (words.length > 1 ? words[0][0] + words.at(-1)![0] : words[0]?.slice(0, 2) || 'TA').toUpperCase()
}

export function ProfileDropdown() {
  const { user } = useUser()
  const { signOut } = useClerk()
  const [busy, setBusy] = useState(false)
  const name = user?.fullName || user?.username || user?.primaryEmailAddress?.emailAddress || 'Akun'
  const email = user?.primaryEmailAddress?.emailAddress || 'tuton.agent'

  async function logout() {
    setBusy(true)
    await signOut({ redirectUrl: '/login/' }).catch(() => { window.location.href = '/login/' })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant='ghost' size='icon' className='relative rounded-full'>
          <Avatar className='size-8'>
            <AvatarImage src={user?.imageUrl} alt={name} />
            <AvatarFallback>{initials(name)}</AvatarFallback>
          </Avatar>
          <span className='ring-card absolute right-0 bottom-0 size-2 rounded-full bg-emerald-500 ring-2' />
          <span className='sr-only'>Buka menu akun</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-64'>
        <DropdownMenuLabel className='flex items-center gap-3 px-2 py-2 font-normal'>
          <Avatar className='size-9'>
            <AvatarImage src={user?.imageUrl} alt={name} />
            <AvatarFallback>{initials(name)}</AvatarFallback>
          </Avatar>
          <span className='min-w-0'>
            <span className='text-foreground block truncate font-semibold'>{name}</span>
            <span className='text-muted-foreground block truncate text-xs'>{email}</span>
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem render={<Link href='/settings/' />}>Pengaturan</DropdownMenuItem>
        <DropdownMenuItem variant='destructive' disabled={busy} onClick={logout}>
          <LogOut /> {busy ? 'Keluar...' : 'Keluar'}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
