import sys
import os
from app import app, db
from models import User, Meter, Balance
from scraper import NescoScraper
from datetime import datetime

def run_daily_fetch():
    """
    This script is designed to be run via a cron job.
    It loops through all registered users and fetches their latest balance.
    """
    with app.app_context():
        users = User.query.all()
        for user in users:
            meter = Meter.query.filter_by(user_id=user.id).first()
            if not meter:
                continue
                
            print(f"[{datetime.now()}] Fetching data for meter {meter.meter_number}...")
            scraper = NescoScraper()
            data = scraper.fetch_monthly_usage(meter.meter_number)
            
            if data and 'current_balance' in data:
                today = datetime.now().date()
                existing = Balance.query.filter_by(meter_id=meter.id, date=today).first()
                if not existing:
                    new_balance = Balance(meter_id=meter.id, date=today, balance=data['current_balance'])
                    db.session.add(new_balance)
                    db.session.commit()
                    print(f"[{datetime.now()}] Success: Recorded balance ৳ {data['current_balance']}")
                else:
                    print(f"[{datetime.now()}] Skipped: Balance already recorded for today.")
            else:
                print(f"[{datetime.now()}] Error: Failed to fetch balance for {meter.meter_number}.")

if __name__ == '__main__':
    run_daily_fetch()
