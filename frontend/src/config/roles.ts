/** Display labels for the roles the backend can return. */
const ROLE_LABELS: Record<string, string> = {
  finance_executive: 'Finance Executive',
  co_founder: 'Co-Founder',
}

/** Turn a role name from the API into something readable. */
export function formatRole(roleName: string): string {
  return ROLE_LABELS[roleName] ?? roleName.replace(/_/g, ' ')
}
