import type { CurrentUser } from '../api/client'
import { formatRole } from '../config/roles'
import type { NavItem } from '../config/navigation'

interface SidebarProps {
  items: NavItem[]
  activeId: string
  onSelect: (id: string) => void
  user: CurrentUser
  onSignOut: () => void
}

export function Sidebar({ items, activeId, onSelect, user, onSignOut }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__brand-mark">EC</span>
        <span className="sidebar__brand-text">Reconciliation</span>
      </div>

      <nav className="sidebar__nav" aria-label="Primary">
        {items.map((item) => {
          const isActive = item.id === activeId
          return (
            <button
              key={item.id}
              type="button"
              className={isActive ? 'sidebar__link sidebar__link--active' : 'sidebar__link'}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => onSelect(item.id)}
            >
              {item.label}
            </button>
          )
        })}
      </nav>

      <div className="sidebar__footer">
        <div className="sidebar__user">
          <span className="sidebar__user-name">{user.full_name}</span>
          <span className="sidebar__user-role">{formatRole(user.role.name)}</span>
        </div>
        <button type="button" className="sidebar__signout" onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </aside>
  )
}
