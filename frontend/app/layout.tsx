import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'SPED Autocorretor',
  description: 'Validação e correção automática EFD ICMS/IPI',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  )
}
