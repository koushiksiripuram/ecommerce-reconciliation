/** Display labels for the roles the backend can return. */
const ROLE_LABELS: Record<string, string> = {
  finance_executive: 'Finance Executive',
  co_founder: 'Co-Founder',
}

/** Turn a role name from the API into something readable. */
export function formatRole(roleName: string): string {
  return ROLE_LABELS[roleName] ?? roleName.replace(/_/g, ' ')
}

/**
 * Roles allowed to mutate finance data (import lifecycle, reconciliation runs).
 *
 * Mirrors the `ImportOperator`/`ReconciliationOperator` dependencies in the
 * backend routers; the UI hides these actions for everyone else, and the API
 * enforces it too.
 */
const FINANCE_OPERATOR_ROLES = new Set(['finance_executive', 'co_founder'])

export function canManageImports(roleName: string): boolean {
  return FINANCE_OPERATOR_ROLES.has(roleName)
}

/** Roles allowed to start a reconciliation run. Mirrors `ReconciliationOperator`. */
export function canManageReconciliation(roleName: string): boolean {
  return FINANCE_OPERATOR_ROLES.has(roleName)
}
