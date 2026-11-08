/**
 * Builders for backend-shaped reconciliation data used across the frontend
 * tests.
 *
 * The shapes mirror `backend/app/schemas/reconciliation.py`, including the
 * decimal-as-string serialisation, so the tests exercise the components against
 * the same contract the API returns.
 */

import type {
  ReconciliationResult,
  ReconciliationRun,
  ReconciliationSummary,
} from '../api/reconciliation'

export function makeRun(overrides: Partial<ReconciliationRun> = {}): ReconciliationRun {
  return {
    id: 1,
    started_at: '2026-11-07T09:00:00Z',
    finished_at: '2026-11-07T09:00:03Z',
    triggered_by_user_id: 1,
    triggered_by_email: 'fin@example.com',
    source_watermark: 7,
    orders_reconciled: 3,
    settlements_matched: 2,
    unmatched_settlements: 1,
    results_created: 4,
    by_status: {
      settled: 1,
      short_paid: 1,
      unpaid_past_due: 1,
      pending: 0,
      missing_in_orders: 1,
    },
    is_current: true,
    created_at: '2026-11-07T09:00:00Z',
    ...overrides,
  }
}

export function makeResult(overrides: Partial<ReconciliationResult> = {}): ReconciliationResult {
  return {
    id: 10,
    status: 'settled',
    currency: 'INR',
    expected_amount: '100.00',
    actual_amount: '100.00',
    difference_amount: '0.00',
    expected_freight_amount: '0.00',
    actual_freight_amount: '0.00',
    tcs_amount: '0.00',
    tds_amount: '0.00',
    issues: [],
    order: {
      id: 1,
      external_order_id: 'A-1',
      marketplace: 'amazon',
      order_date: '2026-10-01T00:00:00Z',
      status: 'delivered',
    },
    settlement_record: {
      id: 1,
      marketplace: 'amazon',
      external_reference: 'TXN-1',
      order_reference: 'A-1',
      settlement_date: '2026-10-05T00:00:00Z',
      net_amount: '100.00',
      import_batch_id: 7,
    },
    import_batch_id: 7,
    run_id: 1,
    is_current: true,
    reconciled_at: '2026-11-07T09:00:00Z',
    created_at: '2026-11-07T09:00:00Z',
    ...overrides,
  }
}

export function makeSummary(overrides: Partial<ReconciliationSummary> = {}): ReconciliationSummary {
  return {
    run_id: 1,
    total: 4,
    by_status: {
      settled: 1,
      short_paid: 1,
      unpaid_past_due: 1,
      pending: 0,
      missing_in_orders: 1,
    },
    expected_total: '300.00',
    actual_total: '250.00',
    difference_total: '50.00',
    tcs_total: '0.00',
    tds_total: '0.00',
    revenue_leakage_total: '50.00',
    freight_overcharge_total: '0.00',
    ...overrides,
  }
}
