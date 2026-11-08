import { useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import { getResult } from '../../api/reconciliation'
import type { ReconciliationResult } from '../../api/reconciliation'
import {
  formatDateTime,
  formatMoney,
  formatNumber,
  formatSignedMoney,
  issueLabel,
  issueTone,
  orderStatusLabel,
  statusMeta,
} from './format'

interface DetailProps {
  resultId: number
  onBack: () => void
}

function loadErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return 'This reconciliation line no longer exists.'
  }
  return 'Could not load this reconciliation line. Please try again.'
}

/**
 * Order-level detail: the evidence behind one reconciliation line — the order,
 * the settlement record that paid it, and any discrepancy detected.
 */
export function ReconciliationDetail({ resultId, onBack }: DetailProps) {
  const [result, setResult] = useState<ReconciliationResult | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)

    getResult(resultId)
      .then((data) => {
        if (!cancelled) setResult(data)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(loadErrorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [resultId])

  if (isLoading && result === null) {
    return (
      <section className="page">
        <p className="empty-state" role="status">
          Loading reconciliation line…
        </p>
      </section>
    )
  }

  if (error !== null || result === null) {
    return (
      <section className="page">
        <button className="link-button" type="button" onClick={onBack}>
          ← Back to reconciliation
        </button>
        <p className="alert alert--danger" role="alert">
          {error ?? 'Reconciliation line unavailable.'}
        </p>
      </section>
    )
  }

  const meta = statusMeta(result.status)
  const reference = result.order?.external_order_id
    ?? result.settlement_record?.external_reference
    ?? `Line #${result.id}`
  const marketplace = result.order?.marketplace ?? result.settlement_record?.marketplace ?? '—'

  return (
    <section className="page page--wide">
      <div className="detail-header">
        <button className="link-button" type="button" onClick={onBack}>
          ← Back to reconciliation
        </button>
        <div className="detail-header__title">
          <h1 className="page__title">{reference}</h1>
          <span className={`tag tag--${meta.tone}`} title={meta.hint}>
            {meta.label}
          </span>
          {!result.is_current && <span className="tag tag--neutral">Superseded</span>}
        </div>
        <p className="page__subtitle">
          {marketplace} · run #{result.run_id ?? '—'} · reconciled {formatDateTime(result.reconciled_at)}
        </p>
      </div>

      <div className="summary-grid">
        <div className="summary-tile">
          <span className="summary-tile__label">Expected</span>
          <span className="summary-tile__value summary-tile__value--small">
            {formatMoney(result.expected_amount, result.currency)}
          </span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">Received</span>
          <span className="summary-tile__value summary-tile__value--small">
            {formatMoney(result.actual_amount, result.currency)}
          </span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">Difference</span>
          <span className="summary-tile__value summary-tile__value--small">
            {formatSignedMoney(result.difference_amount, result.currency)}
          </span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">TCS withheld</span>
          <span className="summary-tile__value summary-tile__value--small">
            {formatMoney(result.tcs_amount, result.currency)}
          </span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">TDS withheld</span>
          <span className="summary-tile__value summary-tile__value--small">
            {formatMoney(result.tds_amount, result.currency)}
          </span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">Freight (rate card)</span>
          <span className="summary-tile__value summary-tile__value--small">
            {formatMoney(result.expected_freight_amount, result.currency)}
          </span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">Freight (charged)</span>
          <span className="summary-tile__value summary-tile__value--small">
            {formatMoney(result.actual_freight_amount, result.currency)}
          </span>
        </div>
      </div>

      <div className="details-grid">
        <div className="card">
          <h2 className="card__title">Order</h2>
          {result.order === null ? (
            <p className="card__hint">
              No matching order. This settlement was received without a corresponding order.
            </p>
          ) : (
            <dl className="kv">
              <div className="kv__row">
                <dt>Order reference</dt>
                <dd>{result.order.external_order_id}</dd>
              </div>
              <div className="kv__row">
                <dt>Marketplace</dt>
                <dd>{result.order.marketplace}</dd>
              </div>
              <div className="kv__row">
                <dt>Order date</dt>
                <dd>{formatDateTime(result.order.order_date)}</dd>
              </div>
              <div className="kv__row">
                <dt>Order status</dt>
                <dd>{orderStatusLabel(result.order.status)}</dd>
              </div>
            </dl>
          )}
        </div>

        <div className="card">
          <h2 className="card__title">Settlement evidence</h2>
          {result.settlement_record === null ? (
            <p className="card__hint">
              No settlement received for this order yet.
            </p>
          ) : (
            <dl className="kv">
              <div className="kv__row">
                <dt>Reference</dt>
                <dd>{result.settlement_record.external_reference}</dd>
              </div>
              <div className="kv__row">
                <dt>Order reference</dt>
                <dd>{result.settlement_record.order_reference ?? '—'}</dd>
              </div>
              <div className="kv__row">
                <dt>Settlement date</dt>
                <dd>{formatDateTime(result.settlement_record.settlement_date)}</dd>
              </div>
              <div className="kv__row">
                <dt>Net amount</dt>
                <dd>{formatMoney(result.settlement_record.net_amount, result.currency)}</dd>
              </div>
              <div className="kv__row">
                <dt>Import batch</dt>
                <dd>
                  {result.settlement_record.import_batch_id === null
                    ? '—'
                    : `#${result.settlement_record.import_batch_id}`}
                </dd>
              </div>
            </dl>
          )}
        </div>
      </div>

      <div className="card">
        <h2 className="card__title">Discrepancies</h2>
        {result.issues.length === 0 ? (
          <p className="card__hint">No issues were detected on this line.</p>
        ) : (
          <dl className="kv">
            {result.issues.map((issue, index) => (
              <div className="kv__row" key={`${issue.code}-${index}`}>
                <dt>
                  <span className={`tag tag--${issueTone(issue.code)}`}>{issueLabel(issue.code)}</span>
                </dt>
                <dd>
                  {issue.message}
                  {issue.amount !== null && (
                    <>
                      {' '}
                      <strong>{formatMoney(issue.amount, result.currency)}</strong>
                    </>
                  )}
                  {issue.references.length > 0 && (
                    <span className="muted"> · refs: {issue.references.join(', ')}</span>
                  )}
                  {issue.settlement_record_ids.length > 0 && (
                    <span className="muted">
                      {' '}
                      · settlement records: {issue.settlement_record_ids.map(formatNumber).join(', ')}
                    </span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </section>
  )
}
