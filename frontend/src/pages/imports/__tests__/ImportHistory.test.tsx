import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ImportBatch, SourceType } from '../../../api/imports'
import { SOURCE_TYPES, makeBatch } from '../../../test/importFixtures'
import { ImportHistory } from '../ImportHistory'
import type { ImportFilters } from '../ImportHistory'

interface SetupOverrides {
  batches?: ImportBatch[]
  isLoading?: boolean
  error?: string | null
  filters?: ImportFilters
  page?: number
  pageSize?: number
  hasNext?: boolean
}

function setup(overrides: SetupOverrides = {}) {
  const handlers = {
    onFiltersChange: vi.fn(),
    onPrevious: vi.fn(),
    onNext: vi.fn(),
    onRefresh: vi.fn(),
    onOpen: vi.fn(),
  }

  render(
    <ImportHistory
      batches={
        overrides.batches ?? [
          makeBatch({ id: 5, original_filename: 'orders-jan.csv', status: 'completed' }),
        ]
      }
      isLoading={overrides.isLoading ?? false}
      error={overrides.error ?? null}
      filters={overrides.filters ?? { status: '', sourceType: '', partner: '' }}
      sourceTypes={SOURCE_TYPES}
      page={overrides.page ?? 0}
      pageSize={overrides.pageSize ?? 20}
      hasNext={overrides.hasNext ?? false}
      {...handlers}
    />,
  )

  return handlers
}

/**
 * Wrapper that reflects filter changes back into the component the way the
 * Imports page does, so controlled inputs behave like they do in the app.
 */
function FilterHarness({
  onFiltersChange,
  sourceTypes = SOURCE_TYPES,
}: {
  onFiltersChange: (filters: ImportFilters) => void
  sourceTypes?: SourceType[]
}) {
  const [filters, setFilters] = useState<ImportFilters>({
    status: '',
    sourceType: '',
    partner: '',
  })

  return (
    <ImportHistory
      batches={[makeBatch({ id: 5, original_filename: 'orders-jan.csv', status: 'completed' })]}
      isLoading={false}
      error={null}
      filters={filters}
      sourceTypes={sourceTypes}
      page={0}
      pageSize={20}
      hasNext={false}
      onFiltersChange={(next) => {
        setFilters(next)
        onFiltersChange(next)
      }}
      onPrevious={() => {}}
      onNext={() => {}}
      onRefresh={() => {}}
      onOpen={() => {}}
    />
  )
}

describe('ImportHistory', () => {
  it('lists batches and opens one', async () => {
    const user = userEvent.setup()
    const { onOpen } = setup()

    expect(screen.getByText('orders-jan.csv')).toBeInTheDocument()
    expect(screen.getByText('Completed', { selector: 'span' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Open' }))
    expect(onOpen).toHaveBeenCalledWith(5)
  })

  it('reports filter changes', async () => {
    const user = userEvent.setup()
    const onFiltersChange = vi.fn()
    render(<FilterHarness onFiltersChange={onFiltersChange} />)

    await user.selectOptions(screen.getByLabelText('Status'), 'completed')
    expect(onFiltersChange).toHaveBeenLastCalledWith({
      status: 'completed',
      sourceType: '',
      partner: '',
    })

    await user.selectOptions(screen.getByLabelText('Source type'), 'settlements')
    expect(onFiltersChange).toHaveBeenLastCalledWith({
      status: 'completed',
      sourceType: 'settlements',
      partner: '',
    })

    await user.type(screen.getByLabelText('Partner'), 'flip')
    expect(onFiltersChange).toHaveBeenLastCalledWith({
      status: 'completed',
      sourceType: 'settlements',
      partner: 'flip',
    })
  })

  it('shows an empty state when there are no imports', () => {
    setup({ batches: [] })
    expect(screen.getByText(/no imports yet/i)).toBeInTheDocument()
  })

  it('shows a loading state before the first page arrives', () => {
    setup({ batches: [], isLoading: true })
    expect(screen.getByText(/loading imports/i)).toBeInTheDocument()
  })

  it('shows an error alert when loading fails', () => {
    setup({ error: 'Could not load the import history. Please try again.' })
    expect(screen.getByRole('alert')).toHaveTextContent(/could not load the import history/i)
  })

  it('pages forward when more rows exist', async () => {
    const user = userEvent.setup()
    const { onNext } = setup({ hasNext: true })

    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(onNext).toHaveBeenCalledTimes(1)
  })

  it('enables Previous once past the first page', () => {
    setup({ page: 1, hasNext: false })
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })
})
