import { useState, useEffect } from 'react'
import axios from 'axios'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from 'recharts'
import './HealthDashboard.css'

const API_BASE = 'http://localhost:8000'

// Custom tooltip for charts
const CustomTooltip = ({ active, payload, label, unit, valueKey }) => {
  if (active && payload && payload.length) {
    return (
      <div className="chart-tooltip">
        <p className="tooltip-label">{label}</p>
        {payload.map((entry, index) => (
          <p key={index} className="tooltip-value" style={{ color: entry.color }}>
            {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(1) : entry.value}{unit || ''}
          </p>
        ))}
      </div>
    )
  }
  return null
}

// Ring component - inspired by Apple Watch
function Ring({ value, max = 100, size = 120, strokeWidth = 10, color, label }) {
  const radius = (size - strokeWidth) / 2
  const circumference = radius * 2 * Math.PI
  const percent = Math.min(value / max, 1)
  const offset = circumference - (percent * circumference)

  return (
    <div className="ring-container">
      <svg width={size} height={size} className="ring">
        <circle
          className="ring-bg"
          strokeWidth={strokeWidth}
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
        <circle
          className="ring-progress"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          r={radius}
          cx={size / 2}
          cy={size / 2}
          style={{
            strokeDasharray: circumference,
            strokeDashoffset: offset,
            stroke: color,
          }}
        />
      </svg>
      <div className="ring-content">
        <span className="ring-value">{Math.round(value)}</span>
        <span className="ring-unit">{label}</span>
      </div>
    </div>
  )
}

// Streak badge
function Streak({ count, label }) {
  return (
    <div className="streak">
      <span className="streak-fire">🔥</span>
      <span className="streak-count">{count}</span>
      <span className="streak-label">{label}</span>
    </div>
  )
}

function HealthDashboard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [authenticated, setAuthenticated] = useState(false)
  const [summary, setSummary] = useState(null)
  const [days, setDays] = useState(14)

  useEffect(() => {
    checkAuthAndFetchData()
  }, [days])

  const checkAuthAndFetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      const authRes = await axios.get(`${API_BASE}/auth/status`)
      setAuthenticated(authRes.data.authenticated)

      if (authRes.data.authenticated) {
        const summaryRes = await axios.get(`${API_BASE}/summary?days=${days}`)
        setSummary(summaryRes.data)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleLogin = () => {
    window.location.href = `${API_BASE}/auth/login`
  }

  if (loading) {
    return (
      <div className="health-loading">
        <div className="loading-ring"></div>
      </div>
    )
  }

  if (!authenticated) {
    return (
      <div className="health-connect">
        <div className="connect-content">
          <div className="connect-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
            </svg>
          </div>
          <h1>Your Health Journey</h1>
          <p>Connect your WHOOP to unlock personalized insights</p>
          <button onClick={handleLogin} className="connect-btn">
            Connect WHOOP
          </button>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="health-error">
        <p>Something went wrong</p>
        <button onClick={checkAuthAndFetchData}>Try again</button>
      </div>
    )
  }

  if (!summary) return null

  // Calculate insights
  const latest = summary.recent_recovery[0] || {}
  const latestSleep = summary.recent_sleep[0] || {}

  const recoveryScore = latest.recovery_score || 0
  const hrvValue = latest.hrv_milli || 0
  const rhrValue = latest.resting_heart_rate || 0
  const sleepHours = latestSleep.total_sleep_hours || 0
  const sleepPerformance = latestSleep.performance_percentage || 0
  const deepSleepHours = latestSleep.deep_sleep_hours || 0
  const remSleepHours = latestSleep.rem_hours || 0
  const sleepEfficiency = latestSleep.efficiency_percentage || 0

  // Calculate averages
  const avgRecovery = summary.recent_recovery.length > 0
    ? summary.recent_recovery.reduce((sum, r) => sum + (r.recovery_score || 0), 0) / summary.recent_recovery.length
    : 0
  const avgHRV = summary.recent_recovery.length > 0
    ? summary.recent_recovery.reduce((sum, r) => sum + (r.hrv_milli || 0), 0) / summary.recent_recovery.length
    : 0
  const avgSleep = summary.recent_sleep.length > 0
    ? summary.recent_sleep.reduce((sum, s) => sum + s.total_sleep_hours, 0) / summary.recent_sleep.length
    : 0
  const avgRHR = summary.recent_recovery.length > 0
    ? summary.recent_recovery.reduce((sum, r) => sum + (r.resting_heart_rate || 0), 0) / summary.recent_recovery.length
    : 0
  const avgDeepSleep = summary.recent_sleep.length > 0
    ? summary.recent_sleep.reduce((sum, s) => sum + (s.deep_sleep_hours || 0), 0) / summary.recent_sleep.length
    : 0

  // Prepare chart data - reversed for chronological order
  const hrvChartData = [...summary.recent_recovery].reverse().map(r => {
    const dateObj = new Date(r.date)
    return {
      date: dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      hrv: r.hrv_milli || 0,
      rhr: r.resting_heart_rate || 0,
    }
  })

  const sleepChartData = [...summary.recent_sleep].reverse().map(s => {
    const dateObj = new Date(s.date)
    return {
      date: dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      deep: s.deep_sleep_hours || 0,
      rem: s.rem_hours || 0,
      light: Math.max(0, (s.total_sleep_hours || 0) - (s.deep_sleep_hours || 0) - (s.rem_hours || 0)),
      total: s.total_sleep_hours || 0,
      efficiency: s.efficiency_percentage || 0,
    }
  })

  const recoveryChartData = [...summary.recent_recovery].reverse().map(r => {
    const dateObj = new Date(r.date)
    return {
      date: dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      recovery: r.recovery_score || 0,
    }
  })

  // Calculate streaks
  let recoveryStreak = 0
  for (const rec of summary.recent_recovery) {
    if (rec.recovery_score >= 50) recoveryStreak++
    else break
  }

  let sleepStreak = 0
  for (const sleep of summary.recent_sleep) {
    if (sleep.total_sleep_hours >= 7) sleepStreak++
    else break
  }

  // Determine recovery color and message
  const getRecoveryState = (score) => {
    if (score >= 67) return { color: '#30D158', state: 'optimal', message: 'Your body is ready for anything' }
    if (score >= 34) return { color: '#FFD60A', state: 'moderate', message: 'Listen to your body today' }
    return { color: '#FF453A', state: 'low', message: 'Focus on recovery today' }
  }

  const recoveryState = getRecoveryState(recoveryScore)

  // Get color for recovery bar
  const getRecoveryColor = (score) => {
    if (score >= 67) return '#30D158'
    if (score >= 34) return '#FFD60A'
    return '#FF453A'
  }

  // Calculate total strain from workouts
  const totalStrain = summary.recent_workouts.reduce((sum, w) => sum + (w.strain || 0), 0)
  const avgStrain = summary.recent_workouts.length > 0 ? totalStrain / summary.recent_workouts.length : 0

  // HRV assessment based on research
  const getHRVAssessment = (hrv, age = 30) => {
    // General population averages by age (simplified)
    if (hrv >= 60) return { status: 'Excellent', color: '#30D158', desc: 'Strong parasympathetic tone' }
    if (hrv >= 45) return { status: 'Good', color: '#30D158', desc: 'Healthy autonomic balance' }
    if (hrv >= 30) return { status: 'Average', color: '#FFD60A', desc: 'Room for improvement' }
    return { status: 'Low', color: '#FF453A', desc: 'Focus on stress management' }
  }

  const hrvAssessment = getHRVAssessment(hrvValue)

  return (
    <div className="health-dashboard">
      {/* Greeting */}
      <header className="greeting">
        <div className="greeting-text">
          <span className="greeting-label">Good {new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 18 ? 'afternoon' : 'evening'},</span>
          <h1>{summary.profile.first_name}</h1>
        </div>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="period-select">
          <option value={7}>7 days</option>
          <option value={14}>14 days</option>
          <option value={30}>30 days</option>
        </select>
      </header>

      {/* Hero: Health Summary + Recovery Ring */}
      <section className="hero">
        <div className="hero-summary">
          <h2>Today's Health</h2>
          <table className="summary-table">
            <tbody>
              <tr>
                <td className="metric-name">Recovery</td>
                <td className="metric-val" style={{ color: recoveryState.color }}>{Math.round(recoveryScore)}%</td>
                <td className="metric-trend">{recoveryScore >= avgRecovery ? '↑' : '↓'} vs avg</td>
              </tr>
              <tr>
                <td className="metric-name">HRV</td>
                <td className="metric-val" style={{ color: hrvAssessment.color }}>{Math.round(hrvValue)} ms</td>
                <td className="metric-trend">{hrvValue >= avgHRV ? '↑' : '↓'} vs avg</td>
              </tr>
              <tr>
                <td className="metric-name">Resting HR</td>
                <td className="metric-val" style={{ color: rhrValue <= 60 ? '#30D158' : rhrValue <= 70 ? '#FFD60A' : '#FF453A' }}>{Math.round(rhrValue)} bpm</td>
                <td className="metric-trend">{rhrValue <= avgRHR ? '↑' : '↓'} vs avg</td>
              </tr>
              <tr>
                <td className="metric-name">Sleep</td>
                <td className="metric-val" style={{ color: '#BF5AF2' }}>{sleepHours.toFixed(1)}h</td>
                <td className="metric-trend">{sleepHours >= avgSleep ? '↑' : '↓'} vs avg</td>
              </tr>
              <tr>
                <td className="metric-name">Deep Sleep</td>
                <td className="metric-val" style={{ color: '#5E5CE6' }}>{deepSleepHours.toFixed(1)}h</td>
                <td className="metric-trend">{deepSleepHours >= 1.5 ? 'Good' : 'Low'}</td>
              </tr>
              <tr>
                <td className="metric-name">Sleep Efficiency</td>
                <td className="metric-val">{Math.round(sleepEfficiency)}%</td>
                <td className="metric-trend">{sleepEfficiency >= 85 ? 'Good' : 'Low'}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="hero-right">
          <div className="hero-ring">
            <Ring
              value={recoveryScore}
              size={180}
              strokeWidth={14}
              color={recoveryState.color}
              label="%"
            />
          </div>
          <div className="hero-insight">
            <span className={`status-badge ${recoveryState.state}`}>
              {recoveryState.state === 'optimal' ? 'Peak' : recoveryState.state === 'moderate' ? 'Moderate' : 'Recover'}
            </span>
            <p className="insight-message">{recoveryState.message}</p>
          </div>
        </div>
      </section>

      {/* Streaks */}
      {(recoveryStreak >= 2 || sleepStreak >= 2) && (
        <section className="streaks">
          {recoveryStreak >= 2 && <Streak count={recoveryStreak} label="day recovery streak" />}
          {sleepStreak >= 2 && <Streak count={sleepStreak} label="nights of quality sleep" />}
        </section>
      )}

      {/* KEY METRICS - Ordered by Scientific Importance */}
      {/* 1. HRV - Most predictive biomarker for health outcomes */}
      <section className="chart-section">
          <div className="section-header">
            <div>
              <h2>Heart Rate Variability</h2>
              <p className="section-subtitle">Most predictive marker of overall health</p>
            </div>
            <div className="metric-highlight">
              <span className="metric-big" style={{ color: hrvAssessment.color }}>{Math.round(hrvValue)}</span>
              <span className="metric-unit">ms</span>
            </div>
          </div>
          <div className="metric-status">
            <span className="status-pill" style={{ background: `${hrvAssessment.color}20`, color: hrvAssessment.color }}>
              {hrvAssessment.status}
            </span>
            <span className="status-desc">{hrvAssessment.desc}</span>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={hrvChartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="hrvGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#64D2FF" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#64D2FF" stopOpacity={0}/>
                  </linearGradient>
                </defs>
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
                  domain={['dataMin - 10', 'dataMax + 10']}
                />
                <Tooltip content={<CustomTooltip unit=" ms" />} />
                <ReferenceLine y={avgHRV} stroke="#636366" strokeDasharray="5 5" />
                <Area
                  type="monotone"
                  dataKey="hrv"
                  name="HRV"
                  stroke="#64D2FF"
                  strokeWidth={2}
                  fill="url(#hrvGradient)"
                  dot={{ fill: '#64D2FF', strokeWidth: 0, r: 3 }}
                  activeDot={{ r: 6, fill: '#64D2FF' }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <p className="chart-insight">
            Average: <strong>{avgHRV.toFixed(0)} ms</strong> • Higher HRV = better stress resilience
          </p>
      </section>

      {/* 2. Sleep Quality - Deep sleep is critical for recovery */}
      <section className="chart-section">
          <div className="section-header">
            <div>
              <h2>Sleep Architecture</h2>
              <p className="section-subtitle">Deep sleep is critical for physical recovery</p>
            </div>
            <div className="metric-highlight">
              <span className="metric-big" style={{ color: '#BF5AF2' }}>{sleepHours.toFixed(1)}</span>
              <span className="metric-unit">hrs</span>
            </div>
          </div>
          <div className="sleep-breakdown">
            <div className="sleep-stat">
              <span className="sleep-dot deep"></span>
              <span className="sleep-label">Deep</span>
              <span className="sleep-value">{deepSleepHours.toFixed(1)}h</span>
            </div>
            <div className="sleep-stat">
              <span className="sleep-dot rem"></span>
              <span className="sleep-label">REM</span>
              <span className="sleep-value">{remSleepHours.toFixed(1)}h</span>
            </div>
            <div className="sleep-stat">
              <span className="sleep-dot efficiency"></span>
              <span className="sleep-label">Efficiency</span>
              <span className="sleep-value">{Math.round(sleepEfficiency)}%</span>
            </div>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={sleepChartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
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
                />
                <Tooltip content={<CustomTooltip unit="h" />} />
                <ReferenceLine y={7} stroke="#30D158" strokeDasharray="5 5" label={{ value: '7h goal', fill: '#636366', fontSize: 10 }} />
                <Bar dataKey="deep" name="Deep Sleep" stackId="sleep" fill="#5E5CE6" radius={[0, 0, 0, 0]} />
                <Bar dataKey="rem" name="REM Sleep" stackId="sleep" fill="#BF5AF2" radius={[0, 0, 0, 0]} />
                <Bar dataKey="light" name="Light Sleep" stackId="sleep" fill="#48484A" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="chart-insight">
            Avg deep sleep: <strong>{avgDeepSleep.toFixed(1)}h</strong> • Need 1.5-2h for optimal recovery
          </p>
      </section>

      {/* 3. Resting Heart Rate */}
      <section className="chart-section compact">
          <div className="section-header">
            <div>
              <h2>Resting Heart Rate</h2>
              <p className="section-subtitle">Lower RHR indicates better cardiovascular fitness</p>
            </div>
            <div className="metric-highlight">
              <span className="metric-big" style={{ color: rhrValue <= 60 ? '#30D158' : rhrValue <= 70 ? '#FFD60A' : '#FF453A' }}>
                {Math.round(rhrValue)}
              </span>
              <span className="metric-unit">bpm</span>
            </div>
          </div>
          <div className="rhr-scale">
            <div className="scale-bar">
              <div className="scale-marker" style={{ left: `${Math.min(100, Math.max(0, (rhrValue - 40) / 50 * 100))}%` }}></div>
            </div>
            <div className="scale-labels">
              <span>Athletic (&lt;60)</span>
              <span>Average (60-70)</span>
              <span>Elevated (&gt;70)</span>
            </div>
          </div>
          <p className="chart-insight">
            Your average: <strong>{avgRHR.toFixed(0)} bpm</strong> • {rhrValue <= 60 ? 'Excellent cardiovascular fitness' : rhrValue <= 70 ? 'Healthy resting heart rate' : 'Consider more cardio exercise'}
          </p>
      </section>

      {/* 4. Recovery Trend */}
      <section className="chart-section">
          <div className="section-header">
            <div>
              <h2>Recovery Trend</h2>
              <p className="section-subtitle">Composite score based on HRV, RHR, and sleep</p>
            </div>
            <div className="metric-highlight">
              <span className="metric-big" style={{ color: recoveryState.color }}>{Math.round(avgRecovery)}</span>
              <span className="metric-unit">% avg</span>
            </div>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={recoveryChartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
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
                  domain={[0, 100]}
                />
                <Tooltip content={<CustomTooltip unit="%" />} />
                <ReferenceLine y={67} stroke="#30D158" strokeDasharray="5 5" />
                <ReferenceLine y={33} stroke="#FF453A" strokeDasharray="5 5" />
                <Bar dataKey="recovery" name="Recovery" radius={[4, 4, 0, 0]}>
                  {recoveryChartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={getRecoveryColor(entry.recovery)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
      </section>

      {/* Three Pillars Summary */}
      <section className="pillars">
        <div className="pillar">
          <div className="pillar-header">
            <span className="pillar-icon recovery-icon"></span>
            <span className="pillar-title">Recovery</span>
          </div>
          <div className="pillar-value" style={{ color: recoveryState.color }}>{Math.round(recoveryScore)}%</div>
          <div className="pillar-detail">Avg {Math.round(avgRecovery)}%</div>
        </div>

        <div className="pillar">
          <div className="pillar-header">
            <span className="pillar-icon sleep-icon"></span>
            <span className="pillar-title">Sleep</span>
          </div>
          <div className="pillar-value" style={{ color: '#BF5AF2' }}>{sleepHours.toFixed(1)}h</div>
          <div className="pillar-detail">Avg {avgSleep.toFixed(1)}h</div>
        </div>

        <div className="pillar">
          <div className="pillar-header">
            <span className="pillar-icon strain-icon"></span>
            <span className="pillar-title">Strain</span>
          </div>
          <div className="pillar-value" style={{ color: '#FF9F0A' }}>{avgStrain.toFixed(1)}</div>
          <div className="pillar-detail">{summary.recent_workouts.length} workouts</div>
        </div>
      </section>

      {/* Achievements */}
      <section className="achievements">
        <h2>Achievements</h2>
        <div className="achievement-grid">
          {recoveryStreak >= 7 && (
            <div className="achievement unlocked">
              <span className="achievement-icon">🏆</span>
              <span className="achievement-label">Week Warrior</span>
            </div>
          )}
          {avgSleep >= 7.5 && (
            <div className="achievement unlocked">
              <span className="achievement-icon">😴</span>
              <span className="achievement-label">Sleep Champion</span>
            </div>
          )}
          {avgRecovery >= 60 && (
            <div className="achievement unlocked">
              <span className="achievement-icon">💚</span>
              <span className="achievement-label">Recovery Pro</span>
            </div>
          )}
          {avgHRV >= 50 && (
            <div className="achievement unlocked">
              <span className="achievement-icon">💓</span>
              <span className="achievement-label">HRV Elite</span>
            </div>
          )}
          {summary.recent_workouts.length >= 5 && (
            <div className="achievement unlocked">
              <span className="achievement-icon">💪</span>
              <span className="achievement-label">Active Life</span>
            </div>
          )}
          {avgDeepSleep >= 1.5 && (
            <div className="achievement unlocked">
              <span className="achievement-icon">🌙</span>
              <span className="achievement-label">Deep Sleeper</span>
            </div>
          )}
          {recoveryStreak < 7 && (
            <div className="achievement locked">
              <span className="achievement-icon">🔒</span>
              <span className="achievement-label">7-day streak</span>
            </div>
          )}
          {avgHRV < 50 && (
            <div className="achievement locked">
              <span className="achievement-icon">🔒</span>
              <span className="achievement-label">HRV above 50</span>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default HealthDashboard
