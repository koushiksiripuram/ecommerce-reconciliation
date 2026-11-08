/** Presentation helpers shared by the reconciliation screens. */

import type { ReconciliationStatus } from '../../api/reconciliation'

// Reuse the generic date/number formatters so both features render identically.
export { formatDateTime, formatNumber } from '../imports/format'

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

const MONEY_FORMAT: Intl.NumberFormatOptions = {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
}

/** Amounts arrive as exact decimal strings; parse for display only. */
function toNumber(value: string | number): number | null {
  const amount = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(amount) ? amount : null
}

/** Format an exact amount with its currency, e.g. `INR 1,234.56`. */
export function formatMoney(value: string | number, currency = 'INR'): string {
  const amount = toNumber(value)
  if (amount === null) return '—'
  return `${currency} ${amount.toLocaleString(undefined, MONEY_FORMAT)}`
}

/** Format a signed amount, marking the sign so a payment gap is unmistakable. */
export function formatSignedMoney(value: string | number, currency = 'INR'): string {
  const amount = toNumber(value)
  if (amount === null) return '—'
  if (amount === 0) return formatMoney(0, currency)
  const sign = amount > 0 ? '+' : '-'
  return `${sign}${formatMoney(Math.abs(amount), currency)}`
}

export interface StatusMeta {
  label: string
  tone: Tone
  /** Short explanation shown as a tooltip / hint. */
  hint: string
}

const STATUS_META: Record<ReconciliationStatus, StatusMeta> = {
  settled: {
    label: 'Settled',
    tone: 'success',
    hint: 'The money received matches what the order expected.',
  },
  short_paid: {
    label: 'Short paid',
    tone: 'danger',
    hint: 'Less was received than expected, beyond the tolerance.',
  },
  unpaid_past_due: {
    label: 'Unpaid (past due)',
    tone: 'danger',
    hint: 'No settlement arrived and the order is past its due window.',
  },
  pending: {
    label: 'Pending',
    tone: 'warning',
    hint: 'No settlement yet, but the order is still within its due window.',
  },
  missing_in_orders: {
    label: 'Missing in orders',
    tone: 'warning',
    hint: 'A settlement was received that could not be tied back to any order.',
  },
}

export function statusMeta(status: ReconciliationStatus): StatusMeta {
  return STATUS_META[status] ?? { label: status, tone: 'neutral', hint: '' }
}

/** Display order for the status counts. Mirrors `ReconciliationStatus`. */
export const STATUS_ORDER: ReconciliationStatus[] = [
  'settled',
  'short_paid',
  'unpaid_past_due',
  'pending',
  'missing_in_orders',
]

const ISSUE_LABELS: Record<string, string> = {
  freight_overcharged: 'Freight overcharged',
  duplicate_settlement: 'Duplicate settlement',
  missing_reference: 'Missing reference',
  order_not_found: 'Order not found',
  return_not_received: 'Return not received',
  overpaid: 'Overpaid',
}

/** Turn a stable issue code into a readable label. */
export function issueLabel(code: string): string {
  return ISSUE_LABELS[code] ?? code.replace(/_/g, ' ')
}

/** Pick a tag tone for a known issue code. */
export function issueTone(code: string): Tone {
  switch (code) {
    case 'freight_overcharged':
    case 'duplicate_settlement':
      return 'danger'
    case 'missing_reference':
    case 'order_not_found':
    case 'return_not_received':
      return 'warning'
    case 'overpaid':
      return 'info'
    default:
      return 'neutral'
  }
}

const ORDER_STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  confirmed: 'Confirmed',
  shipped: 'Shipped',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
  returned: 'Returned',
}

export function orderStatusLabel(status: string): string {
  return ORDER_STATUS_LABELS[status] ?? status.replace(/_/g, ' ')
}
