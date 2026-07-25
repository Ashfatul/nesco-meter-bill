import sys
import os
from app import app, db, log_fetch
from models import User, Meter, Balance
from scraper import NescoScraper
from datetime import datetime, timezone, timedelta

def run_daily_fetch():
    """
    This script is designed to be run via a cron job.
    It loops through all registered users and fetches their latest balance.
    """
    with app.app_context():
        # Check database connection type
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        db_type = "PostgreSQL" if "postgresql" in db_uri else "SQLite"
        print(f"[{datetime.now()}] Connected to database type: {db_type}")
        
        users = User.query.all()
        print(f"[{datetime.now()}] Found {len(users)} users in database to fetch.")
        for user in users:
            meter = Meter.query.filter_by(user_id=user.id).first()
            if not meter:
                continue
                
            print(f"[{datetime.now()}] Fetching data for meter {meter.meter_number}...")
            scraper = NescoScraper()
            data = scraper.fetch_monthly_usage(meter.meter_number)
            
            if data and 'current_balance' in data:
                # Update last sync time (UTC)
                meter.last_synced = datetime.now(timezone.utc).replace(tzinfo=None)
                
                today = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6)).date()
                existing = Balance.query.filter_by(meter_id=meter.id, date=today).first()
                
                # Find the latest balance record before today
                prev_balance_record = Balance.query.filter(
                    Balance.meter_id == meter.id,
                    Balance.date < today
                ).order_by(Balance.date.desc()).first()
                
                current_val = data['current_balance']
                balance_changed = False
                if prev_balance_record is None or current_val != prev_balance_record.balance:
                    balance_changed = True
                    
                telegram_sent_this_time = False
                
                if not existing:
                    # Create new today balance record
                    new_balance = Balance(meter_id=meter.id, date=today, balance=current_val, telegram_sent=False)
                    db.session.add(new_balance)
                    db.session.commit()
                    
                    if balance_changed:
                        # Send telegram alert
                        try:
                            from telegram_bot import send_telegram_alert
                            if send_telegram_alert(user, meter):
                                new_balance.telegram_sent = True
                                telegram_sent_this_time = True
                        except Exception as e:
                            print(f"[{datetime.now()}] Error sending Telegram alert for user {user.email}: {e}")
                    
                    db.session.commit()
                    
                    details = f"Scraped balance: ৳ {current_val:.2f}."
                    if telegram_sent_this_time:
                        details += " Balance changed. Telegram alert sent."
                    else:
                        details += " No balance change. Telegram alert skipped."
                    
                    log_fetch(user.id, "Success", details, "Cron")
                    print(f"[{datetime.now()}] Success: Recorded balance ৳ {current_val}. {details}")
                    
                else:
                    # Update existing today's balance
                    old_recorded_val = existing.balance
                    existing.balance = current_val
                    db.session.commit()
                    
                    # If we haven't sent telegram today yet, check if we should send it now
                    if not existing.telegram_sent and balance_changed:
                        try:
                            from telegram_bot import send_telegram_alert
                            if send_telegram_alert(user, meter):
                                existing.telegram_sent = True
                                telegram_sent_this_time = True
                        except Exception as e:
                            print(f"[{datetime.now()}] Error sending Telegram alert for user {user.email}: {e}")
                    
                    db.session.commit()
                    
                    details = f"Scraped balance: ৳ {current_val:.2f} (Updated today's balance from ৳ {old_recorded_val:.2f})."
                    if telegram_sent_this_time:
                        details += " Telegram alert sent."
                    elif existing.telegram_sent:
                        details += " Telegram already sent today."
                    else:
                        details += " No balance change. Telegram alert skipped."
                    
                    log_fetch(user.id, "Success", details, "Cron")
                    print(f"[{datetime.now()}] Success: Updated balance to ৳ {current_val}. {details}")
            else:
                details = f"Failed to fetch data from NESCO panel for meter: {meter.meter_number}."
                log_fetch(user.id, "Failed", details, "Cron")
                print(f"[{datetime.now()}] Error: Failed to fetch balance for {meter.meter_number}.")


if __name__ == '__main__':
    run_daily_fetch()
