import os
import requests

def send_telegram_alert(user, meter):
    """Formats and sends daily balance status to all configured Telegram Chat IDs."""
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id_str = user.telegram_chat_id
    
    if not bot_token or not chat_id_str:
        print(f"Skipping Telegram notification for User {user.email}: TELEGRAM_BOT_TOKEN or telegram_chat_id not configured.")
        return False
        
    chat_ids = [c.strip() for c in chat_id_str.split(',') if c.strip()]
    if not chat_ids:
        print(f"Skipping Telegram notification for User {user.email}: No valid chat IDs found.")
        return False
        
    metrics = meter.get_metrics()
    current_balance = metrics['current_balance']
    yesterday_usage = metrics['yesterday_usage']
    avg_daily_usage = metrics['avg_daily_usage']
    days_remaining = metrics['days_remaining']
    
    from datetime import datetime, timezone, timedelta
    sync_time_bst = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6))
    sync_time_str = sync_time_bst.strftime('%Y-%m-%d %I:%M %p')
    
    message = (
        f"🔌 <b>NESCO Meter Status Update</b>\n"
        f"📅 <b>As of:</b> {sync_time_str}\n\n"
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
    
    any_success = False
    for cid in chat_ids:
        payload = {
            "chat_id": cid,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"Successfully sent Telegram alert to {user.email} (Chat ID: {cid}).")
                any_success = True
            else:
                print(f"Failed to send Telegram alert to {user.email} (Chat ID: {cid}): {response.text}")
        except Exception as e:
            print(f"Error sending Telegram alert to {user.email} (Chat ID: {cid}): {e}")
            
    return any_success

def send_test_message(bot_token, chat_id_str):
    """Sends a quick test message to verify Bot Token and Chat ID connection."""
    chat_ids = [c.strip() for c in chat_id_str.split(',') if c.strip()]
    if not chat_ids:
        return False, "No valid chat IDs found."
        
    from datetime import datetime, timezone, timedelta
    sync_time_bst = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6))
    sync_time_str = sync_time_bst.strftime('%Y-%m-%d %I:%M %p')
    
    message = (
        f"🧪 <b>NESCO Meter Status Update [TEST CONNECTION]</b>\n"
        f"📅 <b>As of:</b> {sync_time_str}\n\n"
        f"👤 <b>Customer Name:</b> TEST CUSTOMER\n"
        f"🔢 <b>Meter Number:</b> <code>1234567890</code>\n\n"
        f"💰 <b>Current Balance:</b> ৳ 0.00\n"
        f"📉 <b>Previous Day Usage:</b> ৳ 0.00\n"
        f"📊 <b>Average Daily Usage:</b> ৳ 0.00\n"
        f"📅 <b>Estimated Days Left:</b> 0 Days\n\n"
        f"✅ Your Telegram Bot notification channel is now successfully configured! You will receive daily status updates here."
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    failures = []
    success_count = 0
    
    for cid in chat_ids:
        payload = {
            "chat_id": cid,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                success_count += 1
            else:
                failures.append(f"{cid} (Status {response.status_code}: {response.text[:100]})")
        except Exception as e:
            failures.append(f"{cid} (Error: {str(e)})")
            
    if failures:
        err_msg = f"Sent to {success_count}/{len(chat_ids)} chats. Failed chats: " + ", ".join(failures)
        return success_count > 0, err_msg
    return True, "Test messages sent successfully to all chat IDs."

