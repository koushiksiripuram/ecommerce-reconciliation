import type { ImportBatch, ImportBatchStatus, SourceType } from '../../api/imports'
import { formatDateTime, formatNumber, statusMeta } from './format'

const STATUS_OPTIONS: Array<{ value: ImportBatchStatus | ''; label: string }> = [
  { value: '', label: 'All statuses' },
  { value: 'uploaded', label: 'Ready' },
  { value: 'mapping_required', label: 'Mapping required' },
  { value: 'processing', label: 'Processing' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

export interface ImportFilters {
  status: ImportBatchStatus | ''
  sourceType: string
  partner: string
}

interface ImportHistoryProps {
  batches: ImportBatch[]
  isLoading: boolean
  error: string | null
  filters: ImportFilters
  sourceTypes: SourceType[]
  page: number
  pageSize: number
  hasNext: boolean
  onFiltersChange: (filters: ImportFilters) => void
  onPrevious: () => void
  onNext: () => void
  onRefresh: () => void
  onOpen: (batchId: number) => void
}

export function ImportHistory({
  batches,
  isLoading,
  error,
  filters,
  sourceTypes,
  page,
  pageSize,
  hasNext,
  onFiltersChange,
  onPrevious,
  onNext,
  onRefresh,
  onOpen,
}: ImportHistoryProps) {
  const firstRow = batches.length === 0 ? 0 : page * pageSize + 1
  const lastRow = page * pageSize + batches.length

  return (
    <div className="card">
      <div className="card__row">
        <h2 className="card__title">Import history</h2>
        <button className="button button--ghost" type="button" onClick={onRefresh} disabled={isLoading}>
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
              onFiltersChange({ ...filters, status: event.target.value as ImportBatchStatus | '' })
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
          <span className="field__label">Source type</span>
          <select
            className="field__input"
            value={filters.sourceType}
            onChange={(event) => onFiltersChange({ ...filters, sourceType: event.target.value })}
          >
            <option value="">All source types</option>
            {sourceTypes.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </label>

        <label className="toolbar__field">
          <span className="field__label">Partner</span>
          <input
            className="field__input"
            type="search"
            value={filters.partner}
            placeholder="Any partner"
            onChange={(event) => onFiltersChange({ ...filters, partner: event.target.value })}
          />
        </label>
      </div>

      {error !== null && (
        <p className="alert alert--danger" role="alert">
          {error}
        </p>
      )}

      {isLoading && batches.length === 0 ? (
        <p className="empty-state" role="status">
          Loading imports…
        </p>
      ) : batches.length === 0 ? (
        <p className="empty-state">
          No imports yet. Upload a file above to create the first one.
        </p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">File</th>
                <th scope="col">Source</th>
                <th scope="col">Partner</th>
                <th scope="col" className="data-table__num">
                  Rows
                </th>
                <th scope="col">Status</th>
                <th scope="col">Uploaded</th>
                <th scope="col" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {batches.map((batch) => {
                const meta = statusMeta(batch.status)
                return (
                  <tr key={batch.id}>
                    <td className="data-table__strong">{batch.original_filename ?? `Import #${batch.id}`}</td>
                    <td>{batch.source_label}</td>
                    <td>{batch.partner ?? '—'}</td>
                    <td className="data-table__num">{formatNumber(batch.total_rows)}</td>
                    <td>
                      <span className={`tag tag--${meta.tone}`} title={meta.hint}>
                        {meta.label}
                      </span>
                    </td>
                    <td>{formatDateTime(batch.created_at)}</td>
                    <td>
                      <button
                        className="button button--ghost"
                        type="button"
                        onClick={() => onOpen(batch.id)}
                      >
                        Open
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
