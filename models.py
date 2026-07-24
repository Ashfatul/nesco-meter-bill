from extensions import db
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    telegram_chat_id = db.Column(db.String(100))
    
    # Relationships
    meters = db.relationship('Meter', backref='user', lazy=True)

class Meter(db.Model):
    __tablename__ = 'meters'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    meter_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_name = db.Column(db.String(100))
    address = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    feeder = db.Column(db.String(100))
    tariff = db.Column(db.String(50))
    load = db.Column(db.String(50))
    last_synced = db.Column(db.DateTime)
    
    # Relationships
    balances = db.relationship('Balance', backref='meter', lazy=True)
    recharges = db.relationship('Recharge', backref='meter', lazy=True)
    monthly_usages = db.relationship('MonthlyUsage', backref='meter', lazy=True)

    def get_metrics(self):
        # Sort balances descending (latest first)
        balances_sorted = sorted(self.balances, key=lambda x: x.date, reverse=True)
        if not balances_sorted:
            return {
                'current_balance': 0.0,
                'yesterday_usage': 0.0,
                'avg_daily_usage': 0.0,
                'days_remaining': 0
            }
        
        current_balance = balances_sorted[0].balance
        
        daily_usages = []
        for i in range(len(balances_sorted) - 1):
            usage = balances_sorted[i+1].balance - balances_sorted[i].balance
            if usage < 0:
                usage = 0.0
            daily_usages.append(usage)
            
        yesterday_usage = daily_usages[0] if daily_usages else 0.0
        avg_daily_usage = sum(daily_usages) / len(daily_usages) if daily_usages else 0.0
        days_remaining = int(current_balance / avg_daily_usage) if avg_daily_usage > 0 else 0
        
        return {
            'current_balance': current_balance,
            'yesterday_usage': yesterday_usage,
            'avg_daily_usage': avg_daily_usage,
            'days_remaining': days_remaining
        }

class Balance(db.Model):
    __tablename__ = 'balances'
    id = db.Column(db.Integer, primary_key=True)
    meter_id = db.Column(db.Integer, db.ForeignKey('meters.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    balance = db.Column(db.Float, nullable=False)
    
    __table_args__ = (db.UniqueConstraint('meter_id', 'date', name='_meter_date_uc'),)

class Recharge(db.Model):
    __tablename__ = 'recharges'
    id = db.Column(db.Integer, primary_key=True)
    meter_id = db.Column(db.Integer, db.ForeignKey('meters.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    energy_cost = db.Column(db.Float)
    method = db.Column(db.String(50))
    status = db.Column(db.String(50))

class MonthlyUsage(db.Model):
    __tablename__ = 'monthly_usages'
    id = db.Column(db.Integer, primary_key=True)
    meter_id = db.Column(db.Integer, db.ForeignKey('meters.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.String(20), nullable=False)
    total_recharge = db.Column(db.Float)
    used_electricity_tk = db.Column(db.Float)
    meter_rent = db.Column(db.Float)
    demand_charge = db.Column(db.Float)
    vat = db.Column(db.Float)
    total_usage_tk = db.Column(db.Float)
    end_month_balance = db.Column(db.Float)
    used_energy_kwh = db.Column(db.Float)
    
    __table_args__ = (db.UniqueConstraint('meter_id', 'year', 'month', name='_meter_ym_uc'),)
