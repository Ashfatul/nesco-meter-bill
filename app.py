import os
from flask import Flask, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from extensions import db, login_manager
from models import User, Meter, Balance, Recharge
from scraper import NescoScraper
from datetime import datetime, timezone, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

import re
from urllib.parse import quote_plus

# Dynamically fetch database URI from environment, defaulting to SQLite
db_url = os.environ.get('DATABASE_URL', 'sqlite:///nesco.db')

if db_url and (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
    # Standardize scheme
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    # Match scheme, username, password, host/port, and database path
    # This correctly parses passwords containing '@' or other special characters
    match = re.match(r"^(postgresql://)([^:]+):(.*)@([^@/]+)(/.*)?$", db_url)
    if match:
        scheme, username, password, hostinfo, path = match.groups()
        # Avoid double-encoding if it's already encoded (contains '%')
        if "%" not in password:
            password = quote_plus(password)
        db_url = f"{scheme}{username}:{password}@{hostinfo}{path or ''}"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def log_fetch(user_id, status, details, source):
    """Saves a fetch log entry in the database and cleans up old logs."""
    try:
        from models import FetchLog
        # Keep only the last 200 logs per user to prevent DB bloat
        old_logs = FetchLog.query.filter_by(user_id=user_id).order_by(FetchLog.timestamp.desc()).offset(200).all()
        for old_log in old_logs:
            db.session.delete(old_log)
            
        log = FetchLog(user_id=user_id, status=status, details=details, source=source)
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"Error writing fetch log: {e}")


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        meter_number = request.form.get('meter_number')
        
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already exists', 'warning')
            return redirect(url_for('register'))
            
        meter = Meter.query.filter_by(meter_number=meter_number).first()
        if meter:
            flash('Meter number already registered', 'warning')
            return redirect(url_for('register'))
            
        new_user = User(
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        
        new_meter = Meter(
            user_id=new_user.id,
            meter_number=meter_number
        )
        db.session.add(new_meter)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    meter = Meter.query.filter_by(user_id=current_user.id).first()
    
    # Get all balances ordered by date descending
    balances = Balance.query.filter_by(meter_id=meter.id).order_by(Balance.date.desc()).all()
    
    current_balance = balances[0].balance if balances else 0.0
    
    # Calculate daily usages (Difference between consecutive days)
    daily_usages = []
    
    if balances:
        # Bangladesh timezone BST = UTC+6
        today = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6)).date()
        earliest_date = balances[-1].date
        
        # Build a lookup dict
        balances_by_date = {b.date: b for b in balances}
        
        # Generate list of dates from today down to earliest_date
        curr_date = today
        date_list = []
        while curr_date >= earliest_date:
            date_list.append(curr_date)
            curr_date -= timedelta(days=1)
            
        for d in date_list:
            if d in balances_by_date:
                # Find the first recorded balance older than d
                prev_b = None
                for balance_rec in balances:
                    if balance_rec.date < d:
                        prev_b = balance_rec
                        break
                
                usage = 0.0
                if prev_b:
                    usage = prev_b.balance - balances_by_date[d].balance
                    if usage < 0:
                        usage = 0.0  # recharge occurred
                
                daily_usages.append({
                    'date': d.strftime('%Y-%m-%d'),
                    'balance': f"৳ {balances_by_date[d].balance:.2f}",
                    'usage': f"৳ {usage:.2f}",
                    'usage_value': usage,
                    'status': 'Normal'
                })
            else:
                # Date has no recorded sync
                daily_usages.append({
                    'date': d.strftime('%Y-%m-%d'),
                    'balance': 'N/A',
                    'usage': 'N/A',
                    'usage_value': 0.0,
                    'status': 'Sync missing'
                })
    
    # For yesterday usage, if not available show 'N/A'
    yesterday_usage_display = "N/A (Need 2 days of data)"
    normal_usages = [u for u in daily_usages if u['status'] == 'Normal']
    if len(normal_usages) >= 1:
        # normal_usages[0] corresponds to the latest date's usage (e.g. today's decrease compared to yesterday)
        yesterday_usage_display = f"৳ {normal_usages[0]['usage_value']:.2f}"
        
    # Calculate Average Daily Usage & Days Remaining
    avg_daily_usage = sum(u['usage_value'] for u in normal_usages) / len(normal_usages) if normal_usages else 0.0
    days_remaining = int(current_balance / avg_daily_usage) if avg_daily_usage > 0 else 0
    
    # Chart Data for Daily Usages (Reversed for chronological display, only for normal days)
    chart_daily_dates = [u['date'] for u in reversed(normal_usages)]
    chart_daily_values = [u['usage_value'] for u in reversed(normal_usages)]
    
    # Get last 12 months history
    from models import MonthlyUsage
    monthly_usages_query = MonthlyUsage.query.filter_by(meter_id=meter.id).all()
    
    month_order = {'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6, 'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12}
    monthly_usages = sorted(monthly_usages_query, key=lambda x: (x.year, month_order.get(x.month, 0)), reverse=True)[:12]

    # Chart Data for Monthly Usages
    chart_monthly_labels = [f"{u.month} {u.year}" for u in reversed(monthly_usages)]
    chart_monthly_values = [u.total_usage_tk for u in reversed(monthly_usages)]

    # Calculate last sync time in BST (+6 hours) for display
    last_synced_bst = meter.last_synced + timedelta(hours=6) if meter.last_synced else None

    return render_template('dashboard.html', 
                           meter=meter, 
                           current_balance=current_balance,
                           yesterday_usage_display=yesterday_usage_display,
                           avg_daily_usage=avg_daily_usage,
                           days_remaining=days_remaining,
                           daily_usages=daily_usages,
                           monthly_usages=monthly_usages,
                           chart_daily_dates=chart_daily_dates,
                           chart_daily_values=chart_daily_values,
                           chart_monthly_labels=chart_monthly_labels,
                           chart_monthly_values=chart_monthly_values,
                           last_synced_bst=last_synced_bst)

@app.route('/refresh_data')
@login_required
def refresh_data():
    """Manual trigger to scrape latest data"""
    meter = Meter.query.filter_by(user_id=current_user.id).first()
    if meter:
        scraper = NescoScraper()
        # Fetch usage
        data = scraper.fetch_monthly_usage(meter.meter_number)
        if data is not None:
            # Update last sync time (UTC)
            meter.last_synced = datetime.now(timezone.utc).replace(tzinfo=None)
            
            # Save or update today's balance (Bangladesh timezone BST = UTC+6)
            today = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6)).date()
            balance = Balance.query.filter_by(meter_id=meter.id, date=today).first()
            if balance:
                balance.balance = data['current_balance']
            else:
                balance = Balance(meter_id=meter.id, date=today, balance=data['current_balance'])
                db.session.add(balance)
            
            meter.customer_name = data.get('customer_name', meter.customer_name)
            meter.address = data.get('address', meter.address)
            meter.phone = data.get('phone', meter.phone)
            meter.feeder = data.get('feeder', meter.feeder)
            meter.tariff = data.get('tariff', meter.tariff)
            meter.load = data.get('load', meter.load)
            
            # Save Monthly Usages
            if 'monthly_usages' in data:
                from models import MonthlyUsage
                for mu in data['monthly_usages']:
                    existing_mu = MonthlyUsage.query.filter_by(meter_id=meter.id, year=mu['year'], month=mu['month']).first()
                    if not existing_mu:
                        new_mu = MonthlyUsage(
                            meter_id=meter.id, year=mu['year'], month=mu['month'],
                            total_recharge=mu['total_recharge'], used_electricity_tk=mu['used_electricity_tk'],
                            meter_rent=mu['meter_rent'], demand_charge=mu['demand_charge'],
                            vat=mu['vat'], total_usage_tk=mu['total_usage_tk'],
                            end_month_balance=mu['end_month_balance'], used_energy_kwh=mu['used_energy_kwh']
                        )
                        db.session.add(new_mu)
            
            # Fetch recharge history
            recharges = scraper.fetch_recharge_history(meter.meter_number)
            if recharges:
                for r in recharges:
                    try:
                        # Assuming date format is YYYY-MM-DD
                        r_date = datetime.strptime(r['date'][:10], '%Y-%m-%d')
                        # Check if exists based on date and token
                        existing = Recharge.query.filter_by(meter_id=meter.id, token=r['token']).first()
                        if not existing:
                            new_recharge = Recharge(
                                meter_id=meter.id, 
                                date=r_date, 
                                amount=r['amount'], 
                                token=r['token'],
                                energy_cost=r.get('energy_cost', 0.0),
                                method=r.get('method', ''),
                                status=r.get('status', '')
                            )
                            db.session.add(new_recharge)
                    except Exception as e:
                        print(f"Error parsing recharge date {r['date']}: {e}")

            db.session.commit()
            log_fetch(current_user.id, "Success", f"Scraped balance: ৳ {data['current_balance']:.2f}. Manual refresh.", "Manual")
            flash('Data refreshed successfully.', 'success')
        else:
            log_fetch(current_user.id, "Failed", "Failed to fetch data from NESCO panel.", "Manual")
            flash('Failed to fetch data from NESCO.', 'danger')
            
    return redirect(url_for('dashboard'))

@app.route('/logs')
@login_required
def logs():
    from models import FetchLog
    page = request.args.get('page', 1, type=int)
    # Paginate logs for current user (20 per page)
    pagination = FetchLog.query.filter_by(user_id=current_user.id).order_by(FetchLog.timestamp.desc()).paginate(page=page, per_page=20)
    
    # Convert UTC times to BST (UTC+6) for frontend display
    for log in pagination.items:
        log.timestamp_bst = log.timestamp + timedelta(hours=6)
        
    return render_template('logs.html', pagination=pagination)

@app.route('/sw.js')
def service_worker():
    return app.send_static_file('js/sw.js'), 200, {'Content-Type': 'application/javascript'}


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    meter = Meter.query.filter_by(user_id=current_user.id).first()
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_telegram':
            chat_ids = request.form.getlist('telegram_chat_id')
            cleaned_ids = [cid.strip() for cid in chat_ids if cid.strip()]
            current_user.telegram_chat_id = ",".join(cleaned_ids) if cleaned_ids else None
            db.session.commit()
            flash('Telegram settings updated successfully!', 'success')

            
        elif action == 'update_meter':
            new_meter_number = request.form.get('meter_number')
            if new_meter_number:
                new_meter_number = new_meter_number.strip()
            
            if not new_meter_number:
                flash('Meter number cannot be empty.', 'danger')
                return redirect(url_for('settings'))
                
            # Check if registered by another user
            existing = Meter.query.filter_by(meter_number=new_meter_number).first()
            if existing and existing.user_id != current_user.id:
                flash('This meter number is already registered to another account.', 'danger')
                return redirect(url_for('settings'))
                
            if not meter:
                meter = Meter(user_id=current_user.id, meter_number=new_meter_number)
                db.session.add(meter)
            else:
                if meter.meter_number != new_meter_number:
                    # Reset old metadata and remove old data tables since it's a new meter
                    meter.meter_number = new_meter_number
                    meter.customer_name = None
                    meter.address = None
                    meter.phone = None
                    meter.feeder = None
                    meter.tariff = None
                    meter.load = None
                    
                    from models import Balance, Recharge, MonthlyUsage
                    Balance.query.filter_by(meter_id=meter.id).delete()
                    Recharge.query.filter_by(meter_id=meter.id).delete()
                    MonthlyUsage.query.filter_by(meter_id=meter.id).delete()
            
            db.session.commit()
            flash('Meter number updated! Old data cleared. Click "Refresh Data" on the dashboard to fetch the new meter\'s details.', 'success')
            
        return redirect(url_for('settings'))
        
    bot_configured = bool(os.environ.get('TELEGRAM_BOT_TOKEN'))
    return render_template('settings.html', meter=meter, bot_configured=bot_configured)

@app.route('/test_telegram', methods=['POST'])
@login_required
def test_telegram():
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = current_user.telegram_chat_id
    
    if not bot_token:
        flash('Telegram Bot is not configured on the server. Please set TELEGRAM_BOT_TOKEN environment variable.', 'danger')
        return redirect(url_for('settings'))
        
    if not chat_id:
        flash('Please save your Telegram Chat ID first.', 'warning')
        return redirect(url_for('settings'))
        
    from telegram_bot import send_test_message
    success, error_msg = send_test_message(bot_token, chat_id)
    if success:
        flash('Test message sent successfully! Check your Telegram chat.', 'success')
    else:
        flash(f'Failed to send test message: {error_msg}', 'danger')
        
    return redirect(url_for('settings'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not check_password_hash(current_user.password_hash, current_password):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('change_password'))
            
        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            return redirect(url_for('change_password'))
            
        current_user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('change_password.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

def init_db():
    with app.app_context():
        db.create_all()
        # Self-healing migrations for SQLite and PostgreSQL
        try:
            if "sqlite" in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
                # SQLite migrations
                user_cols = [row[1] for row in db.session.execute(db.text("PRAGMA table_info(users)")).fetchall()]
                if 'telegram_chat_id' not in user_cols:
                    db.session.execute(db.text("ALTER TABLE users ADD COLUMN telegram_chat_id TEXT"))
                    db.session.commit()
                
                meter_cols = [row[1] for row in db.session.execute(db.text("PRAGMA table_info(meters)")).fetchall()]
                if 'last_synced' not in meter_cols:
                    db.session.execute(db.text("ALTER TABLE meters ADD COLUMN last_synced TIMESTAMP"))
                    db.session.commit()

                balance_cols = [row[1] for row in db.session.execute(db.text("PRAGMA table_info(balances)")).fetchall()]
                if 'telegram_sent' not in balance_cols:
                    db.session.execute(db.text("ALTER TABLE balances ADD COLUMN telegram_sent BOOLEAN DEFAULT 0 NOT NULL"))
                    db.session.commit()
            else:
                # PostgreSQL (Supabase) migrations
                db.session.execute(db.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT"))
                db.session.execute(db.text("ALTER TABLE users ALTER COLUMN telegram_chat_id TYPE TEXT"))
                db.session.execute(db.text("ALTER TABLE meters ADD COLUMN IF NOT EXISTS last_synced TIMESTAMP"))
                db.session.execute(db.text("ALTER TABLE balances ADD COLUMN IF NOT EXISTS telegram_sent BOOLEAN DEFAULT FALSE NOT NULL"))
                db.session.commit()
            print("Database self-healing columns verified successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"Database self-healing migration skipped/failed: {e}")


# Run database setup and migrations automatically on startup
try:
    init_db()
except Exception as e:
    print(f"Database initialization failed: {e}")

if __name__ == '__main__':
    app.run(debug=True, port=5000)
