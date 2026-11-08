export interface NavItem {
  id: string
  label: string
}

/** Primary navigation entries rendered in the sidebar.
 *
 * Only sections backed by a working API and screen are listed. Rate Cards,
 * Returns and Claims are out of scope for this build, so they are intentionally
 * omitted rather than shown as non-functional placeholders.
 */
export const NAV_ITEMS: NavItem[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'imports', label: 'Imports' },
  { id: 'reconciliation', label: 'Reconciliation' },
]
