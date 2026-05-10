import type { Metadata } from 'next';
import Link from 'next/link';
import '../styles/globals.css';

export const metadata: Metadata = {
  title: '教師評語系統',
  description: 'AI-assisted semester evaluation drafting for K-12 teachers',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body className="min-h-screen">
        <header className="border-b border-stone-200 bg-white">
          <div className="mx-auto max-w-5xl px-6 py-3 flex items-center justify-between">
            <Link href="/" className="font-semibold text-accent">墨痕</Link>
            <span className="text-sm text-ink-muted">教師評語系統</span>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
