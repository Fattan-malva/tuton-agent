import type { Metadata } from 'next';
import { Outfit } from 'next/font/google';
import { Press_Start_2P } from 'next/font/google';
import { Silkscreen } from 'next/font/google';
import type { ReactNode } from 'react';
import './globals.css';

const body = Outfit({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-body',
  weight: ['300', '400', '500', '600', '700'],
});

const display = Press_Start_2P({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-pixel',
  weight: ['400'],
});

const terminal = Silkscreen({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-terminal',
  weight: ['400', '700'],
});

export const metadata: Metadata = {
  title: 'Tuton Agent',
  description: 'Tuton Agent - Auto-Grader and submission controller',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="id" className={`${body.variable} ${display.variable} ${terminal.variable}`}>
      <body className={body.className}>{children}</body>
    </html>
  );
}
