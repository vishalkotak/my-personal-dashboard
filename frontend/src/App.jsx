import { useState } from 'react'
import HealthDashboard from './components/HealthDashboard'
import FinanceDashboard from './components/FinanceDashboard'
import OthersDashboard from './components/OthersDashboard'
import './App.css'

const TABS = [
  { id: 'health', label: 'Health', icon: '❤️', component: HealthDashboard },
  { id: 'finance', label: 'Finance', icon: '💰', component: FinanceDashboard },
  { id: 'others', label: 'Others', icon: '✨', component: OthersDashboard },
]

function App() {
  const [activeTab, setActiveTab] = useState('health')

  const ActiveComponent = TABS.find(tab => tab.id === activeTab)?.component || HealthDashboard

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
                onClick={() => setActiveTab(tab.id)}
              >
                <span className="tab-icon">{tab.icon}</span>
                <span className="tab-label">{tab.label}</span>
              </button>
            ))}
          </nav>
        </div>
      </header>

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
