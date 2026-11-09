import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import UserKeyCard from './UserKeyCard'

const none = { stored: false, unlocked: false, hint: null, server_key: false }

describe('Your OpenAI key card', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks() })

  it('saves a key, shows only its last 4 characters and reports that answers can start', async () => {
    vi.spyOn(api, 'userKey').mockResolvedValue(none)
    const save = vi.spyOn(api, 'saveUserKey').mockResolvedValue({ stored: true, unlocked: true, hint: 'aaaa', server_key: false })
    const onChange = vi.fn()
    render(<UserKeyCard onChange={onChange} />)
    expect(await screen.findByText('No key yet')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Your OpenAI API key'), { target: { value: '  sk-proj-userA0000aaaa ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save key' }))

    await waitFor(() => expect(save).toHaveBeenCalledWith('sk-proj-userA0000aaaa'))
    expect(await screen.findByText('Your key is active · ••••aaaa')).toBeInTheDocument()
    expect(screen.getByLabelText('Your OpenAI API key')).toHaveValue('')
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('asks for the key again when this browser can no longer unlock the saved one', async () => {
    vi.spyOn(api, 'userKey').mockResolvedValue({ stored: true, unlocked: false, hint: 'aaaa', server_key: false })
    render(<UserKeyCard />)
    expect(await screen.findByText(/can't be unlocked in this browser\. Enter it again\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove my key' })).toBeInTheDocument()
  })

  it('shows why a key was refused', async () => {
    vi.spyOn(api, 'userKey').mockResolvedValue(none)
    vi.spyOn(api, 'saveUserKey').mockRejectedValue(new Error("OpenAI didn't accept this key. Check it and try again."))
    render(<UserKeyCard />)
    fireEvent.change(await screen.findByLabelText('Your OpenAI API key'), { target: { value: 'sk-wrong' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save key' }))
    expect(await screen.findByRole('status')).toHaveTextContent("OpenAI didn't accept this key.")
  })
})
