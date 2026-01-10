import aiohttp
import asyncio
import json
import os
import urllib.parse
import time
import random
import base64
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TaskProgressColumn
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich import box

# Load environment variables from .env file (local development)
# Vercel will automatically inject environment variables from its settings
load_dotenv()

# Initialize Rich Console
console = Console()

# --- Rate Limit Manager ---
class RateLimitManager:
    """Global manager to coordinate rate limit pauses across all concurrent requests."""
    def __init__(self):
        self.first_error_occurred = asyncio.Event()
        self.pause_in_progress = False
        self.lock = asyncio.Lock()
    
    async def handle_rate_limit(self, uid: str):
        """
        Handle rate limit error. First error triggers a global 5-second pause.
        Returns True if this was the first error (pause initiated).
        """
        async with self.lock:
            if not self.first_error_occurred.is_set():
                self.first_error_occurred.set()
                self.pause_in_progress = True
                return True
            return False
    
    def reset(self):
        """Reset the manager for a new region/batch."""
        self.first_error_occurred.clear()
        self.pause_in_progress = False

# Global rate limit manager instance
rate_limit_manager = RateLimitManager()

# --- Configuration ---
ACCOUNTS_DIR = Path('accounts')
TOKENS_DIR = Path('tokens')

# Multiple API URLs for fallback support
API_URLS = [
    "https://jwt.tsunstudio.pw/v1/auth/saeed?uid={uid}&password={password}",  # Primary API
    "https://tsun-ff-jwt-api.onrender.com/v1/auth/saeed?uid={uid}&password={password}",  # Fallback API 2
    "https://jwt-tsunstudio.onrender.com/v1/auth/saeed?uid={uid}&password={password}"  # Fallback API 3
]

# Set concurrency limit for simultaneous API calls (Higher limit for simpler API calls)
MAX_CONCURRENT_REQUESTS = 100 
# Scheduler interval in hours (changed from 1 to 6)
SCHEDULE_INTERVAL_HOURS = 6

# --- GitHub Configuration ---
# Supports both local .env and Vercel environment variables
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN') or os.getenv('GPH') or os.getenv('VERCEL_GITHUB_TOKEN')
GITHUB_REPO_OWNER = os.getenv('GITHUB_REPO_OWNER', 'TSun-FreeFire')
GITHUB_REPO_NAME = os.getenv('GITHUB_REPO_NAME', 'TSun-FreeFire-Storage')
GITHUB_BRANCH = os.getenv('GITHUB_BRANCH', 'main')
GITHUB_BASE_PATH = os.getenv('GITHUB_BASE_PATH', 'Spam-api')
GITHUB_API_BASE = "https://api.github.com"

# --- Retry Constants ---
MAX_RETRIES = 15 # Will try up to 15 times per account/operation
INITIAL_DELAY = 5 # Start waiting 5 seconds after the first failure
MAX_DELAY = 120 # Maximum wait time is 120 seconds (2 minutes)
GITHUB_MAX_RETRIES = 15 # Retries for GitHub API operations

# --- Core Async API Function ---

async def fetch_token(session: aiohttp.ClientSession, uid: str, password: str, stats: dict, pause_event: asyncio.Event):
    """
    Fetches a single JWT token using multiple fallback APIs with persistent retry logic
    and exponential backoff to handle rate limits and timeouts.
    Special handling: First 429/500 error triggers a global 5-second pause for ALL requests.
    API Fallback: Tries API_1 -> API_2 -> API_3 -> cycles back to API_1
    """
    encoded_uid = urllib.parse.quote(str(uid))
    encoded_password = urllib.parse.quote(password)
    
    api_index = 0  # Start with first API
    
    for attempt in range(MAX_RETRIES):
        error_message = None
        should_switch_api = False

        try:
            # 1. Exponential Backoff and Jitter
            if attempt > 0:
                # Calculate delay: Initial * 2^(attempt-1), maxed at MAX_DELAY
                base_delay = min(INITIAL_DELAY * (2 ** (attempt - 1)), MAX_DELAY)
                # Add random jitter (up to 5 seconds) to prevent simultaneous retries
                delay = base_delay + random.uniform(0, 5) 
                await asyncio.sleep(delay)

            # 2. Select API URL (cycle through all APIs)
            url = API_URLS[api_index].format(uid=encoded_uid, password=encoded_password)
            api_name = f"API_{api_index + 1}"

            # 3. Make the request
            async with session.get(url, ssl=False, timeout=30) as resp:
                
                # HTTP 200: Successful token retrieval
                if resp.status == 200:
                    data = await resp.json()
                    token = data.get("token")
                    if token:
                        stats['success'] += 1
                        stats['completed'] += 1
                        # Log which API succeeded (only if not first API or after failures)
                        if api_index > 0 or attempt > 0:
                            stats.setdefault('api_usage', {})
                            stats['api_usage'][api_name] = stats['api_usage'].get(api_name, 0) + 1
                        return {"token": token}
                    else:
                        # Success status, but 'token' key is missing or empty
                        error_message = f"{api_name} - Token missing in response"
                        should_switch_api = True
                
                # HTTP 429 or 500: Rate limit or server error - Switch to next API
                elif resp.status in [429, 500]:
                    response_text = await resp.text()
                    error_message = f"{api_name} - Failed ({resp.status})"
                    should_switch_api = True
                    
                    # Check if this is the first global rate limit error
                    is_first_error = await rate_limit_manager.handle_rate_limit(uid)
                    
                    if is_first_error:
                        # Signal all tasks to pause
                        pause_event.set()
                        await asyncio.sleep(5)  # Global 5-second pause
                        pause_event.clear()
                        rate_limit_manager.pause_in_progress = False
                    else:
                        # Wait if another task is handling the pause
                        if pause_event.is_set():
                            await pause_event.wait()
                            await asyncio.sleep(0.1)  # Small buffer
                
                # HTTP non-200: Other server or client errors - Switch to next API
                else:
                    error_message = f"{api_name} - Failed ({resp.status})"
                    should_switch_api = True

        except aiohttp.ClientConnectorError:
            error_message = f"{api_name} - Connection Error"
            should_switch_api = True
        except asyncio.TimeoutError:
            error_message = f"{api_name} - Request Timed Out"
            should_switch_api = True
        except json.JSONDecodeError:
            error_message = f"{api_name} - JSON decode error"
            should_switch_api = True
        except Exception as e:
            error_message = f"{api_name} - Unexpected error: {type(e).__name__}"
            should_switch_api = True

        # Switch to next API on error (cycle through all APIs)
        if should_switch_api:
            api_index = (api_index + 1) % len(API_URLS)

        # If this was the last attempt, break the loop and return failure
        if attempt == MAX_RETRIES - 1:
            break
            
    # If loop completes without returning a token, it means max retries were hit
    stats['failed'] += 1
    stats['completed'] += 1
    return None

# --- GitHub Integration Functions ---

async def get_github_file_sha(session: aiohttp.ClientSession, filename: str):
    """Get the SHA of an existing file on GitHub (needed for updates)."""
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
            elif resp.status == 404:
                # File doesn't exist yet, no SHA needed
                return None
            else:
                console.print(f"[yellow]⚠️ GitHub SHA fetch returned status {resp.status} for {filename}[/yellow]")
                return None
    except Exception as e:
        console.print(f"[yellow]⚠️ Error fetching GitHub SHA for {filename}: {e}[/yellow]")
        return None


async def push_to_github(session: aiohttp.ClientSession, filename: str, content: list, progress: Progress, task_id):
    """
    Push token file to GitHub with retry logic and exponential backoff.
    Returns True if successful, False otherwise.
    """
    if not GITHUB_TOKEN:
        console.print(f"[red]❌ GitHub token not found. Cannot push {filename}[/red]")
        return False
    
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_BASE_PATH}/{filename}"
    
    for attempt in range(GITHUB_MAX_RETRIES):
        try:
            # Add exponential backoff if retrying
            if attempt > 0:
                base_delay = min(INITIAL_DELAY * (2 ** (attempt - 1)), MAX_DELAY)
                delay = base_delay + random.uniform(0, 5)
                progress.update(task_id, description=f"[cyan]📤 Pushing {filename} (Retry {attempt + 1})...")
                await asyncio.sleep(delay)
            
            # Get current file SHA if it exists (required for updates)
            sha = await get_github_file_sha(session, filename)
            
            # Prepare the request payload
            content_json = json.dumps(content, indent=2)
            content_base64 = base64.b64encode(content_json.encode('utf-8')).decode('utf-8')
            
            payload = {
                "message": f"Auto-update {filename} - {time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                "content": content_base64,
                "branch": GITHUB_BRANCH
            }
            
            # Include SHA if file exists (for update)
            if sha:
                payload["sha"] = sha
            
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Make the PUT request
            async with session.put(url, json=payload, headers=headers, ssl=False, timeout=30) as resp:
                if resp.status in [200, 201]:
                    console.print(f"[green]✅ GitHub Push {filename} -> Success on attempt {attempt + 1}[/green]")
                    return True
                else:
                    error_text = await resp.text()
                    if attempt > 2:  # Only log after a few attempts
                        console.print(f"[red]❌ GitHub Push {filename} -> Failed ({resp.status})[/red]")
        
        except asyncio.TimeoutError:
            if attempt > 2:
                console.print(f"[red]❌ GitHub Push {filename} -> Timeout[/red]")
        except Exception as e:
            if attempt > 2:
                console.print(f"[red]❌ GitHub Push {filename} -> Error: {type(e).__name__}[/red]")
    
    # Max retries exceeded
    console.print(f"[bold red]💀 GitHub Push {filename} -> FINAL FAILURE after {GITHUB_MAX_RETRIES} attempts[/bold red]")
    return False


async def cleanup_local_token_file(filepath: Path):
    """Delete local token file after successful GitHub push."""
    try:
        if filepath.exists():
            filepath.unlink()
            console.print(f"[dim]🗑️ Deleted local file: {filepath}[/dim]")
    except Exception as e:
        console.print(f"[yellow]⚠️ Failed to delete local file {filepath}: {e}[/yellow]")


# --- Region Processing Logic ---

async def process_region_accounts(session: aiohttp.ClientSession, account_filepath: Path, overall_progress: Progress):
    """Reads accounts, fetches tokens concurrently with beautiful progress display, saves results, and pushes to GitHub."""
    
    # 1. Extract region from filename (e.g., accounts_pk.json -> pk)
    try:
        region = account_filepath.stem.split('_')[-1].lower()
    except IndexError:
        console.print(f"[red]Skipping file: {account_filepath.name}. Filename must be in 'accounts_{{server}}.json' format.[/red]")
        return

    # 2. Load accounts
    try:
        with open(account_filepath, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]❌ Error decoding JSON from {account_filepath}: {e}[/red]")
        return
    except Exception as e:
        console.print(f"[red]❌ Error loading file {account_filepath}: {e}[/red]")
        return

    # Filter and validate accounts
    valid_accounts = [
        acc for acc in accounts 
        if isinstance(acc, dict) and 'uid' in acc and 'password' in acc
    ]
    
    total_accounts = len(valid_accounts)
    
    if total_accounts == 0:
        console.print(f"[yellow]No valid accounts found in {account_filepath.name}. Skipping.[/yellow]")
        return
    
    # Reset rate limit manager for this region
    rate_limit_manager.reset()
    
    # Shared statistics
    stats = {
        'success': 0,
        'failed': 0,
        'completed': 0,
        'total': total_accounts
    }
    
    # Event to coordinate global pause
    pause_event = asyncio.Event()
    
    # Create beautiful header
    console.print(f"\n[bold magenta]╔{'═' * 68}╗[/bold magenta]")
    console.print(f"[bold magenta]║[/bold magenta] [bold cyan]🔑 Token Fetcher - {region.upper()} Server{' ' * (68 - 28 - len(region))}[/bold cyan][bold magenta]║[/bold magenta]")
    console.print(f"[bold magenta]╠{'═' * 68}╣[/bold magenta]")
    console.print(f"[bold magenta]║[/bold magenta] [yellow]📊 Total Accounts: {total_accounts}{' ' * (68 - 22 - len(str(total_accounts)))}[/yellow][bold magenta]║[/bold magenta]")
    console.print(f"[bold magenta]╚{'═' * 68}╝[/bold magenta]\n")
    
    # Create advanced progress display
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    
    # Progress bars with multiple columns
    progress = Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=50, style="blue", complete_style="green", finished_style="bold green"),
        TaskProgressColumn(),
        TextColumn("[bold cyan]{task.completed}/{task.total}[/bold cyan]"),
        TimeElapsedColumn(),
        console=console,
        expand=True
    )
    
    fetch_task = progress.add_task(
        f"[cyan]Fetching Tokens",
        total=total_accounts
    )
    
    # Live display loop
    start_time = time.time()
    
    async def update_progress():
        """Background task to update progress display."""
        while stats['completed'] < stats['total']:
            progress.update(
                fetch_task,
                completed=stats['completed'],
                description=f"[cyan]{'⏸️  PAUSED - Rate Limit (5s)' if pause_event.is_set() else 'Fetching Tokens'}"
            )
            await asyncio.sleep(0.1)
    
    # Start progress updater
    progress_task = asyncio.create_task(update_progress())
    
    # Display with Live context
    with Live(progress, console=console, refresh_per_second=10):
        # 3. Create tasks and run concurrently
        tasks = [
            fetch_token(session, acc["uid"], acc["password"], stats, pause_event) 
            for acc in valid_accounts
        ]
        
        # Run all fetches concurrently
        results = await asyncio.gather(*tasks)
    
    # Wait for progress task to complete
    await progress_task
    
    # Calculate statistics
    elapsed = time.time() - start_time
    speed = stats['completed'] / elapsed if elapsed > 0 else 0
    
    # Display final statistics panel
    stats_table = Table(box=box.ROUNDED, show_header=False, padding=(0, 2))
    stats_table.add_column(style="bold cyan", width=20)
    stats_table.add_column(style="bold", width=15)
    
    stats_table.add_row("✅ Successful", f"[bold green]{stats['success']}[/bold green]")
    stats_table.add_row("❌ Failed", f"[bold red]{stats['failed']}[/bold red]")
    stats_table.add_row("⚡ Speed", f"[bold yellow]{speed:.1f} acc/sec[/bold yellow]")
    stats_table.add_row("⏱️  Time", f"[bold magenta]{elapsed:.2f}s[/bold magenta]")
    
    # Show API usage breakdown if fallback APIs were used
    if 'api_usage' in stats and stats['api_usage']:
        stats_table.add_row("", "")  # Empty row separator
        for api_name, count in sorted(stats['api_usage'].items()):
            stats_table.add_row(f"🔄 {api_name} Used", f"[bold yellow]{count}[/bold yellow]")
    
    console.print("\n")
    console.print(Panel(
        stats_table,
        title=f"[bold cyan]📊 Final Statistics - {region.upper()}[/bold cyan]",
        border_style="cyan",
        padding=(1, 2)
    ))

    # 4. Process results
    valid_tokens = [r for r in results if r is not None]

    # 5. Save results locally (temporarily)
    TOKENS_DIR.mkdir(exist_ok=True)
    token_filename = f'token_{region}.json'
    token_save_path = TOKENS_DIR / token_filename

    try:
        with open(token_save_path, "w", encoding="utf-8") as f:
            json.dump(valid_tokens, f, indent=2)

        console.print(f"[bold green]✅ Tokens saved locally: {token_save_path}[/bold green]\n")
        
        # 6. Push to GitHub with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            console=console
        ) as gh_progress:
            github_task = gh_progress.add_task(
                f"[cyan]📤 Pushing {token_filename} to GitHub",
                total=1
            )
            
            github_success = await push_to_github(session, token_filename, valid_tokens, gh_progress, github_task)
            gh_progress.update(github_task, completed=1)
            
            # 7. Cleanup local file if GitHub push was successful
            if github_success:
                await cleanup_local_token_file(token_save_path)
            else:
                console.print(f"[yellow]⚠️ Keeping local file {token_save_path} due to GitHub push failure[/yellow]")

    except Exception as e:
        console.print(f"[red]❌ Error saving tokens to file {token_save_path}: {e}[/red]")

# --- Scheduler and Main Function ---

async def main_token_refresh():
    """Finds all region files and triggers processing with beautiful progress display."""
    
    # Ensure directories exist
    ACCOUNTS_DIR.mkdir(exist_ok=True)
    TOKENS_DIR.mkdir(exist_ok=True)
    
    # Find all account files in the /accounts directory matching the pattern accounts_{server}.json
    account_files = sorted(list(ACCOUNTS_DIR.glob('accounts_*.json')))
    
    if not account_files:
        console.print(f"[bold red]⚠️ No accounts_*.json files found in '{ACCOUNTS_DIR}' folder![/bold red]")
        console.print(f"[yellow]Please add account files in the format: accounts_{{server}}.json[/yellow]")
        return
    
    # Display found files
    table = Table(title="[bold cyan]🎯 Detected Account Files[/bold cyan]", box=box.ROUNDED)
    table.add_column("Region", style="cyan", justify="center")
    table.add_column("File", style="green")
    
    for filepath in account_files:
        region = filepath.stem.split('_')[-1].upper()
        table.add_row(region, filepath.name)
    
    console.print(table)
    console.print()
    
    # Create overall progress tracker
    overall_progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console
    )
    
    # Use one session for all requests in this cycle
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        for filepath in account_files:
            await process_region_accounts(session, filepath, overall_progress)
            console.print("\n" + "─" * 80 + "\n")


async def start_scheduler(interval_hours: float):
    """
    Runs the token refresh at startup and then repeats every X hours with beautiful UI.
    """
    interval_seconds = interval_hours * 3600
    
    # Display beautiful startup banner
    console.print("\n")
    console.print(Panel.fit(
        "[bold cyan]🚀 TSun JWT Token Scheduler[/bold cyan]\n"
        f"[green]⏰ Interval:[/green] Every {interval_hours} hours\n"
        f"[green]🔄 Concurrency:[/green] {MAX_CONCURRENT_REQUESTS} requests\n"
        f"[green]🔥 Retries:[/green] Up to {MAX_RETRIES} attempts\n"
        f"[green]🌐 APIs:[/green] {len(API_URLS)} endpoints (with auto-fallback)\n"
        f"[green]📤 GitHub:[/green] {'✅ Enabled' if GITHUB_TOKEN else '❌ Disabled'}\n"
        + (f"[green]📁 Target:[/green] {GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/{GITHUB_BASE_PATH}" if GITHUB_TOKEN else ""),
        title="[bold magenta]╔═══ INITIALIZATION ═══╗[/bold magenta]",
        border_style="magenta",
        padding=(1, 2)
    ))
    console.print("\n")

    cycle_count = 0
    while True:
        cycle_count += 1
        start_time = time.time()
        
        try:
            console.print(f"\n[bold cyan]╔═══════════════════════════════════════════════════════╗[/bold cyan]")
            console.print(f"[bold cyan]║[/bold cyan] [bold yellow]🔄 Cycle #{cycle_count} - {time.strftime('%Y-%m-%d %H:%M:%S')}[/bold yellow] [bold cyan]║[/bold cyan]")
            console.print(f"[bold cyan]╚═══════════════════════════════════════════════════════╝[/bold cyan]\n")
            
            await main_token_refresh()
            
            console.print(f"\n[bold green]{'═' * 80}[/bold green]")
            console.print(f"[bold green]✅ Cycle #{cycle_count} COMPLETE - {time.strftime('%Y-%m-%d %H:%M:%S')}[/bold green]")
            console.print(f"[bold green]{'═' * 80}[/bold green]\n")
            
        except Exception as e:
            console.print(f"[bold red]❌ Critical error during cycle #{cycle_count}: {e}[/bold red]")
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        time_to_wait = interval_seconds - elapsed_time
        
        if time_to_wait > 0:
            wait_hours = time_to_wait / 3600
            wait_minutes = (time_to_wait % 3600) / 60
            
            console.print(Panel.fit(
                f"[bold cyan]😴 Sleeping for next cycle...[/bold cyan]\n"
                f"[yellow]⏰ Wait time:[/yellow] {wait_hours:.1f} hours ({wait_minutes:.0f} minutes)\n"
                f"[yellow]🕐 Next cycle:[/yellow] {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + time_to_wait))}",
                border_style="blue",
                padding=(1, 2)
            ))
            
            await asyncio.sleep(time_to_wait)
        else:
            console.print("[bold yellow]⚠️ Cycle exceeded interval. Starting next cycle immediately.[/bold yellow]")


if __name__ == "__main__":
    console.print("[bold yellow]💡 HINTS:[/bold yellow]")
    console.print(f"  • Place 'accounts_{{server}}.json' files in: [cyan]{ACCOUNTS_DIR}[/cyan]")
    console.print(f"  • Tokens will be pushed to: [cyan]GitHub/{GITHUB_BASE_PATH}[/cyan]")
    console.print(f"  • Set environment variable: [cyan]GITHUB_TOKEN[/cyan] or [cyan]GPH[/cyan]\n")
    
    try:
        # Start the scheduler to refresh every 6 hours
        asyncio.run(start_scheduler(interval_hours=SCHEDULE_INTERVAL_HOURS)) 
    except KeyboardInterrupt:
        console.print("\n[bold red]👋 Scheduler stopped by user. Khuda Hafiz![/bold red]")