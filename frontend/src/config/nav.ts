import {
  BookOpen,
  Bot,
  FileText,
  LayoutDashboard,
  ListTodo,
  Server,
  Settings,
  Sparkles,
  Terminal,
  type LucideIcon,
} from 'lucide-react'

export type NavItem = { title: string; url: string; icon: LucideIcon }

export const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: 'Utama',
    items: [
      { title: 'Dashboard', url: '/', icon: LayoutDashboard },
      { title: 'Kerjakan Tugas', url: '/buat', icon: ListTodo },
      { title: 'Agent Worker', url: '/agents', icon: Bot },
    ],
  },
  {
    title: 'Hasil',
    items: [
      { title: 'Result', url: '/results', icon: FileText },
      { title: 'Log Live', url: '/log', icon: Terminal },
      { title: 'Courses', url: '/courses', icon: BookOpen },
    ],
  },
  {
    title: 'Lainnya',
    items: [
      { title: 'Provider', url: '/providers', icon: Server },
      { title: 'Skill', url: '/skills', icon: Sparkles },
      { title: 'Pengaturan', url: '/settings', icon: Settings },
    ],
  },
]

export function titleFor(pathname: string) {
  const clean = pathname.replace(/\/+$/, '') || '/'
  for (const group of NAV_GROUPS) {
    for (const item of group.items) {
      if (item.url === clean) return item.title
    }
  }
  return 'Dashboard'
}
