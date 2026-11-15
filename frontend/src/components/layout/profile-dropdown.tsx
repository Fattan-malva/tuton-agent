'use client'

import { useUser } from '@clerk/react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { displayName, initials } from '@/lib/user'
import { AccountDialog } from './account-dialog'

/** Avatar di header: membuka modal akun, bukan halaman Clerk. */
export function ProfileDropdown() {
  const { user } = useUser()
  const name = displayName(user)

  return (
    <AccountDialog
      trigger={
        <Button variant='ghost' size='icon' className='relative rounded-full'>
          <Avatar className='size-8'>
            <AvatarImage src={user?.imageUrl} alt={name} />
            <AvatarFallback>{initials(name)}</AvatarFallback>
          </Avatar>
          <span className='ring-card absolute right-0 bottom-0 size-2 rounded-full bg-emerald-500 ring-2' />
          <span className='sr-only'>Buka menu akun</span>
        </Button>
      }
    />
  )
}
