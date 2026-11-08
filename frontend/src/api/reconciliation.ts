/**
 * Typed client for the backend reconciliation endpoints.
 *
 * Every function maps 1:1 onto a route in
 * `backend/app/api/routes/reconciliation.py` and mirrors the Pydantic schemas in
 * `backend/app/schemas/reconciliation.py`, so the UI stays honest about the real
 * API contract.
 *
 * Monetary values are serialised by the backend as exact decimal strings (it
 * never uses floats), so they are typed `string` here and formatted for display.
 */

import { request } from './client'

/** Outcome of comparing an order against its settlements. Mirrors `ReconciliationStatus`. */
export type ReconciliationStatus =
  | 'settled'
  | 'short_paid'
  | 'unpaid_past_due'
  | 'pending'
  | 'missing_in_orders'

/** Lifecycle state of a marketplace order. Mirrors `OrderStatus`. */
export type OrderStatus =
  | 'pending'
  | 'confirmed'
  | 'shipped'
  | 'delivered'
  | 'cancelled'
  | 'returned'

/** A structured problem detected on a reconciliation line. */
export interface ReconciliationIssue {
  code: string
  message: string
  amount: string | null
  references: string[]
  settlement_record_ids: number[]
}

/** The order a reconciliation line is about. */
export interface ReconciliationOrder {
  id: number
  external_order_id: string
  marketplace: string
  order_date: string | null
  status: OrderStatus
}

/** The settlement record used as evidence for a reconciliation line. */
export interface ReconciliationSettlement {
  id: number
  marketplace: string
  external_reference: string
  order_reference: string | null
  settlement_date: string | null
  net_amount: string
  import_batch_id: number | null
}

/** One reconciliation line: an order and the money received against it. */
export interface ReconciliationResult {
  id: number
  status: ReconciliationStatus
  currency: string
  expected_amount: string
  actual_amount: string
  difference_amount: string
  expected_freight_amount: string
  actual_freight_amount: string
  tcs_amount: string
  tds_amount: string
  issues: ReconciliationIssue[]
  order: ReconciliationOrder | null
  settlement_record: ReconciliationSettlement | null
  import_batch_id: number | null
  run_id: number | null
  is_current: boolean
  reconciled_at: string | null
  created_at: string | null
}

/** A page of reconciliation lines, newest first. */
export interface ReconciliationResultPage {
  total: number
  returned: number
  limit: number
  offset: number
  rows: ReconciliationResult[]
}

/** An immutable snapshot of one reconciliation execution. */
export interface ReconciliationRun {
  id: number
  started_at: string
  finished_at: string | null
  triggered_by_user_id: number | null
  triggered_by_email: string | null
  source_watermark: number | null
  orders_reconciled: number
  settlements_matched: number
  unmatched_settlements: number
  results_created: number
  by_status: Record<string, number>
  is_current: boolean
  created_at: string | null
}

/** A page of reconciliation runs, newest first. */
export interface ReconciliationRunPage {
  total: number
  returned: number
  limit: number
  offset: number
  rows: ReconciliationRun[]
}

/** One run together with the results it produced. */
export interface ReconciliationRunDetail {
  run: ReconciliationRun
  results: ReconciliationResultPage
}

/** Aggregated reconciliation figures for one run. */
export interface ReconciliationSummary {
  run_id: number | null
  total: number
  by_status: Record<string, number>
  expected_total: string
  actual_total: string
  difference_total: string
  tcs_total: string
  tds_total: string
  revenue_leakage_total: string
  freight_overcharge_total: string
}

export interface ResultListParams {
  status?: ReconciliationStatus | ''
  marketplace?: string
  hasIssues?: boolean
  runId?: number
  limit?: number
  offset?: number
}

export interface SummaryParams {
  marketplace?: string
  runId?: number
}

export interface RunListParams {
  limit?: number
  offset?: number
}

/** Drop empty filter values and serialise the rest as a query string. */
function toQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '' || value === false) continue
    search.set(key, String(value))
  }
  const query = search.toString()
  return query.length > 0 ? `?${query}` : ''
}

/** Recompute every reconciliation result, preserving the previous run. */
export function runReconciliation(): Promise<ReconciliationRun> {
  return request<ReconciliationRun>('/reconciliation/run', { method: 'POST' })
}

/** List reconciliation runs, newest first, with the current one flagged. */
export function listRuns(params: RunListParams = {}): Promise<ReconciliationRunPage> {
  return request<ReconciliationRunPage>(
    `/reconciliation/runs${toQuery({ limit: params.limit, offset: params.offset })}`,
  )
}

/** Load one run together with the results it produced. */
export function getRun(
  runId: number,
  params: RunListParams = {},
): Promise<ReconciliationRunDetail> {
  return request<ReconciliationRunDetail>(
    `/reconciliation/runs/${runId}${toQuery({ limit: params.limit, offset: params.offset })}`,
  )
}

/** Page through reconciliation lines; reads the latest run by default. */
export function listResults(params: ResultListParams = {}): Promise<ReconciliationResultPage> {
  return request<ReconciliationResultPage>(
    `/reconciliation${toQuery({
      status: params.status,
      marketplace: params.marketplace,
      has_issues: params.hasIssues,
      run_id: params.runId,
      limit: params.limit,
      offset: params.offset,
    })}`,
  )
}

/** Aggregate totals, per-status counts and revenue leakage for one run. */
export function getSummary(params: SummaryParams = {}): Promise<ReconciliationSummary> {
  return request<ReconciliationSummary>(
    `/reconciliation/summary${toQuery({
      marketplace: params.marketplace,
      run_id: params.runId,
    })}`,
  )
}

/** Load one reconciliation line with its supporting evidence. */
export function getResult(resultId: number): Promise<ReconciliationResult> {
  return request<ReconciliationResult>(`/reconciliation/${resultId}`)
}
