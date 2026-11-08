import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ReconciliationResult } from '../../../api/reconciliation'
import { makeResult } from '../../../test/reconciliationFixtures'
import { ReconciliationResultsTable } from '../ReconciliationResultsTable'
import type { ReconciliationFilters } from '../ReconciliationResultsTable'

interface SetupOverrides {
  results?: ReconciliationResult[]
  total?: number
  isLoading?: boolean
  error?: string | null
  filters?: ReconciliationFilters
  marketplaces?: string[]
  page?: number
  pageSize?: number
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
    <ReconciliationResultsTable
      results={overrides.results ?? [makeResult()]}
      total={overrides.total ?? 1}
      isLoading={overrides.isLoading ?? false}
      error={overrides.error ?? null}
      filters={overrides.filters ?? { status: '', marketplace: '' }}
      marketplaces={overrides.marketplaces ?? ['amazon']}
      page={overrides.page ?? 0}
      pageSize={overrides.pageSize ?? 20}
      {...handlers}
    />,
  )

  return handlers
}

/**
 * Wrapper that reflects filter changes back into the component the way the
 * Reconciliation page does, so the controlled selects behave like they do in
 * the app.
 */
function FilterHarness({
  onFiltersChange,
}: {
  onFiltersChange: (filters: ReconciliationFilters) => void
}) {
  const [filters, setFilters] = useState<ReconciliationFilters>({ status: '', marketplace: '' })

  return (
    <ReconciliationResultsTable
      results={[makeResult()]}
      total={1}
      isLoading={false}
      error={null}
      filters={filters}
      marketplaces={['amazon', 'flipkart']}
      page={0}
      pageSize={20}
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

describe('ReconciliationResultsTable', () => {
  it('lists a line with its amounts and status, and opens it', async () => {
    const user = userEvent.setup()
    const { onOpen } = setup({
      results: [
        makeResult({
          id: 10,
          expected_amount: '100.00',
          actual_amount: '75.00',
          difference_amount: '-25.00',
          status: 'short_paid',
        }),
      ],
    })

    expect(screen.getByRole('cell', { name: 'A-1' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'amazon' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'INR 100.00' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'INR 75.00' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '-INR 25.00' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Short paid' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'View' }))
    expect(onOpen).toHaveBeenCalledWith(10)
  })

  it('falls back to the settlement reference when no order was matched', () => {
    setup({
      results: [
        makeResult({
          id: 11,
          status: 'missing_in_orders',
          order: null,
          settlement_record: {
            id: 2,
            marketplace: 'flipkart',
            external_reference: 'TXN-9',
            order_reference: null,
            settlement_date: null,
            net_amount: '80.00',
            import_batch_id: 8,
          },
        }),
      ],
    })

    expect(screen.getByRole('cell', { name: 'TXN-9' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'flipkart' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Missing in orders' })).toBeInTheDocument()
  })

  it('shows a pill for each detected issue', () => {
    setup({
      results: [
        makeResult({
          issues: [
            {
              code: 'freight_overcharged',
              message: 'Freight charged above the rate card.',
              amount: '40.00',
              references: [],
              settlement_record_ids: [],
            },
          ],
        }),
      ],
    })

    expect(screen.getByText('Freight overcharged')).toBeInTheDocument()
  })

  it('reports filter changes', async () => {
    const user = userEvent.setup()
    const onFiltersChange = vi.fn()
    render(<FilterHarness onFiltersChange={onFiltersChange} />)

    await user.selectOptions(screen.getByLabelText('Status'), 'short_paid')
    expect(onFiltersChange).toHaveBeenLastCalledWith({ status: 'short_paid', marketplace: '' })

    await user.selectOptions(screen.getByLabelText('Marketplace'), 'flipkart')
    expect(onFiltersChange).toHaveBeenLastCalledWith({ status: 'short_paid', marketplace: 'flipkart' })
  })

  it('shows an empty state when there are no results', () => {
    setup({ results: [], total: 0 })
    expect(screen.getByText(/no reconciliation results for this filter/i)).toBeInTheDocument()
  })

  it('shows a loading state before the first page arrives', () => {
    setup({ results: [], total: 0, isLoading: true })
    expect(screen.getByText(/loading reconciliation results/i)).toBeInTheDocument()
  })

  it('shows an error alert when loading fails', () => {
    setup({ results: [], total: 0, error: 'Could not load reconciliation data. Please try again.' })
    expect(screen.getByRole('alert')).toHaveTextContent(/could not load reconciliation data/i)
  })

  it('pages forward when more rows exist', async () => {
    const user = userEvent.setup()
    const { onNext } = setup({ total: 30, page: 0 })

    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(onNext).toHaveBeenCalledTimes(1)
  })

  it('enables Previous once past the first page', () => {
    setup({ total: 30, page: 1 })
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
  })
})
