import os
from flask import Flask, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from extensions import db, login_manager
from models import User, Meter, Balance, Recharge
from scraper import NescoScraper
from datetime import datetime, timedelta

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
    for i in range(len(balances) - 1):
        # usage = previous day's balance - current day's balance
        # (This is simplified; if recharges happened, they would need to be added)
        usage = balances[i+1].balance - balances[i].balance
        if usage < 0: 
            usage = 0 # If negative, it means a recharge happened, so usage estimation is thrown off unless we factor recharge
        daily_usages.append({
            'date': balances[i].date.strftime('%Y-%m-%d'),
            'balance': balances[i].balance,
            'usage': usage
        })
    
    # For yesterday usage, if not available show 'N/A'
    yesterday_usage_display = f"৳ {daily_usages[0]['usage']:.2f}" if daily_usages else "N/A (Need 2 days of data)"
    
    # Calculate Average Daily Usage & Days Remaining
    avg_daily_usage = sum(u['usage'] for u in daily_usages) / len(daily_usages) if daily_usages else 0.0
    days_remaining = int(current_balance / avg_daily_usage) if avg_daily_usage > 0 else 0
    
    # Chart Data for Daily Usages (Reversed for chronological left-to-right display)
    chart_daily_dates = [u['date'] for u in reversed(daily_usages)]
    chart_daily_values = [u['usage'] for u in reversed(daily_usages)]
    
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
            # Update last sync time
            meter.last_synced = datetime.now()
            
            # Save or update today's balance
            today = datetime.now().date()
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
            flash('Data refreshed successfully.', 'success')
        else:
            flash('Failed to fetch data from NESCO.', 'danger')
            
    return redirect(url_for('dashboard'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    meter = Meter.query.filter_by(user_id=current_user.id).first()
    if request.method == 'POST':
        telegram_chat_id = request.form.get('telegram_chat_id')
        if telegram_chat_id:
            telegram_chat_id = telegram_chat_id.strip()
        current_user.telegram_chat_id = telegram_chat_id
        db.session.commit()
        flash('Settings updated successfully!', 'success')
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

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
