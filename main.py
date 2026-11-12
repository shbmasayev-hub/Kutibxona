import telebot
from telebot import types

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
    
    # O'zbekcha menyu bo'limlari
    elif text == "📚 Kitobxonlar uchun":
        bot.send_message(chat_id, "Kitobxonlar uchun mo'ljallangan adabiyotlar va resurslar bo'limi.")
    elif text == "👨‍🏫 O'qituvchilar uchun":
        bot.send_message(chat_id, "O'qituvchilar uchun metodik qo'llanmalar va dars ishlanmalari.")
    elif text == "🎒 O'quvchilar uchun":
        bot.send_message(chat_id, "O'quvchilar uchun foydali darsliklar va qo'shimcha adabiyotlar.")
    elif text == "👥 O'qituvchi va o'quvchi":
        bot.send_message(chat_id, "O'qituvchi va o'quvchilar uchun umumiy materiallar bo'limi.")
    
    # Ruscha menyu bo'limlari
    elif text == "📚 Для читателей":
        bot.send_message(chat_id, "Раздел литературы и ресурсов для читателей.")
    elif text == "👨‍🏫 Для учителей":
        bot.send_message(chat_id, "Методические пособия и разработки уроков для учителей.")
    elif text == "🎒 Для учащихся":
        bot.send_message(chat_id, "Полезные учебники и дополнительная литература для учеников.")
    elif text == "👥 Учитель и ученик":
        bot.send_message(chat_id, "Общий раздел материалов для учителей и учеников.")
    
    else:
        lang = user_lang.get(chat_id, 'uz')
        if lang == 'uz':
            bot.send_message(chat_id, "Iltimos, tugmalardan birini tanlang.")
        else:
            bot.send_message(chat_id, "Пожалуйста, выберите кнопку.")

def show_main_menu(chat_id, lang):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if lang == 'uz':
        markup.add(
            types.KeyboardButton("📚 Kitobxonlar uchun"),
            types.KeyboardButton("👨‍🏫 O'qituvchilar uchun"),
            types.KeyboardButton("🎒 O'quvchilar uchun"),
            types.KeyboardButton("👥 O'qituvchi va o'quvchi")
        )
        bot.send_message(chat_id, "Asosiy menyu bo'limini tanlang:", reply_markup=markup)
    else:
        markup.add(
            types.KeyboardButton("📚 Для читателей"),
            types.KeyboardButton("👨‍🏫 Для учителей"),
            types.KeyboardButton("🎒 Для учащихся"),
            types.KeyboardButton("👥 Учитель и ученик")
        )
        bot.send_message(chat_id, "Выберите раздел главного меню:", reply_markup=markup)

bot.infinity_polling()
