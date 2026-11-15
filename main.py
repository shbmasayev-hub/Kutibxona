import io
import hashlib
import hmac
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import parse_qsl, urlsplit

import telebot
from telebot import apihelper, types
from requests.exceptions import RequestException

from ai_assistant import (
    MAX_QUESTION_LENGTH,
    AssistantConfigurationError,
    AssistantError,
    BookTextNotFoundError,
    generate_ai_answer,
)
from audio_library import (
    SUPPORTED_AUDIO_EXTENSIONS,
    AudioLibraryError,
    download_audio_book,
    list_audio_books,
    save_audio_book,
)
from drive_library import DriveLibraryError, download_pdf, list_pdfs
from local_library import (
    MAX_UPLOAD_SIZE,
    LocalLibraryError,
    download_local_pdf,
    list_local_pdfs,
    save_pdf,
)

logger = logging.getLogger(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN) if TOKEN else None
user_lang = {}
TELEGRAM_WEBAPP_URL = os.getenv("TELEGRAM_WEBAPP_URL", "").strip()
TELEGRAM_WEBAPP_ORIGIN = os.getenv(
    "TELEGRAM_WEBAPP_ORIGIN",
    "https://shbmasayev-hub.github.io",
).strip().rstrip("/")
TELEGRAM_WEBAPP_API_PORT = os.getenv("TELEGRAM_WEBAPP_API_PORT", "").strip()
ai_sessions = {}
_AI_REQUESTS = defaultdict(deque)
_AI_REQUESTS_LOCK = Lock()
_AI_RATE_LIMIT = 5
_AI_RATE_WINDOW_SECONDS = 60

LANGUAGE_OPTIONS = {
    "uz": "🇺🇿 O‘zbekcha",
    "ru": "🇷🇺 Русский язык",
}

SECTION_MESSAGES = {
    "uz": {
        "👩‍🏫 O‘qituvchilar": "Darsga tayyorgarlik uchun metodik qo‘llanmalar va foydali materiallar.",
        "🎒 O‘quvchilar": "Darsliklar, qo‘shimcha adabiyotlar va mutolaa uchun tavsiya etilgan asarlar.",
        "👥 Umumiy resurslar": "Ta’lim va mutolaa uchun barcha foydalanuvchilarga mo‘ljallangan materiallar.",
        "ℹ️ Kutubxona haqida": "Kutibxona — kitob va audiokitoblarni bir joyda topish, o‘qish va tinglash uchun raqamli makon.",
        "✉️ Aloqa": "Aloqa ma’lumotlari tez orada yangilanadi. E’tiboringiz uchun rahmat.",
        "❔ Yordam": "Qisqa yo‘riqnoma:\n📚 Kitoblar — tanlangan asar PDF ko‘rinishida yuboriladi.\n🎧 Audiokitoblar — audio Telegram pleerida ochiladi.\n🤖 AI yordamchi — kitobdan javob, tavsiya va ta’limiy yordam.\n\nAsosiy menyu: /menu · AI: /ai\nMa’lumotlar haqida: /privacy",
    },
    "ru": {
        "👩‍🏫 Учителям": "Методические пособия и материалы для подготовки к занятиям.",
        "🎒 Ученикам": "Учебники, дополнительная литература и книги для чтения.",
        "👥 Общие ресурсы": "Материалы для обучения и чтения, полезные всем пользователям.",
        "ℹ️ О библиотеке": "Kutibxona — цифровая библиотека, где удобно находить, читать и слушать книги.",
        "✉️ Связаться": "Контактная информация скоро появится. Спасибо за интерес к библиотеке.",
        "❔ Помощь": "Краткая инструкция:\n📚 Книги — выбранное произведение отправляется в PDF.\n🎧 Аудиокниги — аудио откроется в плеере Telegram.\n🤖 AI-помощник — ответы по книгам, рекомендации и помощь в учёбе.\n\nГлавное меню: /menu · AI: /ai\nО данных: /privacy",
    },
}

PRIVACY_MESSAGES = {
    "uz": (
        "🔒 Ma’lumotlar haqida\n\n"
        "Bot foydalanuvchilarning shaxsiy ma’lumotlari yoki xabarlarini alohida bazaga saqlamaydi. "
        "Til tanlovi bot ishlayotgan paytda xotirada turadi va qayta ishga tushganda o‘chadi. "
        "Admin yuklagan kitob va audiokitoblar bot serveridagi kutubxona papkasida saqlanadi "
        "va foydalanuvchilarga yuborilishi mumkin. AI ishlatilganda savol, tavsiya uchun kitob "
        "nomlari va tanlangan PDF’dan topilgan qisqa parchalar javob yaratish uchun Google Gemini "
        "API’ga uzatiladi; ularning "
        "ma’lumot siyosati qo‘llanadi. Xabarlar Telegram orqali qayta ishlanadi."
    ),
    "ru": (
        "🔒 О данных\n\n"
        "Бот не сохраняет личные данные пользователей или их сообщения в отдельной базе. "
        "Выбранный язык хранится в памяти, пока бот запущен, и сбрасывается после перезапуска. "
        "Книги и аудиокниги, загруженные администратором, хранятся в библиотеке на сервере бота "
        "и могут отправляться пользователям. При использовании AI вопрос, названия книг для "
        "рекомендации и найденные короткие отрывки PDF передаются в Google Gemini API; действует политика "
        "обработки данных Google. Сообщения обрабатываются через Telegram."
    ),
}

SECTION_ALIASES = {
    "uz": {
        "👨‍🏫 O'qituvchilar uchun": "👩‍🏫 O‘qituvchilar",
        "🎒 O'quvchilar uchun": "🎒 O‘quvchilar",
        "👥 O'qituvchi va o'quvchi": "👥 Umumiy resurslar",
        "ℹ️ Biz haqimizda": "ℹ️ Kutubxona haqida",
        "📞 Bog'lanish": "✉️ Aloqa",
        "❓ FAQ": "❔ Yordam",
    },
    "ru": {
        "👨‍🏫 Для учителей": "👩‍🏫 Учителям",
        "🎒 Для учащихся": "🎒 Ученикам",
        "👥 Учитель и ученик": "👥 Общие ресурсы",
        "ℹ️ О нас": "ℹ️ О библиотеке",
        "📞 Контакты": "✉️ Связаться",
        "❓ FAQ": "❔ Помощь",
    },
}

PRIMARY_SUBJECTS = (
    ("ona_tili", "Ona tili", "Родной язык"),
    ("oqish", "O‘qish", "Чтение"),
    ("matematika", "Matematika", "Математика"),
    ("tabiiy_fanlar", "Tabiiy fanlar", "Естествознание"),
    ("ingliz_tili", "Ingliz tili", "Английский язык"),
)
MIDDLE_SUBJECTS = (
    ("matematika", "Matematika", "Математика"),
    ("ona_tili_va_adabiyot", "Ona tili va adabiyot", "Родной язык и литература"),
    ("ingliz_tili", "Ingliz tili", "Английский язык"),
    ("tarix", "Tarix", "История"),
    ("tabiiy_fanlar", "Tabiiy fanlar", "Естествознание"),
    ("informatika", "Informatika", "Информатика"),
)
SECONDARY_SUBJECTS = (
    ("algebra", "Algebra", "Алгебра"),
    ("geometriya", "Geometriya", "Геометрия"),
    ("ona_tili_va_adabiyot", "Ona tili va adabiyot", "Родной язык и литература"),
    ("ingliz_tili", "Ingliz tili", "Английский язык"),
    ("tarix", "Tarix", "История"),
    ("biologiya", "Biologiya", "Биология"),
    ("geografiya", "Geografiya", "География"),
    ("fizika", "Fizika", "Физика"),
    ("kimyo", "Kimyo", "Химия"),
    ("informatika", "Informatika", "Информатика"),
)
SENIOR_SUBJECTS = SECONDARY_SUBJECTS + (
    ("huquq", "Huquq", "Право"),
)
ZIYONET_LIBRARY_URL = "https://library.ziyonet.uz/"
ZIYONET_QA_URL = "https://ask.ziyonet.uz/"
ZIYONET_AUDIO_URL = "https://audio.ziyonet.uz/"
ZIYONET_SITES_URL = "https://sites.ziyonet.uz/"
TEACHER_GUIDE_PDF_PATHS = {
    "primary": Path(__file__).resolve().parent / "resources" / "darsni_rejalash_1-4.pdf",
    "secondary": Path(__file__).resolve().parent / "resources" / "darsni_rejalash_5-11.pdf",
}
STUDENT_SUBJECT_TIPS = {
    "matematika": (
        "Formulani yodlashdan oldin u nimani topishga yordam berishini tushuning. "
        "Yechim bosqichlarini yozing va javobni qayta tekshiring.",
        "Поймите, что помогает найти формула, прежде чем учить её. "
        "Записывайте шаги решения и проверяйте ответ.",
    ),
    "algebra": (
        "Misolni bosqichma-bosqich yeching, har bir o‘zgartirishni yozing "
        "va natijani tenglamaga qayta qo‘yib tekshiring.",
        "Решайте пример по шагам, записывайте каждое преобразование "
        "и проверяйте результат подстановкой в уравнение.",
    ),
    "geometriya": (
        "Masalani chizma bilan boshlang, berilganlarni belgilang va "
        "ishlatilgan teorema yoki formulani yozib qo‘ying.",
        "Начните задачу с чертежа, отметьте данные и запишите "
        "использованную теорему или формулу.",
    ),
    "ona_tili": (
        "Yangi qoidaga o‘zingiz misol tuzing va matndan shu qoidaga "
        "mos so‘z yoki gaplarni toping.",
        "Придумайте свой пример к новому правилу и найдите в тексте "
        "подходящие слова или предложения.",
    ),
    "oqish": (
        "Matnni qismlarga bo‘lib o‘qing, har bir qismga sarlavha qo‘ying "
        "va mazmunini o‘z so‘zlaringiz bilan aytib bering.",
        "Читайте текст по частям, озаглавьте каждую и перескажите "
        "содержание своими словами.",
    ),
    "ona_tili_va_adabiyot": (
        "Asar yoki matn bo‘yicha muallif fikri, asosiy qahramonlar va "
        "muhim dalillarni qisqa qayd eting.",
        "Кратко запишите идею автора, главных героев и важные детали "
        "произведения или текста.",
    ),
    "ingliz_tili": (
        "Yangi so‘zlarni tarjimasi bilan emas, namunaviy gap ichida "
        "o‘rganing va ularni keyin yana takrorlang.",
        "Учите новые слова не только с переводом, но и в примерах, "
        "а затем регулярно повторяйте их.",
    ),
    "tarix": (
        "Voqealarni vaqt chizig‘iga joylang; sana bilan birga sabab va "
        "natijalarni ham yozing.",
        "Расположите события на временной шкале; записывайте не только "
        "даты, но и причины с последствиями.",
    ),
    "tabiiy_fanlar": (
        "Tushunchalarni kuzatish va hayotiy misollar bilan bog‘lang; "
        "jarayonlarni chizma orqali ifodalang.",
        "Связывайте понятия с наблюдениями и примерами из жизни, "
        "изображайте процессы на схемах.",
    ),
    "biologiya": (
        "Atamalarni rasm va sxemalar bilan bog‘lang, o‘simlik yoki "
        "organizm qismlarini o‘zaro taqqoslang.",
        "Связывайте термины с рисунками и схемами, сравнивайте части "
        "растений и организмов.",
    ),
    "geografiya": (
        "Mavzuni xaritadan toping; joy nomlari bilan birga tabiiy "
        "sharoitlar va ularning sabablarini ham o‘rganing.",
        "Находите объекты на карте; изучайте не только названия мест, "
        "но и природные условия с их причинами.",
    ),
    "fizika": (
        "Masalada berilgan kattaliklar va birliklarni yozing, formulani "
        "tanlab, o‘lchov birliklarini tekshiring.",
        "Запишите данные и единицы измерения, выберите формулу "
        "и проверьте размерность результата.",
    ),
    "kimyo": (
        "Modda va reaksiyalarni jadval yoki sxemada taqqoslang; "
        "tajribalarni faqat o‘qituvchi nazoratida bajaring.",
        "Сравнивайте вещества и реакции в таблицах или схемах; "
        "проводите опыты только под контролем учителя.",
    ),
    "informatika": (
        "Yangi tushunchani kichik amaliy topshiriqda sinab ko‘ring "
        "va natijani kutilgan javob bilan taqqoslang.",
        "Проверяйте новое понятие на небольшом практическом задании "
        "и сравнивайте результат с ожидаемым.",
    ),
    "huquq": (
        "Huquq va majburiyatlarni hayotiy vaziyatlar bilan bog‘lang "
        "va har bir xulosaning asosini toping.",
        "Связывайте права и обязанности с жизненными ситуациями "
        "и находите основания для каждого вывода.",
    ),
}
TEACHER_GUIDES = {
    "lesson": (
        (
            "📋 Darsni rejalash qo‘llanmasi\n\n"
            "Maqsad, dars oqimi, baholash va amaliy reja qolipi bo‘yicha "
            "asosiy tavsiyalar hamda sinf bosqichiga mos alohida "
            "qo‘llanmalar mavjud. 1–4 va 5–11-sinflar uchun PDF’lar "
            "alohida beriladi."
        ),
        (
            "📋 Планирование урока\n\n"
            "Доступны основные рекомендации по цели, структуре урока, "
            "оцениванию и шаблону плана, а также отдельные руководства "
            "для 1–4 и 5–11 классов."
        ),
    ),
    "differentiation": (
        (
            "🧩 Darajaga mos topshiriqlar\n\n"
            "• Asosiy daraja: namuna, tayanch so‘z yoki bosqichma-bosqich "
            "ko‘rsatma bilan bajariladigan topshiriq.\n"
            "• Mustaqil daraja: dars maqsadiga mos odatiy topshiriq.\n"
            "• Chuqurlashtirish: bilimni yangi vaziyatda qo‘llash, "
            "taqqoslash yoki yechimni izohlash.\n\n"
            "Barcha darajalar bir xil asosiy maqsadga xizmat qilsin. "
            "O‘quvchilarga zaruratga qarab tayanch bering; darajalarni "
            "doimiy yorliq yoki jazo sifatida ishlatmang."
        ),
        (
            "🧩 Задания разного уровня\n\n"
            "• Базовый уровень: задание с примером, опорными словами "
            "или пошаговой инструкцией.\n"
            "• Самостоятельный уровень: обычное задание по цели урока.\n"
            "• Углубление: применение знаний в новой ситуации, сравнение "
            "или объяснение решения.\n\n"
            "Все уровни должны вести к одной основной цели. Предоставляйте "
            "поддержку по необходимости и не превращайте уровни в постоянные "
            "ярлыки или наказание."
        ),
    ),
    "assessment": (
        (
            "✅ Formativ baholash va fikr-mulohaza\n\n"
            "• Dars boshida: 1–2 savol bilan avvalgi bilimni aniqlang.\n"
            "• Dars davomida: qisqa savol, mini-test yoki juftlikdagi "
            "tekshiruv orqali tushunishni kuzating.\n"
            "• Dars oxirida: “Bugun nimani o‘rgandingiz?” yoki bitta "
            "amaliy topshiriq bilan natijani tekshiring.\n\n"
            "Mezonni topshiriqdan oldin ayting. Fikr-mulohazada avval "
            "nima yaxshi chiqqanini, keyin keyingi aniq qadamni ko‘rsating."
        ),
        (
            "✅ Формирующее оценивание и обратная связь\n\n"
            "• В начале урока: проверьте предыдущие знания 1–2 вопросами.\n"
            "• Во время урока: следите за пониманием с помощью коротких "
            "вопросов, мини-теста или проверки в парах.\n"
            "• В конце: задайте вопрос «Что вы сегодня узнали?» или "
            "предложите одно практическое задание.\n\n"
            "Объясняйте критерии до выполнения задания. В обратной связи "
            "сначала отметьте, что получилось, затем назовите следующий "
            "конкретный шаг."
        ),
    ),
}


def show_language_menu(chat_id):
    if bot is None:
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton(LANGUAGE_OPTIONS["uz"]),
        types.KeyboardButton(LANGUAGE_OPTIONS["ru"]),
    )
    bot.send_message(
        chat_id,
        "👋 Kutibxonaga xush kelibsiz!\nDavom etish uchun tilni tanlang:\n\n👋 Добро пожаловать!\nВыберите язык:",
        reply_markup=markup,
    )


def send_welcome(message):
    show_language_menu(message.chat.id)


def show_section_navigation(chat_id, title, lang):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    back_label = "⬅️ Asosiy menyu" if lang == "uz" else "⬅️ Главное меню"
    markup.add(types.KeyboardButton(back_label))
    bot.send_message(chat_id, title, reply_markup=markup)


def show_section_screen(chat_id, title, content, lang):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    back_label = "⬅️ Asosiy menyu" if lang == "uz" else "⬅️ Главное меню"
    markup.add(types.KeyboardButton(back_label))
    bot.send_message(chat_id, f"{title}\n\n{content}", reply_markup=markup)


def _student_subjects_for_grade(grade):
    if 1 <= grade <= 4:
        return PRIMARY_SUBJECTS
    if grade <= 6:
        return MIDDLE_SUBJECTS
    if grade <= 9:
        return SECONDARY_SUBJECTS
    return SENIOR_SUBJECTS


def show_student_grade_menu(chat_id, lang):
    if bot is None:
        return

    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = [
        types.InlineKeyboardButton(
            f"{grade}-sinf" if lang == "uz" else f"{grade}-й класс",
            callback_data=f"students:grade:{grade}",
        )
        for grade in range(1, 12)
    ]
    markup.add(*buttons)
    back_label = "⬅️ Asosiy menyu" if lang == "uz" else "⬅️ Главное меню"
    markup.add(types.InlineKeyboardButton(back_label, callback_data="students:back"))
    prompt = (
        "🎒 Qaysi sinfda o‘qiysiz? Sinfni tanlang:"
        if lang == "uz"
        else "🎒 В каком классе вы учитесь? Выберите класс:"
    )
    bot.send_message(chat_id, prompt, reply_markup=markup)


def show_student_subject_menu(chat_id, grade, lang):
    if bot is None:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    for subject_id, uz_label, ru_label in _student_subjects_for_grade(grade):
        label = uz_label if lang == "uz" else ru_label
        markup.add(
            types.InlineKeyboardButton(
                f"📘 {label}",
                callback_data=f"students:subject:{grade}:{subject_id}",
            )
        )
    back_label = "⬅️ Sinfni tanlash" if lang == "uz" else "⬅️ Выбрать класс"
    markup.add(
        types.InlineKeyboardButton(back_label, callback_data="students:grades"),
        types.InlineKeyboardButton(
            "🏠 Asosiy menyu" if lang == "uz" else "🏠 Главное меню",
            callback_data="students:back",
        ),
    )
    prompt = (
        f"📚 {grade}-sinf uchun fanni tanlang:"
        if lang == "uz"
        else f"📚 Выберите предмет для {grade}-го класса:"
    )
    bot.send_message(chat_id, prompt, reply_markup=markup)


def show_student_subject_resources(chat_id, grade, subject_id, lang):
    if bot is None:
        return

    subject = next(
        (
            subject
            for subject in _student_subjects_for_grade(grade)
            if subject[0] == subject_id
        ),
        None,
    )
    if subject is None:
        return

    subject_name = subject[1] if lang == "uz" else subject[2]
    if lang == "uz":
        text = (
            f"📘 {grade}-sinf · {subject_name}\n\n"
            "Samarali o‘qish uchun:\n"
            "1. Mavzuni darslikdan o‘qing va yangi atamalarni belgilang.\n"
            "2. Asosiy fikrlarni o‘z so‘zlaringiz bilan qisqa yozib chiqing.\n"
            "3. Mashqlarni javobga qaramasdan mustaqil bajaring.\n"
            "4. Xatolarni tekshirib, tushunmagan joyingizni qayta ko‘rib chiqing.\n\n"
            f"💡 Fan bo‘yicha maslahat: {STUDENT_SUBJECT_TIPS[subject_id][0]}\n\n"
            "📚 Qo‘shimcha materiallarni ZiyoNET kutubxonasidan izlang; "
            "savolingiz bo‘lsa, ta’lim savol-javob xizmatidan foydalaning."
        )
        resource_labels = (
            "📚 ZiyoNET kutubxonasi",
            "🎧 O‘zbekcha audiokitoblar",
            "❓ Ta’lim savol-javoblari",
        )
        back_label = "⬅️ Fanlar ro‘yxati"
        home_label = "🏠 Asosiy menyu"
    else:
        text = (
            f"📘 {grade}-й класс · {subject_name}\n\n"
            "Как заниматься эффективнее:\n"
            "1. Прочитайте тему и отметьте новые термины.\n"
            "2. Кратко запишите главные мысли своими словами.\n"
            "3. Выполните задания самостоятельно, не подглядывая в ответы.\n"
            "4. Проверьте ошибки и повторите непонятные части.\n\n"
            f"💡 Совет по предмету: {STUDENT_SUBJECT_TIPS[subject_id][1]}\n\n"
            "📚 Дополнительные материалы можно искать в библиотеке ZiyoNET, "
            "а вопросы задавать в образовательном сервисе вопросов и ответов."
        )
        resource_labels = (
            "📚 Библиотека ZiyoNET",
            "🎧 Аудиокниги на узбекском",
            "❓ Вопросы и ответы по обучению",
        )
        back_label = "⬅️ Список предметов"
        home_label = "🏠 Главное меню"

    markup = types.InlineKeyboardMarkup(row_width=1)
    for label, url in zip(
        resource_labels,
        (
            ZIYONET_LIBRARY_URL,
            ZIYONET_AUDIO_URL,
            ZIYONET_QA_URL,
        ),
    ):
        markup.add(types.InlineKeyboardButton(label, url=url))
    markup.add(
        types.InlineKeyboardButton(
            back_label,
            callback_data=f"students:grade:{grade}",
        ),
        types.InlineKeyboardButton(home_label, callback_data="students:back"),
    )
    bot.send_message(chat_id, text, reply_markup=markup)


def handle_student_callback(callback):
    if bot is None or callback.message is None:
        return

    chat_id = callback.message.chat.id
    lang = user_lang.get(chat_id, "uz")
    parts = callback.data.split(":")
    if callback.data == "students:back":
        bot.answer_callback_query(callback.id)
        show_main_menu(
            chat_id,
            lang,
            allow_webapp=getattr(callback.message.chat, "type", "private") == "private",
        )
    elif callback.data == "students:grades":
        bot.answer_callback_query(callback.id)
        show_student_grade_menu(chat_id, lang)
    elif len(parts) == 3 and parts[:2] == ["students", "grade"]:
        try:
            grade = int(parts[2])
        except ValueError:
            bot.answer_callback_query(callback.id)
            return
        if not 1 <= grade <= 11:
            bot.answer_callback_query(callback.id)
            return
        bot.answer_callback_query(callback.id)
        show_student_subject_menu(chat_id, grade, lang)
    elif len(parts) == 4 and parts[:2] == ["students", "subject"]:
        try:
            grade = int(parts[2])
        except ValueError:
            bot.answer_callback_query(callback.id)
            return
        if not 1 <= grade <= 11:
            bot.answer_callback_query(callback.id)
            return
        bot.answer_callback_query(callback.id)
        show_student_subject_resources(chat_id, grade, parts[3], lang)
    else:
        bot.answer_callback_query(callback.id)


def show_teacher_resources(chat_id, lang):
    if bot is None:
        return

    if lang == "uz":
        text = (
            "👩‍🏫 O‘qituvchilar uchun metodik qo‘llanmalar\n\n"
            "Darsni rejalash, turli darajadagi topshiriqlar tayyorlash va "
            "o‘quvchilar bilimini dars davomida baholash bo‘yicha qisqa "
            "amaliy tavsiyalarni tanlang. Qo‘shimcha materiallarni ZiyoNET "
            "kutubxonasi va foydali saytlar katalogidan izlang."
        )
        guide_labels = (
            ("📋 Darsni rejalash", "lesson"),
            ("🧩 Darajaga mos topshiriqlar", "differentiation"),
            ("✅ Formativ baholash", "assessment"),
        )
        resource_labels = (
            "📚 ZiyoNET kutubxonasi",
            "❓ ZiyoNET savol-javoblari",
            "🌐 Foydali ta’lim saytlari",
        )
        home_label = "⬅️ Asosiy menyu"
    else:
        text = (
            "👩‍🏫 Методические материалы для учителей\n\n"
            "Выберите краткие практические рекомендации по планированию "
            "урока, подготовке заданий разного уровня и оцениванию знаний "
            "учеников во время занятия. Дополнительные материалы ищите "
            "в библиотеке ZiyoNET и каталоге полезных сайтов."
        )
        guide_labels = (
            ("📋 Планирование урока", "lesson"),
            ("🧩 Задания разного уровня", "differentiation"),
            ("✅ Формирующее оценивание", "assessment"),
        )
        resource_labels = (
            "📚 Библиотека ZiyoNET",
            "❓ Вопросы и ответы ZiyoNET",
            "🌐 Полезные образовательные сайты",
        )
        home_label = "⬅️ Главное меню"

    markup = types.InlineKeyboardMarkup(row_width=1)
    for label, guide_id in guide_labels:
        markup.add(
            types.InlineKeyboardButton(
                label,
                callback_data=f"teacher:guide:{guide_id}",
            )
        )
    for label, url in zip(
        resource_labels,
        (
            ZIYONET_LIBRARY_URL,
            ZIYONET_QA_URL,
            ZIYONET_SITES_URL,
        ),
    ):
        markup.add(types.InlineKeyboardButton(label, url=url))
    markup.add(
        types.InlineKeyboardButton(home_label, callback_data="teacher:back")
    )
    bot.send_message(chat_id, text, reply_markup=markup)


def handle_teacher_callback(callback):
    if bot is None or callback.message is None:
        return

    chat_id = callback.message.chat.id
    lang = user_lang.get(chat_id, "uz")
    if callback.data == "teacher:back":
        bot.answer_callback_query(callback.id)
        show_main_menu(
            chat_id,
            lang,
            allow_webapp=getattr(callback.message.chat, "type", "private") == "private",
        )
        return
    if callback.data == "teacher:home":
        bot.answer_callback_query(callback.id)
        show_teacher_resources(chat_id, lang)
        return
    if callback.data == "teacher:download:lesson":
        show_teacher_pdf_choices(callback)
        return
    if callback.data in (
        "teacher:download:lesson:primary",
        "teacher:download:lesson:secondary",
    ):
        send_teacher_guide_pdf(callback, callback.data.rsplit(":", 1)[1])
        return

    parts = callback.data.split(":")
    if len(parts) != 3 or parts[:2] != ["teacher", "guide"]:
        bot.answer_callback_query(callback.id)
        return

    guide = TEACHER_GUIDES.get(parts[2])
    if guide is None:
        bot.answer_callback_query(callback.id)
        return

    bot.answer_callback_query(callback.id)
    back_label = "⬅️ Qo‘llanmalar" if lang == "uz" else "⬅️ К материалам"
    home_label = "🏠 Asosiy menyu" if lang == "uz" else "🏠 Главное меню"
    markup = types.InlineKeyboardMarkup(row_width=1)
    if parts[2] == "lesson":
        markup.add(
            types.InlineKeyboardButton(
                "📥 1–4-sinflar uchun PDF"
                if lang == "uz"
                else "📥 PDF для 1–4 классов",
                callback_data="teacher:download:lesson:primary",
            ),
            types.InlineKeyboardButton(
                "📥 5–11-sinflar uchun PDF"
                if lang == "uz"
                else "📥 PDF для 5–11 классов",
                callback_data="teacher:download:lesson:secondary",
            )
        )
    markup.add(
        types.InlineKeyboardButton(
            back_label,
            callback_data="teacher:home",
        ),
        types.InlineKeyboardButton(
            home_label,
            callback_data="teacher:back",
        ),
    )
    bot.send_message(chat_id, guide[0] if lang == "uz" else guide[1], reply_markup=markup)


def show_teacher_pdf_choices(callback):
    chat_id = callback.message.chat.id
    lang = user_lang.get(chat_id, "uz")
    bot.answer_callback_query(callback.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "📥 1–4-sinflar uchun PDF"
            if lang == "uz"
            else "📥 PDF для 1–4 классов",
            callback_data="teacher:download:lesson:primary",
        ),
        types.InlineKeyboardButton(
            "📥 5–11-sinflar uchun PDF"
            if lang == "uz"
            else "📥 PDF для 5–11 классов",
            callback_data="teacher:download:lesson:secondary",
        ),
    )
    bot.send_message(
        chat_id,
        "Kerakli sinflar uchun alohida qo‘llanmani tanlang."
        if lang == "uz"
        else "Выберите отдельное руководство для нужных классов.",
        reply_markup=markup,
    )


def send_teacher_guide_pdf(callback, level):
    if bot is None or callback.message is None:
        return

    chat_id = callback.message.chat.id
    lang = user_lang.get(chat_id, "uz")
    if level not in TEACHER_GUIDE_PDF_PATHS:
        bot.answer_callback_query(callback.id)
        return

    bot.answer_callback_query(callback.id)
    try:
        content = TEACHER_GUIDE_PDF_PATHS[level].read_bytes()
    except OSError as error:
        logger.exception("Could not read the %s teacher lesson-planning PDF", level)
        bot.send_message(
            chat_id,
            "PDF qo‘llanmani ochib bo‘lmadi."
            if lang == "uz"
            else "Не удалось открыть руководство PDF.",
        )
        return

    document = io.BytesIO(content)
    grade_range = "1-4" if level == "primary" else "5-11"
    document.name = f"Darsni_rejalash_{grade_range}_sinflar.pdf"
    try:
        bot.send_document(
            chat_id,
            document,
            caption=f"Darsni rejalash — {grade_range} sinflar uchun alohida metodik qo‘llanma",
            timeout=120,
        )
    except (apihelper.ApiException, OSError, RequestException) as error:
        logger.warning("Could not send the %s teacher lesson-planning PDF: %s", level, error)
        bot.send_message(
            chat_id,
            "PDF yuborilmadi. Tugmani yana bosing."
            if lang == "uz"
            else "Не удалось отправить PDF. Нажмите кнопку ещё раз.",
        )


def list_available_books():
    local_books = list_local_pdfs()
    books = [{**item, "source": "local"} for item in local_books]
    drive_error = None
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if credentials_path and folder_id and Path(credentials_path).is_file():
        try:
            books.extend(
                {**item, "source": "drive"}
                for item in list_pdfs()
            )
        except DriveLibraryError as error:
            if not books:
                raise
            drive_error = error
            logger.warning("Could not list Google Drive books; using local books: %s", error)
    return books, drive_error


def validate_telegram_webapp_init_data(init_data, now=None):
    if not TOKEN or not isinstance(init_data, str) or not init_data or len(init_data) > 4096:
        return None

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    values = dict(pairs)
    if len(values) != len(pairs):
        return None

    received_hash = values.pop("hash", "")
    if not re.fullmatch(r"[0-9a-f]{64}", received_hash):
        return None
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(values.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        TOKEN.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        return None

    try:
        auth_date = int(values.get("auth_date", ""))
        user = json.loads(values.get("user", ""))
    except (TypeError, ValueError):
        return None
    current_time = int(time.time()) if now is None else int(now)
    if auth_date > current_time + 30 or current_time - auth_date > 86400:
        return None
    user_id = user.get("id") if isinstance(user, dict) else None
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1:
        return None
    return user_id


def _consume_ai_rate_limit(user_id, now=None):
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1:
        return False
    current_time = time.monotonic() if now is None else now
    with _AI_REQUESTS_LOCK:
        requests_for_user = _AI_REQUESTS[user_id]
        while (
            requests_for_user
            and current_time - requests_for_user[0] >= _AI_RATE_WINDOW_SECONDS
        ):
            requests_for_user.popleft()
        if len(requests_for_user) >= _AI_RATE_LIMIT:
            return False
        requests_for_user.append(current_time)
        return True


def _localized_ai_error(error, lang):
    if lang == "ru":
        if isinstance(error, AssistantConfigurationError):
            return "AI-помощник ещё не настроен. Владелец должен добавить ключ Gemini на сервере."
        if isinstance(error, BookTextNotFoundError):
            return "Не удалось найти подходящий отрывок в PDF. Попробуйте переформулировать вопрос."
        if isinstance(error, AssistantError):
            return "AI-помощник временно не может ответить. Попробуйте позже."
        return "Не удалось прочитать выбранную книгу."
    if isinstance(error, AssistantConfigurationError):
        return "AI yordamchi hali sozlanmagan. Bot egasi serverga Gemini kalitini kiritishi kerak."
    if isinstance(error, BookTextNotFoundError):
        return "PDF matnidan mos parcha topilmadi. Savolni boshqacha ifodalab ko‘ring."
    if isinstance(error, AssistantError):
        return "AI yordamchi hozir javob bera olmadi. Birozdan keyin qayta urinib ko‘ring."
    return "Tanlangan kitobni o‘qib bo‘lmadi."


class BookCatalogRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] != "/api/books":
            self.send_error(404)
            return

        try:
            books, drive_error = list_available_books()
        except (DriveLibraryError, LocalLibraryError):
            logger.exception("Could not provide the Mini App book catalog")
            self._send_json(
                503,
                {"error": "Kitoblar ro‘yxatini hozircha olib bo‘lmadi."},
            )
            return

        if drive_error:
            logger.warning("Mini App book catalog is missing Google Drive books: %s", drive_error)
        self._send_json(
            200,
            {
                "books": [
                    {"id": book["id"], "name": book["name"], "source": book["source"]}
                    for book in books
                ]
            },
        )

    def do_OPTIONS(self):
        path = self.path.split("?", 1)[0]
        origin = self.headers.get("Origin", "").rstrip("/")
        if path != "/api/assistant" or origin != TELEGRAM_WEBAPP_ORIGIN:
            self.send_error(403)
            return

        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", TELEGRAM_WEBAPP_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Telegram-Init-Data",
        )
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/assistant":
            self.send_error(404)
            return

        origin = self.headers.get("Origin", "").rstrip("/")
        if origin != TELEGRAM_WEBAPP_ORIGIN:
            self._send_json(403, {"error": "Manba ruxsat etilmagan."})
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json(415, {"error": "JSON so‘rovi yuborilishi kerak."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send_json(400, {"error": "So‘rov hajmini aniqlab bo‘lmadi."})
            return
        if not 1 <= content_length <= 8192:
            self._send_json(413, {"error": "So‘rov hajmi ruxsat etilgan chegaradan katta."})
            return

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "So‘rov JSON formatida emas."})
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "So‘rov formati noto‘g‘ri."})
            return

        user_id = validate_telegram_webapp_init_data(
            self.headers.get("X-Telegram-Init-Data", "")
        )
        if user_id is None:
            self._send_json(401, {"error": "Telegram foydalanuvchisini tasdiqlab bo‘lmadi."})
            return
        if not _consume_ai_rate_limit(user_id):
            self._send_json(429, {"error": "AI so‘rovlari limiti tugadi. Birozdan keyin urinib ko‘ring."})
            return

        question = payload.get("question")
        mode = payload.get("mode")
        lang = payload.get("language", "uz")
        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question.strip()) > MAX_QUESTION_LENGTH
            or not isinstance(mode, str)
            or mode not in {"book_qa", "recommend", "study"}
            or not isinstance(lang, str)
            or lang not in {"uz", "ru"}
        ):
            self._send_json(400, {"error": "Savol yoki yordamchi turi noto‘g‘ri."})
            return

        try:
            books, _ = list_available_books()
            selected_book = None
            if mode == "book_qa":
                source = payload.get("book_source")
                book_id = payload.get("book_id")
                if (
                    not isinstance(source, str)
                    or source not in {"local", "drive"}
                    or not isinstance(book_id, str)
                ):
                    self._send_json(400, {"error": "Savol uchun kitob tanlanmagan."})
                    return
                selected_book = next(
                    (
                        book
                        for book in books
                        if book["source"] == source and book["id"] == book_id
                    ),
                    None,
                )
                if selected_book is None:
                    self._send_json(400, {"error": "Tanlangan kitob katalogda topilmadi."})
                    return
            answer = generate_ai_answer(
                question.strip(),
                mode,
                lang,
                books,
                selected_book=selected_book,
            )
        except (DriveLibraryError, LocalLibraryError) as error:
            logger.warning("Could not prepare AI request from the library: %s", error)
            self._send_json(
                503,
                {"error": _localized_ai_error(error, lang)},
            )
            return
        except AssistantConfigurationError as error:
            logger.warning("Gemini assistant configuration error: %s", error)
            self._send_json(503, {"error": _localized_ai_error(error, lang)})
            return
        except BookTextNotFoundError as error:
            self._send_json(422, {"error": _localized_ai_error(error, lang)})
            return
        except AssistantError as error:
            logger.warning("Gemini assistant request failed: %s", error)
            self._send_json(502, {"error": _localized_ai_error(error, lang)})
            return

        self._send_json(200, {"answer": answer})

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin == TELEGRAM_WEBAPP_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", TELEGRAM_WEBAPP_ORIGIN)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        logger.info("Mini App API: " + format_string, *args)


def start_webapp_api():
    if not TELEGRAM_WEBAPP_API_PORT:
        return None

    try:
        port = int(TELEGRAM_WEBAPP_API_PORT)
    except ValueError as error:
        raise ValueError("TELEGRAM_WEBAPP_API_PORT must be a valid TCP port.") from error
    if not 1 <= port <= 65535:
        raise ValueError("TELEGRAM_WEBAPP_API_PORT must be between 1 and 65535.")

    server = ThreadingHTTPServer(("0.0.0.0", port), BookCatalogRequestHandler)
    Thread(target=server.serve_forever, name="webapp-api", daemon=True).start()
    logger.info("Mini App book catalog API listening on port %s", port)
    return server


def show_book_menu(chat_id, lang):
    if bot is None:
        return

    section_title = "📚 Kitoblar" if lang == "uz" else "📚 Книги"
    show_section_navigation(chat_id, section_title, lang)

    try:
        pdf_files, drive_error = list_available_books()
    except LocalLibraryError as error:
        heading = "Mahalliy kutubxona xatosi:" if lang == "uz" else "Ошибка локальной библиотеки:"
        bot.send_message(chat_id, f"{heading}\n{error}")
        return
    except DriveLibraryError as error:
        heading = "Google Drive sozlamasi:" if lang == "uz" else "Настройка библиотеки Google Drive:"
        bot.send_message(chat_id, f"{heading}\n{error}")
        return

    if drive_error:
        warning = (
            f"Drive’dan kitoblarni olib bo‘lmadi; yuklangan kitoblar ko‘rsatilmoqda.\n{drive_error}"
            if lang == "uz"
            else f"Не удалось загрузить книги с Drive; показаны загруженные книги.\n{drive_error}"
        )
        bot.send_message(chat_id, warning)

    if not pdf_files:
        message = (
            "Hozircha kitoblar qo‘shilmagan. Yangi asarlar tez orada paydo bo‘ladi."
            if lang == "uz"
            else "Пока нет доступных книг. Новые произведения появятся позже."
        )
        bot.send_message(chat_id, message)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for number, item in enumerate(pdf_files, start=1):
        title = item["name"]
        button_text = f"{number}. 📄 {title}"
        if len(button_text) > 64:
            button_text = button_text[:61] + "..."
        markup.add(
            types.InlineKeyboardButton(
                button_text,
                callback_data=f"{item['source']}:{item['id']}",
            )
        )

    back_label = "⬅️ Asosiy menyu" if lang == "uz" else "⬅️ Главное меню"
    markup.add(types.InlineKeyboardButton(back_label, callback_data="books:back"))
    prompt = (
        "📚 Kerakli asarni tanlang — u PDF ko‘rinishida yuboriladi:"
        if lang == "uz"
        else "📚 Выберите книгу — она будет отправлена в формате PDF:"
    )
    bot.send_message(chat_id, prompt, reply_markup=markup)


def handle_book_callback(callback):
    if bot is None or callback.message is None:
        return

    chat_id = callback.message.chat.id
    lang = user_lang.get(chat_id, "uz")
    if callback.data == "books:back":
        bot.answer_callback_query(callback.id)
        show_main_menu(
            chat_id,
            lang,
            allow_webapp=getattr(callback.message.chat, "type", "private") == "private",
        )
        return
    if callback.data == "books:list":
        bot.answer_callback_query(callback.id)
        show_book_menu(chat_id, lang)
        return
    if callback.data.startswith("book:"):
        bot.answer_callback_query(
            callback.id,
            "Menyu yangilandi." if lang == "uz" else "Меню обновлено.",
        )
        show_book_menu(chat_id, lang)
        return
    if not callback.data.startswith(("drive:", "local:")):
        bot.answer_callback_query(callback.id)
        return

    source, file_id = callback.data.split(":", 1)
    if source not in {"drive", "local"}:
        bot.answer_callback_query(callback.id)
        return
    send_book_to_chat(chat_id, lang, source, file_id, callback.id)


def send_book_to_chat(chat_id, lang, source, file_id, callback_id=None):
    try:
        document = (
            download_local_pdf(file_id)
            if source == "local"
            else download_pdf(file_id)
        )
    except (DriveLibraryError, LocalLibraryError) as error:
        if callback_id is not None:
            bot.answer_callback_query(
                callback_id,
                "Yuklab bo'lmadi." if lang == "uz" else "Не удалось загрузить.",
            )
        back_label = "⬅️ Kitoblar ro'yxati" if lang == "uz" else "⬅️ К списку книг"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(back_label, callback_data="books:list"))
        error_heading = "Kitobni yuborishda xatolik:" if lang == "uz" else "Ошибка отправки книги:"
        bot.send_message(
            chat_id,
            f"{error_heading}\n{error}",
            reply_markup=markup,
        )
        return

    if callback_id is not None:
        bot.answer_callback_query(callback_id)
    try:
        bot.send_document(chat_id, document, caption=document.name, timeout=120)
    except (apihelper.ApiException, RequestException):
        message = (
            "PDF yuborilmadi. Tugmani yana bosing; muammo davom etsa, bot serverining internet aloqasini tekshiring."
            if lang == "uz"
            else "Не удалось отправить PDF. Нажмите кнопку ещё раз и проверьте соединение бота."
        )
        bot.send_message(chat_id, message)


def show_audio_menu(chat_id, lang):
    if bot is None:
        return

    section_title = "🎧 Audiokitoblar" if lang == "uz" else "🎧 Аудиокниги"
    show_section_navigation(chat_id, section_title, lang)

    try:
        audio_books = list_audio_books()
    except AudioLibraryError as error:
        heading = "Audiokitoblar xatosi:" if lang == "uz" else "Ошибка аудиокниг:"
        bot.send_message(chat_id, f"{heading}\n{error}")
        return

    if not audio_books:
        message = (
            "Hozircha audiokitoblar qo‘shilmagan. Yangi yozuvlar tez orada paydo bo‘ladi."
            if lang == "uz"
            else "Пока нет аудиокниг. Новые записи появятся позже."
        )
        bot.send_message(chat_id, message)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for number, item in enumerate(audio_books, start=1):
        button_text = f"{number}. 🎧 {item['name']}"
        if len(button_text) > 64:
            button_text = button_text[:61] + "..."
        markup.add(
            types.InlineKeyboardButton(
                button_text,
                callback_data=f"audio:{item['id']}",
            )
        )

    back_label = "⬅️ Asosiy menyu" if lang == "uz" else "⬅️ Главное меню"
    markup.add(types.InlineKeyboardButton(back_label, callback_data="audio:back"))
    prompt = (
        "🎧 Tinglash uchun audiokitobni tanlang:"
        if lang == "uz"
        else "🎧 Выберите аудиокнигу для прослушивания:"
    )
    bot.send_message(chat_id, prompt, reply_markup=markup)


def handle_audio_callback(callback):
    if bot is None or callback.message is None:
        return

    chat_id = callback.message.chat.id
    lang = user_lang.get(chat_id, "uz")
    if callback.data == "audio:back":
        bot.answer_callback_query(callback.id)
        show_main_menu(
            chat_id,
            lang,
            allow_webapp=getattr(callback.message.chat, "type", "private") == "private",
        )
        return
    if callback.data == "audio:list":
        bot.answer_callback_query(callback.id)
        show_audio_menu(chat_id, lang)
        return
    if not callback.data.startswith("audio:"):
        bot.answer_callback_query(callback.id)
        return

    audio_id = callback.data.split(":", 1)[1]
    try:
        audio = download_audio_book(audio_id)
    except AudioLibraryError as error:
        bot.answer_callback_query(
            callback.id,
            "Yuborib bo‘lmadi." if lang == "uz" else "Не удалось отправить.",
        )
        back_label = "⬅️ Audiokitoblar ro‘yxati" if lang == "uz" else "⬅️ К аудиокнигам"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(back_label, callback_data="audio:list"))
        heading = "Audiokitob xatosi:" if lang == "uz" else "Ошибка аудиокниги:"
        bot.send_message(chat_id, f"{heading}\n{error}", reply_markup=markup)
        return

    bot.answer_callback_query(callback.id)
    try:
        bot.send_audio(chat_id, audio, caption=audio.name, timeout=120)
    except (apihelper.ApiException, RequestException):
        message = (
            "Audiokitob yuborilmadi. Tugmani yana bosing; muammo davom etsa, bot serverining internet aloqasini tekshiring."
            if lang == "uz"
            else "Не удалось отправить аудиокнигу. Нажмите кнопку ещё раз и проверьте соединение бота."
        )
        bot.send_message(chat_id, message)


def show_ai_menu(chat_id, lang):
    if bot is None:
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    if lang == "ru":
        markup.add(
            types.InlineKeyboardButton("📖 Спросить по книге", callback_data="ai:books"),
            types.InlineKeyboardButton("✨ Подобрать книгу", callback_data="ai:recommend"),
            types.InlineKeyboardButton("🎓 Помощь в учёбе и преподавании", callback_data="ai:study"),
            types.InlineKeyboardButton("⬅️ Главное меню", callback_data="ai:back"),
        )
        prompt = (
            "🤖 AI-помощник умеет отвечать по выбранному PDF, подбирать книги "
            "и помогать ученикам и учителям. Выберите задачу:"
        )
    else:
        markup.add(
            types.InlineKeyboardButton("📖 Savolni kitobdan so‘rash", callback_data="ai:books"),
            types.InlineKeyboardButton("✨ Kitob tavsiya qilish", callback_data="ai:recommend"),
            types.InlineKeyboardButton("🎓 O‘qish va darsga yordam", callback_data="ai:study"),
            types.InlineKeyboardButton("⬅️ Asosiy menyu", callback_data="ai:back"),
        )
        prompt = (
            "🤖 AI yordamchi tanlangan PDF matnidan javob topadi, kitob tavsiya qiladi "
            "va o‘quvchi hamda o‘qituvchilarga yordam beradi. Vazifani tanlang:"
        )
    bot.send_message(chat_id, prompt, reply_markup=markup)


def _send_ai_answer(chat_id, question, session, user_id):
    lang = session.get("lang", user_lang.get(chat_id, "uz"))
    if not _consume_ai_rate_limit(user_id):
        bot.send_message(
            chat_id,
            "AI so‘rovlari limiti tugadi. Birozdan keyin qayta urinib ko‘ring."
            if lang == "uz"
            else "Лимит AI-запросов исчерпан. Попробуйте позже.",
        )
        return

    try:
        books, _ = list_available_books()
        answer = generate_ai_answer(
            question,
            session["mode"],
            lang,
            books,
            selected_book=session.get("book"),
        )
    except (AssistantError, DriveLibraryError, LocalLibraryError) as error:
        bot.send_message(chat_id, _localized_ai_error(error, lang))
        return

    remaining = answer.strip()
    while remaining:
        if len(remaining) <= 4000:
            chunk, remaining = remaining, ""
        else:
            split_at = remaining.rfind("\n", 0, 4000)
            if split_at < 1:
                split_at = 4000
            chunk, remaining = remaining[:split_at], remaining[split_at:].lstrip()
        bot.send_message(chat_id, chunk)


def handle_ai_callback(callback):
    if bot is None or callback.message is None:
        return

    chat_id = callback.message.chat.id
    lang = user_lang.get(chat_id, "uz")
    data = callback.data or ""
    if getattr(callback.message.chat, "type", "private") != "private":
        bot.answer_callback_query(
            callback.id,
            "Shaxsiy chatda oching." if lang == "uz" else "Откройте в личном чате.",
        )
        return

    if data == "ai:back":
        ai_sessions.pop(chat_id, None)
        bot.answer_callback_query(callback.id)
        show_main_menu(
            chat_id,
            lang,
            allow_webapp=getattr(callback.message.chat, "type", "private") == "private",
        )
        return
    if data in {"ai:recommend", "ai:study"}:
        ai_sessions[chat_id] = {
            "mode": "recommend" if data == "ai:recommend" else "study",
            "lang": lang,
        }
        bot.answer_callback_query(callback.id)
        prompt = (
            "Qaysi kitobni yoqtirishingiz yoki qaysi mavzuda yordam kerakligini yozing. "
            "Savol 1200 belgidan oshmasin."
            if lang == "uz"
            else "Напишите, какую книгу вы ищете или по какой теме нужна помощь. "
            "Вопрос — не более 1200 символов."
        )
        bot.send_message(chat_id, prompt)
        return
    if data == "ai:books":
        try:
            books, _ = list_available_books()
        except (DriveLibraryError, LocalLibraryError) as error:
            bot.answer_callback_query(callback.id)
            bot.send_message(chat_id, _localized_ai_error(error, lang))
            return
        if not books:
            bot.answer_callback_query(callback.id)
            bot.send_message(
                chat_id,
                "Kutubxonada hozircha PDF kitoblar yo‘q."
                if lang == "uz"
                else "В библиотеке пока нет PDF-книг.",
            )
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for book in books[:100]:
            source_code = "l" if book["source"] == "local" else "d"
            callback_data = f"aib:{source_code}:{book['id']}"
            title = book["name"]
            if len(title) > 61:
                title = title[:58] + "..."
            markup.add(
                types.InlineKeyboardButton(
                    title,
                    callback_data=callback_data,
                )
            )
        markup.add(
            types.InlineKeyboardButton(
                "⬅️ Orqaga" if lang == "uz" else "⬅️ Назад",
                callback_data="ai:back",
            )
        )
        bot.answer_callback_query(callback.id)
        bot.send_message(
            chat_id,
            "Savol bermoqchi bo‘lgan kitobni tanlang:"
            if lang == "uz"
            else "Выберите книгу для вопроса:",
            reply_markup=markup,
        )
        return
    if data.startswith("aib:"):
        parts = data.split(":", 2)
        if len(parts) != 3 or parts[1] not in {"l", "d"}:
            bot.answer_callback_query(callback.id)
            return
        source = "local" if parts[1] == "l" else "drive"
        try:
            books, _ = list_available_books()
        except (DriveLibraryError, LocalLibraryError) as error:
            bot.answer_callback_query(callback.id)
            bot.send_message(chat_id, _localized_ai_error(error, lang))
            return
        book = next(
            (
                item
                for item in books
                if item["source"] == source and item["id"] == parts[2]
            ),
            None,
        )
        if book is None:
            bot.answer_callback_query(
                callback.id,
                "Kitob topilmadi." if lang == "uz" else "Книга не найдена.",
            )
            return
        ai_sessions[chat_id] = {"mode": "book_qa", "book": book, "lang": lang}
        bot.answer_callback_query(callback.id)
        bot.send_message(
            chat_id,
            f"“{book['name']}” kitobi haqida savolingizni yozing (1200 belgigacha)."
            if lang == "uz"
            else f"Задайте вопрос о книге «{book['name']}» (до 1200 символов).",
        )
        return

    bot.answer_callback_query(callback.id)


def show_main_menu(chat_id, lang, allow_webapp=True):
    if bot is None:
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if TELEGRAM_WEBAPP_URL and allow_webapp:
        launcher_label = "🚀 3D kutubxona" if lang == "uz" else "🚀 3D-библиотека"
        markup.row(
            types.KeyboardButton(
                launcher_label,
                web_app=types.WebAppInfo(url=TELEGRAM_WEBAPP_URL),
            )
        )
    if lang == "uz":
        markup.add(
            types.KeyboardButton("📚 Kitoblar"),
            types.KeyboardButton("🎧 Audiokitoblar"),
            types.KeyboardButton("🤖 AI yordamchi"),
            types.KeyboardButton("👩‍🏫 O‘qituvchilar"),
            types.KeyboardButton("🎒 O‘quvchilar"),
            types.KeyboardButton("👥 Umumiy resurslar"),
            types.KeyboardButton("ℹ️ Kutubxona haqida"),
            types.KeyboardButton("✉️ Aloqa"),
            types.KeyboardButton("❔ Yordam"),
            types.KeyboardButton("🌐 Tilni o‘zgartirish"),
        )
        bot.send_message(
            chat_id,
            "✨ Kutubxonaga xush kelibsiz!\n📖 Kitob o‘qing, 🎧 audiokitob tinglang.\n\nKerakli bo‘limni tanlang:",
            reply_markup=markup,
        )
    else:
        markup.add(
            types.KeyboardButton("📚 Книги"),
            types.KeyboardButton("🎧 Аудиокниги"),
            types.KeyboardButton("🤖 AI-помощник"),
            types.KeyboardButton("👩‍🏫 Учителям"),
            types.KeyboardButton("🎒 Ученикам"),
            types.KeyboardButton("👥 Общие ресурсы"),
            types.KeyboardButton("ℹ️ О библиотеке"),
            types.KeyboardButton("✉️ Связаться"),
            types.KeyboardButton("❔ Помощь"),
            types.KeyboardButton("🌐 Сменить язык"),
        )
        bot.send_message(
            chat_id,
            "✨ Добро пожаловать в библиотеку!\n📖 Читайте книги и 🎧 слушайте аудиокниги.\n\nВыберите раздел:",
            reply_markup=markup,
        )


def handle_commands(message):
    if bot is None or message is None or message.text is None:
        return

    chat_id = message.chat.id
    text = message.text
    if text.startswith("/"):
        ai_sessions.pop(chat_id, None)

    if text == "/ai":
        if getattr(message.chat, "type", "private") != "private":
            bot.send_message(
                chat_id,
                "AI yordamchidan bot bilan shaxsiy chatda foydalaning."
                if user_lang.get(chat_id, "uz") == "uz"
                else "Используйте AI-помощник в личном чате с ботом.",
            )
            return True
        show_ai_menu(chat_id, user_lang.get(chat_id, "uz"))
        return True
    if text == "/cancel":
        ai_sessions.pop(chat_id, None)
        bot.send_message(
            chat_id,
            "AI so‘rovi bekor qilindi." if user_lang.get(chat_id, "uz") == "uz" else "Запрос AI отменён.",
        )
        return True
    if text == "/start":
        ai_sessions.pop(chat_id, None)
        show_language_menu(chat_id)
        return True
    if text == "/menu":
        ai_sessions.pop(chat_id, None)
        lang = user_lang.get(chat_id, "uz")
        show_main_menu(chat_id, lang, allow_webapp=message.chat.type == "private")
        return True
    if text == "/help":
        lang = user_lang.get(chat_id, "uz")
        if lang == "uz":
            bot.send_message(
                chat_id,
                "Yordam kerakmi?\n📚 Kitoblar bo‘limidan asarni tanlang.\n🎧 Audiokitoblar bo‘limidan tinglash uchun yozuvni tanlang.\n\nAsosiy menyu: /menu",
            )
        else:
            bot.send_message(
                chat_id,
                "Как пользоваться библиотекой:\n📚 выберите произведение в разделе «Книги».\n🎧 выберите запись в разделе «Аудиокниги».\n\nГлавное меню: /menu",
            )
        return True
    if text == "/privacy":
        lang = user_lang.get(chat_id, "uz")
        bot.send_message(chat_id, PRIVACY_MESSAGES[lang])
        return True
    if text in {"/lang", "/language"}:
        show_language_menu(chat_id)
        return True
    if text == "/myid":
        user = getattr(message, "from_user", None)
        user_id = getattr(user, "id", None)
        if user_id is not None:
            bot.send_message(chat_id, f"Telegram ID: {user_id}")
        return True
    return False


def _configured_admin_ids():
    raw_ids = os.getenv("TELEGRAM_ADMIN_IDS", "")
    admin_ids = set()
    for value in raw_ids.split(","):
        value = value.strip()
        if not value:
            continue
        if not value.isdecimal():
            raise ValueError("TELEGRAM_ADMIN_IDS faqat raqamli Telegram ID’lardan iborat bo‘lishi kerak.")
        admin_ids.add(int(value))
    return admin_ids


def _handle_admin_upload(message, telegram_file, file_name, save_function, item_label):
    if bot is None or message is None or telegram_file is None:
        return

    chat_id = message.chat.id
    if message.chat.type != "private":
        bot.send_message(chat_id, "Fayllarni botga shaxsiy chatda yuboring.")
        return

    try:
        admin_ids = _configured_admin_ids()
    except ValueError:
        bot.send_message(chat_id, "Admin sozlamasi noto‘g‘ri. TELEGRAM_ADMIN_IDS qiymatini tekshiring.")
        return
    if not admin_ids:
        bot.send_message(chat_id, "Admin hali sozlanmagan. Avval /myid yuboring va bot egasiga ID’ingizni ayting.")
        return
    if message.from_user is None or message.from_user.id not in admin_ids:
        bot.send_message(chat_id, "Fayl yuklash faqat bot admini uchun.")
        return

    if telegram_file.file_size is not None and telegram_file.file_size > MAX_UPLOAD_SIZE:
        bot.send_message(chat_id, "Bot orqali yuklanadigan fayl 20 MB dan kichik bo‘lishi kerak.")
        return
    try:
        file_info = bot.get_file(telegram_file.file_id)
        contents = bot.download_file(file_info.file_path)
        if len(contents) > MAX_UPLOAD_SIZE:
            bot.send_message(chat_id, "Bot orqali yuklanadigan fayl 20 MB dan kichik bo‘lishi kerak.")
            return
        saved = save_function(file_name, contents)
    except (AudioLibraryError, LocalLibraryError) as error:
        bot.send_message(chat_id, str(error))
        return
    except (apihelper.ApiException, OSError, RequestException):
        bot.send_message(chat_id, "Telegramdan faylni yuklab olib bo‘lmadi. Qayta urinib ko‘ring.")
        return

    bot.send_message(chat_id, f"{item_label} yuklandi: {saved['name']}")


def handle_document_upload(message):
    if bot is None or message is None or message.document is None:
        return

    file_name = message.document.file_name or ""
    extension = Path(file_name).suffix.lower()
    if extension == ".pdf":
        _handle_admin_upload(message, message.document, file_name, save_pdf, "Kitob")
    elif extension in SUPPORTED_AUDIO_EXTENSIONS:
        _handle_admin_upload(message, message.document, file_name, save_audio_book, "Audiokitob")
    else:
        bot.send_message(message.chat.id, "Faqat PDF, MP3 yoki M4A fayllarni yuborish mumkin.")


def handle_audio_upload(message):
    if bot is None or message is None or message.audio is None:
        return

    telegram_audio = message.audio
    file_name = telegram_audio.file_name
    if not file_name:
        file_name = "audiokitob.m4a" if telegram_audio.mime_type == "audio/mp4" else "audiokitob.mp3"
    _handle_admin_upload(message, telegram_audio, file_name, save_audio_book, "Audiokitob")


def handle_messages(message):
    if bot is None or message is None or message.text is None:
        return

    chat_id = message.chat.id
    text = message.text

    if handle_commands(message):
        return

    if text in {"🤖 AI yordamchi", "🤖 AI-помощник"}:
        ai_sessions.pop(chat_id, None)
        if getattr(message.chat, "type", "private") != "private":
            bot.send_message(
                chat_id,
                "AI yordamchidan bot bilan shaxsiy chatda foydalaning."
                if user_lang.get(chat_id, "uz") == "uz"
                else "Используйте AI-помощник в личном чате с ботом.",
            )
            return
        show_ai_menu(chat_id, user_lang.get(chat_id, "uz"))
        return

    navigation_texts = {
        "⬅️ Asosiy menyu",
        "⬅️ Главное меню",
        "📚 Kitoblar",
        "📚 Книги",
        "📚 Kitobxonlar uchun",
        "📚 Для читателей",
        "🎧 Audiokitoblar",
        "🎧 Audio kitoblar",
        "🎧 Аудиокниги",
        "👩‍🏫 O‘qituvchilar",
        "👩‍🏫 Учителям",
        "🎒 O‘quvchilar",
        "🎒 Ученикам",
        "👥 Umumiy resurslar",
        "👥 Общие ресурсы",
        "ℹ️ Kutubxona haqida",
        "ℹ️ О библиотеке",
        "✉️ Aloqa",
        "✉️ Связаться",
        "❔ Yordam",
        "❔ Помощь",
        "🌐 Tilni o‘zgartirish",
        "🔄 Tilni o'zgartirish",
        "🌐 Сменить язык",
        "🔄 Сменить язык",
        "🇺🇿 O‘zbekcha",
        "🇺🇿 O'zbek tili",
        "🇺🇿 O‘zbek tili",
        "🇷🇺 Русский язык",
    }
    if text in navigation_texts:
        ai_sessions.pop(chat_id, None)
    elif chat_id in ai_sessions:
        if len(text.strip()) > MAX_QUESTION_LENGTH:
            bot.send_message(
                chat_id,
                f"Savol {MAX_QUESTION_LENGTH} belgidan oshmasin."
                if user_lang.get(chat_id, "uz") == "uz"
                else f"Вопрос не должен превышать {MAX_QUESTION_LENGTH} символов.",
            )
            return
        session = ai_sessions.pop(chat_id)
        user = getattr(message, "from_user", None)
        user_id = getattr(user, "id", None) or chat_id
        _send_ai_answer(chat_id, text.strip(), session, user_id)
        return

    if text in {"🇺🇿 O‘zbekcha", "🇺🇿 O'zbek tili", "🇺🇿 O‘zbek tili"}:
        user_lang[chat_id] = "uz"
        show_main_menu(chat_id, "uz", allow_webapp=message.chat.type == "private")
    elif text == "🇷🇺 Русский язык":
        user_lang[chat_id] = "ru"
        show_main_menu(chat_id, "ru", allow_webapp=message.chat.type == "private")
    elif text in {"⬅️ Asosiy menyu", "⬅️ Главное меню"}:
        show_main_menu(
            chat_id,
            user_lang.get(chat_id, "uz"),
            allow_webapp=message.chat.type == "private",
        )
    elif text in {"📚 Kitoblar", "📚 Книги", "📚 Kitobxonlar uchun", "📚 Для читателей"}:
        show_book_menu(chat_id, user_lang.get(chat_id, "uz"))
    elif text in {"🎧 Audiokitoblar", "🎧 Audio kitoblar", "🎧 Аудиокниги"}:
        show_audio_menu(chat_id, user_lang.get(chat_id, "uz"))
    elif text in {"🎒 O‘quvchilar", "🎒 Ученикам"}:
        show_student_grade_menu(chat_id, user_lang.get(chat_id, "uz"))
    elif text in {"👩‍🏫 O‘qituvchilar", "👩‍🏫 Учителям"}:
        show_teacher_resources(chat_id, user_lang.get(chat_id, "uz"))
    elif text in {"🌐 Tilni o‘zgartirish", "🔄 Tilni o'zgartirish", "🌐 Сменить язык", "🔄 Сменить язык"}:
        show_language_menu(chat_id)
    else:
        lang = user_lang.get(chat_id, "uz")
        section_label = SECTION_ALIASES.get(lang, {}).get(text, text)
        section_message = SECTION_MESSAGES.get(lang, {}).get(section_label)
        if section_message:
            show_section_screen(chat_id, section_label, section_message, lang)
            return

        if lang == "uz":
            bot.send_message(chat_id, "Bu bo‘limni topa olmadim. Iltimos, menyudan tanlang.")
        else:
            bot.send_message(chat_id, "Не нашёл этот раздел. Выберите пункт в меню.")


def handle_webapp_data(message):
    if bot is None or message is None or message.web_app_data is None:
        return

    chat_id = message.chat.id
    lang = user_lang.get(chat_id, "uz")
    try:
        payload = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, TypeError):
        bot.send_message(
            chat_id,
            "So‘rovni tushunmadim. Ilovani qayta ochib, bo‘limni tanlang."
            if lang == "uz"
            else "Не удалось обработать запрос. Откройте приложение и выберите раздел.",
        )
        return

    if not isinstance(payload, dict):
        payload = {}

    action = payload.get("action")
    if action == "download_book":
        source = payload.get("source")
        file_id = payload.get("id")
        if (
            not isinstance(source, str)
            or source not in {"drive", "local"}
            or not isinstance(file_id, str)
        ):
            bot.send_message(
                chat_id,
                "Kitob tanlovi noto‘g‘ri. Ro‘yxatni yangilab qayta urinib ko‘ring."
                if lang == "uz"
                else "Неверный выбор книги. Обновите список и попробуйте снова.",
            )
            return
        send_book_to_chat(chat_id, lang, source, file_id)
        return

    section = payload.get("section") if action == "open" else None
    if not isinstance(section, str):
        section = None

    if section == "books":
        show_book_menu(chat_id, lang)
    elif section == "audio":
        show_audio_menu(chat_id, lang)
    elif section == "teachers":
        show_teacher_resources(chat_id, lang)
    elif section == "students":
        show_student_grade_menu(chat_id, lang)
    elif section in {"resources", "about", "contact", "help"}:
        section_ids = {
            "resources": "👥 Umumiy resurslar" if lang == "uz" else "👥 Общие ресурсы",
            "about": "ℹ️ Kutubxona haqida" if lang == "uz" else "ℹ️ О библиотеке",
            "contact": "✉️ Aloqa" if lang == "uz" else "✉️ Связаться",
            "help": "❔ Yordam" if lang == "uz" else "❔ Помощь",
        }
        title = section_ids[section]
        content = SECTION_MESSAGES[lang][title]
        show_section_screen(chat_id, title, content, lang)
    else:
        bot.send_message(
            chat_id,
            "Bu bo‘lim mavjud emas. Ilovani yangilang va qayta urinib ko‘ring."
            if lang == "uz"
            else "Этот раздел недоступен. Обновите приложение и попробуйте снова.",
        )


def validate_telegram_webapp_url():
    if not TELEGRAM_WEBAPP_URL:
        return
    parsed_url = urlsplit(TELEGRAM_WEBAPP_URL)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("TELEGRAM_WEBAPP_URL must be a public HTTPS URL.")


if bot is not None:
    bot.message_handler(
        commands=["start", "menu", "help", "privacy", "lang", "language", "myid", "ai", "cancel"]
    )(handle_commands)
    bot.message_handler(content_types=["text"])(handle_messages)
    bot.message_handler(content_types=["web_app_data"])(handle_webapp_data)
    bot.message_handler(content_types=["document"])(handle_document_upload)
    bot.message_handler(content_types=["audio"])(handle_audio_upload)
    bot.callback_query_handler(
        func=lambda callback: callback.data
        and callback.data.startswith("teacher:")
    )(handle_teacher_callback)
    bot.callback_query_handler(
        func=lambda callback: callback.data
        and callback.data.startswith("students:")
    )(handle_student_callback)
    bot.callback_query_handler(
        func=lambda callback: callback.data and callback.data.startswith("audio:")
    )(handle_audio_callback)
    bot.callback_query_handler(
        func=lambda callback: callback.data
        and callback.data.startswith(("ai:", "aib:"))
    )(handle_ai_callback)
    bot.callback_query_handler(
        func=lambda callback: callback.data
        and callback.data.startswith(("book:", "books:", "drive:", "local:"))
    )(
        handle_book_callback
    )


def main():
    if bot is None:
        raise RuntimeError("Set the TELEGRAM_BOT_TOKEN environment variable before running the bot.")
    validate_telegram_webapp_url()
    configure_bot_commands()
    start_webapp_api()
    bot.infinity_polling()


def configure_bot_commands():
    if bot is None:
        return

    commands_by_language = (
        (
            None,
            [
                types.BotCommand("start", "Kutubxonani boshlash"),
                types.BotCommand("menu", "Asosiy menyu"),
                types.BotCommand("help", "Yordam"),
                types.BotCommand("lang", "Tilni tanlash"),
                types.BotCommand("privacy", "Ma’lumotlar haqida"),
                types.BotCommand("ai", "Sun’iy intellekt yordamchisi"),
            ],
        ),
        (
            "ru",
            [
                types.BotCommand("start", "Открыть библиотеку"),
                types.BotCommand("menu", "Главное меню"),
                types.BotCommand("help", "Помощь"),
                types.BotCommand("lang", "Выбрать язык"),
                types.BotCommand("privacy", "О данных"),
                types.BotCommand("ai", "AI-помощник"),
            ],
        ),
    )
    for language_code, commands in commands_by_language:
        try:
            bot.set_my_commands(commands, language_code=language_code)
        except (apihelper.ApiException, RequestException) as error:
            logger.warning(
                "Could not register Telegram commands for %s: %s",
                language_code or "default",
                error,
            )


if __name__ == "__main__":
    main()
