/**
 * Builders for backend-shaped import data used across the frontend tests.
 *
 * The shapes mirror `backend/app/schemas/imports.py` so the tests exercise the
 * components against the same contract the API returns.
 */

import type {
  ImportBatch,
  ImportPreview,
  ImportRecord,
  SourceType,
} from '../api/imports'

export const SOURCE_TYPES: SourceType[] = [
  { value: 'orders', label: 'Orders', required_fields: ['external_order_id', 'order_amount'] },
  {
    value: 'settlements',
    label: 'Marketplace settlements',
    required_fields: ['settlement_amount'],
  },
]

export function makeBatch(overrides: Partial<ImportBatch> = {}): ImportBatch {
  return {
    id: 1,
    source_type: 'orders',
    source_label: 'Orders',
    partner: 'amazon',
    status: 'uploaded',
    original_filename: 'orders.csv',
    content_type: 'text/csv',
    size_bytes: 2048,
    total_rows: 3,
    processed_rows: 0,
    failed_rows: 0,
    column_mapping: null,
    started_at: null,
    completed_at: null,
    error_message: null,
    created_at: '2026-11-01T10:00:00Z',
    ...overrides,
  }
}

export function makePreview(overrides: Partial<ImportPreview> = {}): ImportPreview {
  return {
    batch: makeBatch({ status: 'mapping_required' }),
    headers: ['Order ID', 'Amount', 'Order Date'],
    rows: [{ 'Order ID': 'A-1', Amount: '10.00', 'Order Date': '2026-10-01' }],
    fields: [
      {
        name: 'external_order_id',
        label: 'Order ID',
        kind: 'text',
        required: true,
        mapped_header: 'Order ID',
        confidence: 'exact',
      },
      {
        name: 'order_amount',
        label: 'Order amount',
        kind: 'decimal',
        required: true,
        mapped_header: null,
        confidence: null,
      },
    ],
    unmapped_headers: ['Order Date'],
    missing_required_fields: ['order_amount'],
    mapping_complete: false,
    ...overrides,
  }
}

export function makeRecord(overrides: Partial<ImportRecord> = {}): ImportRecord {
  return {
    row_number: 2,
    external_reference: 'A-1',
    is_valid: false,
    raw_data: { 'Order ID': 'A-1', Amount: 'abc' },
    normalized_data: null,
    errors: [
      { field: 'order_amount', code: 'invalid_decimal', message: 'Amount is not a number.' },
    ],
    ...overrides,
  }
}
