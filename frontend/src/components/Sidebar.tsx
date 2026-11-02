import type { NavItem } from '../config/navigation'

interface SidebarProps {
  items: NavItem[]
  activeId: string
  onSelect: (id: string) => void
}

export function Sidebar({ items, activeId, onSelect }: SidebarProps) {
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
    </aside>
  )
}
