import telebot
from telebot import types
import os
import re
import random
import string
import sqlite3
import threading
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('TOKEN')

bot = telebot.TeleBot(TOKEN)

db_lock = threading.Lock()
conn = sqlite3.connect("botdata.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(deals);")
columns = [row[1] for row in cursor.fetchall()]
if 'deal_type' not in columns:
    try:
        cursor.execute("ALTER TABLE deals ADD COLUMN deal_type TEXT;")
        conn.commit()
    except sqlite3.OperationalError:
        pass

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    ton_wallet TEXT,
    card_number TEXT,
    lang TEXT DEFAULT 'ru',
    successful_deals INTEGER DEFAULT 0
);
""")

cursor.execute("PRAGMA table_info(users);")
user_columns = [row[1] for row in cursor.fetchall()]
if 'successful_deals' not in user_columns:
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN successful_deals INTEGER DEFAULT 0;")
        conn.commit()
        print("✅ Added successful_deals column to users table")
    except sqlite3.OperationalError as e:
        print(f"⚠️ Could not add successful_deals column: {e}")

cursor.execute("""
CREATE TABLE IF NOT EXISTS deals (
    deal_id TEXT PRIMARY KEY,
    seller_id INTEGER,
    seller_username TEXT,
    buyer_id INTEGER,
    amount REAL,
    offer TEXT,
    deal_type TEXT,
    status TEXT DEFAULT 'open',
    successful INTEGER DEFAULT 0
);
""")
conn.commit()

def generate_deal_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_user_lang(user_id):
    with db_lock:
        cursor.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        lang = res[0] if res and res[0] else 'ru'
        if lang not in ['ru', 'en']:
            lang = 'ru'
        return lang

def set_user_lang(user_id, lang):
    with db_lock:
        cursor.execute(
            "INSERT INTO users(user_id, lang) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET lang = ?",
            (user_id, lang, lang)
        )
        conn.commit()

def set_user_ton_wallet(user_id, ton_wallet):
    with db_lock:
        cursor.execute(
            "INSERT INTO users(user_id, ton_wallet) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET ton_wallet = ?",
            (user_id, ton_wallet, ton_wallet)
        )
        conn.commit()

def set_user_card_number(user_id, card_number):
    with db_lock:
        cursor.execute(
            "INSERT INTO users(user_id, card_number) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET card_number = ?",
            (user_id, card_number, card_number)
        )
        conn.commit()

def get_user_ton_wallet(user_id):
    with db_lock:
        cursor.execute("SELECT ton_wallet FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        return res[0] if res else None

def get_user_card_number(user_id):
    with db_lock:
        cursor.execute("SELECT card_number FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        return res[0] if res else None

def has_payment_methods(user_id):
    ton = get_user_ton_wallet(user_id)
    card = get_user_card_number(user_id)
    return bool(ton or card)

def set_user_successful_deals(user_id, count):
    with db_lock:
        cursor.execute(
            "INSERT INTO users(user_id, successful_deals) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET successful_deals = ?",
            (user_id, count, count)
        )
        conn.commit()

def get_user_successful_deals(user_id):
    with db_lock:
        cursor.execute("SELECT successful_deals FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        return res[0] if res else 0

def create_deal(deal_id, seller_id, seller_username, amount, offer, deal_type):
    with db_lock:
        cursor.execute("""
        INSERT INTO deals (deal_id, seller_id, seller_username, amount, offer, deal_type, status, successful)
        VALUES (?, ?, ?, ?, ?, ?, 'open', 0)""",
                       (deal_id, seller_id, seller_username, amount, offer, deal_type))
        conn.commit()
        print(f"✅ Deal created: {deal_id} with status 'open'")

def get_deal(deal_id):
    clean_id = deal_id.replace('#', '').strip()
    with db_lock:
        cursor.execute("SELECT * FROM deals WHERE deal_id = ?", (clean_id,))
        row = cursor.fetchone()
        if row:
            keys = ['deal_id', 'seller_id', 'seller_username', 'buyer_id', 'amount', 'offer', 'deal_type', 'status', 'successful']
            deal_dict = dict(zip(keys, row))
            print(f"📦 Found deal: {clean_id} - Status: {deal_dict['status']}")
            return deal_dict
        print(f"❌ Deal not found: {clean_id}")
        return None

def set_deal_buyer(deal_id, buyer_id):
    clean_id = deal_id.replace('#', '').strip()
    with db_lock:
        cursor.execute("UPDATE deals SET buyer_id = ? WHERE deal_id = ?", (buyer_id, clean_id))
        conn.commit()
        print(f"👤 Buyer {buyer_id} assigned to deal {clean_id}")

def close_deal(deal_id):
    clean_id = deal_id.replace('#', '').strip()
    with db_lock:
        cursor.execute("DELETE FROM deals WHERE deal_id = ?", (clean_id,))
        conn.commit()
        print(f"🗑️ Deal {clean_id} deleted from database")

def mark_deal_successful(deal_id):
    clean_id = deal_id.replace('#', '').strip()
    with db_lock:
        cursor.execute("SELECT seller_id FROM deals WHERE deal_id = ?", (clean_id,))
        result = cursor.fetchone()
        if result:
            seller_id = result[0]
            cursor.execute("UPDATE deals SET successful = 1, status='completed' WHERE deal_id = ?", (clean_id,))
            cursor.execute("UPDATE users SET successful_deals = successful_deals + 1 WHERE user_id = ?", (seller_id,))
            conn.commit()
            print(f"✅ Deal {clean_id} marked as successful")

def get_successful_deals_count(user_id):
    return get_user_successful_deals(user_id)

user_states = {}
user_inputs = {}

def set_user_state(user_id, state):
    user_states[user_id] = state

def get_user_state(user_id):
    return user_states.get(user_id)

def clear_user_state(user_id):
    user_states.pop(user_id, None)
    user_inputs.pop(user_id, None)

def set_user_input(user_id, key, value):
    if user_id not in user_inputs:
        user_inputs[user_id] = {}
    user_inputs[user_id][key] = value

def get_user_input(user_id, key):
    if user_id in user_inputs:
        return user_inputs[user_id].get(key)
    return None

def validate_ton_address(addr): 
    return bool(re.fullmatch(r'^[a-zA-Z0-9\-_]{48,64}$', addr.strip()))

def validate_nft_link(link): 
    return 't.me/nft/' in link or 'https://t.me/nft/' in link

def validate_card_number(card):
    card_clean = card.replace(' ', '').replace('-', '')
    return bool(re.fullmatch(r'\d{12,19}', card_clean))

MESSAGES = {
    'ru': {
        'welcome': ("Добро пожаловать в TESTNAME – надежный P2P-гарант\n\n"
                    "💼 Покупайте и продавайте всё, что угодно – безопасно!\n"
                    "От Telegram-подарков и NFT до токенов и фиата – сделки проходят легко и без риска.\n\n"
                    "Выберите нужный раздел ниже:"),
        'manage_rekv': "Выберите действие:",
        'add_ton_wallet': "🔑 Добавьте ваш TON-кошелек:",
        'add_card_number': "💳 Введите номер вашей карты (12-19 цифр):",
        'ton_invalid': "❌ Неверный адрес TON-кошелька",
        'card_invalid': "❌ Неверный формат номера карты. Введите только цифры, от 12 до 19 символов.",
        'ton_ok': "✅ Установлен TON-кошелек",
        'card_ok': "✅ Номер карты сохранен",
        'back_btn': "⬅️ Вернуться в меню",
        'create_deal_start': ("При проведении сделки со скинами Steam укажите ссылку на любой подарок.\n"
                             "После оплаты свяжитесь с системой — @GemGiftHelper\n\n"
                             "💰 Выберите метод оплаты:"),
        'choose_pay_method_ton': "💎 TON-Кошелек",
        'choose_pay_method_star': "⭐ Звезды",
        'choose_pay_method_card': "💳 На карту",
        'enter_ton_amount': "Введите сумму TON сделки (например: 199.99):",
        'enter_star_amount': "Введите количество звезд для оплаты (например: 150):",
        'enter_card_amount': "💼 Создание сделки\n\nВведите сумму RUB сделки в формате: 199.99",
        'enter_deal_offer': ("📝 Опишите, что предлагаете за {amount} {currency}.\n\n"
                            "Пример:\nhttps://t.me/nft/PlushPepe-1\nhttps://t.me/nft/DurovsCap-1"),
        'enter_deal_offer_card': ("📝 Укажите, что вы предлагаете в этой сделке за {amount} RUB\n\n"
                            "Пример:\nhttps://t.me/nft/PlushPepe-1\nhttps://t.me/nft/DurovsCap-1"),
        'deal_created': ("✅ Сделка создана!\n\n"
                         "💰 Сумма: {amount} {currency}\n"
                         "📜 Описание: {offer}\n"
                         "🔗 Ссылка для покупателя:\n{link}"),
        'deal_closed_confirm': "❓ Уверены, что хотите закрыть сделку #{deal_id}?",
        'deal_closed_yes': "✅ Сделка #{deal_id} удалена",
        'lang_change': "Изменить язык:",
        'support_info': "💁‍♂️ Поддержка: @APECTOKPAT_AKERMANSEX",
        'invalid_amount': "❌ Неверный формат суммы. Попробуйте снова.",
        'invalid_nft_link': "❌ Принимайте ссылки только в формате https://t.me/nft/… Попробуйте снова.",
        'deal_joined_notify_seller': "✅ Пользователь @{buyer} присоединился к сделке #{deal_id}",
        'deal_info_for_buyer_ton': ("💳 Информация о сделке #{deal_id}\n\n"
                               "👤 Вы покупатель\n"
                               "📌 Продавец: @{seller_username} | 🆔 {seller_id}\n"
                               "• Успешных сделок: {seller_deals}\n\n"
                               "• Вы покупаете:\n{offer}\n\n"
                               "🏦 Оплатить на:\nUQD-i4anTNudm11nB4E3KHTjY54c7DfngRTAKznSScnqKCPT\n\n"
                               "💰 Сумма: {amount} TON\n"
                               "📝 Комментарий: {deal_id}\n\n"
                               "⚠️ Проверьте данные, мемо обязателен!\nЕсли без мемо, заполните форму — @GemGiftHelper"),
        'deal_info_for_buyer_star': ("💳 Информация о сделке #{deal_id}\n\n"
                               "👤 Вы покупатель в сделке.\n"
                               "📌 Продавец: @{seller_username} | 🆔 {seller_id}\n"
                               "• Успешные сделки: {seller_deals}\n\n"
                               "• Вы покупаете:\n{offer}\n\n"
                               "🏦 Адрес для оплаты:\n@GemGiftHelper\n\n"
                               "💰 Сумма к оплате: {amount} STAR\n"
                               "📝 Комментарий к платежу(мемо): {deal_id}\n\n"
                               "⚠️ Пожалуйста, убедитесь в правильности данных перед оплатой. Комментарий(мемо) обязателен!\n"
                               "В случае если вы отправили транзакцию без комментария заполните форму — @GemGiftHelper"),
        'deal_info_for_buyer_card': ("💳 Информация о сделке #{deal_id}\n\n"
                               "👤 Вы покупатель в сделке.\n"
                               "📌 Продавец: @{seller_username} | 🆔 {seller_id}\n"
                               "• Успешные сделки: {seller_deals}\n\n"
                               "• Вы покупаете:\n{offer}\n\n"
                               "🏦 Адрес для оплаты:\n{card_number}\n\n"
                               "💰 Сумма к оплате: {amount} RUB\n"
                               "📝 Комментарий к платежу(мемо): {deal_id}\n\n"
                               "⚠️ Пожалуйста, убедитесь в правильности данных перед оплатой. Комментарий(мемо) обязателен!\n"
                               "В случае если вы отправили транзакцию без комментария заполните форму — @GemGiftHelper"),
        'payment_confirm_text': "✅ Подтвердить оплату",
        'exit_deal_text': "❌ Выйти из сделки",
        'pay_stars_btn': "💫 Оплатить Stars",
        'exit_confirm_text': "❓ Вы уверены, что хотите покинуть сделку #{deal_id}?",
        'exit_confirm_yes': "✅ Вы покинули сделку #{deal_id}",
        'exit_confirm_no': "⬅️ Нет",
        'deal_not_found': "❌ Сделка #{deal_id} не найдена или уже закрыта.",
        'cannot_buy_own': "❌ Вы не можете купить у самого себя!",
        'buyer_exists': "❌ К этой сделке уже присоединился другой покупатель!",
        'seller_notified': "✅ Продавец получил уведомление об оплате!",
        'no_payment_methods': "❌ Для создания сделки необходимо добавить TON-кошелек или карту!\n\nПерейдите в 'Управление реквизитами' и добавьте платежные данные.",
        'deals_set': "✅ Установлено успешных сделок: {count}",
        'buy_command_usage': "Использование: /buy <ID сделки>\nПример: /buy ABC123XY",
        'set_deals_usage': "Использование: /set_my_deals <число>\nПример: /set_my_deals 100",
        'payment_success': "✅ Оплата успешно проведена! Спасибо за покупку!",
    },
    'en': {
        'welcome': ("Welcome to TESTNAME – reliable P2P guarantor\n\n"
                    "💼 Buy and sell anything – safely!\n"
                    "From Telegram gifts and NFTs to tokens and fiat – deals are easy and risk-free.\n\n"
                    "Choose a section below:"),
        'manage_rekv': "Choose an action:",
        'add_ton_wallet': "🔑 Add your TON wallet:",
        'add_card_number': "💳 Enter your card number (12-19 digits):",
        'ton_invalid': "❌ Invalid TON wallet address",
        'card_invalid': "❌ Invalid card number format. Enter only digits, 12 to 19 characters.",
        'ton_ok': "✅ TON wallet set",
        'card_ok': "✅ Card number saved",
        'back_btn': "⬅️ Back to menu",
        'create_deal_start': ("For Steam skins deals, provide a link to any gift.\n"
                             "After payment, contact the system — @GemGiftHelper\n\n"
                             "💰 Choose payment method:"),
        'choose_pay_method_ton': "💎 TON Wallet",
        'choose_pay_method_star': "⭐ Stars",
        'choose_pay_method_card': "💳 Card",
        'enter_ton_amount': "Enter TON deal amount (e.g.: 199.99):",
        'enter_star_amount': "Enter number of stars for payment (e.g.: 150):",
        'enter_card_amount': "💼 Creating deal\n\nEnter RUB deal amount in format: 199.99",
        'enter_deal_offer': ("📝 Describe what you offer for {amount} {currency}.\n\n"
                            "Example:\nhttps://t.me/nft/PlushPepe-1\nhttps://t.me/nft/DurovsCap-1"),
        'enter_deal_offer_card': ("📝 Specify what you offer in this deal for {amount} RUB\n\n"
                            "Example:\nhttps://t.me/nft/PlushPepe-1\nhttps://t.me/nft/DurovsCap-1"),
        'deal_created': ("✅ Deal created!\n\n"
                         "💰 Amount: {amount} {currency}\n"
                         "📜 Description: {offer}\n"
                         "🔗 Link for buyer:\n{link}"),
        'deal_closed_confirm': "❓ Are you sure you want to close deal #{deal_id}?",
        'deal_closed_yes': "✅ Deal #{deal_id} deleted",
        'lang_change': "Change language:",
        'support_info': "💁‍♂️ Support: @GemGiftHelper",
        'invalid_amount': "❌ Invalid amount format. Try again.",
        'invalid_nft_link': "❌ Only accept links in format https://t.me/nft/… Try again.",
        'deal_joined_notify_seller': "✅ User @{buyer} joined deal #{deal_id}",
        'deal_info_for_buyer_ton': ("💳 Deal info #{deal_id}\n\n"
                               "👤 You are the buyer\n"
                               "📌 Seller: @{seller_username} | 🆔 {seller_id}\n"
                               "• Successful deals: {seller_deals}\n\n"
                               "• You are buying:\n{offer}\n\n"
                               "🏦 Pay to:\nUQD-i4anTNudm11nB4E3KHTjY54c7DfngRTAKznSScnqKCPT\n\n"
                               "💰 Amount: {amount} TON\n"
                               "📝 Comment: {deal_id}\n\n"
                               "⚠️ Check details, memo is required!\nIf without memo, fill form — @GemGiftHelper"),
        'deal_info_for_buyer_star': ("💳 Deal info #{deal_id}\n\n"
                               "👤 You are the buyer in this deal.\n"
                               "📌 Seller: @{seller_username} | 🆔 {seller_id}\n"
                               "• Successful deals: {seller_deals}\n\n"
                               "• You are buying:\n{offer}\n\n"
                               "🏦 Payment address:\n@GemGiftHelper\n\n"
                               "💰 Amount to pay: {amount} STAR\n"
                               "📝 Payment comment(memo): {deal_id}\n\n"
                               "⚠️ Please check the details before payment. Comment(memo) is required!\n"
                               "If you sent transaction without comment, fill the form — @GemGiftHelper"),
        'deal_info_for_buyer_card': ("💳 Deal info #{deal_id}\n\n"
                               "👤 You are the buyer in this deal.\n"
                               "📌 Seller: @{seller_username} | 🆔 {seller_id}\n"
                               "• Successful deals: {seller_deals}\n\n"
                               "• You are buying:\n{offer}\n\n"
                               "🏦 Payment address:\n{card_number}\n\n"
                               "💰 Amount to pay: {amount} RUB\n"
                               "📝 Payment comment(memo): {deal_id}\n\n"
                               "⚠️ Please check the details before payment. Comment(memo) is required!\n"
                               "If you sent transaction without comment, fill the form — @GemGiftHelper"),
        'payment_confirm_text': "✅ Confirm payment",
        'exit_deal_text': "❌ Exit deal",
        'pay_stars_btn': "💫 Pay Stars",
        'exit_confirm_text': "❓ Are you sure you want to leave deal #{deal_id}?",
        'exit_confirm_yes': "✅ You left deal #{deal_id}",
        'exit_confirm_no': "⬅️ No",
        'deal_not_found': "❌ Deal #{deal_id} not found or already closed.",
        'cannot_buy_own': "❌ You cannot buy from yourself!",
        'buyer_exists': "❌ Another buyer already joined this deal!",
        'seller_notified': "✅ Seller received payment notification!",
        'no_payment_methods': "❌ To create a deal, add TON wallet or card!\n\nGo to 'Manage Wallets' and add payment details.",
        'deals_set': "✅ Successful deals set: {count}",
        'buy_command_usage': "Usage: /buy <Deal ID>\nExample: /buy ABC123XY",
        'set_deals_usage': "Usage: /set_my_deals <number>\nExample: /set_my_deals 100",
        'payment_success': "✅ Payment successful! Thank you for your purchase!",
    }
}

def main_menu_keyboard(lang):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📥 " + ("Управление реквизитами" if lang=='ru' else "Manage Wallets"), callback_data="manage_rekv"),
        types.InlineKeyboardButton("📔 " + ("Создать сделку" if lang=='ru' else "Create Deal"), callback_data="create_deal"),
        types.InlineKeyboardButton("🏴 " + ("Сменить язык" if lang=='ru' else "Change Language"), callback_data="change_lang"),
        types.InlineKeyboardButton("💁‍♂️ " + ("Поддержка" if lang=='ru' else "Support"), url="https://t.me/@GemGiftHelper")
    )
    return kb

def rekv_keyboard(lang):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🪙 " + ("Добавить/Изменить TON" if lang=='ru' else "Add/Edit TON Wallet"), callback_data="add_ton"),
        types.InlineKeyboardButton("💳 " + ("Добавить/Изменить карту" if lang=='ru' else "Add/Edit Card"), callback_data="add_card"),
        types.InlineKeyboardButton(MESSAGES[lang]["back_btn"], callback_data="back_to_menu")
    )
    return kb

def pay_method_keyboard(lang):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(MESSAGES[lang]["choose_pay_method_ton"], callback_data="pay_ton"),
        types.InlineKeyboardButton(MESSAGES[lang]["choose_pay_method_star"], callback_data="pay_star")
    )
    kb.add(types.InlineKeyboardButton(MESSAGES[lang]["choose_pay_method_card"], callback_data="pay_card"))
    kb.add(types.InlineKeyboardButton(MESSAGES[lang]["back_btn"], callback_data="back_to_menu"))
    return kb

def deal_close_keyboard(deal_id, lang):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("❌ " + ("Закрыть Сделку" if lang=='ru' else "Close Deal"), callback_data=f"close_{deal_id}"))
    kb.add(types.InlineKeyboardButton(MESSAGES[lang]["back_btn"], callback_data="back_to_menu"))
    return kb

def confirm_exit_keyboard(deal_id, lang):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ " + ("Да, закрыть" if lang=='ru' else "Yes, Close"), callback_data=f"exit_yes_{deal_id}"),
        types.InlineKeyboardButton(MESSAGES[lang]["exit_confirm_no"], callback_data="back_to_menu"),
    )
    return kb

def deal_buyer_keyboard_ton(deal_id, lang):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(MESSAGES[lang]['payment_confirm_text'], callback_data=f"confirm_pay_{deal_id}"),
        types.InlineKeyboardButton(MESSAGES[lang]['exit_deal_text'], callback_data=f"exit_deal_{deal_id}")
    )
    return kb

def deal_buyer_keyboard_star(deal_id, amount, lang):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(MESSAGES[lang]['pay_stars_btn'], callback_data=f"pay_stars_{deal_id}"),
        types.InlineKeyboardButton(MESSAGES[lang]['exit_deal_text'], callback_data=f"exit_deal_{deal_id}")
    )
    return kb

def deal_buyer_keyboard_card(deal_id, lang):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(MESSAGES[lang]['payment_confirm_text'], callback_data=f"confirm_pay_{deal_id}"),
        types.InlineKeyboardButton(MESSAGES[lang]['exit_deal_text'], callback_data=f"exit_deal_{deal_id}")
    )
    return kb

def language_choose_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("Русский", callback_data="lang_ru"),
        types.InlineKeyboardButton("English", callback_data="lang_en"),
        types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")
    )
    return kb

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    clear_user_state(user_id)

    args = message.text.split()
    print(f"📩 Start command from user {user_id}: {message.text}")
    
    if len(args) > 1:
        param = args[1]
        print(f"🔍 Parameter detected: {param}")
        
        if param.startswith("order_ton_"):
            deal_id = param.replace("order_ton_", "").replace('#', '').strip()
            print(f"🔎 Looking for deal: {deal_id}")
            
            deal = get_deal(deal_id)
            
            if not deal:
                print(f"❌ Deal {deal_id} not found in database")
                bot.send_message(user_id, MESSAGES[lang]['deal_not_found'].format(deal_id=deal_id), reply_markup=main_menu_keyboard(lang))
                return
            
            if deal['status'] != 'open':
                print(f"⚠️ Deal {deal_id} has status: {deal['status']}")
                bot.send_message(user_id, MESSAGES[lang]['deal_not_found'].format(deal_id=deal_id), reply_markup=main_menu_keyboard(lang))
                return
            
            if deal['seller_id'] == user_id:
                print(f"⛔ User {user_id} trying to buy own deal")
                bot.send_message(user_id, MESSAGES[lang]['cannot_buy_own'], reply_markup=main_menu_keyboard(lang))
                return
            
            if deal['buyer_id'] and deal['buyer_id'] != user_id:
                print(f"⛔ Deal {deal_id} already has buyer: {deal['buyer_id']}")
                bot.send_message(user_id, MESSAGES[lang]['buyer_exists'], reply_markup=main_menu_keyboard(lang))
                return
            
            set_deal_buyer(deal_id, user_id)
            buyer_username = message.from_user.username or 'unknown'
            
            try:
                bot.send_message(deal['seller_id'], MESSAGES['ru']['deal_joined_notify_seller'].format(buyer=buyer_username, deal_id=deal_id))
                print(f"📧 Seller {deal['seller_id']} notified about buyer")
            except Exception as e:
                print(f"❌ Failed to notify seller: {e}")
            
            seller_deals_count = get_successful_deals_count(deal['seller_id'])
            
            if deal['deal_type'] == 'ton':
                info_text = MESSAGES[lang]['deal_info_for_buyer_ton'].format(
                    deal_id=deal_id,
                    seller_username=deal['seller_username'],
                    seller_id=deal['seller_id'],
                    seller_deals=seller_deals_count,
                    offer=deal['offer'],
                    amount=deal['amount']
                )
                bot.send_message(user_id, info_text, reply_markup=deal_buyer_keyboard_ton(deal_id, lang))
            elif deal['deal_type'] == 'star':
                info_text = MESSAGES[lang]['deal_info_for_buyer_star'].format(
                    deal_id=deal_id,
                    seller_username=deal['seller_username'],
                    seller_id=deal['seller_id'],
                    seller_deals=seller_deals_count,
                    offer=deal['offer'],
                    amount=int(deal['amount'])
                )
                bot.send_message(user_id, info_text, reply_markup=deal_buyer_keyboard_star(deal_id, int(deal['amount']), lang))
            elif deal['deal_type'] == 'card':
                seller_card = get_user_card_number(deal['seller_id'])
                info_text = MESSAGES[lang]['deal_info_for_buyer_card'].format(
                    deal_id=deal_id,
                    seller_username=deal['seller_username'],
                    seller_id=deal['seller_id'],
                    seller_deals=seller_deals_count,
                    offer=deal['offer'],
                    amount=deal['amount'],
                    card_number=seller_card if seller_card else "Не указана"
                )
                bot.send_message(user_id, info_text, reply_markup=deal_buyer_keyboard_card(deal_id, lang))
            
            clear_user_state(user_id)
            return

    bot.send_message(user_id, MESSAGES[lang]['welcome'], reply_markup=main_menu_keyboard(lang))

@bot.message_handler(commands=['buy'])
def handle_buy_command(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(user_id, MESSAGES[lang]['buy_command_usage'])
        return
    
    deal_id = args[1].replace('#', '').strip()
    deal = get_deal(deal_id)
    
    if not deal:
        bot.send_message(user_id, MESSAGES[lang]['deal_not_found'].format(deal_id=deal_id))
        return
    
    if deal['status'] != 'open':
        bot.send_message(user_id, MESSAGES[lang]['deal_not_found'].format(deal_id=deal_id))
        return
    
    if deal['seller_id'] == user_id:
        bot.send_message(user_id, MESSAGES[lang]['cannot_buy_own'])
        return
    
    if deal['buyer_id'] and deal['buyer_id'] != user_id:
        bot.send_message(user_id, MESSAGES[lang]['buyer_exists'])
        return
    
    set_deal_buyer(deal_id, user_id)
    mark_deal_successful(deal_id)
    
    buyer_username = message.from_user.username or 'unknown'
    currency = 'TON' if deal['deal_type']=='ton' else ('STAR' if deal['deal_type']=='star' else 'RUB')
    try:
        bot.send_message(deal['seller_id'], f"✅ Покупатель @{buyer_username} подтвердил оплату по сделке #{deal_id}\n\n💰 Сумма: {deal['amount']} {currency}")
    except Exception as e:
        print(f"Failed to notify seller: {e}")
    
    bot.send_message(user_id, MESSAGES[lang]['payment_success'])

@bot.message_handler(commands=['set_my_deals'])
def handle_set_deals_command(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(user_id, MESSAGES[lang]['set_deals_usage'])
        return
    
    try:
        count = int(args[1])
        if count < 0:
            raise ValueError
        set_user_successful_deals(user_id, count)
        bot.send_message(user_id, MESSAGES[lang]['deals_set'].format(count=count))
    except ValueError:
        bot.send_message(user_id, MESSAGES[lang]['set_deals_usage'])

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    lang = get_user_lang(user_id)
    data = call.data

    if data == "manage_rekv":
        bot.edit_message_text(MESSAGES[lang]['manage_rekv'], user_id, call.message.message_id, reply_markup=rekv_keyboard(lang))

    elif data == "add_ton":
        ton = get_user_ton_wallet(user_id)
        text = MESSAGES[lang]['add_ton_wallet']
        if ton:
            text += f"\n\n{MESSAGES[lang]['ton_ok']}: `{ton}`"
        set_user_state(user_id, 'waiting_ton_wallet')
        bot.edit_message_text(text, user_id, call.message.message_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton(MESSAGES[lang]['back_btn'], callback_data="back_to_menu")),
                              parse_mode="Markdown")

    elif data == "add_card":
        card = get_user_card_number(user_id)
        text = MESSAGES[lang]['add_card_number']
        if card:
            text += f"\n\n{MESSAGES[lang]['card_ok']}: `{card}`"
        set_user_state(user_id, 'waiting_card_number')
        bot.edit_message_text(text, user_id, call.message.message_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton(MESSAGES[lang]['back_btn'], callback_data="back_to_menu")),
                              parse_mode="Markdown")

    elif data == "back_to_menu":
        clear_user_state(user_id)
        bot.edit_message_text(MESSAGES[lang]['welcome'], user_id, call.message.message_id, reply_markup=main_menu_keyboard(lang))

    elif data == "create_deal":
        if not has_payment_methods(user_id):
            bot.answer_callback_query(call.id, MESSAGES[lang]['no_payment_methods'], show_alert=True)
            return
        set_user_state(user_id, 'waiting_pay_method')
        bot.edit_message_text(MESSAGES[lang]['create_deal_start'], user_id, call.message.message_id, reply_markup=pay_method_keyboard(lang))

    elif data == "pay_ton":
        set_user_state(user_id, 'waiting_ton_amount')
        bot.edit_message_text(MESSAGES[lang]['enter_ton_amount'], user_id, call.message.message_id)

    elif data == "pay_star":
        set_user_state(user_id, 'waiting_star_amount')
        bot.edit_message_text(MESSAGES[lang]['enter_star_amount'], user_id, call.message.message_id)

    elif data == "pay_card":
        set_user_state(user_id, 'waiting_card_amount')
        bot.edit_message_text(MESSAGES[lang]['enter_card_amount'], user_id, call.message.message_id)

    elif data.startswith("close_"):
        deal_id = data[6:]
        bot.edit_message_text(MESSAGES[lang]['deal_closed_confirm'].format(deal_id=deal_id), user_id, call.message.message_id, reply_markup=confirm_exit_keyboard(deal_id, lang))

    elif data.startswith("exit_yes_"):
        deal_id = data[9:]
        close_deal(deal_id)
        bot.edit_message_text(MESSAGES[lang]['deal_closed_yes'].format(deal_id=deal_id), user_id, call.message.message_id)
        bot.send_message(user_id, MESSAGES[lang]['welcome'], reply_markup=main_menu_keyboard(lang))
        clear_user_state(user_id)

    elif data.startswith("confirm_pay_"):
        deal_id = data[12:]
        deal = get_deal(deal_id)
        if deal and deal['buyer_id'] == user_id:
            mark_deal_successful(deal_id)
            bot.answer_callback_query(call.id, MESSAGES[lang]['seller_notified'])
            currency = 'TON' if deal['deal_type']=='ton' else ('STAR' if deal['deal_type']=='star' else 'RUB')
            try:
                bot.send_message(deal['seller_id'], f"✅ Покупатель @{call.from_user.username or 'unknown'} подтвердил оплату по сделке #{deal_id}\n\n💰 Сумма: {deal['amount']} {currency}")
            except Exception as e:
                print(f"Failed to notify seller: {e}")
        else:
            bot.answer_callback_query(call.id, "Ошибка: сделка не найдена или вы не покупатель.", show_alert=True)

    elif data.startswith("pay_stars_"):
        deal_id = data[10:]
        deal = get_deal(deal_id)
        if deal and deal['buyer_id'] == user_id:
            amount = int(deal['amount'])
            prices = [types.LabeledPrice(label="XTR", amount=amount)]
            
            try:
                bot.send_invoice(
                    user_id,
                    title=f"Оплата сделки #{deal_id}",
                    description=f"Оплата {amount} Stars за: {deal['offer'][:50]}...",
                    invoice_payload=f"deal_{deal_id}",
                    provider_token="",
                    currency="XTR",
                    prices=prices
                )
            except Exception as e:
                print(f"Failed to send invoice: {e}")
                bot.answer_callback_query(call.id, "Ошибка отправки инвойса", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "Ошибка: сделка не найдена", show_alert=True)

    elif data.startswith("exit_deal_"):
        deal_id = data[10:]
        bot.edit_message_text(MESSAGES[lang]['exit_confirm_text'].format(deal_id=deal_id), user_id, call.message.message_id, reply_markup=confirm_exit_keyboard(deal_id, lang))

    elif data == "change_lang":
        bot.edit_message_text(MESSAGES[lang]['lang_change'], user_id, call.message.message_id, reply_markup=language_choose_keyboard())

    elif data in ["lang_ru", "lang_en"]:
        selected = data.split("_")[1]
        set_user_lang(user_id, selected)
        clear_user_state(user_id)
        bot.edit_message_text(MESSAGES[selected]['welcome'], user_id, call.message.message_id, reply_markup=main_menu_keyboard(selected))
        bot.answer_callback_query(call.id, f"Язык изменен на {'Русский' if selected=='ru' else 'English'}")

@bot.pre_checkout_query_handler(func=lambda query: True)
def handle_pre_checkout_query(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    
    payload = message.successful_payment.invoice_payload
    if payload.startswith("deal_"):
        deal_id = payload.replace("deal_", "")
        deal = get_deal(deal_id)
        
        if deal:
            mark_deal_successful(deal_id)
            bot.send_message(user_id, MESSAGES[lang]['payment_success'])
            
            try:
                bot.send_message(deal['seller_id'], f"✅ Покупатель @{message.from_user.username or 'unknown'} оплатил сделку #{deal_id} через Telegram Stars\n\n💰 Сумма: {deal['amount']} STAR")
            except Exception as e:
                print(f"Failed to notify seller: {e}")

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_ton_wallet')
def ton_wallet_handler(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    addr = message.text.strip()
    if validate_ton_address(addr):
        set_user_ton_wallet(user_id, addr)
        clear_user_state(user_id)
        bot.send_message(user_id, MESSAGES[lang]['ton_ok'], reply_markup=rekv_keyboard(lang))
    else:
        bot.send_message(user_id, MESSAGES[lang]['ton_invalid'])

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_card_number')
def card_number_handler(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    card = message.text.strip()
    if validate_card_number(card):
        set_user_card_number(user_id, card)
        clear_user_state(user_id)
        bot.send_message(user_id, MESSAGES[lang]['card_ok'], reply_markup=rekv_keyboard(lang))
    else:
        bot.send_message(user_id, MESSAGES[lang]['card_invalid'])

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_ton_amount')
def ton_amount_handler(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except:
        bot.send_message(user_id, MESSAGES[lang]['invalid_amount'])
        return
    set_user_input(user_id, 'deal_amount', amount)
    set_user_input(user_id, 'deal_type', 'ton')
    set_user_state(user_id, 'waiting_deal_offer')
    bot.send_message(user_id, MESSAGES[lang]['enter_deal_offer'].format(amount=amount, currency="TON"))

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_star_amount')
def star_amount_handler(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except:
        bot.send_message(user_id, MESSAGES[lang]['invalid_amount'])
        return
    set_user_input(user_id, 'deal_amount', amount)
    set_user_input(user_id, 'deal_type', 'star')
    set_user_state(user_id, 'waiting_deal_offer')
    bot.send_message(user_id, MESSAGES[lang]['enter_deal_offer'].format(amount=amount, currency="STAR"))

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_card_amount')
def card_amount_handler(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except:
        bot.send_message(user_id, MESSAGES[lang]['invalid_amount'])
        return
    set_user_input(user_id, 'deal_amount', amount)
    set_user_input(user_id, 'deal_type', 'card')
    set_user_state(user_id, 'waiting_deal_offer')
    bot.send_message(user_id, MESSAGES[lang]['enter_deal_offer_card'].format(amount=amount))

@bot.message_handler(func=lambda m: get_user_state(m.from_user.id) == 'waiting_deal_offer')
def deal_offer_handler(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    offer = message.text.strip()
    deal_type = get_user_input(user_id, 'deal_type')
    
    if not validate_nft_link(offer):
        bot.send_message(user_id, MESSAGES[lang]['invalid_nft_link'])
        return
    
    amount = get_user_input(user_id, 'deal_amount')
    deal_id = generate_deal_id()
    
    create_deal(deal_id, user_id, message.from_user.username or "unknown", amount, offer, deal_type)
    
    buyer_link = f"https://t.me/testtonnisbot?start=order_ton_{deal_id}"
    currency = "TON" if deal_type == 'ton' else ("STAR" if deal_type == 'star' else "RUB")
    
    bot.send_message(user_id, MESSAGES[lang]['deal_created'].format(
        amount=amount, 
        offer=offer, 
        link=buyer_link, 
        currency=currency
    ), reply_markup=deal_close_keyboard(deal_id, lang))
    
    clear_user_state(user_id)

if __name__ == '__main__':
    print("🤖 Bot started...")
    bot.infinity_polling()
