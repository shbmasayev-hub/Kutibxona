import telebot
from telebot import types

# BotFather'dan olingan yangi token
TOKEN = "9267813800:AAHXmwECl4NG38pLX74qAMqt4LkYcWLRnSE"

bot = telebot.TeleBot(TOKEN)
user_lang = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_uz = types.KeyboardButton("🇺🇿 O'zbek tili")
    btn_ru = types.KeyboardButton("🇷🇺 Русский язык")
    markup.add(btn_uz, btn_ru)
    bot.send_message(message.chat.id, "Assalomu alaykum! Tilni tanlang:\nЗдравствуйте! Выберите язык:", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    chat_id = message.chat.id
    text = message.text

    if text == "🇺🇿 O'zbek tili":
        user_lang[chat_id] = 'uz'
        show_main_menu(chat_id, 'uz')
    elif text == "🇷🇺 Русский язык":
        user_lang[chat_id] = 'ru'
        show_main_menu(chat_id, 'ru')
    elif text == "📚 Badiiy kitoblar":
        bot.send_message(chat_id, "Badiiy kitoblar ro'yxati:\n1. O'tkan kunlar\n2. Halqa")
    elif text == "🏫 Maktab darsliklari":
        bot.send_message(chat_id, "Maktab darsliklari (1-11 sinflar).")
    elif text == "📚 Художественные книги":
        bot.send_message(chat_id, "Список книг:\n1. Минувшие дни\n2. Мастер и Маргарита")
    elif text == "🏫 Школьные учебники":
        bot.send_message(chat_id, "Школьные учебники (1-11 классы).")
    else:
        lang = user_lang.get(chat_id, 'uz')
        if lang == 'uz':
            bot.send_message(chat_id, "Iltimos, tugmalardan birini tanlang.")
        else:
            bot.send_message(chat_id, "Пожалуйста, выберите кнопку.")

def show_main_menu(chat_id, lang):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if lang == 'uz':
        markup.add(types.KeyboardButton("📚 Badiiy kitoblar"), types.KeyboardButton("🏫 Maktab darsliklari"))
        bot.send_message(chat_id, "Asosiy menyu:", reply_markup=markup)
    else:
        markup.add(types.KeyboardButton("📚 Художественные книги"), types.KeyboardButton("🏫 Школьные учебники"))
        bot.send_message(chat_id, "Главное меню:", reply_markup=markup)

bot.infinity_polling()
