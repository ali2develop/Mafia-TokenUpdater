# 🔑 TSun JWT Token Auto-Updater with Beautiful Dashboard

Automated token fetcher with a **stunning web dashboard** for monitoring progress in real-time. Supports automatic scheduling via external cron services.

## ✨ Features

### 🔥 Premium Cyberpunk Dashboard
- **Hand-crafted UI** with fire-orange accents and glassmorphism
- **Real-time progress bars** with gradient effects and live statistics
- **Auto-updating interface** (refreshes every 2 seconds)
- **Live log streaming** using Server-Sent Events
- **Terminal-style logs** with color-coded messages
- **Run history** with success rate tracking
- **Professional typography** (Outfit, Inter, JetBrains Mono)
- **Mesh gradient background** with subtle grid overlay
- **One-click manual trigger** for testing
- **Fully responsive** design (mobile, tablet, desktop)

### 🔧 Core Functionality
- ✅ Auto-detects all `accounts_{server}.json` files from the `accounts/` folder
- ✅ **Multi-API fallback** (3 endpoints with automatic rotation)
- ✅ **Global rate limit handling** (5-second coordinated pause)
- ✅ Fetches JWT tokens concurrently with retry logic and exponential backoff
- ✅ Automatically pushes updated tokens to GitHub repository
- ✅ **Automated scheduling** via free external cron service (no manual clicks)
- ✅ Cleans up local token files after successful GitHub upload
- ✅ Supports multiple regions/servers (pk, ind, br, bd, us, etc.)

## 🚀 Quick Start (Recommended: Vercel + Free Cron)

This setup gives you:
- ✅ Free hosting on Vercel
- ✅ Automatic execution every 6 hours (via cron-job.org)
- ✅ Beautiful web dashboard to monitor progress
- ✅ Zero maintenance required

### Setup Instructions

### 1. Deploy to Vercel

**Option A: Deploy via Vercel Dashboard**
1. Push your code to GitHub
2. Go to [vercel.com](https://vercel.com) and sign in
3. Click "Import Project" → Select your GitHub repository
4. Vercel will auto-detect Python and use `vercel.json` config
5. Click "Deploy"

**Option B: Deploy via Vercel CLI**
```bash
npm i -g vercel
vercel --prod
```

### 2. Setup Neon PostgreSQL Database (Execution History)

**Create a free Neon database:**
1. Go to [neon.tech](https://neon.tech) and sign up (free tier available)
2. Click "Create Project"
3. Name your project (e.g., "TSun Token Fetcher")
4. Select a region closest to your Vercel deployment
5. Click "Create Project"

**Initialize the database schema:**
1. In Neon dashboard, go to your project → **SQL Editor**
2. Copy the contents of `schema.sql` from this repository
3. Paste into the SQL Editor and click "Run"
4. Verify tables were created:
   ```sql
   SELECT table_name FROM information_schema.tables 
   WHERE table_schema = 'public' AND table_name IN ('runs', 'region_results');
   ```
5. Copy your **Database Connection String** from Neon dashboard (format: `postgresql://user:password@host/database`)

### 3. Configure Environment Variables in Vercel

Create a GitHub Personal Access Token with `repo` permissions:
1. Go to GitHub Settings → Developer Settings → Personal Access Tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Select scope: `repo` (Full control of private repositories)
4. Copy the generated token

1. Go to your Vercel project → **Settings** → **Environment Variables**
2. Add the following variables (select "Production, Preview, Development" for all):

| Key | Value | Description |
|-----|-------|-------------|
| `DATABASE_URL` | `postgresql://user:pass@host/db?sslmode=require` | Neon database connection string |
| `GITHUB_TOKEN` | `ghp_your_token_here` | GitHub Personal Access Token |
| `GITHUB_REPO_OWNER` | `Github_Username` | Repository owner |
| `GITHUB_REPO_NAME` | `repo_name` | Repository name |
| `GITHUB_BRANCH` | `main` | Target branch |
| `GITHUB_BASE_PATH` | `folder_name` | Path in repo |
| `RUN_ENABLED` | `true` | **IMPORTANT**: Set to `true` to allow executions (kill switch) |
| `RUN_SECRET_TOKEN` | `your-strong-random-string` | **SECURITY**: Secret token to authenticate run requests |

3. Click "Redeploy" in Vercel dashboard

### 4. Upload Account Files

Your account files should already be in the `accounts/` folder:

Place your account JSON files in the `accounts/` folder with the naming pattern:
- `accounts_pk.json` → Will create `token_pk.json` on GitHub
- `accounts_ind.json` → Will create `token_ind.json` on GitHub
- `accounts_br.json` → Will create `token_br.json` on GitHub
- `accounts_bd.json` → Will create `token_bd.json` on GitHub
- `accounts_us.json` → Will create `token_us.json` on GitHub

**Account file format:**
```json
[
  {
    "uid": 4293441911,
    "password": "password_here",
    "accountId": "13882506893",
    "accountNickname": "nickname"
  }
]
```

- `accounts_pk.json`
- `accounts_ind.json`
- etc.

Make sure they're committed to your GitHub repository.

### 5. Setup Free Auto-Scheduling (cron-job.org)

**This step enables automatic execution every 6 hours:**

1. Go to [cron-job.org](https://console.cron-job.org/) (100% free, no credit card)
2. Create a free account (or use without registration)
3. Click "Create Cron Job"
4. Configure:
   - **Title**: TSun Token Fetcher
   - **URL**: `https://your-app-name.vercel.app/api/run`
   - **Schedule**: Every 6 hours
     - Cron expression: `0 */6 * * *`
     - Or use the visual picker: Select "Every 6 hours"
5. Click "Create"

**That's it!** Your token fetcher will now run automatically every 6 hours. ✅

### 6. Access Your Dashboard

Visit `https://your-app-name.vercel.app` to see the **premium cyberpunk dashboard** with:
- 🔥 **Fire-orange accents** with glassmorphic cards
- 📊 **Real-time progress bars** with gradient effects
- 📜 **Terminal-style live logs** with color coding
- 📈 **Run history** with success rate tracking (stored in Neon database)
- ⚡ **Performance metrics** (speed, success rate, failures)
- 🚀 **Manual "Execute Now"** button for testing
- 🎨 **Premium dark theme** with mesh gradient background

**Note:** The execution history table displays real data from your Neon database. Each run is automatically saved with detailed region-wise statistics.

---

## 📊 Database Schema

The application uses Neon PostgreSQL to store execution history:

### Tables

**runs** - Stores execution metadata
- `id` (Primary Key)
- `run_number` - Sequential run number
- `started_at` - Execution start timestamp
- `completed_at` - Execution completion timestamp
- `total_duration_seconds` - Total run duration
- `status` - Run status (running, completed, timeout, error)

**region_results** - Stores per-region results
- `id` (Primary Key)
- `run_id` (Foreign Key → runs.id)
- `region` - Region code (BD, IND, PK)
- `total_accounts` - Total accounts processed
- `success_count` - Successful token fetches
- `failed_count` - Failed attempts
- `timed_out_count` - Timed out requests
- `success_rate` - Success percentage
- `duration_seconds` - Region processing duration

### Querying History

```sql
-- Get last 10 runs with region details
SELECT r.run_number, r.started_at, r.status,
       rr.region, rr.total_accounts, rr.success_rate
FROM runs r
JOIN region_results rr ON r.id = rr.run_id
ORDER BY r.started_at DESC
LIMIT 10;
```

---

## 🖥️ Local Development

To run the dashboard locally for testing:

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file with credentials
cat > .env << EOF
DATABASE_URL=postgresql://user:pass@host/database?sslmode=require
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPO_OWNER=Your-Username
GITHUB_REPO_NAME=Your-Repo
GITHUB_BRANCH=main
GITHUB_BASE_PATH=Spam-api
EOF

# Run the Flask app
python web_app.py
```

Visit `http://localhost:5000` to see the dashboard.

**Local Database Setup:**
- The app will automatically create tables using `db.init_db()` on startup
- Make sure your `DATABASE_URL` in `.env` is correct
- Tables will be created if they don't exist

---

## 📖 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/api/run` | GET/POST | Trigger token fetch (called by cron) |
| `/api/status` | GET | Get current job status (JSON) |
| `/api/logs` | GET | Stream logs (Server-Sent Events) |
| `/api/history` | GET | Get run history (JSON) |
| `/health` | GET | Health check |

---

## Configuration

Edit `app.py` to customize:

```python
# Scheduler interval (hours)
SCHEDULE_INTERVAL_HOURS = 6

# Concurrent API requests
MAX_CONCURRENT_REQUESTS = 100

# Retry settings
MAX_RETRIES = 15
INITIAL_DELAY = 5
MAX_DELAY = 120

# GitHub repository settings
GITHUB_REPO_OWNER = "TSun-FreeFire"
GITHUB_REPO_NAME = "TSun-FreeFire-Storage"
GITHUB_BRANCH = "main"
GITHUB_BASE_PATH = "Spam-api"
```

## GitHub File Paths

Tokens are automatically pushed to:
```
https://raw.githubusercontent.com/TSun-FreeFire/TSun-FreeFire-Storage/refs/heads/main/Spam-api/token_{server}.json
```

Example URLs:
- `token_pk.json` → `.../Spam-api/token_pk.json`
- `token_ind.json` → `.../Spam-api/token_ind.json`
- `token_br.json` → `.../Spam-api/token_br.json`

## How It Works

1. **Startup**: Script scans `accounts/` folder for all `accounts_*.json` files
2. **Token Fetching**: For each account file, fetches JWT tokens concurrently from the API
3. **Retry Logic**: Failed requests are retried up to 15 times with exponential backoff
4. **Local Save**: Tokens are temporarily saved to `tokens/token_{server}.json`
5. **GitHub Push**: Updated tokens are pushed to GitHub repository, replacing old content
6. **Cleanup**: Local token files are deleted after successful GitHub push
7. **Sleep**: Script waits 6 hours before the next refresh cycle
8. **Repeat**: Process continues indefinitely

## Error Handling

- **API Failures**: Retries up to 15 times with exponential backoff (5s to 120s delays)
- **GitHub Push Failures**: Retries up to 15 times, keeps local file if all attempts fail
- **Network Issues**: Handles timeouts, connection errors, and JSON decode errors
- **Partial Failures**: Continues processing other regions even if one fails

## Logs

The script provides detailed logging:
- ✅ Success messages for token fetches and GitHub pushes
- ⚠️ Warnings for retries and non-critical errors
- ❌ Error messages for failures
- 💀 Final failure messages after max retries
- 🗑️ Cleanup confirmation messages

## 🎯 How Auto-Scheduling Works

```
┌─────────────────────────────────────┐
│  cron-job.org (Free Service)        │
│  Triggers: Every 6 hours            │
│  Action: GET /api/run               │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Your Vercel App                    │
│  • Receives automated ping          │
│  • Starts background job            │
│  • Returns 200 OK immediately       │
│  • Fetches tokens concurrently      │
│  • Streams logs to dashboard        │
│  • Pushes results to GitHub         │
└─────────────────────────────────────┘
```

**No manual clicks needed!** The system runs fully automatically.

**Note:** Vercel serverless functions have a 300-second timeout limit. For long-running tasks, consider using:
- Vercel Cron Jobs
- GitHub Actions (recommended for scheduled tasks)
- Self-hosted deployment

## 🔥 Cyberpunk Dashboard Features

### Premium Visual Design
- **Fire-orange accent color** (#FF4500) with glow effects
- **Glassmorphism cards** with backdrop-blur(12px)
- **Mesh gradient background** (orange + purple radial gradients)
- **Grid overlay** with radial fade mask for depth
- **Professional typography** using Outfit, Inter, and JetBrains Mono fonts

### Real-Time Updates
- **Status Indicator**: Animated dots (Idle/Running/Error) with pulsing glow
- **Progress Bar**: Fire-to-purple gradient with shimmer animation
- **Live Statistics**: Success count, failed count, speed (accounts/sec)
- **Terminal Logs**: Color-coded entries with smooth animations
- **Auto-refresh**: Status (2s), History (10s), Logs (real-time SSE)

### Interactive Elements
- **Pill Navigation Tabs**: Centered, modern tab design
- **Execute Now Button**: Uppercase, bold, fire-orange with glow
- **Hover Effects**: Smooth translateY(-4px) with border glow
- **Loading States**: Dual rotating border spinner

### Responsive Design
- **Mobile**: Single column layout, full-width buttons
- **Tablet**: 2-column grid for cards
- **Desktop**: Multi-column grid, centered 1200px container

---

## 🔧 Configuration

Edit environment variables in Vercel dashboard or `.env` for local:

```python
# Scheduler interval (controlled by cron-job.org)
SCHEDULE_INTERVAL_HOURS = 6

# Concurrent API requests
MAX_CONCURRENT_REQUESTS = 100

# Retry settings
MAX_RETRIES = 15
INITIAL_DELAY = 5
MAX_DELAY = 120
```

---

## 🐛 Troubleshooting

### Vercel Deployment Issues

**Error: "Environment Variable references Secret"**
- ✅ **Solution:** Remove the `env` section from `vercel.json`
- Add variables directly in Vercel dashboard

**Error: "Serverless Function has crashed"**
- ✅ **Solution:** This is fixed! The app now uses background threading
- Vercel function returns immediately and processes in background

**Error: "No GitHub token found"**
- ✅ **Solution:** Add `GITHUB_TOKEN` in Vercel environment variables
- Ensure it's set for Production, Preview, and Development

### Cron Job Not Triggering

**Tokens not updating automatically**
- ✅ Check cron-job.org dashboard for execution history
- ✅ Verify the URL is correct: `https://your-app.vercel.app/api/run`
- ✅ Test manually by clicking "Force Run Now" in dashboard

### Local Development

**"Module not found" errors**
- ✅ Run `pip install -r requirements.txt`

**"No account files found"**
- ✅ Add `accounts_*.json` files to `accounts/` folder

---

## 📊 System Architecture

```
accounts/
  ├── accounts_pk.json     → Token fetcher → GitHub
  ├── accounts_ind.json    → Token fetcher → GitHub  
  └── accounts_bd.json     → Token fetcher → GitHub

web_app.py               → Flask server with dashboard
core/token_fetcher.py    → Core fetching logic
templates/dashboard.html → Beautiful UI
data/run_history.json    → Persistent run history
```

## Notes

- Local `tokens/` folder is used only temporarily and cleaned after GitHub push
- Script runs continuously - use Ctrl+C to stop
- Each region is processed independently
- Failed accounts are logged but don't stop the entire process