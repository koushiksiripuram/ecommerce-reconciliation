import { describe, expect, it } from 'vitest'
import {
  STATUS_ORDER,
  formatMoney,
  formatSignedMoney,
  issueLabel,
  issueTone,
  orderStatusLabel,
  statusMeta,
} from '../format'

describe('formatMoney', () => {
  it('renders an amount with its currency and two decimals', () => {
    // Grouping separator varies by locale, so only assert the grouping occurs.
    expect(formatMoney('1234.5')).toMatch(/^INR 1[^0-9]234\.50$/)
    expect(formatMoney(0)).toBe('INR 0.00')
  })

  it('respects a non-default currency', () => {
    expect(formatMoney('10', 'USD')).toBe('USD 10.00')
  })

  it('falls back to an em dash for unparseable values', () => {
    expect(formatMoney('not-a-number')).toBe('—')
  })
})

describe('formatSignedMoney', () => {
  it('marks the sign so a payment gap is unmistakable', () => {
    expect(formatSignedMoney('50')).toBe('+INR 50.00')
    expect(formatSignedMoney('-25.5')).toBe('-INR 25.50')
  })

  it('does not sign an exact zero', () => {
    expect(formatSignedMoney('0.00')).toBe('INR 0.00')
  })
})

describe('statusMeta', () => {
  it('maps every reconciliation status to a label and tone', () => {
    expect(statusMeta('settled')).toMatchObject({ label: 'Settled', tone: 'success' })
    expect(statusMeta('short_paid')).toMatchObject({ tone: 'danger' })
    expect(statusMeta('unpaid_past_due')).toMatchObject({ tone: 'danger' })
    expect(statusMeta('pending')).toMatchObject({ tone: 'warning' })
    expect(statusMeta('missing_in_orders')).toMatchObject({ tone: 'warning' })
  })

  it('covers every status in the display order', () => {
    expect(STATUS_ORDER).toHaveLength(5)
    for (const status of STATUS_ORDER) {
      expect(statusMeta(status).label.length).toBeGreaterThan(0)
    }
  })
})

describe('issueLabel', () => {
  it('translates known issue codes', () => {
    expect(issueLabel('freight_overcharged')).toBe('Freight overcharged')
    expect(issueLabel('duplicate_settlement')).toBe('Duplicate settlement')
    expect(issueLabel('order_not_found')).toBe('Order not found')
  })

  it('humanises an unknown code', () => {
    expect(issueLabel('something_new')).toBe('something new')
  })
})

describe('issueTone', () => {
  it('tones known issues by severity', () => {
    expect(issueTone('freight_overcharged')).toBe('danger')
    expect(issueTone('duplicate_settlement')).toBe('danger')
    expect(issueTone('missing_reference')).toBe('warning')
    expect(issueTone('overpaid')).toBe('info')
  })

  it('falls back to neutral for an unknown code', () => {
    expect(issueTone('unknown')).toBe('neutral')
  })
})

describe('orderStatusLabel', () => {
  it('renders a readable order status', () => {
    expect(orderStatusLabel('delivered')).toBe('Delivered')
    expect(orderStatusLabel('returned')).toBe('Returned')
  })
})
