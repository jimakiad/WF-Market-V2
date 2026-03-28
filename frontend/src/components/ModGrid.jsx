import { useState, useEffect } from 'react'
import './ModGrid.css'

function ModGrid({ factions, selectedFaction, onFactionChange, platinum, onPlatinumChange, addToast }) {
  const [mods, setMods] = useState([])
  const [loadingMods, setLoadingMods] = useState(false)
  const [busyModIds, setBusyModIds] = useState(new Set())
  const [search, setSearch] = useState('')

  const loadMods = (faction) => {
    if (!faction) return
    setLoadingMods(true)
    fetch(`/factions/${encodeURIComponent(faction)}/mods`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load mods')
        return res.json()
      })
      .then((data) => setMods(data.mods || []))
      .catch(() => addToast('Failed to load mods for this syndicate', 'error'))
      .finally(() => setLoadingMods(false))
  }

  useEffect(() => {
    setSearch('')
    loadMods(selectedFaction)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFaction])

  const handleCreateOrder = async (mod) => {
    if (!mod.id || platinum <= 0) return
    setBusyModIds((prev) => new Set(prev).add(mod.id))

    try {
      const res = await fetch('/api/mod/order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: mod.id, platinum }),
      })
      const data = await res.json()
      if (res.ok) {
        addToast(`Order created for ${mod.name}`, 'success')
        loadMods(selectedFaction)
      } else {
        addToast(data.error || 'Failed to create order', 'error')
      }
    } catch {
      addToast(`Failed to create order for ${mod.name}`, 'error')
    } finally {
      setBusyModIds((prev) => {
        const next = new Set(prev)
        next.delete(mod.id)
        return next
      })
    }
  }

  const handleDeleteOrder = async (mod) => {
    if (!mod.order_id) return
    setBusyModIds((prev) => new Set(prev).add(mod.id))

    try {
      const res = await fetch(`/api/mod/order/${mod.order_id}`, { method: 'DELETE' })
      const data = await res.json()
      if (res.ok) {
        addToast(`Removed listing for ${mod.name}`, 'success')
        // Immediately clear order state so the UI reflects the deletion even if
        // WFM's orders endpoint hasn't propagated yet
        setMods((prev) =>
          prev.map((m) => m.id === mod.id ? { ...m, has_order: false, order_id: null } : m)
        )
        // Background re-fetch to confirm ground truth
        loadMods(selectedFaction)
      } else {
        addToast(data.error || 'Failed to remove listing', 'error')
      }
    } catch {
      addToast(`Failed to remove listing for ${mod.name}`, 'error')
    } finally {
      setBusyModIds((prev) => {
        const next = new Set(prev)
        next.delete(mod.id)
        return next
      })
    }
  }

  const filteredMods = mods.filter(
    (mod) =>
      mod.name.toLowerCase().includes(search.toLowerCase()) ||
      mod.url_name.includes(search.toLowerCase())
  )

  return (
    <div className="mod-grid-container">
      {/* Controls bar */}
      <div className="mod-controls">
        <div className="mod-controls-left">
          <select
            className="faction-select"
            value={selectedFaction}
            onChange={(e) => onFactionChange(e.target.value)}
          >
            {factions.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
          <div className="mod-search-wrap">
            <svg className="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              className="mod-search"
              placeholder="Search mods..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
        <div className="mod-controls-right">
          <div className="plat-input-mini">
            <span className="plat-diamond">&#9830;</span>
            <input
              type="number"
              min="1"
              value={platinum}
              onChange={(e) => onPlatinumChange(parseInt(e.target.value) || 0)}
            />
          </div>
          <span className="mod-count">{filteredMods.length} mods</span>
        </div>
      </div>

      {/* Mod grid */}
      {loadingMods ? (
        <div className="mod-grid-loading">
          <div className="spinner" />
          <span>Loading mods...</span>
        </div>
      ) : filteredMods.length === 0 ? (
        <div className="mod-grid-empty">
          {mods.length === 0
            ? 'No mod data available. Run a batch process first to populate data.'
            : 'No mods match your search.'}
        </div>
      ) : (
        <div className="mod-grid">
          {filteredMods.map((mod) => (
            <div key={mod.url_name} className={`mod-card ${mod.has_order ? 'has-order' : ''} ${!mod.id ? 'no-id' : ''}`}>
              <div className="mod-thumb">
                {mod.thumb ? (
                  <img src={mod.thumb} alt={mod.name} loading="lazy" />
                ) : (
                  <div className="mod-thumb-placeholder">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                      <circle cx="8.5" cy="8.5" r="1.5" />
                      <polyline points="21 15 16 10 5 21" />
                    </svg>
                  </div>
                )}
                {mod.has_order && (
                  <div className="mod-badge">Listed</div>
                )}
              </div>
              <div className="mod-info">
                <span className="mod-name">{mod.name}</span>
              </div>
              <button
                className={`mod-action ${mod.has_order ? 'remove' : ''}`}
                disabled={!mod.id || busyModIds.has(mod.id) || (mod.has_order && !mod.order_id)}
                onClick={() => mod.has_order ? handleDeleteOrder(mod) : handleCreateOrder(mod)}
                title={
                  !mod.id
                    ? 'No item ID — run batch first'
                    : mod.has_order
                    ? 'Remove listing'
                    : `Sell for ${platinum}p`
                }
              >
                {busyModIds.has(mod.id) ? (
                  <span className="spinner spinner-small" />
                ) : mod.has_order ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default ModGrid
