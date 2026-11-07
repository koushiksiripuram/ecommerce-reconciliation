/**
 * Typed client for the backend import endpoints.
 *
 * Every function maps 1:1 onto a route in `backend/app/api/routes/imports.py`
 * and mirrors the Pydantic schemas in `backend/app/schemas/imports.py`, so the
 * UI stays honest about the real API contract.
 */

import { API_BASE_URL, ApiError, apiErrorMessage, request } from './client'

/** Lifecycle states a batch can be in. Mirrors `ImportBatchStatus`. */
export type ImportBatchStatus =
  | 'uploaded'
  | 'mapping_required'
  | 'processing'
  | 'completed'
  | 'failed'

export interface ImportBatch {
  id: number
  source_type: string
  source_label: string
  partner: string | null
  status: ImportBatchStatus
  original_filename: string | null
  content_type: string | null
  size_bytes: number | null
  total_rows: number
  processed_rows: number
  failed_rows: number
  column_mapping: Record<string, string> | null
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  created_at: string | null
}

export interface ImportField {
  name: string
  label: string
  kind: string
  required: boolean
  mapped_header: string | null
  confidence: string | null
}

export interface ImportPreview {
  batch: ImportBatch
  headers: string[]
  rows: Array<Record<string, string>>
  fields: ImportField[]
  unmapped_headers: string[]
  missing_required_fields: string[]
  mapping_complete: boolean
}

export interface SourceType {
  value: string
  label: string
  required_fields: string[]
}

export interface ImportRowError {
  field: string
  code: string
  message: string
}

export interface ImportRecord {
  row_number: number
  external_reference: string | null
  is_valid: boolean
  raw_data: Record<string, unknown>
  normalized_data: Record<string, unknown> | null
  errors: ImportRowError[]
}

export interface ImportRecordPage {
  total: number
  returned: number
  rows: ImportRecord[]
}

export interface ImportListParams {
  status?: ImportBatchStatus | ''
  sourceType?: string
  partner?: string
  limit?: number
  offset?: number
}

export interface RecordListParams {
  onlyInvalid?: boolean
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

/** List the source types the backend accepts (for the upload form). */
export function listSourceTypes(): Promise<SourceType[]> {
  return request<SourceType[]>('/imports/source-types')
}

/** List recent import batches, newest first. */
export function listImports(params: ImportListParams = {}): Promise<ImportBatch[]> {
  return request<ImportBatch[]>(
    `/imports${toQuery({
      status: params.status,
      source_type: params.sourceType,
      partner: params.partner,
      limit: params.limit,
      offset: params.offset,
    })}`,
  )
}

/** Fetch a single batch. */
export function getImport(batchId: number): Promise<ImportBatch> {
  return request<ImportBatch>(`/imports/${batchId}`)
}

/** Fetch the parsed columns, sample rows and current mapping for a batch. */
export function getImportPreview(batchId: number): Promise<ImportPreview> {
  return request<ImportPreview>(`/imports/${batchId}/preview`)
}

/** Replace a batch's mapping, optionally saving it as the partner default. */
export function updateImportMapping(
  batchId: number,
  mapping: Record<string, string | null>,
  saveForPartner: boolean,
): Promise<ImportBatch> {
  return request<ImportBatch>(`/imports/${batchId}/mapping`, {
    method: 'PUT',
    body: JSON.stringify({ mapping, save_for_partner: saveForPartner }),
  })
}

/** Project every row of a ready batch onto the canonical fields. */
export function processImport(batchId: number): Promise<ImportBatch> {
  return request<ImportBatch>(`/imports/${batchId}/process`, { method: 'POST' })
}

/** Page through the rows stored for a processed batch. */
export function listImportRecords(
  batchId: number,
  params: RecordListParams = {},
): Promise<ImportRecordPage> {
  return request<ImportRecordPage>(
    `/imports/${batchId}/records${toQuery({
      only_invalid: params.onlyInvalid,
      limit: params.limit,
      offset: params.offset,
    })}`,
  )
}

export interface UploadImportInput {
  file: File
  sourceType: string
  partner: string
  onProgress?: (percent: number) => void
}

/**
 * Upload a file as multipart/form-data.
 *
 * Uses `XMLHttpRequest` rather than `fetch` because the browser only reports
 * upload progress through XHR events.
 */
export function uploadImport(input: UploadImportInput): Promise<ImportBatch> {
  const { file, sourceType, partner, onProgress } = input

  return new Promise<ImportBatch>((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    form.append('source_type', sourceType)
    form.append('partner', partner)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/imports`)
    xhr.withCredentials = true

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }

    xhr.onload = () => {
      const parsed: unknown = xhr.responseText ? safeJson(xhr.responseText) : undefined
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(parsed as ImportBatch)
        return
      }
      reject(new ApiError(xhr.status, detailMessage(parsed, xhr.status)))
    }

    xhr.onerror = () => {
      reject(new ApiError(0, 'Network error while uploading the file. Please try again.'))
    }

    xhr.send(form)
  })
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

function detailMessage(payload: unknown, status: number): string {
  if (payload !== null && typeof payload === 'object' && 'detail' in payload) {
    return apiErrorMessage((payload as { detail: unknown }).detail, status)
  }
  return apiErrorMessage(undefined, status)
}
