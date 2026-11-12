# My Personal Dashboard

A personal health dashboard that integrates with WHOOP to display health metrics, recovery scores, sleep analysis, and hypertrophy workout tracking.

## Features

### WHOOP Health Tracking
- **WHOOP Integration**: OAuth2 authentication with WHOOP API
- **Health Metrics**: HRV, resting heart rate, recovery scores
- **Sleep Analysis**: Deep sleep, REM, sleep efficiency tracking
- **Interactive Charts**: Visual trends for all key metrics
- **Gamification**: Streaks and achievements for motivation
- **Offline Support**: Local SQLite database for fast access
- **Auto Sync**: Daily cron job to fetch latest data

### Apple Health Sync (iPhone app)
- **[apple-health-sync/](./apple-health-sync)**: a small iPhone app that copies Apple Health data (activity, heart, sleep, body & vitals) into your own Supabase database, in the background
- Runs on a free Apple ID; a Mac script keeps it installed past the 7-day free-signing limit
- Row-Level Security means each account can only ever see its own rows
- MIT licensed, so anyone can use it. Setup is in its own README.

### Hypertrophy Training
- **4-Day Upper/Lower Split**: Pre-configured workout program
- **Workout Logging**: Track sets, reps, and weight for each exercise
- **Progressive Overload**: Auto-suggests weight increases when you hit rep targets
- **Baseline Weights**: Starting weights calibrated to your body profile
- **Rest Timer**: Built-in timer between sets
- **Volume Tracking**: Chart showing total volume over time

## Project Structure

```
my-personal-dashboard/
├── backend/                 # Python FastAPI backend
│   ├── api.py              # REST API endpoints
│   ├── database.py         # SQLite database & repository
│   ├── models.py           # Pydantic data models
│   ├── whoop_client.py     # WHOOP API client
│   ├── sync_service.py     # Data sync service
│   └── requirements.txt    # Python dependencies
├── frontend/               # React frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── HealthDashboard.jsx
│   │   │   ├── HypertrophyDashboard.jsx
│   │   │   ├── HypertrophyDashboard.css
│   │   │   ├── FinanceDashboard.jsx
│   │   │   └── OthersDashboard.jsx
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── package.json
├── apple-health-sync/      # iPhone app: Apple Health → Supabase (MIT)
├── start.sh                # Start all services
├── stop.sh                 # Stop all services
├── setup_sync.sh           # Setup daily sync job
└── README.md
```

## Prerequisites

- Python 3.9+
- Node.js 18+
- WHOOP account and API credentials

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/vishalkotak/my-personal-dashboard.git
cd my-personal-dashboard
```

### 2. Configure environment

Create a `.env` file in the root directory:

```bash
cp .env.example .env
```

Edit `.env` and add your WHOOP API credentials:

```
WHOOP_CLIENT_ID=your_client_id
WHOOP_CLIENT_SECRET=your_client_secret
```

Get credentials from [WHOOP Developer Portal](https://developer.whoop.com).

### 3. Install dependencies

**Backend:**
```bash
cd backend
pip3 install -r requirements.txt
```

**Frontend:**
```bash
cd frontend
npm install
```

### 4. Start the application

```bash
./start.sh
```

This starts:
- API server at http://localhost:8000
- Frontend at http://localhost:5173

### 5. Authenticate with WHOOP

1. Open http://localhost:5173
2. Click "Connect WHOOP"
3. Complete OAuth flow
4. Data will sync automatically

## Usage

### Start/Stop Services

```bash
./start.sh   # Start API and frontend
./stop.sh    # Stop all services
```

### API Endpoints

#### WHOOP Health

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /auth/login` | Start OAuth flow |
| `GET /auth/status` | Check auth status |
| `GET /summary?days=14` | Get health summary |
| `GET /recovery` | Get recovery data |
| `GET /sleep` | Get sleep data |
| `GET /workouts` | Get workout data |
| `POST /sync` | Trigger manual sync |

#### Hypertrophy Training

| Endpoint | Description |
|----------|-------------|
| `GET /gym/templates` | Get workout templates |
| `GET /gym/templates/{id}` | Get template with exercises |
| `POST /gym/sessions` | Start a workout session |
| `GET /gym/sessions/{id}` | Get session details |
| `PUT /gym/sessions/{id}/complete` | Complete a session |
| `POST /gym/sessions/{id}/sets` | Log a set |
| `DELETE /gym/sessions/{id}/sets/{set}` | Delete a set |
| `GET /gym/exercises/{id}/suggest` | Get weight suggestion |
| `GET /gym/volume-history` | Get volume trends |

API documentation: http://localhost:8000/docs

### Setup Daily Sync

To automatically sync data daily:

```bash
./setup_sync.sh
```

This creates a launchd job (macOS) that runs at 12:30 AM daily.

## Tech Stack

**Backend:**
- FastAPI (Python web framework)
- SQLite (local database)
- WHOOP API v2

**Frontend:**
- React 18
- Recharts (interactive charts)
- Vite (build tool)

## Health Metrics Explained

The dashboard prioritizes metrics based on scientific research:

1. **HRV (Heart Rate Variability)** - Most predictive biomarker for overall health and stress resilience
2. **Sleep Architecture** - Deep sleep (1.5-2h needed) is critical for physical recovery
3. **Resting Heart Rate** - Lower RHR indicates better cardiovascular fitness
4. **Recovery Score** - Composite metric based on HRV, RHR, and sleep

## License

Private - Personal Use Only, except `apple-health-sync/`, which is MIT licensed (see its LICENSE file).
