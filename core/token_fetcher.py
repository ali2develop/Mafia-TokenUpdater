"""
Core token fetching logic - extracted from app.py for reusability.
This module handles the actual token fetching process.
"""

import aiohttp
import asyncio
import json
import os
import urllib.parse
import time
import random
import base64
from pathlib import Path
from datetime import datetime

# --- Configuration ---
# Detect serverless environment
IS_SERVERLESS = os.getenv('VERCEL') == '1'

# Use /tmp for serverless, local paths otherwise
ACCOUNTS_DIR = Path('accounts')
TOKENS_DIR = Path('/tmp/tokens') if IS_SERVERLESS else Path('tokens')

# Multiple API URLs - now used for DISTRIBUTION (not fallback)
API_URLS = [
    "https://jwt.tsunstudio.pw/v1/auth/saeed?uid={uid}&password={password}",
    "https://tsun-ff-jwt-api.onrender.com/v1/auth/saeed?uid={uid}&password={password}",
    "https://jwt-tsunstudio.onrender.com/v1/auth/saeed?uid={uid}&password={password}"
]

# Rate-limit optimized configuration
MAX_CONCURRENT_PER_API = 30  # Concurrent requests per API (reduced from 100 total)
BATCH_SIZE = 30              # Process accounts in batches
BATCH_DELAY = 2.0            # Seconds to wait between batches
MAX_RETRIES = 15
INITIAL_DELAY = 5
MAX_DELAY = 120
GITHUB_MAX_RETRIES = 15

# GitHub Configuration
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN') or os.getenv('GPH') or os.getenv('VERCEL_GITHUB_TOKEN')
GITHUB_REPO_OWNER = os.getenv('GITHUB_REPO_OWNER', 'TSun-FreeFire')
GITHUB_REPO_NAME = os.getenv('GITHUB_REPO_NAME', 'TSun-FreeFire-Storage')
GITHUB_BRANCH = os.getenv('GITHUB_BRANCH', 'main')
GITHUB_BASE_PATH = os.getenv('GITHUB_BASE_PATH', 'Spam-api')
GITHUB_API_BASE = "https://api.github.com"


class RateLimitManager:
    """Global manager to coordinate rate limit pauses across all concurrent requests."""
    def __init__(self):
        self.first_error_occurred = asyncio.Event()
        self.pause_in_progress = False
        self.lock = asyncio.Lock()
    
    async def handle_rate_limit(self, uid: str):
        async with self.lock:
            if not self.first_error_occurred.is_set():
                self.first_error_occurred.set()
                self.pause_in_progress = True
                return True
            return False
    
    def reset(self):
        self.first_error_occurred.clear()
        self.pause_in_progress = False


class LogCollector:
    """Collects logs during token fetching for dashboard display."""
    def __init__(self):
        self.logs = []
        self.max_logs = 500
    
    def add(self, message, level="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append({
            "timestamp": timestamp,
            "message": message,
            "level": level
        })
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
    
    def get_recent(self, count=100):
        return self.logs[-count:] if self.logs else []
    
    def clear(self):
        self.logs = []


async def fetch_token_with_timeout(session, uid, password, api_url, api_name, stats, pause_event, log_collector=None, timeout=180):
    """Wrapper to enforce per-account timeout."""
    try:
        return await asyncio.wait_for(
            fetch_token(session, uid, password, api_url, api_name, stats, pause_event, log_collector),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        stats['failed'] += 1
        stats['completed'] += 1
        stats['timed_out'] = stats.get('timed_out', 0) + 1
        if log_collector:
            log_collector.add(f"⏱️ {api_name}: Account {uid} timed out after {timeout}s", "warning")
        return None


def distribute_accounts_across_apis(accounts):
    """
    Distributes accounts evenly across all 3 APIs.
    Returns list of (api_url, api_name, accounts_group) tuples.
    """
    total = len(accounts)
    accounts_per_api = total // len(API_URLS)
    remainder = total % len(API_URLS)
    
    distributed = []
    start_idx = 0
    
    for i, api_url in enumerate(API_URLS):
        # Distribute remainder evenly (first APIs get +1 account if remainder exists)
        group_size = accounts_per_api + (1 if i < remainder else 0)
        end_idx = start_idx + group_size
        
        api_name = f"API_{i + 1}"
        accounts_group = accounts[start_idx:end_idx]
        
        distributed.append((api_url, api_name, accounts_group))
        start_idx = end_idx
    
    return distributed


async def process_api_batch(session, api_url, api_name, accounts, stats, pause_event, log_collector=None):
    """
    Process accounts assigned to a specific API in controlled batches.
    Returns list of token results.
    """
    if not accounts:
        return []
    
    total_accounts = len(accounts)
    all_results = []
    
    if log_collector:
        log_collector.add(f"🎯 {api_name}: Processing {total_accounts} accounts", "info")
    
    # Process in batches to avoid overwhelming the API
    for batch_idx in range(0, total_accounts, BATCH_SIZE):
        batch = accounts[batch_idx:batch_idx + BATCH_SIZE]
        batch_num = (batch_idx // BATCH_SIZE) + 1
        total_batches = (total_accounts + BATCH_SIZE - 1) // BATCH_SIZE
        
        if log_collector and total_batches > 1:
            log_collector.add(f"📦 {api_name}: Batch {batch_num}/{total_batches} ({len(batch)} accounts)", "info")
        
        # Create tasks for this batch with per-API concurrency limit
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PER_API)
        
        async def bounded_fetch(acc):
            async with semaphore:
                return await fetch_token_with_timeout(
                    session, acc["uid"], acc["password"], 
                    api_url, api_name, stats, pause_event, log_collector
                )
        
        tasks = [bounded_fetch(acc) for acc in batch]
        batch_results = await asyncio.gather(*tasks)
        all_results.extend(batch_results)
        
        # Add delay between batches (except for last batch)
        if batch_idx + BATCH_SIZE < total_accounts:
            if log_collector:
                log_collector.add(f"⏸️ {api_name}: Waiting {BATCH_DELAY}s before next batch...", "info")
            await asyncio.sleep(BATCH_DELAY)
    
    successful = sum(1 for r in all_results if r is not None)
    if log_collector:
        log_collector.add(f"✅ {api_name}: Complete - {successful}/{total_accounts} tokens", "success")
    
    return all_results


async def fetch_token(session, uid, password, api_url, api_name, stats, pause_event, log_collector=None):
    """
    Fetches a single JWT token using the ASSIGNED API only (no fallback).
    Each account is sticky to one API to distribute load evenly.
    """
    encoded_uid = urllib.parse.quote(str(uid))
    encoded_password = urllib.parse.quote(password)
    url = api_url.format(uid=encoded_uid, password=encoded_password)
    start_time = time.time()
    
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                base_delay = min(INITIAL_DELAY * (2 ** (attempt - 1)), MAX_DELAY)
                delay = base_delay + random.uniform(0, 5)
                await asyncio.sleep(delay)
            
            async with session.get(url, ssl=False, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    token = data.get("token")
                    if token:
                        stats['success'] += 1
                        stats['completed'] += 1
                        # Track which API was used
                        stats.setdefault('api_usage', {})
                        stats['api_usage'][api_name] = stats['api_usage'].get(api_name, 0) + 1
                        return {"token": token}
                    else:
                        if log_collector and attempt == 0:
                            log_collector.add(f"⚠️ {api_name}: Token missing for {uid}", "warning")
                
                elif resp.status == 429:
                    if log_collector and attempt == 0:
                        log_collector.add(f"⚠️ {api_name}: Rate limit for {uid} - will retry", "warning")
                    
                    # Coordinate pause if needed
                    rate_limit_manager = stats.get('rate_limit_manager')
                    if rate_limit_manager:
                        is_first = await rate_limit_manager.handle_rate_limit(uid)
                        if is_first:
                            pause_event.set()
                            await asyncio.sleep(5)
                            pause_event.clear()
                            rate_limit_manager.pause_in_progress = False
                        else:
                            if pause_event.is_set():
                                await pause_event.wait()
                                await asyncio.sleep(0.1)
                
                elif resp.status == 500:
                    if log_collector and attempt == 0:
                        log_collector.add(f"🔥 {api_name}: Server error for {uid}", "warning")
                else:
                    if log_collector and attempt == 0:
                        log_collector.add(f"❓ {api_name}: Status {resp.status} for {uid}", "warning")
        
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
            if log_collector and attempt == 0:
                log_collector.add(f"🔌 {api_name}: {type(e).__name__} for {uid}", "warning")
        
        if attempt == MAX_RETRIES - 1:
            break
    
    elapsed = time.time() - start_time
    if elapsed > 120 and log_collector:
        log_collector.add(f"🐌 {api_name}: Slow account {uid}: {elapsed:.1f}s", "warning")
    
    if log_collector:
        log_collector.add(f"❌ {api_name}: Failed {uid} after {MAX_RETRIES} attempts", "error")
    
    stats['failed'] += 1
    stats['completed'] += 1
    return None


async def get_github_file_sha(session, filename):
    """Get the SHA of an existing file on GitHub."""
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_BASE_PATH}/{filename}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        async with session.get(url, headers=headers, ssl=False, timeout=30) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("sha")
            return None
    except Exception:
        return None


async def push_to_github(session, filename, content, log_collector=None):
    """Push token file to GitHub with retry logic."""
    if not GITHUB_TOKEN:
        if log_collector:
            log_collector.add("❌ GitHub token not configured", "error")
        return False
    
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_BASE_PATH}/{filename}"
    
    for attempt in range(GITHUB_MAX_RETRIES):
        try:
            if attempt > 0:
                delay = min(INITIAL_DELAY * (2 ** (attempt - 1)), MAX_DELAY) + random.uniform(0, 5)
                await asyncio.sleep(delay)
            
            sha = await get_github_file_sha(session, filename)
            content_json = json.dumps(content, indent=2)
            content_base64 = base64.b64encode(content_json.encode('utf-8')).decode('utf-8')
            
            payload = {
                "message": f"Auto-update {filename} - {time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                "content": content_base64,
                "branch": GITHUB_BRANCH
            }
            
            if sha:
                payload["sha"] = sha
            
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            async with session.put(url, json=payload, headers=headers, ssl=False, timeout=30) as resp:
                if resp.status in [200, 201]:
                    if log_collector:
                        log_collector.add(f"✅ Pushed {filename} to GitHub", "success")
                    return True
        
        except Exception:
            pass
    
    if log_collector:
        log_collector.add(f"❌ Failed to push {filename} to GitHub", "error")
    return False


async def process_region(session, account_filepath, stats, log_collector=None):
    """
    Process a single region's accounts using PARALLEL API distribution.
    Accounts are split evenly across all 3 APIs and processed simultaneously.
    """
    try:
        region = account_filepath.stem.split('_')[-1].lower()
    except IndexError:
        return None
    
    try:
        with open(account_filepath, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
    except Exception as e:
        if log_collector:
            log_collector.add(f"❌ Error loading {account_filepath.name}: {str(e)}", "error")
        return None
    
    valid_accounts = [
        acc for acc in accounts 
        if isinstance(acc, dict) and 'uid' in acc and 'password' in acc
    ]
    
    total = len(valid_accounts)
    if total == 0:
        return None
    
    if log_collector:
        log_collector.add(f"🔑 Starting {region.upper()} - {total} accounts across {len(API_URLS)} APIs", "info")
    
    # Distribute accounts across APIs
    api_distribution = distribute_accounts_across_apis(valid_accounts)
    
    for api_url, api_name, accounts_group in api_distribution:
        if log_collector:
            log_collector.add(f"📊 {api_name}: Assigned {len(accounts_group)} accounts", "info")
    
    stats['current_region'] = region.upper()
    stats['total'] = total
    stats['completed'] = 0
    stats['success'] = 0
    stats['failed'] = 0
    stats['timed_out'] = 0
    
    rate_limit_manager = RateLimitManager()
    stats['rate_limit_manager'] = rate_limit_manager
    pause_event = asyncio.Event()
    start_time = time.time()
    
    # Progress tracking
    last_logged_progress = -1
    
    async def track_progress():
        nonlocal last_logged_progress
        while stats.get('completed', 0) < total:
            completed = stats.get('completed', 0)
            # Log every 10 accounts or at the very beginning
            if completed % 10 == 0 and completed != last_logged_progress:
                elapsed = time.time() - start_time
                timer_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
                if log_collector:
                    log_collector.add(f"PROGRESS:{region.upper()}:{completed}/{total}:{timer_str}", "info")
                last_logged_progress = completed
            await asyncio.sleep(1)

    progress_task = asyncio.create_task(track_progress())
    
    # Process all APIs in parallel
    api_tasks = [
        process_api_batch(session, api_url, api_name, accounts_group, stats, pause_event, log_collector)
        for api_url, api_name, accounts_group in api_distribution
    ]
    
    try:
        # All 3 APIs work simultaneously with 20-minute overall timeout
        api_results = await asyncio.wait_for(
            asyncio.gather(*api_tasks),
            timeout=1200
        )
        # Flatten results from all APIs
        results = []
        for api_result in api_results:
            results.extend(api_result)
    except asyncio.TimeoutError:
        if log_collector:
            log_collector.add(f"⏱️ {region.upper()} batch timeout after 20 minutes", "error")
        results = [None] * total
    finally:
        progress_task.cancel()
        # Final progress log
        elapsed = time.time() - start_time
        timer_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
        if log_collector:
            log_collector.add(f"PROGRESS:{region.upper()}:{total}/{total}:{timer_str}", "info")
    
    duration = time.time() - start_time
    valid_tokens = [r for r in results if r is not None]
    timed_out_count = stats.get('timed_out', 0)
    
    # Log API usage stats
    if 'api_usage' in stats and stats['api_usage'] and log_collector:
        for api_name, count in sorted(stats['api_usage'].items()):
            log_collector.add(f"📈 {api_name}: {count} successful tokens", "info")
    
    # Save locally
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    token_filename = f'token_{region}.json'
    token_save_path = TOKENS_DIR / token_filename
    
    try:
        with open(token_save_path, "w", encoding="utf-8") as f:
            json.dump(valid_tokens, f, indent=2)
        
        summary = f"✅ {region.upper()} Complete: {len(valid_tokens)}/{total} tokens"
        if timed_out_count > 0:
            summary += f" ({timed_out_count} timed out)"
        
        if log_collector:
            log_collector.add(summary, "success")
        
        # Push to GitHub
        await push_to_github(session, token_filename, valid_tokens, log_collector)
        
        # Cleanup local file
        if token_save_path.exists():
            token_save_path.unlink()
    
    except Exception as e:
        if log_collector:
            log_collector.add(f"❌ Error saving {region}: {str(e)}", "error")
    
    return {
        'region': region.upper(),
        'total': total,
        'success': len(valid_tokens),
        'failed': total - len(valid_tokens),
        'success_rate': round((len(valid_tokens) / total) * 100, 1) if total > 0 else 0,
        'duration': round(duration, 2)
    }


async def run_token_fetch(log_collector=None, stats=None, on_region_complete=None):
    """Main token fetching function - runs once per invocation."""
    ACCOUNTS_DIR.mkdir(exist_ok=True)
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    
    account_files = sorted(list(ACCOUNTS_DIR.glob('accounts_*.json')))
    
    if not account_files:
        if log_collector:
            log_collector.add("❌ No account files found", "error")
        return {'status': 'error', 'message': 'No account files found'}
    
    if log_collector:
        log_collector.add(f"📂 Found {len(account_files)} region files", "info")
    
    results = []
    if stats is None:
        stats = {}
    else:
        stats.clear() # Reset stats for new run
    start_time = time.time()
    
    # Total concurrent connections: 3 APIs * 30 per API = 90, set limit to 100 for safety
    connector = aiohttp.TCPConnector(limit=100, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        for filepath in account_files:
            region_result = await process_region(session, filepath, stats, log_collector)
            if region_result:
                results.append(region_result)
                # Trigger callback for incremental updates (e.g., database save)
                if on_region_complete:
                    try:
                        on_region_complete(region_result)
                    except Exception as e:
                        if log_collector:
                            log_collector.add(f"⚠️ Callback error: {str(e)}", "warning")
    
    elapsed = time.time() - start_time
    
    if log_collector:
        log_collector.add(f"✅ All regions complete in {elapsed:.1f}s", "success")
    
    return {
        'status': 'success',
        'results': results,
        'elapsed': round(elapsed, 2),
        'timestamp': datetime.now().isoformat()
    }