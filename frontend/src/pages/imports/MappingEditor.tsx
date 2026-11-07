import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '../../api/client'
import type { ImportPreview } from '../../api/imports'
import { confidenceLabel } from './format'

interface MappingEditorProps {
  preview: ImportPreview
  canManage: boolean
  /** Persist the mapping without processing. */
  onSave: (mapping: Record<string, string | null>, saveForPartner: boolean) => Promise<void>
  /** Persist the mapping and immediately process the batch. */
  onApproveAndProcess: (
    mapping: Record<string, string | null>,
    saveForPartner: boolean,
  ) => Promise<void>
}

function initialMapping(preview: ImportPreview): Record<string, string> {
  const result: Record<string, string> = {}
  for (const field of preview.fields) {
    const saved = preview.batch.column_mapping?.[field.name] ?? field.mapped_header ?? ''
    result[field.name] = saved ?? ''
  }
  return result
}

function toPayload(mapping: Record<string, string>): Record<string, string | null> {
  const payload: Record<string, string | null> = {}
  for (const [name, header] of Object.entries(mapping)) {
    payload[name] = header === '' ? null : header
  }
  return payload
}

function actionError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return 'You do not have permission to change this mapping.'
    if (error.status === 409) return error.message
    if (error.status === 422) return error.message
    return error.message
  }
  return 'Something went wrong. Please try again.'
}

export function MappingEditor({
  preview,
  canManage,
  onSave,
  onApproveAndProcess,
}: MappingEditorProps) {
  const [mapping, setMapping] = useState<Record<string, string>>(() => initialMapping(preview))
  const [saveForPartner, setSaveForPartner] = useState(false)
  const [busy, setBusy] = useState<'save' | 'process' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    setMapping(initialMapping(preview))
    setError(null)
    setNotice(null)
  }, [preview])

  const missingRequired = useMemo(
    () => preview.fields.filter((field) => field.required && mapping[field.name] === ''),
    [preview.fields, mapping],
  )
  const isComplete = missingRequired.length === 0

  function update(fieldName: string, header: string) {
    setMapping((current) => ({ ...current, [fieldName]: header }))
    setNotice(null)
  }

  async function run(kind: 'save' | 'process') {
    setBusy(kind)
    setError(null)
    setNotice(null)
    try {
      if (kind === 'save') {
        await onSave(toPayload(mapping), saveForPartner)
        setNotice('Mapping saved.')
      } else {
        await onApproveAndProcess(toPayload(mapping), saveForPartner)
        setNotice('Mapping approved and the file is being processed.')
      }
    } catch (err) {
      setError(actionError(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="card">
      <h2 className="card__title">Column mapping</h2>
      <p className="card__hint">
        Match each canonical field to a column from the file. Fields marked
        <span className="required-dot" aria-hidden="true"> *</span> are required before the file can
        be processed.
      </p>

      {preview.missing_required_fields.length > 0 && preview.batch.column_mapping === null && (
        <p className="alert alert--warning">
          The importer could not match every required field automatically. Set the remaining
          columns below.
        </p>
      )}

      <div className="mapping-list">
        {preview.fields.map((field) => {
          const confidence = confidenceLabel(field.confidence)
          return (
            <div className="mapping-row" key={field.name}>
              <div className="mapping-row__field">
                <span className="mapping-row__label">
                  {field.label}
                  {field.required && (
                    <span className="required-dot" title="Required">
                      {' '}
                      *
                    </span>
                  )}
                </span>
                <span className="mapping-row__meta">
                  <code>{field.name}</code>
                  {confidence !== null && mapping[field.name] !== '' && (
                    <span className={`tag tag--${field.confidence ?? 'manual'}`}>{confidence}</span>
                  )}
                </span>
                {field.mapped_header !== null && mapping[field.name] === field.mapped_header && (
                  <span className="mapping-row__suggested">
                    Suggested: {field.mapped_header}
                  </span>
                )}
              </div>

              <label className="mapping-row__control">
                <span className="visually-hidden">Source column for {field.label}</span>
                <select
                  className="field__input"
                  value={mapping[field.name] ?? ''}
                  disabled={!canManage || busy !== null}
                  onChange={(event) => update(field.name, event.target.value)}
                >
                  <option value="">— Not mapped —</option>
                  {preview.headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )
        })}
      </div>

      {preview.unmapped_headers.length > 0 && (
        <p className="mapping-note">
          Not used by this source type: {preview.unmapped_headers.join(', ')}
        </p>
      )}

      {canManage && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={saveForPartner}
            disabled={busy !== null}
            onChange={(event) => setSaveForPartner(event.target.checked)}
          />
          <span>Remember this mapping for future uploads from this partner</span>
        </label>
      )}

      {error !== null && (
        <p className="alert alert--danger" role="alert">
          {error}
        </p>
      )}
      {notice !== null && (
        <p className="alert alert--success" role="status">
          {notice}
        </p>
      )}

      {!isComplete && (
        <p className="alert alert--warning">
          Still required: {missingRequired.map((field) => field.label).join(', ')}
        </p>
      )}

      {canManage && (
        <div className="card__actions">
          <button
            className="button"
            type="button"
            disabled={busy !== null}
            onClick={() => run('save')}
          >
            {busy === 'save' ? 'Saving…' : 'Save mapping'}
          </button>
          <button
            className="button button--primary"
            type="button"
            disabled={busy !== null || !isComplete}
            onClick={() => run('process')}
          >
            {busy === 'process' ? 'Processing…' : 'Approve & process'}
          </button>
        </div>
      )}
    </div>
  )
}
