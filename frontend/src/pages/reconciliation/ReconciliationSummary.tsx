import type { ReconciliationRun, ReconciliationSummary } from '../../api/reconciliation'
import {
  STATUS_ORDER,
  formatMoney,
  formatNumber,
  formatSignedMoney,
  statusMeta,
} from './format'

interface SummaryCardsProps {
  summary: ReconciliationSummary | null
  /** The run the summary is scoped to; supplies the run-level counts. */
  run: ReconciliationRun | null
  isLoading: boolean
  error: string | null
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-tile">
      <span className="summary-tile__label">{label}</span>
      <span className="summary-tile__value summary-tile__value--small">{value}</span>
    </div>
  )
}

/**
 * Headline figures for one reconciliation run: how much was reconciled, how
 * much money is at stake, and how the orders broke down by status.
 */
export function ReconciliationSummaryCards({
  summary,
  run,
  isLoading,
  error,
}: SummaryCardsProps) {
  if (error !== null) {
    return (
      <p className="alert alert--danger" role="alert">
        {error}
      </p>
    )
  }

  if (isLoading && summary === null) {
    return (
      <p className="empty-state" role="status">
        Loading reconciliation summary…
      </p>
    )
  }

  const byStatus = summary?.by_status ?? {}

  return (
    <div className="summary-grid">
      <Tile label="Total orders" value={run === null ? '—' : formatNumber(run.orders_reconciled)} />
      <Tile
        label="Settlements matched"
        value={run === null ? '—' : formatNumber(run.settlements_matched)}
      />
      <Tile label="Expected" value={formatMoney(summary?.expected_total ?? 0)} />
      <Tile label="Received" value={formatMoney(summary?.actual_total ?? 0)} />
      <Tile label="Difference" value={formatSignedMoney(summary?.difference_total ?? 0)} />
      <Tile label="Revenue leakage" value={formatMoney(summary?.revenue_leakage_total ?? 0)} />
      <Tile
        label="Freight overcharge"
        value={formatMoney(summary?.freight_overcharge_total ?? 0)}
      />
      {STATUS_ORDER.map((status) => (
        <Tile
          key={status}
          label={statusMeta(status).label}
          value={formatNumber(byStatus[status] ?? 0)}
        />
      ))}
    </div>
  )
}
