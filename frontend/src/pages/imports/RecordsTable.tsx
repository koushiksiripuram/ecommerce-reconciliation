import { Fragment, useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import { listImportRecords } from '../../api/imports'
import type { ImportRecord } from '../../api/imports'

const PAGE_SIZE = 25

interface RecordsTableProps {
  batchId: number
  /** Bump this to force a reload (e.g. after processing finishes). */
  reloadToken: number
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function recordErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Could not load rows for this import.'
}

export function RecordsTable({ batchId, reloadToken }: RecordsTableProps) {
  const [records, setRecords] = useState<ImportRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [onlyInvalid, setOnlyInvalid] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const result = await listImportRecords(batchId, {
        onlyInvalid,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      setRecords(result.rows)
      setTotal(result.total)
    } catch (err) {
      setError(recordErrorMessage(err))
      setRecords([])
      setTotal(0)
    } finally {
      setIsLoading(false)
    }
  }, [batchId, onlyInvalid, page])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  function toggleExpanded(rowNumber: number) {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(rowNumber)) next.delete(rowNumber)
      else next.add(rowNumber)
      return next
    })
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="card">
      <div className="card__row">
        <h2 className="card__title">Rows</h2>
        <span className="card__label">{total.toLocaleString()} total</span>
      </div>

      <div className="toolbar">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={onlyInvalid}
            onChange={(event) => {
              setOnlyInvalid(event.target.checked)
              setPage(0)
            }}
          />
          <span>Only rows with errors</span>
        </label>
      </div>

      {error !== null && (
        <p className="alert alert--danger" role="alert">
          {error}
        </p>
      )}

      {isLoading ? (
        <p className="empty-state" role="status">
          Loading rows…
        </p>
      ) : records.length === 0 ? (
        <p className="empty-state">
          {onlyInvalid ? 'No rows with errors. Everything validated cleanly.' : 'No rows stored yet.'}
        </p>
      ) : (
        <div className="table-scroll">
          <table className="data-table data-table--records">
            <thead>
              <tr>
                <th scope="col" className="data-table__index">
                  Row
                </th>
                <th scope="col">Reference</th>
                <th scope="col">Status</th>
                <th scope="col">Errors</th>
                <th scope="col" aria-label="Details" />
              </tr>
            </thead>
            <tbody>
              {records.map((record) => {
                const isOpen = expanded.has(record.row_number)
                return (
                  <Fragment key={record.row_number}>
                    <tr>
                      <td className="data-table__index">{record.row_number}</td>
                      <td>{record.external_reference ?? '—'}</td>
                      <td>
                        <span
                          className={
                            record.is_valid ? 'tag tag--valid' : 'tag tag--invalid'
                          }
                        >
                          {record.is_valid ? 'Valid' : 'Invalid'}
                        </span>
                      </td>
                      <td>
                        {record.errors.length === 0 ? (
                          <span className="muted">—</span>
                        ) : (
                          <ul className="error-list">
                            {record.errors.map((rowError) => (
                              <li key={`${rowError.field}-${rowError.code}`}>
                                <code>{rowError.field}</code> {rowError.message}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="link-button"
                          aria-expanded={isOpen}
                          onClick={() => toggleExpanded(record.row_number)}
                        >
                          {isOpen ? 'Hide' : 'View'}
                        </button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="data-table__details">
                        <td colSpan={5}>
                          <div className="details-grid">
                            <div>
                              <h3 className="details-grid__title">Raw values</h3>
                              <dl className="kv">
                                {Object.entries(record.raw_data).map(([key, value]) => (
                                  <div className="kv__row" key={key}>
                                    <dt>{key}</dt>
                                    <dd>{formatValue(value)}</dd>
                                  </div>
                                ))}
                              </dl>
                            </div>
                            <div>
                              <h3 className="details-grid__title">Normalised values</h3>
                              {record.normalized_data === null ? (
                                <p className="muted">Not normalised (row failed validation).</p>
                              ) : (
                                <dl className="kv">
                                  {Object.entries(record.normalized_data).map(([key, value]) => (
                                    <div className="kv__row" key={key}>
                                      <dt>{key}</dt>
                                      <dd>{formatValue(value)}</dd>
                                    </div>
                                  ))}
                                </dl>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {pageCount > 1 && (
        <div className="pagination">
          <button
            className="button button--ghost"
            type="button"
            disabled={page === 0 || isLoading}
            onClick={() => setPage((current) => Math.max(0, current - 1))}
          >
            Previous
          </button>
          <span className="pagination__label">
            Page {page + 1} of {pageCount}
          </span>
          <button
            className="button button--ghost"
            type="button"
            disabled={page + 1 >= pageCount || isLoading}
            onClick={() => setPage((current) => current + 1)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
