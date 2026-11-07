import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api/client'
import { listImports, listSourceTypes } from '../api/imports'
import type { ImportBatch, SourceType } from '../api/imports'
import { useAuth } from '../auth/AuthContext'
import { canManageImports } from '../config/roles'
import { ImportDetail } from './imports/ImportDetail'
import { ImportHistory } from './imports/ImportHistory'
import type { ImportFilters } from './imports/ImportHistory'
import { ImportUploadForm } from './imports/ImportUploadForm'

const PAGE_SIZE = 20

const EMPTY_FILTERS: ImportFilters = { status: '', sourceType: '', partner: '' }

function listErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return 'Your session has expired. Please sign in again.'
  }
  return 'Could not load the import history. Please try again.'
}

export function Imports() {
  const { user } = useAuth()
  const canManage = user !== null && canManageImports(user.role.name)

  const [sourceTypes, setSourceTypes] = useState<SourceType[]>([])
  const [batches, setBatches] = useState<ImportBatch[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<ImportFilters>(EMPTY_FILTERS)
  const [page, setPage] = useState(0)
  const [reloadToken, setReloadToken] = useState(0)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  // Source types power both the upload picker and the history filter.
  useEffect(() => {
    let cancelled = false
    listSourceTypes()
      .then((types) => {
        if (!cancelled) setSourceTypes(types)
      })
      .catch(() => {
        // The picker falls back to an empty list; the history still works.
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)

    listImports({
      status: filters.status,
      sourceType: filters.sourceType,
      partner: filters.partner.trim(),
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    })
      .then((data) => {
        if (!cancelled) setBatches(data)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(listErrorMessage(err))
          setBatches([])
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [filters, page, reloadToken])

  const refresh = useCallback(() => {
    setReloadToken((token) => token + 1)
  }, [])

  const handleFiltersChange = useCallback((next: ImportFilters) => {
    setFilters(next)
    setPage(0)
  }, [])

  const handleUploaded = useCallback((batch: ImportBatch) => {
    setReloadToken((token) => token + 1)
    setSelectedId(batch.id)
  }, [])

  const handleChanged = useCallback((batch: ImportBatch) => {
    setBatches((current) =>
      current.map((item) => (item.id === batch.id ? batch : item)),
    )
  }, [])

  const partnerSuggestions = useMemo(() => {
    const names = new Set<string>()
    for (const batch of batches) {
      if (batch.partner !== null && batch.partner !== '') names.add(batch.partner)
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b))
  }, [batches])

  if (selectedId !== null) {
    return (
      <ImportDetail
        batchId={selectedId}
        canManage={canManage}
        onBack={() => {
          setSelectedId(null)
          refresh()
        }}
        onChanged={handleChanged}
      />
    )
  }

  return (
    <section className="page page--wide">
      <header className="page__header">
        <h1 className="page__title">Imports</h1>
        <p className="page__subtitle">
          Upload orders, settlements and remittance files, review how the columns map to the
          canonical fields, then process them.
        </p>
      </header>

      <ImportUploadForm
        canManage={canManage}
        sourceTypes={sourceTypes}
        partnerSuggestions={partnerSuggestions}
        onUploaded={handleUploaded}
      />

      <ImportHistory
        batches={batches}
        isLoading={isLoading}
        error={error}
        filters={filters}
        sourceTypes={sourceTypes}
        page={page}
        pageSize={PAGE_SIZE}
        hasNext={batches.length === PAGE_SIZE}
        onFiltersChange={handleFiltersChange}
        onPrevious={() => setPage((current) => Math.max(0, current - 1))}
        onNext={() => setPage((current) => current + 1)}
        onRefresh={refresh}
        onOpen={setSelectedId}
      />
    </section>
  )
}
