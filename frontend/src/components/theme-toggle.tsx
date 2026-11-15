'use client'

import { Moon, Sun } from 'lucide-react'
import { useTheme, type Theme } from '@/components/theme-provider'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const LABEL: Record<Theme, string> = {
  light: 'Terang',
  dark: 'Gelap',
  system: 'Ikut sistem',
}

export function ThemeToggle() {
  const { theme, resolvedTheme, setTheme } = useTheme()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant='ghost' size='icon' title='Ubah tema'>
          {resolvedTheme === 'dark' ? <Moon /> : <Sun />}
          <span className='sr-only'>Ubah tema</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end'>
        {(Object.keys(LABEL) as Theme[]).map((value) => (
          <DropdownMenuItem
            key={value}
            onClick={() => setTheme(value)}
            className={value === theme ? 'bg-accent' : ''}
          >
            {LABEL[value]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
