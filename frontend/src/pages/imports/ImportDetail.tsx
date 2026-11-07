import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import {
  getImportPreview,
  processImport,
  updateImportMapping,
} from '../../api/imports'
import type { ImportBatch, ImportPreview } from '../../api/imports'
import { MappingEditor } from './MappingEditor'
import { PreviewTable } from './PreviewTable'
import { RecordsTable } from './RecordsTable'
import { formatBytes, formatDateTime, formatNumber, statusMeta } from './format'

interface ImportDetailProps {
  batchId: number
  canManage: boolean
  onBack: () => void
  /** Notify the parent so the history list can refresh its row. */
  onChanged: (batch: ImportBatch) => void
}

function loadErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return 'This import no longer exists.'
  }
  return 'Could not load this import. Please try again.'
}

export function ImportDetail({ batchId, canManage, onBack, onChanged }: ImportDetailProps) {
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [recordsToken, setRecordsToken] = useState(0)

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)

    getImportPreview(batchId)
      .then((data) => {
        if (!cancelled) setPreview(data)
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
  }, [batchId, reloadToken])

  const handleSave = useCallback(
    async (mapping: Record<string, string | null>, saveForPartner: boolean) => {
      const batch = await updateImportMapping(batchId, mapping, saveForPartner)
      onChanged(batch)
      setReloadToken((token) => token + 1)
    },
    [batchId, onChanged],
  )

  const handleApproveAndProcess = useCallback(
    async (mapping: Record<string, string | null>, saveForPartner: boolean) => {
      await updateImportMapping(batchId, mapping, saveForPartner)
      const batch = await processImport(batchId)
      onChanged(batch)
      setRecordsToken((token) => token + 1)
      setReloadToken((token) => token + 1)
    },
    [batchId, onChanged],
  )

  if (isLoading && preview === null) {
    return (
      <section className="page">
        <p className="empty-state" role="status">
          Loading import…
        </p>
      </section>
    )
  }

  if (error !== null || preview === null) {
    return (
      <section className="page">
        <button className="link-button" type="button" onClick={onBack}>
          ← Back to imports
        </button>
        <p className="alert alert--danger" role="alert">
          {error ?? 'Import unavailable.'}
        </p>
      </section>
    )
  }

  const batch = preview.batch
  const meta = statusMeta(batch.status)
  const isSettled = batch.status === 'completed' || batch.status === 'failed'

  return (
    <section className="page page--wide">
      <div className="detail-header">
        <button className="link-button" type="button" onClick={onBack}>
          ← Back to imports
        </button>
        <div className="detail-header__title">
          <h1 className="page__title">{batch.original_filename ?? `Import #${batch.id}`}</h1>
          <span className={`tag tag--${meta.tone}`} title={meta.hint}>
            {meta.label}
          </span>
        </div>
        <p className="page__subtitle">
          {batch.source_label} · {batch.partner ?? 'unknown partner'}
        </p>
      </div>

      {batch.error_message !== null && (
        <p className="alert alert--danger" role="alert">
          {batch.error_message}
        </p>
      )}

      <div className="summary-grid">
        <div className="summary-tile">
          <span className="summary-tile__label">Total rows</span>
          <span className="summary-tile__value">{formatNumber(batch.total_rows)}</span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">Processed</span>
          <span className="summary-tile__value">{formatNumber(batch.processed_rows)}</span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">Failed</span>
          <span className="summary-tile__value">{formatNumber(batch.failed_rows)}</span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">Size</span>
          <span className="summary-tile__value">{formatBytes(batch.size_bytes)}</span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">Uploaded</span>
          <span className="summary-tile__value summary-tile__value--small">
            {formatDateTime(batch.created_at)}
          </span>
        </div>
        <div className="summary-tile">
          <span className="summary-tile__label">Completed</span>
          <span className="summary-tile__value summary-tile__value--small">
            {formatDateTime(batch.completed_at)}
          </span>
        </div>
      </div>

      {isSettled ? (
        <>
          <MappedColumnsList preview={preview} />
          <RecordsTable batchId={batchId} reloadToken={recordsToken} />
        </>
      ) : (
        <>
          <MappingEditor
            preview={preview}
            canManage={canManage}
            onSave={handleSave}
            onApproveAndProcess={handleApproveAndProcess}
          />
          <PreviewTable headers={preview.headers} rows={preview.rows} />
        </>
      )}
    </section>
  )
}

/** Compact read-only view of the approved mapping for a settled batch. */
function MappedColumnsList({ preview }: { preview: ImportPreview }) {
  return (
    <div className="card">
      <h2 className="card__title">Approved mapping</h2>
      <dl className="kv">
        {preview.fields
          .filter((field) => field.mapped_header !== null)
          .map((field) => (
            <div className="kv__row" key={field.name}>
              <dt>{field.label}</dt>
              <dd>
                <code>{field.mapped_header}</code>
              </dd>
            </div>
          ))}
      </dl>
    </div>
  )
}
