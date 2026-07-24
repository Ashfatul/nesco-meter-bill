# NESCO Tracker - Hosting & Deployment Guide

Since this application requires a persistent database, background processes (Cron Jobs), and web scraping capabilities, standard shared hosting or highly restricted serverless platforms (like Vercel) are not suitable. 

You need either a **Free Web Host (with custom Python/Cron support)**, a **Modern Cloud Setup (App + Cloud DB + Scheduled Actions)**, or a **Linux Virtual Private Server (VPS)**.

## 1. Hosting Provider Recommendations

Here are the best options for hosting this application:

| Provider | Pricing | Requires Card? | Why choose this? |
| :--- | :--- | :--- | :--- |
| **Render + Neon/Supabase + GitHub Actions** | **Always Free** | **No** | **Highly Recommended!** A modern cloud architecture. Splits your web app (Render), database (Neon/Supabase), and daily cron scraping job (GitHub Actions). 100% free, card-free, and always open for signups. |
| **Serv00** | **Always Free** | **No** | A single free hosting provider that supports Python, SQLite, and cron jobs. *(Note: Registration is frequently closed/full due to server limits.)* |
| **Microsoft Azure (Azure for Students)** | **Free for 1 Year** | **No** | Perfect if you have a student (.edu) email! You get a free `B1s` Linux VM running Ubuntu flawlessly. |
| **AWS EC2 (Free Tier)** | **Free for 1 Year** | Yes | Get a `t2.micro` Ubuntu server free for 12 months. |
| **Oracle Cloud** | **Always Free** | Yes | Always Free ARM/x86 VPS. Great if you can secure an instance. |
| **PythonAnywhere** | Free Tier | **No** | *Not recommended!* Free accounts restrict outbound web requests to a whitelist, which blocks NESCO scraping. |
| **DigitalOcean / Linode** | $4 - $6 / month | Yes | The easiest Linux VPS options for beginners. |

*(Recommendation: Since Serv00 registration is frequently full/closed, the **Render + Neon/Supabase + GitHub Actions** setup is the absolute best way to host this app 100% free with no credit card required.)*

---

## 2. Cloud Deployment Guide: Render + Neon/Supabase + GitHub Actions (Recommended)

This modern setup splits your stack so you remain 100% free without needing a credit card:
1. **Neon** or **Supabase** hosts your persistent PostgreSQL database (which replaces local SQLite).
2. **Render** hosts your Flask web UI (which automatically sleeps when inactive to save resources, but wakes up on page load).
3. **GitHub Actions** runs your daily scraper script `fetch_daily.py` at 4:00 AM. Since GitHub Actions has unrestricted outbound internet access, scraping NESCO works perfectly.

### Step 1: Create a Free PostgreSQL Database
1. Go to [Neon.tech](https://neon.tech/) or [Supabase.com](https://supabase.com/) and register a free account (no credit card required).
2. Create a new project.
3. Copy your PostgreSQL connection string (it will start with `postgres://` or `postgresql://`).

### Step 2: Deploy the Web App on Render
1. Sign up on [Render.com](https://render.com/) (no credit card required).
2. Click **New** -> **Web Service**.
3. Link your GitHub repository.
4. Set the following details during setup:
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
5. Click **Advanced** and add the following Environment Variable:
   - **Key**: `DATABASE_URL`
   - **Value**: *Your PostgreSQL connection string from Step 1*
6. Click **Deploy Web Service**. Render will build and deploy your app.
   *(Note: On the free tier, Render will spin down the app if it has no traffic for 15 minutes. It will automatically wake up and load when someone visits your URL, which takes about 30–60 seconds.)*

### Step 3: Configure GitHub Actions for the Daily Fetch (Cron)
Since Render's free tier spins down and doesn't run background processes, we schedule the daily 4:00 AM scraper on GitHub Actions:
1. Go to your repository on GitHub.
2. Navigate to **Settings** -> **Secrets and variables** -> **Actions**.
3. Click **New repository secret**.
4. Name the secret `DATABASE_URL` and paste your PostgreSQL connection string into the value.
5. In your local code repository, make sure the `.github/workflows/fetch_daily.yml` file is pushed to GitHub.
6. The action will run automatically at 4:00 AM UTC every day. You can also manually trigger it under the **Actions** tab by choosing **NESCO Daily Balance Fetcher** -> **Run workflow**.

---

## 3. Serv00 Deployment Guide (100% Free, No Card - Alternative)

*If Serv00 registrations are open*, it is a great free hosting service based on FreeBSD. It provides full SSH access, cron jobs, and unrestricted outbound web access.

### Step 1: Sign up on Serv00
1. Go to [Serv00.com](https://www.serv00.com/) and register a free account.
2. Select a username and a domain name (you will get a free subdomain like `username.serv00.net`).
3. You will receive an email with your SSH password, host server name (e.g. `s1.serv00.com`), and login link to the administration panel.

### Step 2: Enable Phusion Passenger
1. Log in to the Serv00 Panel.
2. Go to **Additional services** -> **SSH**.
3. Find **Phusion Passenger** and make sure it is **Enabled** (click "Enable" if it is disabled).

### Step 3: Add Python Application
1. In the Serv00 Panel, go to **WWW websites** -> **Add new website**.
2. Configure it as follows:
   - **Domain**: `username.serv00.net` (or your subdomain)
   - **Type**: `python`
   - **Python version**: Select the latest (e.g., `python3.11` or `python3`)
3. Click **Add**. This will create your web directory at `/usr/home/YOUR_USERNAME/domains/username.serv00.net/public_python/`.

### Step 4: Upload/Clone Code via SSH
1. Connect to your Serv00 server via SSH using the credentials from your signup email:
   ```bash
   ssh YOUR_USERNAME@sX.serv00.com
   ```
2. Navigate to your app directory:
   ```bash
   cd ~/domains/username.serv00.net/public_python/
   ```
3. Remove the default index file:
   ```bash
   rm -f index.html
   ```
4. Clone your project files into this directory (using git or SFTP):
   ```bash
   git clone https://github.com/YOUR_GITHUB_USER/meter-balance-bot.git .
   ```
   *(Ensure you include the dot `.` at the end to clone directly into the current directory)*

### Step 5: Setup Python Virtual Environment
1. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. Install the application dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Initialize the SQLite database:
   ```bash
   python -c "from app import app, db; app.app_context().push(); db.create_all()"
   ```

### Step 6: Configure Phusion Passenger
Serv00 uses Phusion Passenger to serve Python web applications, looking for a file named `passenger_wsgi.py` in the `public_python/` folder.

Create or update this file:
```bash
nano passenger_wsgi.py
```
And add the following python code:
```python
import sys
import os

# Point to project root
sys.path.insert(0, os.path.dirname(__file__))

# Dynamically find virtualenv site-packages
venv_dir = os.path.join(os.path.dirname(__file__), 'venv')
if os.path.exists(venv_dir):
    lib_dir = os.path.join(venv_dir, 'lib')
    if os.path.exists(lib_dir):
        for item in os.listdir(lib_dir):
            site_packages = os.path.join(lib_dir, item, 'site-packages')
            if os.path.exists(site_packages):
                sys.path.insert(0, site_packages)
                break

from app import app as application
```
Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

Create a `tmp` folder to allow restarting Passenger when code changes:
```bash
mkdir -p tmp
touch tmp/restart.txt
```

### Step 7: Configure the Daily Auto-Fetch Cron Job
To run `fetch_daily.py` daily at 4:00 AM on Serv00:
1. Log in to the Serv00 Panel.
2. Navigate to **Cron jobs** -> **Add cron job**.
3. Set the schedule:
   - **Minute**: `0`
   - **Hour**: `4`
   - **Day**: `*`
   - **Month**: `*`
   - **Day of week**: `*`
4. Set the **Command** to (adjusting username and domain):
   ```bash
   /usr/home/YOUR_USERNAME/domains/username.serv00.net/public_python/venv/bin/python /usr/home/YOUR_USERNAME/domains/username.serv00.net/public_python/fetch_daily.py >> /usr/home/YOUR_USERNAME/domains/username.serv00.net/public_python/cron.log 2>&1
   ```
5. Click **Add**.

---

## 4. Ubuntu VPS Deployment Guide (AWS, Azure, Oracle, etc.)

Once you purchase/create your Ubuntu VPS and connect to it via SSH, the deployment process is **100% automated** using the provided `deploy.sh` script.

### Step 1: Upload Your Code to the Server
Clone your repository or upload your project folder to your server:
```bash
git clone https://github.com/yourusername/nesco-tracker.git
cd nesco-tracker
```

### Step 2: Run the Automated Deployment Script
Simply run this command inside the project folder:
```bash
sudo bash deploy.sh
```
This script automatically:
1. Installs Python, Nginx, and system dependencies.
2. Creates the Python Virtual Environment and installs Flask dependencies.
3. Initializes the SQLite Database with correct permissions.
4. Sets up and starts a Gunicorn Systemd service (`nesco.service`).
5. Configures Nginx as a reverse proxy on port 80.
6. Automatically adds the 4:00 AM Daily Fetch Cron Job to your user profile.

### Step 3: Access Your Application!
Open your web browser and navigate to your server's Public IP address. Your NESCO Tracker is live!

---

## 5. How the Daily Auto-Fetch Works

The daily fetch script `fetch_daily.py` is configured to run at exactly **4:00 AM** every single day:
- **What it does:** It loops through all registered users in your database, visits the NESCO portal invisibly, and securely stores the end-of-day balances.
- **Where are the logs?** To check if the fetch was successful, view the log file in your project directory:
  ```bash
  cat cron.log
  ```
