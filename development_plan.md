# NESCO Prepaid Meter Dashboard - Development Plan

## 1. Project Overview
A personal, secure dashboard to track NESCO prepaid meter usage. Since NESCO does not provide an official API and only shows limited data on their portal, this application will programmatically scrape the NESCO portal using the meter number, store the daily data, and calculate insightful metrics (daily usage, monthly trends, recharge history). 

## 2. Technology Stack
- **Backend Framework:** Python with Flask (Lightweight, well-suited for PythonAnywhere)
- **Database:** SQLite (Built-in, perfectly supported by PythonAnywhere for low-to-medium traffic)
- **ORM:** SQLAlchemy (For secure and easy database operations)
- **Frontend/UI:** HTML/CSS with Bootstrap 5 (for a modern, responsive, minimal design)
- **Data Visualization:** Chart.js (for rendering usage and balance trends)
- **Scraping Engine:** `requests` + `BeautifulSoup4` (If JavaScript rendering is required, we will fallback to `Selenium` headless browser).
- **Authentication:** `Flask-Login` and `Werkzeug.security` (for session management and password hashing)
- **Hosting/Deployment:** PythonAnywhere (Supports Python, scheduled tasks/cron jobs, and automated HTTPS).

## 3. Core Features
1. **Landing Page:** Minimalistic page explaining what the app does, emphasizing that it's exclusively for NESCO prepaid meters, with a clear "Login / Sign Up" call to action.
2. **User Authentication:** 
   - Sign up requires: Email, Password, and NESCO Prepaid Meter Number.
   - Login requires: Email and Password.
3. **Automated Data Scraping:** 
   - A scheduled task (running daily shortly after 12:00 PM) that uses the user's meter number to fetch current balance, meter details, and recharge history from NESCO's portal.
4. **Data Analytics & Dashboard:**
   - **Current Balance:** Latest scraped balance.
   - **Yesterday's Usage:** Calculated by subtracting today's balance from yesterday's balance (accounting for any recharges).
   - **Monthly Usage:** Aggregated usage for the current month vs. previous month.
   - **Usage Trends:** Interactive charts showing daily balance decay and consumption rates.
   - **Recharge History:** A tabular view of past recharges (Date, Amount, Token).

## 4. Database Schema Design
We will use a relational model with the following core tables:

### `users`
- `id` (Primary Key)
- `email` (Unique, String)
- `password_hash` (String)

### `meters`
- `id` (Primary Key)
- `user_id` (Foreign Key -> users.id)
- `meter_number` (String, Unique)
- `customer_name` (String, Optional)
- `address` (String, Optional)

### `balances`
- `id` (Primary Key)
- `meter_id` (Foreign Key -> meters.id)
- `date` (Date)
- `balance` (Float)
- *(Unique constraint on meter_id + date)*

### `recharges`
- `id` (Primary Key)
- `meter_id` (Foreign Key -> meters.id)
- `date` (DateTime)
- `amount` (Float)
- `token` (String, Unique)

## 5. Security Measures
- **Data Encryption:** Passwords hashed using `bcrypt` or `Werkzeug` defaults.
- **Session Security:** Managed via `Flask-Login` with secure cookies.
- **CSRF Protection:** Implemented on all forms using `Flask-WTF`.
- **SQL Injection Prevention:** Ensured by using SQLAlchemy ORM.
- **Rate Limiting:** Protect login routes against brute-force attacks.
- **Transport Security:** Enforce HTTPS via PythonAnywhere.

## 6. Development Phases

### Phase 1: Scraping Prototype (Proof of Concept)
- Analyze the NESCO prepaid portal network requests (using browser DevTools).
- Write a standalone Python script to submit a meter number and parse the resulting HTML/JSON.
- Ensure we can reliably extract: Current Balance, Customer Info, and Recharge History.

### Phase 2: Database & Backend Setup
- Initialize a Flask project structure.
- Configure SQLite and define SQLAlchemy models (`User`, `Meter`, `Balance`, `Recharge`).
- Create user registration and login flows.

### Phase 3: Scraping Integration & Task Scheduling
- Integrate the scraping script into the Flask backend.
- Create a manual "Refresh Data" button for testing.
- Set up a Python script that can be executed via a PythonAnywhere Cron Job to scrape data daily for all registered meters.

### Phase 4: Frontend Dashboard & Analytics
- Design a clean, modern UI using Bootstrap.
- Write the backend logic to calculate daily usage (Yesterday Balance + Recharges - Today Balance = Yesterday Usage).
- Implement Chart.js on the dashboard to visualize daily usage and balance drops over the last 30 days.
- Build tables to display the recharge history.

### Phase 5: Testing, Deployment, and Polish
- Thoroughly test the scraping logic against edge cases (e.g., site downtime, unexpected HTML changes).
- Deploy the application to PythonAnywhere.
- Configure domain settings, enforce HTTPS, and schedule the daily scraping cron job.
