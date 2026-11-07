import { useCallback, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { uploadImport } from '../../api/imports'
import type { ImportBatch, SourceType } from '../../api/imports'

const ACCEPT = '.csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

interface UploadFormProps {
  /** Operators may upload; everyone else sees a read-only notice. */
  canManage: boolean
  /** Source types from the API, used to populate the picker. */
  sourceTypes: SourceType[]
  /** Partner names already used, offered as suggestions. */
  partnerSuggestions: string[]
  /** Ask the parent to refresh the history when a batch is created. */
  onUploaded: (batch: ImportBatch) => void
}

function uploadErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 0:
        return error.message
      case 401:
        return 'Your session has expired. Please sign in again.'
      case 403:
        return 'You do not have permission to upload imports.'
      case 413:
        return 'The file is larger than the upload limit.'
      case 415:
        return 'Only CSV and XLSX files are supported.'
      case 409:
        return error.message
      default:
        return error.message
    }
  }
  return 'Upload failed. Please try again.'
}

export function ImportUploadForm({
  canManage,
  sourceTypes,
  partnerSuggestions,
  onUploaded,
}: UploadFormProps) {
  const [sourceType, setSourceType] = useState('')
  const [partner, setPartner] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [progress, setProgress] = useState(0)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Default the source-type picker once the list arrives.
  const effectiveSourceType = sourceType || sourceTypes[0]?.value || ''

  const reset = useCallback(() => {
    setFile(null)
    setProgress(0)
    if (inputRef.current) inputRef.current.value = ''
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (file === null || effectiveSourceType === '' || partner.trim() === '') return

    setError(null)
    setSuccess(null)
    setIsUploading(true)
    setProgress(0)

    try {
      const batch = await uploadImport({
        file,
        sourceType: effectiveSourceType,
        partner: partner.trim(),
        onProgress: setProgress,
      })
      setSuccess(`Uploaded ${batch.original_filename ?? 'file'}.`)
      reset()
      setPartner('')
      onUploaded(batch)
    } catch (err) {
      setError(uploadErrorMessage(err))
    } finally {
      setIsUploading(false)
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null)
    setError(null)
    setSuccess(null)
  }

  if (!canManage) {
    return (
      <div className="card">
        <h2 className="card__title">New import</h2>
        <p className="card__hint">
          Your role can view imports but not upload or change them. Ask a Finance
          Executive or Co-Founder to run the import.
        </p>
      </div>
    )
  }

  const canSubmit = file !== null && effectiveSourceType !== '' && partner.trim() !== '' && !isUploading

  return (
    <form className="card import-upload" onSubmit={handleSubmit}>
      <h2 className="card__title">New import</h2>
      <p className="card__hint">
        Upload a CSV or XLSX file. You will review the column mapping before anything is
        processed.
      </p>

      <div className="form-grid">
        <label className="field">
          <span className="field__label">Source type</span>
          <select
            className="field__input"
            value={effectiveSourceType}
            onChange={(event) => setSourceType(event.target.value)}
            disabled={sourceTypes.length === 0 || isUploading}
            required
          >
            {sourceTypes.length === 0 && <option value="">Loading…</option>}
            {sourceTypes.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="field__label">Partner</span>
          <input
            className="field__input"
            type="text"
            value={partner}
            list="import-partners"
            placeholder="e.g. amazon"
            onChange={(event) => setPartner(event.target.value)}
            disabled={isUploading}
            required
          />
          <datalist id="import-partners">
            {partnerSuggestions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </label>

        <label className="field field--wide">
          <span className="field__label">File</span>
          <input
            ref={inputRef}
            className="field__input"
            type="file"
            accept={ACCEPT}
            onChange={handleFileChange}
            disabled={isUploading}
            required
          />
        </label>
      </div>

      {isUploading && (
        <div className="progress" role="status" aria-live="polite">
          <div className="progress__bar" style={{ width: `${progress}%` }} />
          <span className="progress__label">Uploading… {progress}%</span>
        </div>
      )}

      {error !== null && (
        <p className="alert alert--danger" role="alert">
          {error}
        </p>
      )}

      {success !== null && (
        <p className="alert alert--success" role="status">
          {success}
        </p>
      )}

      <div className="card__actions">
        <button className="button button--primary" type="submit" disabled={!canSubmit}>
          {isUploading ? 'Uploading…' : 'Upload file'}
        </button>
      </div>
    </form>
  )
}
