import { useState } from 'react'
import { Layout } from './components/Layout'
import { NAV_ITEMS } from './config/navigation'
import { Overview } from './pages/Overview'
import { PlaceholderPage } from './pages/Placeholder'

export default function App() {
  const [activeId, setActiveId] = useState(NAV_ITEMS[0].id)
  const activeItem = NAV_ITEMS.find((item) => item.id === activeId) ?? NAV_ITEMS[0]

  return (
    <Layout items={NAV_ITEMS} activeId={activeId} onSelect={setActiveId}>
      {activeId === 'overview' ? <Overview /> : <PlaceholderPage title={activeItem.label} />}
    </Layout>
  )
}
