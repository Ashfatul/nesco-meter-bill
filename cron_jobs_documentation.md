# NESCO Meter Tracker - Cron Jobs Documentation

This document describes the automated background jobs (cron jobs) configured for the NESCO Prepaid Meter Tracker. These tasks ensure that meter balances are regularly updated and manual sync requests from the web dashboard are processed promptly.

---

## 1. Overview of the Sync Modes

The fetch script `fetch_daily.py` supports two execution modes:

### A. Automated Daily Fetch (Full Scan)
*   **Command:** `python fetch_daily.py`
*   **Purpose:** Automatically scans all users in the database and updates their daily meter balances.
*   **Rate-Limit Optimization (New):** Once a successful balance is received for a meter today, subsequent automated runs of this script will **automatically skip** fetching for that meter for the rest of the day. This prevents unnecessary scraping requests to the NESCO portal. If a fetch fails (e.g., due to NESCO site downtime), the script will retry on its next scheduled run until a successful balance is successfully recorded.
*   **Recommended Frequency:** Run every **30 to 60 minutes** (e.g., between 4:00 AM and 11:30 PM local time). This acts as a reliable retry loop in case NESCO is offline early in the morning.

### B. Manual Requested Fetch (Manual Flag System)
*   **Command:** `python fetch_daily.py --check-requested`
*   **Purpose:** Runs continuously in the background to listen for manual sync requests from the web dashboard (triggered by clicking "Request Local Sync" in the UI, which sets the `sync_requested` flag to `True` for the meter).
*   **Behavior:** When it finds a meter with `sync_requested = True`, it immediately fetches the latest balance and resets the flag to `False`. This mode **always executes**, bypassing the daily success skip check.
*   **Recommended Frequency:** Run every **5 minutes** to ensure responsive manual updates.

---

## 2. Cron Configuration Syntax (Crontab)

To install these jobs on your target server (VPS, Serv00, or local PC), run `crontab -e` and append the following lines:

### VPS / Local Linux Machine Setup
*(Replace `/mnt/01DAAF995C961E10/personal_projects/meter_balence_bot` with your actual project absolute path)*

```bash
# 1. Automated Daily Fetch (Runs every 30 minutes; skips after first daily success)
*/30 * * * * cd /mnt/01DAAF995C961E10/personal_projects/meter_balence_bot && /mnt/01DAAF995C961E10/personal_projects/meter_balence_bot/.venv/bin/python fetch_daily.py >> /mnt/01DAAF995C961E10/personal_projects/meter_balence_bot/cron.log 2>&1

# 2. Manual Requested Fetch (Runs every 5 minutes to process on-demand web requests)
*/5 * * * * cd /mnt/01DAAF995C961E10/personal_projects/meter_balence_bot && /mnt/01DAAF995C961E10/personal_projects/meter_balence_bot/.venv/bin/python fetch_daily.py --check-requested >> /mnt/01DAAF995C961E10/personal_projects/meter_balence_bot/cron.log 2>&1
```

### Serv00 Setup
*(Replace `YOUR_USERNAME` and `username.serv00.net` with your Serv00 domain/username details)*

```bash
# 1. Automated Daily Fetch
*/30 * * * * /usr/home/YOUR_USERNAME/domains/username.serv00.net/public_python/venv/bin/python /usr/home/YOUR_USERNAME/domains/username.serv00.net/public_python/fetch_daily.py >> /usr/home/YOUR_USERNAME/domains/username.serv00.net/public_python/cron.log 2>&1

# 2. Manual Requested Fetch
*/5 * * * * /usr/home/YOUR_USERNAME/domains/username.serv00.net/public_python/venv/bin/python /usr/home/YOUR_USERNAME/domains/username.serv00.net/public_python/fetch_daily.py --check-requested >> /usr/home/YOUR_USERNAME/domains/username.serv00.net/public_python/cron.log 2>&1
```

---

## 3. Environment Variables Needed

The cron jobs need connection details to update the database. If you use Supabase or Neon (PostgreSQL), ensure these environment variables are exported before the command is run. 

You can define them directly inside a helper shell script (like `run_fetch.sh`):

```bash
#!/bin/bash
export DATABASE_URL="postgresql://username:password@hostname:port/database"
export TELEGRAM_BOT_TOKEN="your_bot_token"

/path/to/venv/bin/python /path/to/fetch_daily.py "$@"
```

Then configure crontab to execute the wrapper script:
```bash
*/30 * * * * bash /path/to/project/run_fetch.sh >> /path/to/project/cron.log 2>&1
*/5 * * * * bash /path/to/project/run_fetch.sh --check-requested >> /path/to/project/cron.log 2>&1
```

---

## 4. Monitoring & Troubleshooting

### Log File Location
Logs are saved in the project root folder under `cron.log`.
You can view them in real time using:
```bash
tail -f cron.log
```

### Typical Log Entries
*   **Skip Event (Normal automated run after success):**
    ```
    [2026-07-25 23:45:57.691107] Connected to database type: PostgreSQL (check_requested_only=False)
    [2026-07-25 23:45:58.138279] Found 1 users in database to check/fetch.
    [2026-07-25 23:45:58.460922] Skipping automatic fetch for meter 82001249 - balance already successfully fetched for today (2026-07-25).
    ```
*   **Fetch Event (First successful run of the day or manual sync):**
    ```
    [2026-07-25 23:46:53.104205] Connected to database type: PostgreSQL (check_requested_only=True)
    [2026-07-25 23:46:53.522923] Found 1 users in database to check/fetch.
    [2026-07-25 23:46:53.726024] Fetching data for meter 82001249...
    [2026-07-25 23:46:56.739627] Success: Updated balance to ৳ 257.997. Scraped balance: ৳ 258.00. Telegram already sent today.
    ```
