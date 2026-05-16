"""
routes/telegram.py — NoveeBus Telegram Bot webhook handler.

Supported commands:
  /start <token>  — Link Telegram account to NoveeBus employee ID
  /status         — Show today's upcoming bookings
  /unlink         — Unlink this Telegram account
"""

import os
import logging
from datetime import date
from flask import Blueprint, request, jsonify
from models import User, Booking, Schedule
from extensions import db

logger = logging.getLogger(__name__)
telegram_bp = Blueprint('telegram', __name__)

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')


def _send(chat_id, text, parse_mode=None):
    """Send a message via Telegram Bot API."""
    if not BOT_TOKEN:
        return
    import requests
    payload = {'chat_id': chat_id, 'text': text}
    if parse_mode:
        payload['parse_mode'] = parse_mode
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json=payload,
            timeout=5
        )
    except Exception as e:
        logger.warning(f'Telegram send failed: {e}')


@telegram_bp.route('/telegram/webhook', methods=['POST'])
def webhook():
    """Receive updates from Telegram."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'ok': True})

    # Handle regular messages
    message = data.get('message') or data.get('edited_message')
    if not message:
        return jsonify({'ok': True})

    chat_id = str(message.get('chat', {}).get('id', ''))
    text = (message.get('text') or '').strip()

    if not chat_id or not text:
        return jsonify({'ok': True})

    # --- /start <link_token> ---
    if text.startswith('/start'):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            link_token = parts[1].strip()
            user = User.query.filter_by(telegram_link_token=link_token, active=True).first()
            if user:
                user.telegram_chat_id = chat_id
                user.telegram_link_token = None
                db.session.commit()
                _send(chat_id,
                      f'✅ Linked! Hi {user.name}, your NoveeBus account is now connected.\n'
                      f'You\'ll receive booking reminders and arrival alerts here.\n\n'
                      f'Try /status to see your upcoming rides.')
            else:
                _send(chat_id,
                      '❌ Invalid or expired link token. Please generate a new one from the NoveeBus portal.')
        else:
            # /start with no token
            existing = User.query.filter_by(telegram_chat_id=chat_id).first()
            if existing:
                _send(chat_id,
                      f'👋 Already linked to {existing.name}\'s account.\n'
                      f'Use /status to see upcoming rides, or /unlink to disconnect.')
            else:
                _send(chat_id,
                      '👋 Welcome to NoveeBus!\n\n'
                      'To link your account, go to NoveeBus → My Profile → Link Telegram '
                      'and tap the link button. You\'ll be redirected here automatically.')

    # --- /status ---
    elif text == '/status':
        user = User.query.filter_by(telegram_chat_id=chat_id).first()
        if not user:
            _send(chat_id, '❌ No linked account. Use /start to link.')
            return jsonify({'ok': True})

        today = date.today()
        bookings = (
            Booking.query
            .join(Schedule, Booking.schedule_id == Schedule.id)
            .filter(
                Booking.user_id == user.id,
                Booking.status.in_(['booked', 'waitlisted']),
                Schedule.date >= today
            )
            .order_by(Schedule.date)
            .limit(5)
            .all()
        )

        if not bookings:
            _send(chat_id, f'📅 No upcoming bookings for {user.name}.')
        else:
            lines = [f'📅 Upcoming rides for {user.name}:']
            for b in bookings:
                s = b.schedule
                status_icon = '✅' if b.status == 'booked' else '⏳'
                lines.append(
                    f'{status_icon} {s.date.strftime("%d %b")} — {s.route.name} '
                    f'({s.shift.name} {s.shift.departure_time}) [{b.status}]'
                )
            _send(chat_id, '\n'.join(lines))

    # --- /unlink ---
    elif text == '/unlink':
        user = User.query.filter_by(telegram_chat_id=chat_id).first()
        if user:
            user.telegram_chat_id = None
            db.session.commit()
            _send(chat_id, f'🔓 Unlinked. {user.name}\'s account is disconnected from Telegram.')
        else:
            _send(chat_id, '❌ No account linked to this chat.')

    # --- unknown ---
    else:
        _send(chat_id,
              'Commands:\n'
              '/status — upcoming rides\n'
              '/unlink — disconnect account')

    return jsonify({'ok': True})


@telegram_bp.route('/telegram/set_webhook', methods=['GET'])
def set_webhook():
    """Admin helper: set webhook URL. Call once after deploy."""
    import requests
    webhook_url = request.args.get('url', '')
    if not webhook_url:
        return jsonify({'error': 'Pass ?url=https://your-domain/telegram/webhook'}), 400
    if not BOT_TOKEN:
        return jsonify({'error': 'TELEGRAM_BOT_TOKEN not set'}), 500
    r = requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/setWebhook',
        json={'url': webhook_url},
        timeout=10
    )
    return jsonify(r.json())
