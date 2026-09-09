import os
import requests
from django.conf import settings

def get_bot_token():
    """
    Retrieves the Telegram Bot Token from settings or environment variables.
    """
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    if not token:
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
    return token

def send_telegram_message(chat_id, text, parse_mode='HTML'):
    """
    Sends a text message to a Telegram chat using requests.
    Supports HTML markdown formatting.
    """
    token = get_bot_token()
    if not token or not chat_id:
        print("Telegram Warning: Bot token or chat_id not configured.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        response_data = response.json()
        if response_data.get('ok'):
            return True
        else:
            print(f"Telegram Error Response: {response_data}")
            return False
    except Exception as e:
        print(f"Telegram Exception: {str(e)}")
        return False

def generate_telegram_link(user):
    """
    Generates a unique linking token and Telegram bot URL for a user.
    """
    import uuid
    token = f"tg_{uuid.uuid4().hex[:16]}"
    user.telegram_token = token
    user.save()
    
    bot_username = getattr(settings, 'TELEGRAM_BOT_USERNAME', None)
    if not bot_username:
        bot_username = os.environ.get('TELEGRAM_BOT_USERNAME', 'FumaIsakBot')
        
    return f"https://t.me/{bot_username}?start={token}"
