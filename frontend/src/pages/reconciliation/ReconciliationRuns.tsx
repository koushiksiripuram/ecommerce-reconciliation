import type { ReconciliationRun } from '../../api/reconciliation'
import { formatDateTime, formatNumber } from './format'

interface RunsProps {
  runs: ReconciliationRun[]
  /** The run currently in scope; its row is marked and not re-selectable. */
  activeRunId: number | null
  isLoading: boolean
  error: string | null
  page: number
  pageSize: number
  hasNext: boolean
  onSelect: (run: ReconciliationRun) => void
  onPrevious: () => void
  onNext: () => void
  onRefresh: () => void
}

/**
 * The immutable run ledger: every execution, newest first, with the current run
 * flagged. Selecting a row scopes the summary and results to that run's
 * preserved snapshot, so a past conclusion stays reproducible.
 */
export function ReconciliationRuns({
  runs,
  activeRunId,
  isLoading,
  error,
  page,
  pageSize,
  hasNext,
  onSelect,
  onPrevious,
  onNext,
  onRefresh,
}: RunsProps) {
  const firstRow = runs.length === 0 ? 0 : page * pageSize + 1
  const lastRow = page * pageSize + runs.length

  return (
    <div className="card">
      <div className="card__row">
        <h2 className="card__title">Run history</h2>
        <button
          className="button button--ghost"
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
        >
          {isLoading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error !== null && (
        <p className="alert alert--danger" role="alert">
          {error}
        </p>
      )}

      {isLoading && runs.length === 0 ? (
        <p className="empty-state" role="status">
          Loading run history…
        </p>
      ) : runs.length === 0 ? (
        <p className="empty-state">
          No reconciliation has run yet. Start a run once orders and settlements are imported.
        </p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Started</th>
                <th scope="col">Triggered by</th>
                <th scope="col" className="data-table__num">
                  Orders
                </th>
                <th scope="col" className="data-table__num">
                  Matched
                </th>
                <th scope="col" className="data-table__num">
                  Results
                </th>
                <th scope="col">Status</th>
                <th scope="col" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const isActive = run.id === activeRunId
                return (
                  <tr key={run.id}>
                    <td className="data-table__strong">#{run.id}</td>
                    <td>{formatDateTime(run.started_at)}</td>
                    <td>{run.triggered_by_email ?? '—'}</td>
                    <td className="data-table__num">{formatNumber(run.orders_reconciled)}</td>
                    <td className="data-table__num">{formatNumber(run.settlements_matched)}</td>
                    <td className="data-table__num">{formatNumber(run.results_created)}</td>
                    <td>
                      {run.is_current ? (
                        <span className="tag tag--success" title="The latest run. Default views read this one.">
                          Current
                        </span>
                      ) : (
                        <span
                          className="tag tag--neutral"
                          title="Superseded by a later run; preserved for audit."
                        >
                          Superseded
                        </span>
                      )}
                    </td>
                    <td>
                      {isActive ? (
                        <span className="tag tag--info">Viewing</span>
                      ) : (
                        <button
                          className="button button--ghost"
                          type="button"
                          onClick={() => onSelect(run)}
                        >
                          View
                        </button>
                      )}
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
            {firstRow}–{lastRow}
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
