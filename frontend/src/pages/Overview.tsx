import { useEffect, useState } from 'react'
import { fetchHealth } from '../api/client'

type ConnectionState = 'checking' | 'online' | 'offline'

const STATUS_LABEL: Record<ConnectionState, string> = {
  checking: 'Checking…',
  online: 'Connected',
  offline: 'Unavailable',
}

const PLACEHOLDER_SECTIONS = [
  'Settlement summary vs. platform payouts',
  'Recovered and recovered-adjacent amounts',
  'Open discrepancies by marketplace',
]

export function Overview() {
  const [connection, setConnection] = useState<ConnectionState>('checking')

  useEffect(() => {
    let cancelled = false

    fetchHealth()
      .then(() => {
        if (!cancelled) setConnection('online')
      })
      .catch(() => {
        if (!cancelled) setConnection('offline')
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Overview</h1>
        <p className="page__subtitle">
          Financial reconciliation workspace for the D2C home textiles business.
        </p>
      </header>

      <div className="card">
        <div className="card__row">
          <span className="card__label">Backend connection</span>
          <span className={`status status--${connection}`}>{STATUS_LABEL[connection]}</span>
        </div>
      </div>

      <div className="card">
        <h2 className="card__title">Summary metrics</h2>
        <p className="card__hint">
          Dashboard calculations are not implemented yet. The metrics below are placeholders.
        </p>
        <ul className="placeholder-list">
          {PLACEHOLDER_SECTIONS.map((section) => (
            <li key={section} className="placeholder-list__item">
              <span className="placeholder-list__dash">—</span>
              {section}
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
