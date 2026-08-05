import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import App from '../App'

vi.mock('../api/client', () => ({
  api: {
    GET: vi.fn().mockResolvedValue({ data: { status: 'ok' } }),
  },
}))

describe('App shell', () => {
  it('renders the NextTrack title', async () => {
    render(<App />)
    expect(await screen.findByText('NextTrack')).toBeInTheDocument()
  })

  it('shows Last.fm connected badge after health check resolves', async () => {
    render(<App />)
    expect(await screen.findByText('Last.fm connected')).toBeInTheDocument()
  })
})
