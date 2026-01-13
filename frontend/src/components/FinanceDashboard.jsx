import './FinanceDashboard.css'

function FinanceDashboard() {
  return (
    <div className="finance-dashboard">
      <div className="placeholder-content">
        <div className="placeholder-icon">💰</div>
        <h2>Finance Dashboard</h2>
        <p>Track your investments, expenses, and financial goals</p>
        <div className="coming-soon">Coming Soon</div>

        <div className="feature-preview">
          <h3>Planned Features</h3>
          <ul>
            <li>Portfolio tracking & performance</li>
            <li>Expense categorization</li>
            <li>Budget management</li>
            <li>Investment analytics</li>
            <li>Net worth tracking</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

export default FinanceDashboard
