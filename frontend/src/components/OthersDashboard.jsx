import './OthersDashboard.css'

function OthersDashboard() {
  return (
    <div className="others-dashboard">
      <div className="placeholder-content">
        <div className="placeholder-icon">✨</div>
        <h2>More Coming Soon</h2>
        <p>We're working on additional features to help you track more aspects of your life</p>

        <div className="ideas-section">
          <h3>Potential Integrations</h3>
          <div className="ideas-grid">
            <div className="idea-card">
              <span className="idea-icon">📚</span>
              <span className="idea-label">Reading & Learning</span>
            </div>
            <div className="idea-card">
              <span className="idea-icon">🎯</span>
              <span className="idea-label">Goals & Habits</span>
            </div>
            <div className="idea-card">
              <span className="idea-icon">🏠</span>
              <span className="idea-label">Smart Home</span>
            </div>
            <div className="idea-card">
              <span className="idea-icon">📅</span>
              <span className="idea-label">Calendar & Tasks</span>
            </div>
            <div className="idea-card">
              <span className="idea-icon">🎵</span>
              <span className="idea-label">Music & Media</span>
            </div>
            <div className="idea-card">
              <span className="idea-icon">✈️</span>
              <span className="idea-label">Travel & Places</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default OthersDashboard
