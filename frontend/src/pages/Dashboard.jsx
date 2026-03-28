import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import Toast from '../components/Toast'
import './Dashboard.css'

function Dashboard() {
  const [factions, setFactions] = useState([])
  const [selectedFaction, setSelectedFaction] = useState('')
  const [platinum, setPlatinum] = useState(12)
  const [loading, setLoading] = useState(false)
  const [loadingAction, setLoadingAction] = useState('')
  const [toasts, setToasts] = useState([])
  const navigate = useNavigate()

  const addToast = useCallback((message, type = 'success') => {
    const id = Date.now()
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 4000)
  }, [])

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  useEffect(() => {
    const loadData = async () => {
      try {
        const [statusRes, factionsRes] = await Promise.all([
          fetch('/status'),
          fetch('/factions'),
        ])

        if (statusRes.status === 401 || factionsRes.status === 401) {
          navigate('/login')
          return
        }

        const statusData = await statusRes.json()
        if (statusData.operation_in_progress) {
          setLoading(true)
          setLoadingAction('Previous operation still in progress...')
        }

        const factionsData = await factionsRes.json()
        if (factionsData.factions?.length > 0) {
          setFactions(factionsData.factions)
          setSelectedFaction(factionsData.factions[0])
        }
      } catch {
        addToast('Failed to connect to server', 'error')
      }
    }
    loadData()
  }, [navigate, addToast])

  const handleCreateOrders = async () => {
    if (!selectedFaction) {
      addToast('Please select a syndicate', 'error')
      return
    }
    if (platinum <= 0) {
      addToast('Please enter a valid platinum amount', 'error')
      return
    }

    setLoading(true)
    setLoadingAction('Creating orders...')

    try {
      const response = await fetch('/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ factions: [selectedFaction], platinum }),
      })

      const data = await response.json()

      if (response.ok) {
        addToast(data.message, 'success')
      } else if (response.status === 409) {
        addToast('Operation already in progress', 'error')
      } else {
        addToast(data.error || 'An error occurred', 'error')
      }
    } catch {
      addToast('Failed to create orders', 'error')
    } finally {
      setLoading(false)
      setLoadingAction('')
    }
  }

  const handleDeleteOrders = async () => {
    if (!window.confirm('Delete all matching augment mod orders?')) return

    setLoading(true)
    setLoadingAction('Deleting orders...')

    try {
      const response = await fetch('/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })

      const data = await response.json()

      if (response.ok) {
        addToast(data.message, 'success')
      } else if (response.status === 409) {
        addToast('Operation already in progress', 'error')
      } else {
        addToast(data.error || 'An error occurred', 'error')
      }
    } catch {
      addToast('Failed to delete orders', 'error')
    } finally {
      setLoading(false)
      setLoadingAction('')
    }
  }

  const handleLogout = () => {
    window.location.href = '/logout'
  }

  return (
    <div className="dashboard">
      <Toast toasts={toasts} onRemove={removeToast} />

      <header className="dash-header">
        <div className="dash-header-inner">
          <div className="dash-brand">
            <svg width="28" height="28" viewBox="0 0 40 40" fill="none">
              <path d="M20 2L36 11V29L20 38L4 29V11L20 2Z" stroke="#d4a44a" strokeWidth="2" fill="none" />
              <path d="M20 8L30 14V26L20 32L10 26V14L20 8Z" fill="#d4a44a" fillOpacity="0.15" stroke="#d4a44a" strokeWidth="1.5" />
              <circle cx="20" cy="20" r="4" fill="#d4a44a" />
            </svg>
            <span>WF Market</span>
          </div>
          <button className="logout-btn" onClick={handleLogout}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Logout
          </button>
        </div>
      </header>

      <main className="dash-main">
        <div className="dash-content">
          <div className="page-title">
            <h1>Order Manager</h1>
            <p>Create and manage augment mod sell orders</p>
          </div>

          <div className="dash-grid">
            {/* Syndicate Selection */}
            <section className="card syndicate-card">
              <h2 className="card-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
                Select Syndicate
              </h2>
              <div className="syndicate-list">
                {factions.length === 0 ? (
                  <div className="syndicate-loading">Loading syndicates...</div>
                ) : (
                  factions.map((faction) => (
                    <label
                      key={faction}
                      className={`syndicate-option ${selectedFaction === faction ? 'selected' : ''}`}
                    >
                      <input
                        type="radio"
                        name="faction"
                        value={faction}
                        checked={selectedFaction === faction}
                        onChange={(e) => setSelectedFaction(e.target.value)}
                      />
                      <span className="radio-dot" />
                      <span className="syndicate-name">{faction}</span>
                    </label>
                  ))
                )}
              </div>
            </section>

            {/* Order Configuration */}
            <section className="card config-card">
              <h2 className="card-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
                Configuration
              </h2>

              <div className="config-field">
                <label htmlFor="platinum">Platinum per order</label>
                <div className="platinum-input-wrap">
                  <span className="platinum-icon">&#9830;</span>
                  <input
                    id="platinum"
                    type="number"
                    min="1"
                    value={platinum}
                    onChange={(e) => setPlatinum(parseInt(e.target.value) || 0)}
                  />
                </div>
              </div>

              <div className="config-summary">
                <div className="summary-row">
                  <span>Syndicate</span>
                  <span className="summary-value">{selectedFaction || '—'}</span>
                </div>
                <div className="summary-row">
                  <span>Price</span>
                  <span className="summary-value">{platinum}p</span>
                </div>
              </div>

              <div className="action-buttons">
                <button
                  className="btn btn-primary"
                  onClick={handleCreateOrders}
                  disabled={loading}
                >
                  {loading && loadingAction.includes('Creating') ? (
                    <span className="btn-loading">
                      <span className="spinner" />
                      Creating...
                    </span>
                  ) : (
                    <>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="12" y1="5" x2="12" y2="19" />
                        <line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                      Create Orders
                    </>
                  )}
                </button>
                <button
                  className="btn btn-danger"
                  onClick={handleDeleteOrders}
                  disabled={loading}
                >
                  {loading && loadingAction.includes('Deleting') ? (
                    <span className="btn-loading">
                      <span className="spinner spinner-light" />
                      Deleting...
                    </span>
                  ) : (
                    <>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                      </svg>
                      Delete Orders
                    </>
                  )}
                </button>
              </div>
            </section>
          </div>

          {/* Loading overlay */}
          {loading && (
            <div className="loading-bar">
              <div className="loading-bar-inner" />
              <span>{loadingAction}</span>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default Dashboard
