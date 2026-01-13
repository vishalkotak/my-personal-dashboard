import { useState } from 'react'
import HealthDashboard from './components/HealthDashboard'
import HypertrophyDashboard from './components/HypertrophyDashboard'
import FinanceDashboard from './components/FinanceDashboard'
import OthersDashboard from './components/OthersDashboard'
import './App.css'

const TABS = [
  {
    id: 'health',
    label: 'Health',
    icon: '❤️',
    subtabs: [
      { id: 'whoop', label: 'WHOOP', component: HealthDashboard },
      { id: 'gym', label: 'Gym', component: HypertrophyDashboard },
    ]
  },
  { id: 'finance', label: 'Finance', icon: '💰', component: FinanceDashboard },
  { id: 'others', label: 'Others', icon: '✨', component: OthersDashboard },
]

function App() {
  const [activeTab, setActiveTab] = useState('health')
  const [activeSubTab, setActiveSubTab] = useState('whoop')

  const currentTab = TABS.find(tab => tab.id === activeTab)

  // Get the active component
  const getActiveComponent = () => {
    if (currentTab?.subtabs) {
      const subtab = currentTab.subtabs.find(s => s.id === activeSubTab)
      return subtab?.component || currentTab.subtabs[0]?.component
    }
    return currentTab?.component || HealthDashboard
  }

  const ActiveComponent = getActiveComponent()

  const handleTabChange = (tabId) => {
    setActiveTab(tabId)
    const tab = TABS.find(t => t.id === tabId)
    if (tab?.subtabs) {
      setActiveSubTab(tab.subtabs[0].id)
    }
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-content">
          <h1 className="app-title">Personal Dashboard</h1>
          <nav className="tab-nav">
            {TABS.map(tab => (
              <button
                key={tab.id}
                className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => handleTabChange(tab.id)}
              >
                <span className="tab-icon">{tab.icon}</span>
                <span className="tab-label">{tab.label}</span>
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Sub-tabs for Health */}
      {currentTab?.subtabs && (
        <div className="subtab-nav">
          {currentTab.subtabs.map(subtab => (
            <button
              key={subtab.id}
              className={`subtab-btn ${activeSubTab === subtab.id ? 'active' : ''}`}
              onClick={() => setActiveSubTab(subtab.id)}
            >
              {subtab.label}
            </button>
          ))}
        </div>
      )}

      {/* Main Content */}
      <main className="app-main">
        <div className="content-container">
          <ActiveComponent />
        </div>
      </main>
    </div>
  )
}

export default App
