import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import './HypertrophyDashboard.css'

const API_BASE = 'http://localhost:8000'

// Rest Timer Component
function RestTimer({ seconds, onComplete }) {
  const [timeLeft, setTimeLeft] = useState(seconds)
  const [isRunning, setIsRunning] = useState(true)

  useEffect(() => {
    if (!isRunning || timeLeft <= 0) {
      if (timeLeft <= 0) onComplete?.()
      return
    }

    const timer = setInterval(() => {
      setTimeLeft(t => t - 1)
    }, 1000)

    return () => clearInterval(timer)
  }, [isRunning, timeLeft, onComplete])

  const formatTime = (secs) => {
    const mins = Math.floor(secs / 60)
    const s = secs % 60
    return `${mins}:${s.toString().padStart(2, '0')}`
  }

  const progress = (seconds - timeLeft) / seconds

  return (
    <div className="rest-timer">
      <div className="timer-ring">
        <svg width="80" height="80">
          <circle
            cx="40"
            cy="40"
            r="35"
            fill="none"
            stroke="#2C2C2E"
            strokeWidth="6"
          />
          <circle
            cx="40"
            cy="40"
            r="35"
            fill="none"
            stroke="#30D158"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={2 * Math.PI * 35}
            strokeDashoffset={2 * Math.PI * 35 * (1 - progress)}
            transform="rotate(-90 40 40)"
          />
        </svg>
        <span className="timer-value">{formatTime(timeLeft)}</span>
      </div>
      <div className="timer-controls">
        <button onClick={() => setIsRunning(!isRunning)}>
          {isRunning ? 'Pause' : 'Resume'}
        </button>
        <button onClick={() => { setTimeLeft(0); onComplete?.() }}>
          Skip
        </button>
      </div>
    </div>
  )
}

// Set Input Row Component
function SetRow({ setNum, defaultWeight, onLog, onDelete, logged, canDelete }) {
  const [weight, setWeight] = useState(defaultWeight || '')
  const [reps, setReps] = useState('')

  // Update weight when defaultWeight changes
  useEffect(() => {
    if (defaultWeight && !weight) {
      setWeight(defaultWeight)
    }
  }, [defaultWeight])

  const handleLog = () => {
    if (weight && reps) {
      onLog({
        set_number: setNum,
        weight_lbs: parseFloat(weight),
        reps: parseInt(reps),
        rir: 0
      })
    }
  }

  if (logged) {
    return (
      <div className="set-row logged">
        <span className="set-num">{setNum}</span>
        <span className="set-data">{logged.weight_lbs} lbs x {logged.reps}</span>
        <span className="set-check">✓</span>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(setNum); }}
          className="delete-set-btn"
        >
          ×
        </button>
      </div>
    )
  }

  return (
    <div className="set-row">
      <span className="set-num">{setNum}</span>
      <input
        type="number"
        placeholder="lbs"
        value={weight}
        onChange={(e) => setWeight(e.target.value)}
        className="set-input weight"
      />
      <span className="set-x">x</span>
      <input
        type="number"
        placeholder="reps"
        value={reps}
        onChange={(e) => setReps(e.target.value)}
        className="set-input reps"
      />
      <button onClick={handleLog} className="log-btn">Log</button>
    </div>
  )
}

// Exercise Card Component
function ExerciseCard({ exercise, sessionId, onSetLogged, onSetDeleted, loggedSets }) {
  const [expanded, setExpanded] = useState(false)
  const [lastWorkout, setLastWorkout] = useState([])
  const [suggestion, setSuggestion] = useState(null)
  const [showTimer, setShowTimer] = useState(false)
  const [numSets, setNumSets] = useState(exercise.target_sets || 3)

  useEffect(() => {
    fetchLastWorkout()
    fetchSuggestion()
  }, [exercise.exercise_id])

  const fetchLastWorkout = async () => {
    try {
      const res = await axios.get(`${API_BASE}/gym/exercises/${exercise.exercise_id}/last`)
      setLastWorkout(res.data)
    } catch (err) {
      console.error('Failed to fetch last workout:', err)
    }
  }

  const fetchSuggestion = async () => {
    try {
      const res = await axios.get(`${API_BASE}/gym/exercises/${exercise.exercise_id}/suggest`)
      setSuggestion(res.data)
    } catch (err) {
      console.error('Failed to fetch suggestion:', err)
    }
  }

  const handleLogSet = async (setData) => {
    try {
      await axios.post(`${API_BASE}/gym/sessions/${sessionId}/sets`, null, {
        params: {
          exercise_id: exercise.exercise_id,
          ...setData
        }
      })
      onSetLogged(exercise.exercise_id, setData)
      setShowTimer(true)
    } catch (err) {
      console.error('Failed to log set:', err)
    }
  }

  const handleDeleteSet = (setNum) => {
    // For now, just remove from local state
    // The set will remain in DB but won't show
    onSetDeleted(exercise.exercise_id, setNum)
  }

  const addSet = () => {
    setNumSets(prev => prev + 1)
  }

  const removeSet = () => {
    if (numSets > 1) {
      setNumSets(prev => prev - 1)
    }
  }

  const exerciseSets = loggedSets[exercise.exercise_id] || []

  // Get default weight: use suggestion if available, otherwise last workout's weight
  const getDefaultWeight = () => {
    if (suggestion?.suggestion) {
      return suggestion.suggestion
    }
    if (lastWorkout.length > 0) {
      return lastWorkout[0].weight_lbs
    }
    return ''
  }

  const defaultWeight = getDefaultWeight()

  return (
    <div className={`exercise-card ${expanded ? 'expanded' : ''}`}>
      <div className="exercise-header" onClick={() => setExpanded(!expanded)}>
        <div className="exercise-info">
          <h3>{exercise.name}</h3>
          <span className="muscle-tag">{exercise.muscle_group}</span>
        </div>
        <div className="exercise-target">
          <span className="target-sets">{numSets}x</span>
          <span className="target-reps">{exercise.target_reps_min}-{exercise.target_reps_max}</span>
          <span className="expand-icon">{expanded ? '−' : '+'}</span>
        </div>
      </div>

      {expanded && (
        <div className="exercise-body">
          {suggestion?.suggestion && (
            <div className="suggestion-box">
              <span className="suggestion-label">Suggested</span>
              <span className="suggestion-weight">{suggestion.suggestion} lbs</span>
              <span className="suggestion-reason">{suggestion.reason}</span>
            </div>
          )}

          {lastWorkout.length > 0 && (
            <div className="last-workout">
              <span className="last-label">Last time:</span>
              {lastWorkout.map((set, i) => (
                <span key={i} className="last-set">
                  {set.weight_lbs}x{set.reps}
                </span>
              ))}
            </div>
          )}

          <div className="sets-container">
            {Array.from({ length: numSets }, (_, i) => i + 1).map(setNum => {
              const loggedSet = exerciseSets.find(s => s.set_number === setNum)
              return (
                <SetRow
                  key={`${setNum}-${loggedSet ? 'logged' : 'input'}`}
                  setNum={setNum}
                  defaultWeight={defaultWeight}
                  onLog={handleLogSet}
                  onDelete={handleDeleteSet}
                  logged={loggedSet}
                  canDelete={numSets > 1}
                />
              )
            })}
          </div>

          <div className="set-controls">
            <button onClick={removeSet} className="set-control-btn" disabled={numSets <= 1}>
              − Remove Set
            </button>
            <button onClick={addSet} className="set-control-btn add">
              + Add Set
            </button>
          </div>

          {showTimer && (
            <RestTimer
              seconds={exercise.rest_seconds || 150}
              onComplete={() => setShowTimer(false)}
            />
          )}
        </div>
      )}
    </div>
  )
}

function HypertrophyDashboard() {
  const [loading, setLoading] = useState(true)
  const [templates, setTemplates] = useState([])
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [activeSession, setActiveSession] = useState(null)
  const [currentWorkout, setCurrentWorkout] = useState(null)
  const [recentSessions, setRecentSessions] = useState([])
  const [stats, setStats] = useState(null)
  const [volumeHistory, setVolumeHistory] = useState([])
  const [loggedSets, setLoggedSets] = useState({})
  const [view, setView] = useState('home') // home, workout, history

  useEffect(() => {
    fetchInitialData()
  }, [])

  const fetchInitialData = async () => {
    try {
      setLoading(true)
      const [templatesRes, sessionsRes, statsRes, volumeRes] = await Promise.all([
        axios.get(`${API_BASE}/gym/templates`),
        axios.get(`${API_BASE}/gym/sessions?limit=10`),
        axios.get(`${API_BASE}/gym/stats`),
        axios.get(`${API_BASE}/gym/volume-history?days=30`)
      ])
      setTemplates(templatesRes.data)
      setRecentSessions(sessionsRes.data)
      setStats(statsRes.data)
      setVolumeHistory(volumeRes.data)
    } catch (err) {
      console.error('Failed to fetch data:', err)
    } finally {
      setLoading(false)
    }
  }

  const startWorkout = async (templateId) => {
    try {
      const res = await axios.post(`${API_BASE}/gym/sessions`, null, {
        params: { template_id: templateId }
      })
      setActiveSession(res.data.session_id)
      setCurrentWorkout(res.data.template)
      setLoggedSets({})
      setView('workout')
    } catch (err) {
      console.error('Failed to start workout:', err)
    }
  }

  const completeWorkout = async () => {
    try {
      await axios.post(`${API_BASE}/gym/sessions/${activeSession}/complete`)
      setActiveSession(null)
      setCurrentWorkout(null)
      setView('home')
      fetchInitialData()
    } catch (err) {
      console.error('Failed to complete workout:', err)
    }
  }

  const handleSetLogged = (exerciseId, setData) => {
    setLoggedSets(prev => ({
      ...prev,
      [exerciseId]: [...(prev[exerciseId] || []), setData]
    }))
  }

  const handleSetDeleted = (exerciseId, setNum) => {
    setLoggedSets(prev => ({
      ...prev,
      [exerciseId]: (prev[exerciseId] || []).filter(s => s.set_number !== setNum)
    }))
  }

  // Determine which workout is next based on rotation
  const getNextWorkout = () => {
    if (!recentSessions.length || !templates.length) {
      return templates[0]
    }

    const lastSession = recentSessions[0]
    if (!lastSession.template_id) return templates[0]

    const lastIndex = templates.findIndex(t => t.id === lastSession.template_id)
    const nextIndex = (lastIndex + 1) % templates.length
    return templates[nextIndex]
  }

  const nextWorkout = getNextWorkout()

  if (loading) {
    return (
      <div className="gym-loading">
        <div className="loading-ring"></div>
      </div>
    )
  }

  // Workout View
  if (view === 'workout' && currentWorkout) {
    const completedExercises = Object.keys(loggedSets).length
    const totalExercises = currentWorkout.exercises?.length || 0

    return (
      <div className="gym-dashboard workout-active">
        <header className="workout-header">
          <button onClick={() => setView('home')} className="back-btn">←</button>
          <div className="workout-title">
            <h1>{currentWorkout.name}</h1>
            <p>{currentWorkout.description}</p>
          </div>
          <div className="workout-progress">
            <span>{completedExercises}/{totalExercises}</span>
          </div>
        </header>

        <div className="exercises-list">
          {currentWorkout.exercises?.map((exercise, index) => (
            <ExerciseCard
              key={exercise.exercise_id}
              exercise={exercise}
              sessionId={activeSession}
              onSetLogged={handleSetLogged}
              onSetDeleted={handleSetDeleted}
              loggedSets={loggedSets}
            />
          ))}
        </div>

        <div className="workout-actions">
          <button onClick={completeWorkout} className="complete-btn">
            Complete Workout
          </button>
        </div>
      </div>
    )
  }

  // History View
  if (view === 'history') {
    return (
      <div className="gym-dashboard">
        <header className="gym-header">
          <button onClick={() => setView('home')} className="back-btn">←</button>
          <h1>Workout History</h1>
        </header>

        <div className="history-list">
          {recentSessions.map(session => (
            <div key={session.id} className="history-card">
              <div className="history-date">
                {new Date(session.session_date).toLocaleDateString('en-US', {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric'
                })}
              </div>
              <div className="history-info">
                <h3>{session.template_name || 'Custom Workout'}</h3>
                <span className="history-type">{session.day_type}</span>
              </div>
              <div className="history-stats">
                <span>{session.total_sets || 0} sets</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Home View
  return (
    <div className="gym-dashboard">
      <header className="gym-header">
        <div className="header-text">
          <span className="header-label">Hypertrophy Training</span>
          <h1>Build Muscle</h1>
        </div>
      </header>

      {/* Next Workout Card */}
      {nextWorkout && (
        <section className="next-workout">
          <div className="next-label">Up Next</div>
          <div className="next-card" onClick={() => startWorkout(nextWorkout.id)}>
            <div className="next-info">
              <h2>{nextWorkout.name}</h2>
              <p>{nextWorkout.description}</p>
            </div>
            <button className="start-btn">Start</button>
          </div>
        </section>
      )}

      {/* Weekly Schedule */}
      <section className="schedule">
        <h2>Program</h2>
        <div className="schedule-grid">
          {templates.map((template, index) => (
            <div
              key={template.id}
              className={`schedule-day ${template.id === nextWorkout?.id ? 'next' : ''}`}
              onClick={() => startWorkout(template.id)}
            >
              <span className="day-num">Day {index + 1}</span>
              <span className="day-name">{template.name}</span>
              <span className="day-type">{template.day_type}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Stats */}
      {stats && (
        <section className="gym-stats">
          <h2>Progress (30 Days)</h2>
          <div className="stats-grid">
            <div className="stat-card">
              <span className="stat-value">{stats.total_sessions}</span>
              <span className="stat-label">Workouts</span>
            </div>
            <div className="stat-card">
              <span className="stat-value">{stats.total_sets}</span>
              <span className="stat-label">Sets</span>
            </div>
            <div className="stat-card">
              <span className="stat-value">{Math.round(stats.total_volume_lbs / 1000)}k</span>
              <span className="stat-label">Volume (lbs)</span>
            </div>
          </div>

          {Object.keys(stats.sets_by_muscle_group || {}).length > 0 && (
            <div className="muscle-breakdown">
              <h3>Sets by Muscle Group</h3>
              <div className="muscle-bars">
                {Object.entries(stats.sets_by_muscle_group).map(([muscle, sets]) => (
                  <div key={muscle} className="muscle-bar">
                    <span className="muscle-name">{muscle}</span>
                    <div className="bar-container">
                      <div
                        className="bar-fill"
                        style={{ width: `${Math.min(100, (sets / Math.max(...Object.values(stats.sets_by_muscle_group))) * 100)}%` }}
                      ></div>
                    </div>
                    <span className="muscle-sets">{sets}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Volume Chart */}
      <section className="volume-section">
        <div className="section-header">
          <h2>Volume Trend</h2>
          <button onClick={() => setView('history')} className="view-all-btn">History</button>
        </div>
        {volumeHistory.length > 0 ? (
          <div className="volume-chart">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={volumeHistory.map(v => ({
                date: new Date(v.session_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                volume: Math.round((v.volume || 0) / 1000),
                workout: v.workout_name
              }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2C2C2E" vertical={false} />
                <XAxis
                  dataKey="date"
                  stroke="#636366"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  stroke="#636366"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v}k`}
                />
                <Tooltip
                  contentStyle={{
                    background: '#2C2C2E',
                    border: '1px solid #3A3A3C',
                    borderRadius: '10px',
                  }}
                  labelStyle={{ color: '#8E8E93' }}
                  formatter={(value, name) => [`${value}k lbs`, 'Volume']}
                />
                <Bar dataKey="volume" fill="#FF9F0A" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="empty-chart">
            <p>Complete your first workout to see volume trends</p>
          </div>
        )}
      </section>

    </div>
  )
}

export default HypertrophyDashboard
