/** Presentation helpers shared by the import screens. */

import type { ImportBatchStatus } from '../../api/imports'

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

interface StatusMeta {
  label: string
  tone: Tone
  /** Short explanation shown as a tooltip / hint. */
  hint: string
}

const STATUS_META: Record<ImportBatchStatus, StatusMeta> = {
  uploaded: {
    label: 'Ready',
    tone: 'info',
    hint: 'The file is parsed and a complete mapping is in place. It can be processed.',
  },
  mapping_required: {
    label: 'Mapping required',
    tone: 'warning',
    hint: 'At least one required field is unmapped. Review the columns before processing.',
  },
  processing: {
    label: 'Processing',
    tone: 'info',
    hint: 'Rows are being projected onto the canonical fields.',
  },
  completed: {
    label: 'Completed',
    tone: 'success',
    hint: 'Every row has been stored. Open the batch to inspect the rows.',
  },
  failed: {
    label: 'Failed',
    tone: 'danger',
    hint: 'Processing did not finish. The stored error explains why.',
  },
}

export function statusMeta(status: ImportBatchStatus): StatusMeta {
  return STATUS_META[status] ?? { label: status, tone: 'neutral', hint: '' }
}

/** How a suggested mapping was derived. Mirrors `app.imports.mapping`. */
const CONFIDENCE_LABELS: Record<string, string> = {
  saved: 'Saved',
  exact: 'Exact',
  alias: 'Alias',
  contains: 'Partial',
  manual: 'Manual',
}

export function confidenceLabel(confidence: string | null): string | null {
  if (confidence === null) return null
  return CONFIDENCE_LABELS[confidence] ?? confidence
}

export function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatNumber(value: number): string {
  return value.toLocaleString()
}

/** Render an ISO timestamp as a compact local string. */
export function formatDateTime(value: string | null): string {
  if (value === null) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
