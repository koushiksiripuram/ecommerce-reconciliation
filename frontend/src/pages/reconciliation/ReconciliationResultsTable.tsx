import type { ReconciliationResult, ReconciliationStatus } from '../../api/reconciliation'
import {
  STATUS_ORDER,
  formatMoney,
  formatSignedMoney,
  issueLabel,
  issueTone,
  statusMeta,
} from './format'

const STATUS_OPTIONS: Array<{ value: ReconciliationStatus | ''; label: string }> = [
  { value: '', label: 'All statuses' },
  ...STATUS_ORDER.map((status) => ({ value: status, label: statusMeta(status).label })),
]

export interface ReconciliationFilters {
  status: ReconciliationStatus | ''
  marketplace: string
}

interface ResultsTableProps {
  results: ReconciliationResult[]
  total: number
  isLoading: boolean
  error: string | null
  filters: ReconciliationFilters
  /** Marketplaces seen in the loaded rows, offered as filter options. */
  marketplaces: string[]
  page: number
  pageSize: number
  onFiltersChange: (filters: ReconciliationFilters) => void
  onPrevious: () => void
  onNext: () => void
  onRefresh: () => void
  onOpen: (resultId: number) => void
}

/** The order reference, falling back to the settlement's for unmatched money. */
function referenceOf(result: ReconciliationResult): string {
  if (result.order !== null) return result.order.external_order_id
  return result.settlement_record?.external_reference ?? '—'
}

function marketplaceOf(result: ReconciliationResult): string {
  return result.order?.marketplace ?? result.settlement_record?.marketplace ?? '—'
}

export function ReconciliationResultsTable({
  results,
  total,
  isLoading,
  error,
  filters,
  marketplaces,
  page,
  pageSize,
  onFiltersChange,
  onPrevious,
  onNext,
  onRefresh,
  onOpen,
}: ResultsTableProps) {
  const firstRow = total === 0 ? 0 : page * pageSize + 1
  const lastRow = page * pageSize + results.length
  const hasNext = lastRow < total

  return (
    <div className="card">
      <div className="card__row">
        <h2 className="card__title">Results</h2>
        <button
          className="button button--ghost"
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
        >
          {isLoading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div className="toolbar toolbar--wrap">
        <label className="toolbar__field">
          <span className="field__label">Status</span>
          <select
            className="field__input"
            value={filters.status}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                status: event.target.value as ReconciliationStatus | '',
              })
            }
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="toolbar__field">
          <span className="field__label">Marketplace</span>
          <select
            className="field__input"
            value={filters.marketplace}
            onChange={(event) => onFiltersChange({ ...filters, marketplace: event.target.value })}
          >
            <option value="">All marketplaces</option>
            {marketplaces.map((marketplace) => (
              <option key={marketplace} value={marketplace}>
                {marketplace}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error !== null && (
        <p className="alert alert--danger" role="alert">
          {error}
        </p>
      )}

      {isLoading && results.length === 0 ? (
        <p className="empty-state" role="status">
          Loading reconciliation results…
        </p>
      ) : results.length === 0 ? (
        <p className="empty-state">
          No reconciliation results for this filter. Import orders and settlements, then run
          reconciliation.
        </p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Order reference</th>
                <th scope="col">Marketplace</th>
                <th scope="col" className="data-table__num">
                  Expected
                </th>
                <th scope="col" className="data-table__num">
                  Received
                </th>
                <th scope="col" className="data-table__num">
                  Difference
                </th>
                <th scope="col">Status</th>
                <th scope="col">Issues</th>
                <th scope="col" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {results.map((result) => {
                const meta = statusMeta(result.status)
                return (
                  <tr key={result.id}>
                    <td className="data-table__strong">{referenceOf(result)}</td>
                    <td>{marketplaceOf(result)}</td>
                    <td className="data-table__num">
                      {formatMoney(result.expected_amount, result.currency)}
                    </td>
                    <td className="data-table__num">
                      {formatMoney(result.actual_amount, result.currency)}
                    </td>
                    <td className="data-table__num">
                      {formatSignedMoney(result.difference_amount, result.currency)}
                    </td>
                    <td>
                      <span className={`tag tag--${meta.tone}`} title={meta.hint}>
                        {meta.label}
                      </span>
                    </td>
                    <td>
                      {result.issues.length === 0 ? (
                        <span className="muted">—</span>
                      ) : (
                        <span className="issue-tags">
                          {result.issues.map((issue, index) => (
                            <span
                              key={`${issue.code}-${index}`}
                              className={`tag tag--${issueTone(issue.code)}`}
                              title={issue.message}
                            >
                              {issueLabel(issue.code)}
                            </span>
                          ))}
                        </span>
                      )}
                    </td>
                    <td>
                      <button
                        className="button button--ghost"
                        type="button"
                        onClick={() => onOpen(result.id)}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {(page > 0 || hasNext) && (
        <div className="pagination">
          <button
            className="button button--ghost"
            type="button"
            disabled={page === 0 || isLoading}
            onClick={onPrevious}
          >
            Previous
          </button>
          <span className="pagination__label">
            {firstRow}–{lastRow} of {total}
          </span>
          <button
            className="button button--ghost"
            type="button"
            disabled={!hasNext || isLoading}
            onClick={onNext}
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
