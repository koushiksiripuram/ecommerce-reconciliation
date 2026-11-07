import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../api/client'
import { listImportRecords } from '../../../api/imports'
import { makeRecord } from '../../../test/importFixtures'
import { RecordsTable } from '../RecordsTable'

vi.mock('../../../api/imports', () => ({
  listImportRecords: vi.fn(),
}))

const listMock = vi.mocked(listImportRecords)

beforeEach(() => {
  vi.resetAllMocks()
})

describe('RecordsTable', () => {
  it('loads rows and shows their validation errors', async () => {
    listMock.mockResolvedValue({ total: 1, returned: 1, rows: [makeRecord()] })

    render(<RecordsTable batchId={7} reloadToken={0} />)

    expect(await screen.findByText('A-1')).toBeInTheDocument()
    expect(screen.getByText('Invalid')).toBeInTheDocument()
    expect(screen.getByText(/amount is not a number/i)).toBeInTheDocument()
    expect(listMock).toHaveBeenCalledWith(7, { onlyInvalid: false, limit: 25, offset: 0 })
  })

  it('expands a row to reveal raw and normalised values', async () => {
    const user = userEvent.setup()
    listMock.mockResolvedValue({ total: 1, returned: 1, rows: [makeRecord()] })

    render(<RecordsTable batchId={7} reloadToken={0} />)

    await user.click(await screen.findByRole('button', { name: 'View' }))

    expect(screen.getByText('Raw values')).toBeInTheDocument()
    expect(screen.getByText('abc')).toBeInTheDocument()
    expect(screen.getByText(/not normalised/i)).toBeInTheDocument()
  })

  it('refetches only invalid rows when the filter is toggled', async () => {
    const user = userEvent.setup()
    listMock.mockResolvedValue({ total: 0, returned: 0, rows: [] })

    render(<RecordsTable batchId={3} reloadToken={0} />)
    await screen.findByText(/no rows stored/i)

    await user.click(screen.getByLabelText(/only rows with errors/i))

    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith(3, { onlyInvalid: true, limit: 25, offset: 0 }),
    )
    expect(await screen.findByText(/no rows with errors/i)).toBeInTheDocument()
  })

  it('pages through rows', async () => {
    const user = userEvent.setup()
    listMock.mockResolvedValue({ total: 60, returned: 1, rows: [makeRecord({ row_number: 1 })] })

    render(<RecordsTable batchId={9} reloadToken={0} />)
    await screen.findByText('Page 1 of 3')

    await user.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith(9, { onlyInvalid: false, limit: 25, offset: 25 }),
    )
    expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument()
  })

  it('shows an error alert when loading fails', async () => {
    listMock.mockRejectedValue(new ApiError(404, 'This import no longer exists.'))

    render(<RecordsTable batchId={1} reloadToken={0} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('This import no longer exists.')
  })
})
