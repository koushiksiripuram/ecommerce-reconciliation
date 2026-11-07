import { describe, expect, it } from 'vitest'
import {
  confidenceLabel,
  formatBytes,
  formatDateTime,
  formatNumber,
  statusMeta,
} from '../format'

describe('statusMeta', () => {
  it('maps every batch status to a label and tone', () => {
    expect(statusMeta('uploaded')).toMatchObject({ label: 'Ready', tone: 'info' })
    expect(statusMeta('mapping_required')).toMatchObject({ tone: 'warning' })
    expect(statusMeta('processing')).toMatchObject({ tone: 'info' })
    expect(statusMeta('completed')).toMatchObject({ tone: 'success' })
    expect(statusMeta('failed')).toMatchObject({ tone: 'danger' })
  })
})

describe('confidenceLabel', () => {
  it('translates known confidence values', () => {
    expect(confidenceLabel('exact')).toBe('Exact')
    expect(confidenceLabel('alias')).toBe('Alias')
    expect(confidenceLabel('saved')).toBe('Saved')
  })

  it('returns null when no suggestion exists', () => {
    expect(confidenceLabel(null)).toBeNull()
  })
})

describe('formatBytes', () => {
  it('renders bytes, kilobytes and megabytes', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB')
  })

  it('renders an em dash when the size is unknown', () => {
    expect(formatBytes(null)).toBe('—')
  })
})

describe('formatNumber', () => {
  it('groups thousands using the runtime locale', () => {
    // Grouping separator varies by locale (e.g. 1,234 vs 1.234), so only assert
    // that the digits are grouped rather than the exact separator.
    expect(formatNumber(1234)).toMatch(/^1[^0-9]234$/)
    expect(formatNumber(0)).toBe('0')
  })
})

describe('formatDateTime', () => {
  it('renders an em dash for missing timestamps', () => {
    expect(formatDateTime(null)).toBe('—')
  })

  it('passes through unparseable values untouched', () => {
    expect(formatDateTime('not-a-date')).toBe('not-a-date')
  })

  it('renders a human readable timestamp for ISO input', () => {
    const result = formatDateTime('2026-11-01T10:00:00Z')
    expect(result).not.toBe('—')
    expect(result).toContain('2026')
  })
})
