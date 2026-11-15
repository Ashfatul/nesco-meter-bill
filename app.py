import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from extensions import db, login_manager
from models import User, Meter, Balance, Recharge, MonthlyUsage
from scraper import NescoScraper
from datetime import datetime, timezone, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

import re
from urllib.parse import quote_plus

# Dynamically fetch database URI from environment, defaulting to SQLite
db_url = os.environ.get('DATABASE_URL', 'sqlite:///nesco.db')

if db_url and (db_url.startswith("postgres://") or db_url.startswith("postgresql://") or db_url.startswith("postgresql+")):
    # Standardize scheme to postgresql+psycopg2 to use psycopg2 driver
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgresql+psycopg://"):
        db_url = db_url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
        
    # Match scheme, username, password, host/port, and database path
    # This correctly parses passwords containing '@' or other special characters
    match = re.match(r"^(postgresql(?:\+[a-zA-Z0-9_]+)?://)([^:]+):(.*)@([^@/]+)(/.*)?$", db_url)
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

def ensure_db_schema():
    with app.app_context():
        try:
            db.create_all()
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            if 'recharges' in inspector.get_table_names():
                existing_cols = {c['name'] for c in inspector.get_columns('recharges')}
                new_cols = {
                    'meter_rent': 'FLOAT DEFAULT 0.0',
                    'demand_charge': 'FLOAT DEFAULT 0.0',
                    'pfc_charge': 'FLOAT DEFAULT 0.0',
                    'vat': 'FLOAT DEFAULT 0.0',
                    'arrears': 'FLOAT DEFAULT 0.0',
                    'rebate': 'FLOAT DEFAULT 0.0',
                }
                with db.engine.begin() as conn:
                    for col_name, col_type in new_cols.items():
                        if col_name not in existing_cols:
                            conn.execute(text(f"ALTER TABLE recharges ADD COLUMN {col_name} {col_type}"))
        except Exception as e:
            print(f"Error ensuring DB schema: {e}")

ensure_db_schema()

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
    if not meter:
        flash('Please configure your meter number in Settings first.', 'warning')
        return redirect(url_for('settings'))

    month_order = {'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6, 'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12}
    month_order_rev = {v: k for k, v in month_order.items()}
    
    # Get all balances ordered by date descending
    balances = Balance.query.filter_by(meter_id=meter.id).order_by(Balance.date.desc()).all()
    current_balance = balances[0].balance if balances else 0.0
    
    # Bangladesh timezone BST = UTC+6
    today = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6)).date()
    today_month_str = today.strftime('%Y-%m')
    
    # Recharges & Monthly Usages
    recharges_all = sorted(meter.recharges, key=lambda x: x.date, reverse=True)
    recharges_asc = sorted(meter.recharges, key=lambda x: x.date)
    monthly_usages_query = MonthlyUsage.query.filter_by(meter_id=meter.id).all()
    all_monthly_usages = sorted(monthly_usages_query, key=lambda x: (x.year, month_order.get(x.month, 0)), reverse=True)

    # 1. Build all daily usages across all tracked history
    all_daily_usages = []
    pending_recharges = []
    
    if balances:
        earliest_date = balances[-1].date
        balances_by_date = {b.date: b for b in balances}
        
        # Generate full date sequence from today down to earliest_date
        curr_date = today
        date_list = []
        while curr_date >= earliest_date:
            date_list.append(curr_date)
            curr_date -= timedelta(days=1)
            
        # First pass: calculate raw daily usages
        raw_usages = {}
        for d in date_list:
            if d in balances_by_date:
                prev_b = None
                for balance_rec in balances:
                    if balance_rec.date < d:
                        prev_b = balance_rec
                        break
                if prev_b:
                    raw_usages[d] = prev_b.balance - balances_by_date[d].balance
                    
        # Second pass: allocate recharges to dates where NESCO balance actually jumped (raw_usage < 0)
        credited_recharges_by_date = {}
        recharges_by_date = {}
        other_costs_by_date = {}
        
        for r in recharges_asc:
            r_date = r.date.date()
            if r_date < earliest_date - timedelta(days=1):
                continue
                
            energy_val = r.energy_cost if r.energy_cost else r.amount
            other_val = r.amount - energy_val
            
            target_date = None
            for offset in range(7):
                candidate = r_date + timedelta(days=offset)
                if candidate in raw_usages and raw_usages[candidate] < 0:
                    target_date = candidate
                    break
                    
            if target_date:
                if target_date not in credited_recharges_by_date:
                    credited_recharges_by_date[target_date] = []
                credited_recharges_by_date[target_date].append(r)
                recharges_by_date[target_date] = recharges_by_date.get(target_date, 0.0) + energy_val
                other_costs_by_date[target_date] = other_costs_by_date.get(target_date, 0.0) + other_val
            else:
                if (today - r_date).days <= 7:
                    pending_recharges.append(r)
                other_costs_by_date[r_date] = other_costs_by_date.get(r_date, 0.0) + other_val

        # Third pass: build daily usages list with distinct recharge rows inserted
        for d in date_list:
            d_month_str = d.strftime('%Y-%m')
            recharges_on_d = [r for r in recharges_asc if r.date.date() == d and r.date.date() >= earliest_date - timedelta(days=1)]
            for r in recharges_on_d:
                energy_val = r.energy_cost if r.energy_cost else r.amount
                other_val = r.amount - energy_val
                arrears_val = getattr(r, 'arrears', 0.0) or 0.0
                other_fees_val = max(0.0, other_val - arrears_val)
                is_pending = r in pending_recharges
                all_daily_usages.append({
                    'date': d.strftime('%Y-%m-%d'),
                    'date_obj': d,
                    'month_str': d_month_str,
                    'is_recharge_row': True,
                    'balance': f"+ ৳ {r.amount:.2f}",
                    'balance_val': None,
                    'other_cost': f"৳ {other_val:.2f}" if other_val > 0 else "-",
                    'arrears': arrears_val,
                    'other_fees': other_fees_val,
                    'vat': getattr(r, 'vat', 0.0) or 0.0,
                    'meter_rent': getattr(r, 'meter_rent', 0.0) or 0.0,
                    'demand_charge': getattr(r, 'demand_charge', 0.0) or 0.0,
                    'usage': f"+ ৳ {energy_val:.2f}",
                    'usage_value': energy_val,
                    'status': 'Pending NESCO Credit' if is_pending else 'Recharge Credited',
                    'token': r.token,
                    'method': r.method,
                    'recharge': r
                })

            if d in balances_by_date:
                b_val = balances_by_date[d].balance
                if d in raw_usages:
                    usage = raw_usages[d]
                    if d in recharges_by_date:
                        usage += recharges_by_date[d]
                    if usage < 0:
                        usage = 0.0
                    
                    all_daily_usages.append({
                        'date': d.strftime('%Y-%m-%d'),
                        'date_obj': d,
                        'month_str': d_month_str,
                        'is_recharge_row': False,
                        'balance': f"৳ {b_val:.2f}",
                        'balance_val': b_val,
                        'usage': f"৳ {usage:.2f}",
                        'usage_value': usage,
                        'other_cost': "-",
                        'status': 'Normal'
                    })
                else:
                    # Oldest balance in history has no older data to compare
                    all_daily_usages.append({
                        'date': d.strftime('%Y-%m-%d'),
                        'date_obj': d,
                        'month_str': d_month_str,
                        'is_recharge_row': False,
                        'balance': f"৳ {b_val:.2f}",
                        'balance_val': b_val,
                        'usage': 'N/A',
                        'usage_value': 0.0,
                        'other_cost': "-",
                        'status': 'Initial Balance'
                    })
            else:
                all_daily_usages.append({
                    'date': d.strftime('%Y-%m-%d'),
                    'date_obj': d,
                    'month_str': d_month_str,
                    'is_recharge_row': False,
                    'balance': 'N/A',
                    'balance_val': None,
                    'usage': 'N/A',
                    'usage_value': 0.0,
                    'other_cost': "-",
                    'status': 'Sync missing'
                })

    # 2. Extract all available months (from balances, recharges, and monthly usages)
    b_months = set(b.date.strftime('%Y-%m') for b in balances)
    r_months = set(r.date.strftime('%Y-%m') for r in recharges_asc)
    mu_months = set(f"{mu.year}-{month_order.get(mu.month, 1):02d}" for mu in all_monthly_usages)
    all_month_keys = sorted(b_months.union(r_months).union(mu_months), reverse=True)
    if not all_month_keys:
        all_month_keys = [today_month_str]

    # Build available_months list with readable labels
    available_months = []
    for m_key in all_month_keys:
        try:
            m_dt = datetime.strptime(m_key, '%Y-%m')
            label = m_dt.strftime('%B %Y')
        except Exception:
            label = m_key
        available_months.append({
            'key': m_key,
            'label': label,
            'is_current': (m_key == today_month_str)
        })

    # Determine selected month from request args, default to current month or latest available
    req_month = request.args.get('month')
    if req_month and req_month in all_month_keys:
        selected_month = req_month
    elif today_month_str in all_month_keys:
        selected_month = today_month_str
    else:
        selected_month = all_month_keys[0]

    # Prev and Next month navigation keys
    idx = all_month_keys.index(selected_month)
    next_month = all_month_keys[idx - 1] if idx > 0 else None
    prev_month = all_month_keys[idx + 1] if idx < len(all_month_keys) - 1 else None

    def get_month_label(m_key):
        if not m_key:
            return ""
        try:
            return datetime.strptime(m_key, '%Y-%m').strftime('%b %Y')
        except Exception:
            return m_key

    prev_month_label = get_month_label(prev_month)
    next_month_label = get_month_label(next_month)

    try:
        selected_month_label = datetime.strptime(selected_month, '%Y-%m').strftime('%B %Y')
    except Exception:
        selected_month_label = selected_month

    is_selected_current = (selected_month == today_month_str)

    # 3. Filter daily usages & recharges for the SELECTED MONTH
    month_daily_usages = [u for u in all_daily_usages if u['month_str'] == selected_month]
    month_normal_usages = [u for u in month_daily_usages if not u['is_recharge_row'] and u['status'] == 'Normal']
    
    month_total_usage = sum(u['usage_value'] for u in month_normal_usages)
    month_days_recorded = len(month_normal_usages)
    month_avg_daily_usage = (month_total_usage / month_days_recorded) if month_days_recorded > 0 else 0.0

    month_peak = max(month_normal_usages, key=lambda x: x['usage_value']) if month_normal_usages else None
    month_peak_usage = month_peak['usage_value'] if month_peak else 0.0
    month_peak_date = month_peak['date'] if month_peak else None

    # Recharges belonging to the selected month
    month_recharges = [r for r in recharges_all if r.date.strftime('%Y-%m') == selected_month]
    month_total_recharge = sum(r.amount for r in month_recharges)
    month_energy_recharge = sum(r.energy_cost or 0.0 for r in month_recharges)
    month_fees_recharge = month_total_recharge - month_energy_recharge
    month_arrears_recharge = sum(getattr(r, 'arrears', 0.0) or 0.0 for r in month_recharges)

    # Yesterday usage and days remaining (if viewing current month)
    yesterday_usage_display = None
    days_remaining = None
    month_end_balance = None

    if is_selected_current:
        if month_normal_usages:
            yesterday_usage_display = f"৳ {month_normal_usages[0]['usage_value']:.2f}"
        else:
            yesterday_usage_display = "N/A"
        days_remaining = int(current_balance / month_avg_daily_usage) if month_avg_daily_usage > 0 else 0
    else:
        # Find latest recorded balance of this historical month
        hist_balances = [u for u in month_daily_usages if not u['is_recharge_row'] and u.get('balance_val') is not None]
        month_end_balance = hist_balances[0]['balance_val'] if hist_balances else None

    # Check for official NESCO MonthlyUsage record for selected month
    sel_parts = selected_month.split('-')
    sel_year = int(sel_parts[0])
    sel_month_num = int(sel_parts[1])
    sel_month_name = month_order_rev.get(sel_month_num, '')
    official_month_usage = next((m for m in all_monthly_usages if m.year == sel_year and m.month == sel_month_name), None)

    # Chart data for selected month (chronological order)
    chart_month_dates = [u['date'] for u in reversed(month_normal_usages)]
    chart_month_values = [round(u['usage_value'], 2) for u in reversed(month_normal_usages)]

    # 4. OVERALL WHOLE-DATA RECORDS & LIFETIME STATS
    # All-time recharges
    overall_total_recharge_amt = sum(r.amount for r in recharges_all)
    overall_total_energy_cost = sum(r.energy_cost or 0.0 for r in recharges_all)
    overall_total_fees = overall_total_recharge_amt - overall_total_energy_cost
    overall_total_arrears = sum(getattr(r, 'arrears', 0.0) or 0.0 for r in recharges_all)
    overall_recharge_count = len(recharges_all)
    overall_avg_recharge_amt = (overall_total_recharge_amt / overall_recharge_count) if overall_recharge_count > 0 else 0.0

    # All-time tracked daily usages
    all_normal_usages = [u for u in all_daily_usages if not u['is_recharge_row'] and u['status'] == 'Normal']
    overall_total_daily_usage = sum(u['usage_value'] for u in all_normal_usages)
    overall_tracked_days = len(all_normal_usages)
    overall_avg_daily_usage = (overall_total_daily_usage / overall_tracked_days) if overall_tracked_days > 0 else 0.0
    overall_peak_day = max(all_normal_usages, key=lambda x: x['usage_value']) if all_normal_usages else None

    # Earliest & latest tracked dates
    earliest_tracked_date = balances[-1].date if balances else None
    latest_tracked_date = balances[0].date if balances else None

    # Official monthly statements aggregate
    overall_official_billed_tk = sum(m.total_usage_tk or 0.0 for m in all_monthly_usages)
    overall_official_kwh = sum(m.used_energy_kwh or 0.0 for m in all_monthly_usages)
    overall_official_recharge = sum(m.total_recharge or 0.0 for m in all_monthly_usages)
    overall_official_electricity_tk = sum(m.used_electricity_tk or 0.0 for m in all_monthly_usages)
    overall_official_meter_rent = sum(m.meter_rent or 0.0 for m in all_monthly_usages)
    overall_official_demand_charge = sum(m.demand_charge or 0.0 for m in all_monthly_usages)
    overall_official_vat = sum(m.vat or 0.0 for m in all_monthly_usages)
    overall_official_months_count = len(all_monthly_usages)
    overall_avg_monthly_bill = (overall_official_billed_tk / overall_official_months_count) if overall_official_months_count > 0 else 0.0
    overall_avg_monthly_kwh = (overall_official_kwh / overall_official_months_count) if overall_official_months_count > 0 else 0.0

    highest_usage_month = max(all_monthly_usages, key=lambda x: x.total_usage_tk or 0.0) if all_monthly_usages else None
    lowest_usage_month = min(all_monthly_usages, key=lambda x: x.total_usage_tk or 999999.0) if all_monthly_usages else None

    # Overall Monthly Chart Data
    chart_overall_labels = [f"{u.month[:3]} '{str(u.year)[2:]}" for u in reversed(all_monthly_usages)]
    chart_overall_values_tk = [round(u.total_usage_tk or 0.0, 2) for u in reversed(all_monthly_usages)]
    chart_overall_values_kwh = [round(u.used_energy_kwh or 0.0, 2) for u in reversed(all_monthly_usages)]

    # Active tab parameter ('monthly' or 'overall')
    active_tab = request.args.get('tab', 'monthly')
    if active_tab not in ['monthly', 'overall']:
        active_tab = 'monthly'

    # BST last synced time
    last_synced_bst = meter.last_synced + timedelta(hours=6) if meter.last_synced else None

    return render_template('dashboard.html', 
                           meter=meter, 
                           current_balance=current_balance,
                           last_synced_bst=last_synced_bst,
                           pending_recharges=pending_recharges,
                           active_tab=active_tab,
                           # Month-wise context
                           available_months=available_months,
                           selected_month=selected_month,
                           selected_month_label=selected_month_label,
                           is_selected_current=is_selected_current,
                           prev_month=prev_month,
                           prev_month_label=prev_month_label,
                           next_month=next_month,
                           next_month_label=next_month_label,
                           month_daily_usages=month_daily_usages,
                           month_total_usage=month_total_usage,
                           month_days_recorded=month_days_recorded,
                           month_avg_daily_usage=month_avg_daily_usage,
                           month_peak_usage=month_peak_usage,
                           month_peak_date=month_peak_date,
                           month_total_recharge=month_total_recharge,
                           month_energy_recharge=month_energy_recharge,
                           month_fees_recharge=month_fees_recharge,
                           month_arrears_recharge=month_arrears_recharge,
                           month_recharges=month_recharges,
                           yesterday_usage_display=yesterday_usage_display,
                           days_remaining=days_remaining,
                           month_end_balance=month_end_balance,
                           official_month_usage=official_month_usage,
                           chart_month_dates=chart_month_dates,
                           chart_month_values=chart_month_values,
                           # Overall context
                           overall_total_recharge_amt=overall_total_recharge_amt,
                           overall_total_energy_cost=overall_total_energy_cost,
                           overall_total_fees=overall_total_fees,
                           overall_total_arrears=overall_total_arrears,
                           overall_recharge_count=overall_recharge_count,
                           overall_avg_recharge_amt=overall_avg_recharge_amt,
                           overall_total_daily_usage=overall_total_daily_usage,
                           overall_tracked_days=overall_tracked_days,
                           overall_avg_daily_usage=overall_avg_daily_usage,
                           overall_peak_day=overall_peak_day,
                           earliest_tracked_date=earliest_tracked_date,
                           latest_tracked_date=latest_tracked_date,
                           overall_official_billed_tk=overall_official_billed_tk,
                           overall_official_kwh=overall_official_kwh,
                           overall_official_recharge=overall_official_recharge,
                           overall_official_electricity_tk=overall_official_electricity_tk,
                           overall_official_meter_rent=overall_official_meter_rent,
                           overall_official_demand_charge=overall_official_demand_charge,
                           overall_official_vat=overall_official_vat,
                           overall_official_months_count=overall_official_months_count,
                           overall_avg_monthly_bill=overall_avg_monthly_bill,
                           overall_avg_monthly_kwh=overall_avg_monthly_kwh,
                           highest_usage_month=highest_usage_month,
                           lowest_usage_month=lowest_usage_month,
                           all_monthly_usages=all_monthly_usages,
                           chart_overall_labels=chart_overall_labels,
                           chart_overall_values_tk=chart_overall_values_tk,
                           chart_overall_values_kwh=chart_overall_values_kwh,
                           all_recharges=recharges_all)

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
                                meter_rent=r.get('meter_rent', 0.0),
                                demand_charge=r.get('demand_charge', 0.0),
                                pfc_charge=r.get('pfc_charge', 0.0),
                                vat=r.get('vat', 0.0),
                                arrears=r.get('arrears', 0.0),
                                rebate=r.get('rebate', 0.0),
                                energy_cost=r.get('energy_cost', 0.0),
                                method=r.get('method', ''),
                                status=r.get('status', '')
                            )
                            db.session.add(new_recharge)
                        else:
                            existing.amount = r['amount']
                            existing.energy_cost = r.get('energy_cost', existing.energy_cost)
                            existing.meter_rent = r.get('meter_rent', 0.0)
                            existing.demand_charge = r.get('demand_charge', 0.0)
                            existing.pfc_charge = r.get('pfc_charge', 0.0)
                            existing.vat = r.get('vat', 0.0)
                            existing.arrears = r.get('arrears', 0.0)
                            existing.rebate = r.get('rebate', 0.0)
                            existing.method = r.get('method', existing.method)
                            existing.status = r.get('status', existing.status)
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

@app.route('/request_local_sync')
@login_required
def request_local_sync():
    meter = Meter.query.filter_by(user_id=current_user.id).first()
    if meter:
        meter.sync_requested = True
        db.session.commit()
        log_fetch(current_user.id, "Success", "Requested a manual sync from local PC.", "Manual")
        flash('Local sync requested. If your local PC is on, it will fetch the latest data shortly.', 'info')
    else:
        flash('No meter configured to sync.', 'warning')
    return redirect(url_for('dashboard'))



@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    meter = Meter.query.filter_by(user_id=current_user.id).first()
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_telegram':
            chat_ids = request.form.getlist('telegram_chat_id')
            cleaned_ids = []
            for cid in chat_ids:
                parts = [p.strip() for p in re.split(r'[\s,;\n]+', cid) if p.strip()]
                for p in parts:
                    if p not in cleaned_ids:
                        cleaned_ids.append(p)
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
    success, msg = send_test_message(bot_token, chat_id)
    if success and "Failures:" not in msg:
        flash(msg, 'success')
    elif success:
        flash(f'Partial Success: {msg}', 'warning')
    else:
        flash(f'Failed to send test message: {msg}', 'danger')
        
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
                if 'sync_requested' not in meter_cols:
                    db.session.execute(db.text("ALTER TABLE meters ADD COLUMN sync_requested BOOLEAN DEFAULT 0 NOT NULL"))
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
                db.session.execute(db.text("ALTER TABLE meters ADD COLUMN IF NOT EXISTS sync_requested BOOLEAN DEFAULT FALSE NOT NULL"))
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
