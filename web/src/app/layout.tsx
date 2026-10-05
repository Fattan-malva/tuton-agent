import type { Metadata, Viewport } from 'next';
import { Inter, Fira_Code } from 'next/font/google';
import type { ReactNode } from 'react';
import './globals.css';

const body = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-body',
  weight: ['300', '400', '500', '600', '700'],
});

const mono = Fira_Code({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-mono',
  weight: ['400', '500'],
});

export const metadata: Metadata = {
  title: 'Tuton Agent',
  description: 'Tuton Agent - Auto-Grader and submission controller',
  // iOS memakai `apple-touch-icon` untuk Home Screen, bukan favicon. File-nya
  // di-generate oleh `web/scripts/make-icons.py` dari geometri ikon sidebar,
  // jadi bentuknya sama persis dengan logo di dalam app.
  appleWebApp: {
    capable: true,
    title: 'Tuton Agent',
    statusBarStyle: 'black-translucent',
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  // Warna address bar di iOS & Android. Tanpa ini, iOS memakai putih default
  // sehingga Home Screen "kedip putih" setiap kali app dibuka.
  themeColor: '#f8fafc',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="id" className={`${body.variable} ${mono.variable}`}>
      <head>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" />
      </head>
      <body className={body.className}>{children}</body>
    </html>
  );
}
