from flask import request, jsonify, redirect, url_for
import telebot
import requests
from telebot.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from flask_babel import _

from app import app, csrf
from .models import User

TOKEN = app.config['TELEGRAM_API_TOKEN']
URL = 'https://jiiin.online'
bot = telebot.TeleBot(TOKEN)
# print('https://api.telegram.org/bot{}/setWebhook?url={}/webhook/'.format(TOKEN, URL))
# print('https://api.telegram.org/bot{}/deleteWebhook'.format(TOKEN))

TEXT_CONFIRM = _('Please confirm your phone number')
TEXT_REGISTER = _('Please register to jiiin.online')
TEXT_CONFIRM_SUCCESS = _('Contact confirmed successfully!')
TEXT_IMPORT_SUCCESS = _('Contact imported successfully!')


def register_phone(user_id, contact):
    pass


def send_bot_message(chat_id, text):
    method = "sendMessage"
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = {"chat_id": chat_id, "text": text}
    requests.post(url, data=data)


@csrf.exempt
@app.route('/webhook/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        json_string = request.get_json()
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return jsonify({"ok": 'true'})
    return redirect(url_for('index'))


@bot.message_handler(commands=['start'])
def start(message):
    token = message.text.strip('/start ')
    if not User.check_token(token):
        bot.send_message(message.from_user.id, TEXT_REGISTER)
    else:
        keyboard = ReplyKeyboardMarkup(row_width=1,
                                       resize_keyboard=True,
                                       one_time_keyboard=True)
        button = KeyboardButton(text='Send phone number',
                                request_contact=True)
        keyboard.add(button)
        bot.send_message(message.from_user.id, TEXT_CONFIRM,
                         reply_markup=keyboard)


@bot.message_handler(content_types=['contact'])
def receive_contact(message):
    if message.contact.user_id == message.from_user.id:
        bot.send_message(message.from_user.id, TEXT_CONFIRM_SUCCESS,
                         reply_markup=ReplyKeyboardRemove())
    else:
        contact_name = ' '.join([message.contact.first_name,
                                 message.contact.last_name])
        contact = message.contact.phone_number, contact_name, message.contact.user_id
        register_phone(message.from_user.id, contact)
        bot.send_message(message.from_user.id, TEXT_IMPORT_SUCCESS)
