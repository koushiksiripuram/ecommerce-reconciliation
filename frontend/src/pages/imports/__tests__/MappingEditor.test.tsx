import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makePreview } from '../../../test/importFixtures'
import { MappingEditor } from '../MappingEditor'

function setup(canManage = true) {
  const onSave = vi.fn<(mapping: Record<string, string | null>, save: boolean) => Promise<void>>()
  const onApproveAndProcess = vi.fn<
    (mapping: Record<string, string | null>, save: boolean) => Promise<void>
  >()
  onSave.mockResolvedValue(undefined)
  onApproveAndProcess.mockResolvedValue(undefined)

  render(
    <MappingEditor
      preview={makePreview()}
      canManage={canManage}
      onSave={onSave}
      onApproveAndProcess={onApproveAndProcess}
    />,
  )
  return { onSave, onApproveAndProcess }
}

describe('MappingEditor', () => {
  it('blocks processing until every required field is mapped', async () => {
    const user = userEvent.setup()
    const { onApproveAndProcess } = setup()

    const approve = screen.getByRole('button', { name: /approve & process/i })
    expect(approve).toBeDisabled()
    expect(screen.getByText(/still required: order amount/i)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Source column for Order amount'), 'Amount')

    expect(approve).toBeEnabled()
    await user.click(approve)

    await waitFor(() =>
      expect(onApproveAndProcess).toHaveBeenCalledWith(
        { external_order_id: 'Order ID', order_amount: 'Amount' },
        false,
      ),
    )
    expect(await screen.findByText(/being processed/i)).toBeInTheDocument()
  })

  it('saves the current mapping without processing', async () => {
    const user = userEvent.setup()
    const { onSave, onApproveAndProcess } = setup()

    await user.click(screen.getByRole('button', { name: /save mapping/i }))

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onApproveAndProcess).not.toHaveBeenCalled()
    // The unmapped field is sent as null rather than an empty string.
    expect(onSave).toHaveBeenCalledWith(
      { external_order_id: 'Order ID', order_amount: null },
      false,
    )
    expect(await screen.findByText('Mapping saved.')).toBeInTheDocument()
  })

  it('is read-only for non-operators', () => {
    setup(false)
    expect(screen.queryByRole('button', { name: /save mapping/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approve & process/i })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Source column for Order amount')).toBeDisabled()
  })

  it('reports failures from the backend', async () => {
    const user = userEvent.setup()
    const { onSave } = setup()
    onSave.mockRejectedValue(new Error('boom'))

    await user.click(screen.getByRole('button', { name: /save mapping/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/something went wrong/i)
  })
})
