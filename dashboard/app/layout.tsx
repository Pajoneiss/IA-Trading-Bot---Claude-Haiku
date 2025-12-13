import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'IA Trading Dashboard',
  description: 'Dashboard para monitoramento do bot de trading com IA',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="pt-BR">
      <body className="antialiased">
        {children}
      </body>
    </html>
  )
}
