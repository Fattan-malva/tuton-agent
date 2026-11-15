'use client'

import { useUser } from '@clerk/react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { AccountDialog } from './account-dialog'

function initials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean)
  return (
    words.length > 1
      ? words[0][0] + words.at(-1)![0]
      : words[0]?.slice(0, 2) || 'TA'
  ).toUpperCase()
}

/** Avatar di header: membuka modal akun, bukan halaman Clerk. */
export function ProfileDropdown() {
  const { user } = useUser()
  const name =
    user?.fullName ||
    user?.username ||
    user?.primaryEmailAddress?.emailAddress ||
    'Akun'

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
