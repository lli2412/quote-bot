import telebot
import random
import os
import json
import threading
import time
from datetime import datetime, timezone, timedelta

# === Токен из переменной окружения ===
TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("Установите TELEGRAM_TOKEN в Render!")

bot = telebot.TeleBot(TOKEN)

# === Файлы для хранения ===
CHATS_FILE = "subscribed_chats.json"
PENDING_CAPTCHA_FILE = "pending_captcha.json"  # хранит: {user_id: {group_id, time}}

# === Загрузка данных ===
def load_subscribed_chats():
    if os.path.exists(CHATS_FILE):
        with open(CHATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_subscribed_chats(chats):
    with open(CHATS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(set(chats)), f, ensure_ascii=False)

def load_pending_captcha():
    if os.path.exists(PENDING_CAPTCHA_FILE):
        with open(PENDING_CAPTCHA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_pending_captcha(data):
    with open(PENDING_CAPTCHA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

# === База цитат с авторами ===
QUOTES = {
    "пословица": [
        ("Что посеешь, то и пожнёшь.", "Русская народная мудрость"),
        ("Не имей сто рублей, а имей сто друзей.", "Русская пословица"),
        ("Делу — время, потехе — час.", "Русская пословица")
    ],
    "китайская_мудрость": [
        ("Путешествие в тысячу ли начинается с одного шага.", "Лао-цзы"),
        ("Лучше зажечь одну свечу, чем проклинать темноту.", "Китайская мудрость")
    ],
    "цитаты_великих": [
        ("Познай самого себя.", "Сократ"),
        ("Я мыслю — следовательно, существую.", "Рене Декарт")
    ],
    "мотивация": [
        ("Успех — это 1% таланта и 99% труда.", "Томас Эдисон")
    ]
}

CATEGORY_MAP = {
    'пословица': 'пословица',
    'китайская': 'китайская_мудрость',
    'великие': 'цитаты_великих',
    'мотивация': 'мотивация'
}

CATEGORY_EMOJI = {
    'пословица': '🪵',
    'китайская_мудрость': '🐉',
    'цитаты_великих': '📜',
    'мотивация': '💪'
}

def format_quote(text, author, category_key):
    emoji = CATEGORY_EMOJI.get(category_key, '✨')
    category_name = {
        'пословица': 'Русская пословица',
        'китайская_мудрость': 'Китайская мудрость',
        'цитаты_великих': 'Цитата великих',
        'мотивация': 'Мотивация'
    }.get(category_key, category_key)
    return f"{emoji} *{text}*\n— _{author}_\n\n📚 {category_name}"

# === Команда /start ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = str(message.chat.id)
    chats = load_subscribed_chats()
    if chat_id not in chats:
        chats.append(chat_id)
        save_subscribed_chats(chats)
    bot.send_message(
        message.chat.id,
        "Привет! 💬 Я — бот мудрости.\n\n"
        "Команды:\n"
        "/quote — случайная цитата\n"
        "/мотивация — мотивирующая фраза\n"
        "/пословица — русская мудрость\n"
        "/китайская — древняя мудрость Востока\n"
        "/великие — слова великих людей\n\n"
        "✨ Каждое утро в 9:00 по Москве я присылаю мудрость дня!",
        parse_mode="Markdown"
    )

# === Обработка новых участников в группе ===
@bot.message_handler(func=lambda m: m.new_chat_members is not None)
def handle_new_member(message):
    for new_member in message.new_chat_members:
        user_id = new_member.id
        user_name = new_member.first_name
        group_id = message.chat.id

        # Отправить капчу в личку пользователю
        try:
            markup = telebot.types.InlineKeyboardMarkup()
            button = telebot.types.InlineKeyboardButton("Я человек ✅", callback_data=f"captcha_{user_id}")
            markup.add(button)

            bot.send_message(
                user_id,
                f"Привет, {user_name}! Подтверди, что ты человек, чтобы остаться в группе:",
                reply_markup=markup
            )

            # Записать в ожидание капчи
            pending = load_pending_captcha()
            pending[str(user_id)] = {"group_id": group_id, "time": time.time()}
            save_pending_captcha(pending)

            # Удалить через 10 секунд, если не подтвердил
            threading.Timer(10.0, lambda: check_captcha_timeout(user_id, group_id)).start()
        except Exception:
            # Пользователь заблокировал бота — сразу кик
            bot.kick_chat_member(group_id, user_id)

# === Проверка таймаута капчи ===
def check_captcha_timeout(user_id, group_id):
    pending = load_pending_captcha()
    entry = pending.get(str(user_id))
    if entry and entry["group_id"] == group_id:
        try:
            bot.kick_chat_member(group_id, user_id)
            bot.send_message(group_id, f"Пользователь {user_id} был удален за неактивность.")
        except Exception:
            pass
        # Удаляем из ожидания
        pending.pop(str(user_id), None)
        save_pending_captcha(pending)

# === Обработка кнопки капчи ===
@bot.callback_query_handler(func=lambda call: call.data.startswith("captcha_"))
def handle_captcha_button(call):
    user_id = int(call.data.split("_")[1])
    if call.from_user.id == user_id:
        # Подписываем на рассылку
        chats = load_subscribed_chats()
        chat_id_str = str(user_id)
        if chat_id_str not in chats:
            chats.append(chat_id_str)
            save_subscribed_chats(chats)

        # Отправляем приветствие
        bot.send_message(user_id, "✅ Подтверждено! Вы подписались на рассылку цитат.")
        bot.send_message(call.message.chat.id, f"Добро пожаловать в группу, {call.from_user.first_name}!")

        # Удаляем из ожидания
        pending = load_pending_captcha()
        pending.pop(str(user_id), None)
        save_pending_captcha(pending)

        # Ответ на кнопку
        bot.answer_callback_query(call.id, "Добро пожаловать!")

# === Отправка цитат ===
@bot.message_handler(commands=['quote'])
def send_random_quote(message):
    all_quotes = []
    for cat, quotes in QUOTES.items():
        for q in quotes:
            all_quotes.append((q[0], q[1], cat))
    text, author, cat = random.choice(all_quotes)
    msg = format_quote(text, author, cat)
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['мотивация', 'пословица', 'китайская', 'великие'])
def send_category_quote(message):
    cmd = message.text.replace("/", "")
    if cmd in CATEGORY_MAP:
        cat_key = CATEGORY_MAP[cmd]
        text, author = random.choice(QUOTES[cat_key])
        msg = format_quote(text, author, cat_key)
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    else:
        bot.reply_to(message, "Не знаю такой команды. Напиши /start.")

# === Ежедневная рассылка ===
def send_daily_quote():
    moscow_tz = timezone(timedelta(hours=3))
    while True:
        now = datetime.now(moscow_tz)
        next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        sleep_seconds = (next_run - now).total_seconds()
        time.sleep(sleep_seconds)

        chats = load_subscribed_chats()
        all_quotes = []
        for cat, quotes in QUOTES.items():
            for q in quotes:
                all_quotes.append((q[0], q[1], cat))
        text, author, cat = random.choice(all_quotes)
        msg = format_quote(text, author, cat)

        valid_chats = []
        for chat_id in chats:
            try:
                bot.send_message(chat_id, msg, parse_mode="Markdown")
                valid_chats.append(chat_id)
            except Exception:
                continue
        save_subscribed_chats(valid_chats)

threading.Thread(target=send_daily_quote, daemon=True).start()

if __name__ == '__main__':
    bot.infinity_polling()
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, 
        "Привет! 💬 Я — бот мудрости.\n\n"
        "Команды:\n"
        "/quote — случайная цитата\n"
        "/мотивация — мотивирующая фраза\n"
        "/пословица — русская мудрость\n"
        "/философия — мысли великих\n"
        "/юмор — улыбнись 😊"
    )

@bot.message_handler(commands=['quote'])
def send_random_quote(message):
    quote = random.choice(QUOTES["all"])
    bot.send_message(message.chat.id, f"✨ {quote}")

@bot.message_handler(commands=['мотивация', 'пословица', 'философия', 'юмор'])
def send_category_quote(message):
    cmd = message.text.replace("/", "")
    if cmd in QUOTES:
        quote = random.choice(QUOTES[cmd])
        bot.send_message(message.chat.id, f"💭 {quote}\n\n📚 Категория: {cmd}")
    else:
        bot.send_message(message.chat.id, "Не знаю такой команды. Напиши /start.")

# Запуск
if __name__ == '__main__':
    bot.infinity_polling()
