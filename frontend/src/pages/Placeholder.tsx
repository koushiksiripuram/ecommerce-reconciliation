interface PlaceholderPageProps {
  title: string
}

export function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">{title}</h1>
        <p className="page__subtitle">This section has not been implemented yet.</p>
      </header>

      <div className="card">
        <p className="card__hint">Planned for a later milestone.</p>
      </div>
    </section>
  )
}
