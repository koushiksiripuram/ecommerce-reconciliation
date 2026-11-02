export interface NavItem {
  id: string
  label: string
}

/** Primary navigation entries rendered in the sidebar. */
export const NAV_ITEMS: NavItem[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'imports', label: 'Imports' },
  { id: 'reconciliation', label: 'Reconciliation' },
  { id: 'rate-cards', label: 'Rate Cards' },
  { id: 'returns', label: 'Returns' },
  { id: 'claims', label: 'Claims' },
]
