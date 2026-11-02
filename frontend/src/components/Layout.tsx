import type { ReactNode } from 'react'
import type { NavItem } from '../config/navigation'
import { Sidebar } from './Sidebar'

interface LayoutProps {
  items: NavItem[]
  activeId: string
  onSelect: (id: string) => void
  children: ReactNode
}

export function Layout({ items, activeId, onSelect, children }: LayoutProps) {
  return (
    <div className="app-shell">
      <Sidebar items={items} activeId={activeId} onSelect={onSelect} />
      <main className="app-main">{children}</main>
    </div>
  )
}
