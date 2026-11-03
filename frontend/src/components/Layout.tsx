import type { ReactNode } from 'react'
import type { CurrentUser } from '../api/client'
import type { NavItem } from '../config/navigation'
import { Sidebar } from './Sidebar'

interface LayoutProps {
  items: NavItem[]
  activeId: string
  onSelect: (id: string) => void
  user: CurrentUser
  onSignOut: () => void
  children: ReactNode
}

export function Layout({ items, activeId, onSelect, user, onSignOut, children }: LayoutProps) {
  return (
    <div className="app-shell">
      <Sidebar
        items={items}
        activeId={activeId}
        onSelect={onSelect}
        user={user}
        onSignOut={onSignOut}
      />
      <main className="app-main">{children}</main>
    </div>
  )
}
