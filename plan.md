
## Vercel vs Render Comparison

### Key Differences

| Feature | Vercel (Current) | Render (Alternative) |
|---------|------------------|---------------------|
| **Type** | Serverless Functions | Long-lived Web Service |
| **Timeout** | 50s (Hobby), 300s (Pro) | **No timeout limit** |
| **Execution** | Function dies after timeout | Process runs continuously |
| **Best For** | Quick API responses | **Long-running tasks** ✅ |
| **Free Tier** | Yes | Yes (750 hours/month) |
| **Custom Domain** | Easy | Easy |
| **Environment Variables** | Dashboard | Dashboard |
| **GitHub Integration** | Excellent | Excellent |
| **Cold Starts** | Yes (~1-2s) | Minimal (keeps running) |

**Verdict:** ✅ **Render is BETTER for your use case** (long token fetching tasks)

---

## Why Render Solves Your Problem

### Current Issue on Vercel
```
Start → BD (12s) → IND (12s) → [TIMEOUT at 50s] → ❌ PK never reached
```

### With Render
```
Start → BD (12s) → IND (12s) → PK (as long as needed) ✅ → All regions completed!
```

**On Render:**
- No 50-second timeout
- Process runs as long as needed
- Can handle 100, 1000, or even 10,000 accounts
- Background job can run for minutes or hours

---

## Render Setup Steps

### 1. Prerequisites

✅ You already have:
- GitHub repository with code
- Neon PostgreSQL database
- GitHub Personal Access Token

---

### 2. Create Render Account

1. Go to [render.com](https://render.com)
2. Sign up with GitHub (free)
3. Connect your GitHub account

---

### 3. Deploy Web Service

**Step-by-step:**

1. **In Render Dashboard:**
   - Click "New +" → "Web Service"
   - Select your GitHub repository
   - Click "Connect"

2. **Configure Web Service:**
   ```
   Name: tsun-token-fetcher
   Region: Oregon (or closest to you)
   Branch: main
   Root Directory: (leave blank)
   Runtime: Python 3
   Build Command: pip install -r requirements.txt
   Start Command: python app.py
   ```

3. **Select Plan:**
   - Free tier (750 hours/month)
   - Or Starter ($7/month) for always-on

4. **Add Environment Variables:**
   ```
   DATABASE_URL = postgresql://user:pass@host/db?sslmode=require
   GITHUB_TOKEN = ghp_your_token_here
   GITHUB_REPO_OWNER = Your-Username
   GITHUB_REPO_NAME = Your-Repo
   GITHUB_BRANCH = main
   GITHUB_BASE_PATH = folder-name
   RUN_ENABLED = true
   RUN_SECRET_TOKEN = your-secret-token
   ```

5. **Click "Create Web Service"**

**Render will:**
- Clone your repo
- Install dependencies
- Start Flask server
- Give you a URL: `https://tsun-token-fetcher.onrender.com`

---

### 4. Setup Cron Job

**Option A: External Cron (Recommended)**

Use cron-job.org (same as before):
```
URL: https://tsun-token-fetcher.onrender.com/api/run?token=your-secret
Schedule: Every 6 hours (0 */6 * * *)
```

**Option B: Render Cron Jobs (Paid Feature)**

Render has built-in cron jobs but requires Starter plan ($7/month):
- Dashboard → Cron Jobs → Create
- Schedule: `0 */6 * * *`
- Command: `curl https://your-app.onrender.com/api/run?token=secret`

---

### 5. Code Adjustments for Render

**Minimal changes needed!**

#### Update app.py (Minor Fix)

```python
# Current code already works!
# But you can remove serverless detection since Render = always local mode

# Change:
if IS_SERVERLESS:
    result = run_sync_job()  # This was for Vercel
else:
    run_async_job()  # This will run on Render ✅

# On Render: IS_SERVERLESS = False
# So it uses run_async_job() which has NO timeout!
```

**No other changes needed!** Your current code already supports Render.

---

## Render Free Plan Limits

| Resource | Free Tier Limit | Your Usage |
|----------|----------------|------------|
| Hours/Month | 750 hours | ~30 days if always-on ✅ |
| Instances | Sleeps after 15 min inactivity | Wakes on request ✅ |
| Memory | 512 MB | Enough for Flask ✅ |
| Build Minutes | 500 min/month | Uses ~2 min/deploy ✅ |

**Note:** Free tier sleeps after 15 minutes of inactivity
- First request after sleep: 30-60s wake-up time
- Subsequent requests: Fast
- **Solution:** Use cron to ping every 10 minutes to keep awake

---

## Migration Steps (Vercel → Render)

### Step 1: Keep Vercel Running (Backup)
- Don't delete Vercel deployment yet
- Test Render first

### Step 2: Deploy to Render
- Follow setup steps above
- Get Render URL

### Step 3: Test on Render
- Visit `https://your-app.onrender.com`
- Click "Execute Token Refresh"
- Enter secret token
- Wait for ALL regions to complete (including PK!)

### Step 4: Update Cron Job
- Go to cron-job.org
- Update URL from Vercel to Render
- Keep both active for a week

### Step 5: Verify Success
- Check Neon database
- Verify all 3 regions (BD, IND, PK) processed ✅
- Confirm no timeout errors

### Step 6: Decommission Vercel (Optional)
- Once Render is stable
- Delete Vercel deployment
- Save costs

---

## Hybrid Approach (Best of Both Worlds)

Use BOTH platforms for different purposes:

| Platform | Use For |
|----------|---------|
| **Render** | Main production runs (no timeout) |
| **Vercel** | Dashboard only (fast, global CDN) |

**Setup:**
1. Render: Run `app.py` for executions
2. Vercel: Serve static dashboard with Render API

**Benefits:**
- Dashboard loads fast (Vercel CDN)
- Executions complete fully (Render)

---

## Cost Comparison

### Current Setup (Vercel)
- ❌ Timeout issues
- ✅ Free
- ⚠️ Need Pro ($20/month) to fix

### Render Free
- ✅ No timeouts
- ✅ Free
- ⚠️ Sleeps after 15 min (acceptable)

### Render Starter ($7/month)
- ✅ No timeouts
- ✅ Always-on (no sleep)
- ✅ Built-in cron jobs
- ✅ Cheaper than Vercel Pro

---

## Recommendation

### Immediate Action: Deploy to Render (Free)

**Why:**
1. ✅ Solves timeout issue immediately
2. ✅ Free (no credit card needed)
3. ✅ Minimal code changes (already compatible)
4. ✅ Can process all regions (BD, IND, PK)
5. ✅ Same features as Vercel

**How long:** 1-2 hours to deploy and test

---

## Alternative: Fix Vercel Without Migration

If you prefer to stay on Vercel, you can:

1. **Split account files** (no code changes)
   - Limit each file to 200-300 accounts
   - Process completes in <50s

2. **Upgrade to Vercel Pro** ($20/month)
   - Get 300s timeout
   - More expensive than Render

3. **Use Vercel Cron Jobs** (separate feature)
   - Different from serverless functions
   - Longer timeouts
   - Requires Pro plan

---
# To-dos (4)
- [ ] **Create Render account**: Sign up at render.com with GitHub
- [ ] **Deploy web service**: Connect repo, configure Python, add env vars
- [ ] **Test execution**: Verify all regions (BD, IND, PK) complete successfully
- [ ] **Update cron job**: Point to Render URL instead of Vercel