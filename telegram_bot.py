import os
import requests

def send_telegram_alert(user, meter):
    """Formats and sends daily balance status to user's Telegram."""
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = user.telegram_chat_id
    
    if not bot_token or not chat_id:
        print(f"Skipping Telegram notification for User {user.email}: TELEGRAM_BOT_TOKEN or telegram_chat_id not configured.")
        return False
        
    metrics = meter.get_metrics()
    current_balance = metrics['current_balance']
    yesterday_usage = metrics['yesterday_usage']
    avg_daily_usage = metrics['avg_daily_usage']
    days_remaining = metrics['days_remaining']
    
    message = (
        f"🔌 <b>NESCO Meter Status Update</b>\n\n"
        f"👤 <b>Customer Name:</b> {meter.customer_name or 'N/A'}\n"
        f"🔢 <b>Meter Number:</b> <code>{meter.meter_number}</code>\n\n"
        f"💰 <b>Current Balance:</b> ৳ {current_balance:.2f}\n"
        f"📉 <b>Previous Day Usage:</b> ৳ {yesterday_usage:.2f}\n"
        f"📊 <b>Average Daily Usage:</b> ৳ {avg_daily_usage:.2f}\n"
        f"📅 <b>Estimated Days Left:</b> {days_remaining} Days\n"
    )
    
    if current_balance < 50.0:
        message += f"\n⚠️ <b>LOW BALANCE WARNING:</b> Your balance is below ৳ 50.00! Please recharge immediately."
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"Successfully sent Telegram alert to {user.email}.")
            return True
        else:
            print(f"Failed to send Telegram alert to {user.email}: {response.text}")
            return False
    except Exception as e:
        print(f"Error sending Telegram alert: {e}")
        return False

def send_test_message(bot_token, chat_id):
    """Sends a quick test message to verify Bot Token and Chat ID connection."""
    message = (
        f"🔌 <b>NESCO Tracker Test Connection</b>\n\n"
        f"✅ Your Telegram Bot notification channel is now successfully configured! You will receive daily status updates here."
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200, response.text
    except Exception as e:
        return False, str(e)
