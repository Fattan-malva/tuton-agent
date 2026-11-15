import type { Metadata, Viewport } from 'next'
import './globals.css'
import { SWRProvider } from '@/components/swr-provider'
import { ThemeProvider } from '@/components/theme-provider'
import { AppAuthProvider } from '@/components/clerk-provider'

export const metadata: Metadata = {
  title: 'Tuton — Dashboard Pipeline',
  description: 'Dashboard pipeline tutor UT',
  icons: { icon: '/icon.png', apple: '/apple-touch-icon.png' },
  appleWebApp: {
    capable: true,
    title: 'Tuton',
    statusBarStyle: 'default',
  },
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f7f6f3' },
    { media: '(prefers-color-scheme: dark)', color: '#000000' },
  ],
}

// Pasang tema sebelum CSS digambar supaya tidak ada kedip putih saat mode
// gelap dibuka.
const themeScript = `(function(){try{var t=localStorage.getItem('tuton-theme');if(t!=='light'&&t!=='dark'){t=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.classList.toggle('dark',t==='dark')}catch(e){}})()`

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang='id' suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className='min-h-svh bg-background text-foreground antialiased'>
        <ThemeProvider>
          <AppAuthProvider>
            <SWRProvider>{children}</SWRProvider>
          </AppAuthProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
