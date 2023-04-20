import json

from flask import request, jsonify, redirect, url_for
import requests
from app import app, csrf

TOKEN = app.config['TELEGRAM_API_TOKEN']
# https://api.telegram.org/bot{TOKEN}/setWebhook?url={URL}/webhook/
# https://api.telegram.org/bot{TOKEN}/deleteWebhook


def parse_bot_command(command, chat_id):
    if command == '/start' or '/number':
        send_invite_phone(chat_id)


def register_phone(user_id, phone, chat_id):
    # Save phone to database
    text = 'Phone number successfully registered'
    method = "sendMessage"
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = {'chat_id': chat_id,
            'text': text,
            'reply_markup': json.dumps({'remove_keyboard': True})}
    requests.post(url, data=data)


def send_bot_message(chat_id, text):
    method = "sendMessage"
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = {"chat_id": chat_id, "text": text}
    requests.post(url, data=data)


def send_invite_phone(chat_id):
    text = 'Please confirm your phone number'
    method = "sendMessage"
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    button = {'text': 'Send phone number', 'request_contact': True}
    keyboard = [[button]]
    data = {'chat_id': chat_id,
            'text': text,
            'reply_markup': json.dumps({'keyboard': keyboard,
                                        'resize_keyboard': True,
                                        'one_time_keyboard': True})}
    requests.post(url, data=data)


@csrf.exempt
@app.route('/webhook/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        r = request.get_json()
        chat_id = r['message']['chat']['id']
        if 'entities' in r['message']:
            message_type = r['message']['entities'][0]['type']
        else:
            message_type = None
        if 'text' in r['message']:
            message_text = r['message']['text']
        else:
            message_text = None
        if message_type == 'bot_command':
            parse_bot_command(message_text, chat_id)
        if 'contact' in r['message']:
            phone = r['message']['contact']['phone_number']
            user_id = r['message']['contact']['user_id']
            register_phone(user_id, phone, chat_id)
        return jsonify({"ok": 'true'})
    return redirect(url_for('index'))
