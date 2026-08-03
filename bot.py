# -*- coding: utf-8 -*-
import sqlite3
import requests
import telebot
import time
import os
import re
from threading import Thread
from flask import Flask, request, jsonify
from telebot import types

# ----------------- আপনার বোটের মূল সেটিংস -----------------
BOT_TOKEN = "8899197686:AAGq1I806XgwIzNjdyQada9HykdyGciBO8g"
SMMSUN_API_URL = "https://socialpanel.pro/api/v2"
SMMSUN_API_KEY = "14f3163c337f51c7c90c6232d9428bc2"
ADMIN_ID = 6851638362 

USD_TO_BDT = 120.0     # ১ ডলার = ১২০ টাকা
# --------------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "users.db")

# ----------------- ডাটাবেজ সেটআপ -----------------
def init_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            chat_id INTEGER,
            service_name TEXT,
            quantity INTEGER,
            cost REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            method TEXT,
            amount REAL,
            txid TEXT,
            status TEXT DEFAULT 'Pending'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auto_transactions (
            txid TEXT PRIMARY KEY,
            amount REAL,
            method TEXT,
            status TEXT DEFAULT 'Unclaimed'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            category TEXT,
            id_bot TEXT,
            api_id TEXT,
            name TEXT,
            price_per_1k REAL DEFAULT 0.0,
            PRIMARY KEY (category, id_bot)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('profit_margin', '1.10')")
    conn.commit()
    conn.close()

def get_profit_margin():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'profit_margin'")
    row = cursor.fetchone()
    conn.close()
    return float(row[0]) if row else 1.10

def set_profit_margin(margin_value):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('profit_margin', ?)", (str(margin_value),))
    conn.commit()
    conn.close()

def add_user(chat_id):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (chat_id, balance) VALUES (?, ?)", (chat_id, 0.0))
    conn.commit()
    conn.close()

def get_balance(chat_id):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0.0

def update_balance(chat_id, new_balance):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (chat_id, balance) VALUES (?, 0.0)", (chat_id,))
    cursor.execute("UPDATE users SET balance = ? WHERE chat_id = ?", (new_balance, chat_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, balance FROM users")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_stats(chat_id):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM orders WHERE chat_id = ?", (chat_id,))
    total_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM payments WHERE chat_id = ? AND status = 'Approved'", (chat_id,))
    total_payments = cursor.fetchone()[0]
    conn.close()
    return total_orders, total_payments

def add_order_to_db(order_id, chat_id, service_name, quantity, cost):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO orders (order_id, chat_id, service_name, quantity, cost) VALUES (?, ?, ?, ?, ?)",
                   (order_id, chat_id, service_name, quantity, cost))
    conn.commit()
    conn.close()

def get_user_orders(chat_id):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT order_id, service_name, quantity, cost FROM orders WHERE chat_id = ? ORDER BY id DESC LIMIT 5", (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_payment_to_db(chat_id, method, amount, txid, status='Approved'):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO payments (chat_id, method, amount, txid, status) VALUES (?, ?, ?, ?, ?)",
                   (chat_id, method, amount, txid, status))
    conn.commit()
    conn.close()

def save_auto_sms_trx(txid, amount, method):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO auto_transactions (txid, amount, method, status) VALUES (?, ?, ?, 'Unclaimed')",
                   (txid, amount, method))
    conn.commit()
    conn.close()

def claim_auto_trx(txid):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT amount, method, status FROM auto_transactions WHERE txid = ?", (txid,))
    row = cursor.fetchone()
    if row and row[2] == 'Unclaimed':
        cursor.execute("UPDATE auto_transactions SET status = 'Claimed' WHERE txid = ?", (txid,))
        conn.commit()
        conn.close()
        return float(row[0]), row[1]
    conn.close()
    return None, None

def get_user_payments(chat_id):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT method, amount, txid, status FROM payments WHERE chat_id = ? ORDER BY id DESC LIMIT 10", (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_services_by_category(category):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT id_bot, api_id, name, price_per_1k FROM services WHERE category = ?", (category,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "api_id": r[1], "name": r[2], "price_per_1k": float(r[3]) if r[3] is not None else 0.0} for r in rows]

init_db()

# ----------------- 📱 RENDER WEBHOOK SERVER -----------------
@app.route('/')
def home():
    return "SMM Bot Server is Alive and 24/7 Running!", 200

@app.route('/sms-webhook', methods=['POST', 'GET'])
def sms_webhook():
    try:
        data = request.form if request.form else (request.json if request.json else request.args)
        sms_text = data.get('text', '') or data.get('message', '') or data.get('msg', '') or str(data)

        if "bKash" in sms_text or "TrxID" in sms_text:
            trx_match = re.search(r'TrxID\s+([A-Za-z0-9]+)', sms_text, re.IGNORECASE)
            amt_match = re.search(r'Tk\s+([0-9,.]+)', sms_text, re.IGNORECASE)
            if trx_match and amt_match:
                txid = trx_match.group(1).strip()
                amount = float(amt_match.group(1).replace(',', ''))
                save_auto_sms_trx(txid, amount, "bKash")

        elif "Nagad" in sms_text or "TxnID" in sms_text:
            trx_match = re.search(r'TxnID:\s*([A-Za-z0-9]+)', sms_text, re.IGNORECASE)
            amt_match = re.search(r'Amount:\s*Tk\s*([0-9,.]+)', sms_text, re.IGNORECASE)
            if trx_match and amt_match:
                txid = trx_match.group(1).strip()
                amount = float(amt_match.group(1).replace(',', ''))
                save_auto_sms_trx(txid, amount, "Nagad")

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# ----------------- সার্ভিস ও স্ট্যাটাস -----------------
def get_multiple_orders_status(order_ids):
    if not order_ids:
        return {}
    try:
        payload = {
            "key": SMMSUN_API_KEY,
            "action": "status",
            "orders": ",".join(map(str, order_ids))
        }
        response = requests.post(SMMSUN_API_URL, data=payload, timeout=3)
        res = response.json()
        return res if isinstance(res, dict) else {}
    except Exception:
        return {}

def fetch_api_services():
    try:
        payload = {"key": SMMSUN_API_KEY, "action": "services"}
        response = requests.post(SMMSUN_API_URL, data=payload, timeout=3)
        res = response.json()
        return res if isinstance(res, list) else []
    except Exception:
        return []

# ================== 👑 এডমিন প্যানেল (/admin) ==================

@bot.message_handler(commands=["admin"])
def admin_panel_command(message):
    if message.chat.id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("➕ সার্ভিস অ্যাড", callback_data="admin_add_service_start")
    btn2 = types.InlineKeyboardButton("🔍 ইউজার ইনফো ও ব্যালেন্স", callback_data="admin_user_info_start")
    btn3 = types.InlineKeyboardButton("📈 প্রফিট সেট", callback_data="admin_set_profit_start")
    btn4 = types.InlineKeyboardButton("👥 সকল ইউজার লিস্ট", callback_data="admin_users_list")
    btn5 = types.InlineKeyboardButton("🗑️ সার্ভিস ডিলিট", callback_data="admin_clear_services_confirm")
    
    markup.add(btn1, btn2, btn3, btn4, btn5)

    bot.send_message(
        ADMIN_ID,
        "👑 <b>এডমিন কন্ট্রোল প্যানেল</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "নিচের বাটন চেপে যেকোনো কাজ সিলেক্ট করুন:",
        reply_markup=markup,
        parse_mode="HTML"
    )

# ---------------- 1. ফিক্সড ক্যাটাগরিতে সার্ভিস যোগ ----------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_service_start")
def admin_add_service_start(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🎵 TikTok View", callback_data="admcat_tiktok_view")
    btn2 = types.InlineKeyboardButton("❤️ TikTok Like", callback_data="admcat_tiktok_like")
    btn3 = types.InlineKeyboardButton("👥 TikTok Follower", callback_data="admcat_tiktok_follower")
    btn4 = types.InlineKeyboardButton("👁️ Telegram View", callback_data="admcat_telegram_view")
    btn5 = types.InlineKeyboardButton("📢 Telegram Member", callback_data="admcat_telegram_member")
    btn6 = types.InlineKeyboardButton("🔥 Telegram React + View", callback_data="admcat_telegram_react")
    btn7 = types.InlineKeyboardButton("🎬 FB Video View", callback_data="admcat_facebook_video_view")
    btn8 = types.InlineKeyboardButton("👍 FB Page Like", callback_data="admcat_facebook_like")
    btn9 = types.InlineKeyboardButton("👤 FB Followers", callback_data="admcat_facebook_follower")
    btn10 = types.InlineKeyboardButton("▶️ YouTube View", callback_data="admcat_youtube_view")
    btn11 = types.InlineKeyboardButton("📸 Instagram All", callback_data="admcat_instagram")

    markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11)
    bot.send_message(ADMIN_ID, "📁 <b>কোন ক্যাটাগরিতে সার্ভিসটি যোগ করতে চান? সিলেক্ট করুন:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcat_"))
def admin_step_get_choice_id(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)

    category = call.data.replace("admcat_", "")
    msg = bot.send_message(ADMIN_ID, "🆔 <b>কাস্টমার চয়েস ID কত দেবেন?</b> (যেমন: 1, 2, 3 লিখে পাঠান):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_api_id, category)

def admin_step_get_api_id(message, category):
    id_bot = message.text.strip()
    msg = bot.send_message(ADMIN_ID, f"🔌 সোশ্যাল প্যানেল ওয়েবসাইটের <b>আসল API ID</b> টি কত? (যেমন: 19138):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_usd_cost, category, id_bot)

def admin_step_get_usd_cost(message, category, id_bot):
    api_id = message.text.strip()
    msg = bot.send_message(ADMIN_ID, "💵 ওয়েবসাইটের <b>ডলার প্রাইজ (USD Cost)</b> কত? (যেমন: 0.0725 লিখে পাঠান):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_name, category, id_bot, api_id)

def admin_step_get_name(message, category, id_bot, api_id):
    try:
        usd_cost = float(message.text.strip())
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ ভুল ডলার দাম! আবার /admin থেকে চেষ্টা করুন।")
        return

    msg = bot.send_message(ADMIN_ID, "📌 <b>সার্ভিসটির সুন্দর একটি নাম লিখে পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_save_service, category, id_bot, api_id, usd_cost)

def admin_step_save_service(message, category, id_bot, api_id, usd_cost):
    name = message.text.strip()
    price_per_1k = usd_cost * USD_TO_BDT

    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO services (category, id_bot, api_id, name, price_per_1k) VALUES (?, ?, ?, ?, ?)",
                   (category, id_bot, api_id, name, price_per_1k))
    conn.commit()
    conn.close()

    margin = get_profit_margin()
    display_price = price_per_1k * margin

    bot.send_message(
        ADMIN_ID,
        f"✅ <b>সার্ভিসটি সফলভাবে যুক্ত করা হয়েছে!</b>\n\n"
        f"📁 <b>ক্যাটাগরি:</b> <code>{category}</code>\n"
        f"🆔 <b>চয়েস ID:</b> <b>{id_bot}</b> | 🔌 <b>API ID:</b> <b>{api_id}</b>\n"
        f"💰 <b>কাস্টমার প্রাইস (১০০০টি):</b> <b>{display_price:.2f} BDT</b>\n"
        f"📌 <b>নাম:</b> <b>{name}</b>",
        parse_mode="HTML"
    )

# ---------------- 2. ইউজার ইনফো দেখা ও ব্যালেন্স এডিট ----------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_user_info_start")
def admin_user_info_start(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(ADMIN_ID, "🔍 <b>ইউজারের তথ্য দেখতে বা ব্যালেন্স এডিট করতে ইউজার ID লিখে পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_process_user_lookup)

def admin_process_user_lookup(message):
    try:
        target_user = int(message.text.strip())
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ ভুল ইনপুট! ইউজার আইডি শুধুমাত্র সংখ্যা হয়।")
        return

    balance = get_balance(target_user)
    total_orders, total_payments = get_user_stats(target_user)

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("➕ ব্যালেন্স যোগ করুন", callback_data=f"admbal_ADD_{target_user}")
    btn2 = types.InlineKeyboardButton("✏️ ব্যালেন্স সেট/এডিট", callback_data=f"admbal_SET_{target_user}")
    markup.add(btn1, btn2)

    info_text = (
        f"👤 <b>ইউজার অ্যাকাউন্ট ইনফরমেশন</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ইউজার ID:</b> <code>{target_user}</code>\n"
        f"💰 <b>বর্তমান ব্যালেন্স:</b> <b>{balance:.2f} BDT</b>\n"
        f"🛒 <b>মোট সম্পন্ন অর্ডার:</b> <b>{total_orders} টি</b>\n"
        f"💳 <b>মোট সফল ডিপোজিট:</b> <b>{total_payments} টি</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 ব্যালেন্স চেঞ্জ করতে নিচের বাটন ব্যবহার করুন:"
    )
    bot.send_message(ADMIN_ID, info_text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admbal_"))
def admin_process_balance_action(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    
    action_data = call.data.replace("admbal_", "")
    action, target_user = action_data.split("_")
    target_user = int(target_user)

    if action == "ADD":
        msg = bot.send_message(ADMIN_ID, f"💵 ইউজার <code>{target_user}</code> এর সাথে <b>কত টাকা (BDT) যোগ করবেন?</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, admin_save_add_balance, target_user)
    elif action == "SET":
        msg = bot.send_message(ADMIN_ID, f"✏️ ইউজার <code>{target_user}</code> এর <b>নতুন ব্যালেন্স কত টাকা সেট করবেন?</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, admin_save_set_balance, target_user)

def admin_save_add_balance(message, target_user):
    try:
        amount = float(message.text.strip())
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ ভুল ইনপুট!")
        return

    current_bal = get_balance(target_user)
    new_balance = current_bal + amount
    update_balance(target_user, new_balance)

    bot.send_message(ADMIN_ID, f"✅ ইউজার <code>{target_user}</code> এর অ্যাকাউন্টে <b>{amount:.2f} BDT</b> যোগ হয়েছে। নতুন ব্যালেন্স: <b>{new_balance:.2f} BDT</b>", parse_mode="HTML")

    try:
        bot.send_message(
            target_user,
            f"🎉 <b>আপনার অ্যাকাউন্টে ব্যালেন্স যোগ করা হয়েছে!</b>\n\n"
            f"💳 <b>যোগকৃত টাকা:</b> <b>{amount:.2f} BDT</b>\n"
            f"💰 <b>বর্তমান মোট ব্যালেন্স:</b> <b>{new_balance:.2f} BDT</b> ✅",
            parse_mode="HTML"
        )
    except Exception:
        pass

def admin_save_set_balance(message, target_user):
    try:
        new_balance = float(message.text.strip())
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ ভুল ইনপুট!")
        return

    update_balance(target_user, new_balance)
    bot.send_message(ADMIN_ID, f"✅ ইউজার <code>{target_user}</code> এর ব্যালেন্স সফলভাবে <b>{new_balance:.2f} BDT</b> সেট করা হয়েছে।", parse_mode="HTML")

    try:
        bot.send_message(
            target_user,
            f"📢 <b>আপনার অ্যাকাউন্ট ব্যালেন্স আপডেট করা হয়েছে!</b>\n\n"
            f"💰 <b>বর্তমান মোট ব্যালেন্স:</b> <b>{new_balance:.2f} BDT</b> ✅",
            parse_mode="HTML"
        )
    except Exception:
        pass

# ---------------- 3. প্রফিট সেট ও ইউজার লিস্ট ----------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_set_profit_start")
def admin_set_profit_start(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(ADMIN_ID, "📈 <b>শতকরা কত % লাভ রাখতে চান?</b>\n(যেমন: 15 বা 20 লিখে পাঠান):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_profit_save)

def admin_step_profit_save(message):
    try:
        percentage = float(message.text.strip())
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ ভুল পার্সেন্টেজ!")
        return

    margin_value = 1.0 + (percentage / 100.0)
    set_profit_margin(margin_value)
    bot.send_message(ADMIN_ID, f"📈 <b>গ্লোবাল প্রফিট মার্জিন সফলভাবে {percentage}% সেট করা হয়েছে!</b> ✅", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_users_list")
def admin_users_list_callback(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    all_users = get_all_users()
    response = "👥 <b>বোটের সকল ইউজারের তালিকা:</b>\n\n"
    for u in all_users:
        response += f"👤 <b>ID:</b> <code>{u[0]}</code> | <b>ব্যালেন্স:</b> <b>{u[1]:.2f} BDT</b>\n"
    bot.send_message(ADMIN_ID, response, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_clear_services_confirm")
def admin_clear_services_callback(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    try:
        conn = sqlite3.connect(DB_FILE, timeout=30)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM services")
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, "🗑️ <b>সকল পুরাতন সার্ভিস ডিলিট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Error: {str(e)}")

# ===================================================

def get_main_menu_markup(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("🛒 নতুন অর্ডার")
    btn2 = types.KeyboardButton("👤 আমার অ্যাকাউন্ট")
    btn3 = types.KeyboardButton("📜 অর্ডার হিস্ট্রি")
    btn4 = types.KeyboardButton("📊 পেমেন্ট হিস্ট্রি")
    btn5 = types.KeyboardButton("💳 ব্যালেন্স অ্যাড")
    btn6 = types.KeyboardButton("📞 সাপোর্ট")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    return markup

@bot.message_handler(commands=["start"])
def start_command(message):
    chat_id = message.chat.id
    add_user(chat_id)
    bot.send_message(chat_id, "⚙️ Loading...", reply_markup=get_main_menu_markup(chat_id))
    send_main_menu(chat_id, message.from_user.first_name)

def send_main_menu(chat_id, first_name):
    safe_name = "ইউজার" if not first_name else first_name.replace("<", "&lt;").replace(">", "&gt;")

    welcome_text = (
        f"⚡✅<b>আমাদের প্রিমিয়াম SMM বোটে স্বাগতম!</b> 🥰\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"হ্যালো <b>{safe_name}</b>, আশা করি ভালো আছেন! আমাদের বোটে আপনাকে আন্তরিক অভিনন্দন। এখানে আপনি বাজারের সেরা ও দ্রুততম সোশ্যাল মিডিয়া সার্ভিসগুলো পাবেন। 🚀\n\n"
        f"🛒 <b>অর্ডার শুরু করতে নিচের বাটনগুলো ব্যবহার করুন!</b> 👇"
    )
    bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

@bot.message_handler(func=lambda message: True)
def handle_menu_buttons(message):
    chat_id = message.chat.id
    text = message.text

    if text == "👤 আমার অ্যাকাউন্ট":
        balance = get_balance(chat_id)
        account_text = (
            f"┏━━━━━━━━━━━━━━━━━━┓\n"
            f"   👤 <b>আমার অ্যাকাউন্ট ড্যাশবোর্ড</b> 👤\n"
            f"┗━━━━━━━━━━━━━━━━━━┛\n\n"
            f"🆔 আপনার ইউজার আইডি : <code>{chat_id}</code>\n"
            f"💰 বর্তমান ব্যালেন্স : <b>{balance:.2f} BDT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(chat_id, account_text, parse_mode="HTML")

    elif text == "🛒 নতুন অর্ডার":
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("📱 TikTok View", callback_data="cat_tiktok_view")
        btn2 = types.InlineKeyboardButton("📱 TikTok Like", callback_data="cat_tiktok_like")
        btn3 = types.InlineKeyboardButton("📱 TikTok Followers", callback_data="cat_tiktok_follower")
        btn4 = types.InlineKeyboardButton("📢 Telegram View", callback_data="cat_telegram_view")
        btn5 = types.InlineKeyboardButton("📢 Telegram Member", callback_data="cat_telegram_member")
        btn6 = types.InlineKeyboardButton("📢 Telegram React + View", callback_data="cat_telegram_react")
        btn7 = types.InlineKeyboardButton("👥 Facebook Video View", callback_data="cat_facebook_video_view")
        btn8 = types.InlineKeyboardButton("👥 Facebook Like", callback_data="cat_facebook_like")
        btn9 = types.InlineKeyboardButton("👥 Facebook Followers", callback_data="cat_facebook_follower")
        btn10 = types.InlineKeyboardButton("❤️ YouTube View", callback_data="cat_youtube_view")
        btn11 = types.InlineKeyboardButton("📸 Instagram Service", callback_data="cat_instagram")
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11)

        bot.send_message(chat_id, "💸 <b>আমাদের সার্ভিস ক্যাটাগরি নির্বাচন করুন:</b>", reply_markup=markup, parse_mode="HTML")

    elif text == "💳 ব্যালেন্স অ্যাড":
        deposit_text = (
            "💎 <b>অটোমেটেড ব্যালেন্স অ্যাড (Instant)</b> 💎\n"
            "💸𝗦𝗘𝗡𝗗 𝗠𝗢𝗡𝗘𝗬⚡💸\n\n"
            "╔══════════════════════╗\n"
            "💳 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗜𝗡𝗦𝗧𝗥𝗨𝗖𝗧𝗜𝗢𝗡 💳\n"
            "╚══════════════════════╝\n\n"
            "🆔 <b>বিকাশ (পার্সোনাল)</b>\n"
            "<code>01925263571</code>\n\n"
            "💸🆔 <b>নগদ পার্সোনাল</b>\n"
            "<code>01925263571</code>\n\n"
            "📲 <b>Send Money করার পর নিচে শুধুমাত্র TrxID দিলেই ১ সেকেন্ডে অটো ব্যালেন্স যোগ হবে!</b>\n\n"
            "👇 <b>নিচের বাটনে ক্লিক করে টাকা এড করুন:</b>"
        )
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("⚡ অটো পেমেন্ট ট্রানজেকশন আইডি দিন ✅", callback_data="verify_auto_trx_start")
        markup.add(btn)
        bot.send_message(chat_id, deposit_text, reply_markup=markup, parse_mode="HTML")

    elif text == "📜 অর্ডার হিস্ট্রি":
        msg_loading = bot.send_message(chat_id, "⏳ <b>লাইভ অর্ডার স্ট্যাটাস লোড হচ্ছে...</b>", parse_mode="HTML")
        orders = get_user_orders(chat_id)
        if not orders:
            bot.edit_message_text("📭 <b>আপনি এখনো কোনো অর্ডার করেননি।</b>", chat_id=chat_id, message_id=msg_loading.message_id, parse_mode="HTML")
            return

        order_ids = [o[0] for o in orders]
        statuses = get_multiple_orders_status(order_ids)

        response = "📋 <b>আপনার সর্বশেষ ৫টি অর্ডার এবং লাইভ স্ট্যাটাস:</b>\n\n"
        for idx, o in enumerate(orders, 1):
            o_id = str(o[0])
            st = statuses.get(o_id, {}).get("status", "Processing") if isinstance(statuses, dict) else "Processing"
            response += (
                f"<b>{idx}. {o[1]}</b>\n"
                f"🆔 অর্ডার আইডি: <code>{o[0]}</code>\n"
                f"🔢 কোয়ান্টিটি: <b>{o[2]}</b> | 💵 খরচ: <b>{o[3]:.2f} BDT</b>\n"
                f"🚦 লাইভ স্ট্যাটাস: <b>{st}</b>\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            )
        bot.edit_message_text(response, chat_id=chat_id, message_id=msg_loading.message_id, parse_mode="HTML")

    elif text == "📊 পেমেন্ট হিস্ট্রি":
        payments = get_user_payments(chat_id)
        if not payments:
            bot.send_message(chat_id, "📭  আপনার কোনো পেমেন্ট রেকর্ড নেই।")
            return

        response = "📊 <b>আপনার সর্বশেষ ১০টি পেমেন্ট রিকোয়েস্ট:</b>\n\n"
        for idx, p in enumerate(payments, 1):
            status_icon = "⏳" if p[3] == "Pending" else "✅"
            response += (
                f"<b>{idx}. {p[0]} ডিপোজিট</b>\n"
                f"💵 পরিমাণ: <b>{p[1]:.2f} BDT</b> | 🆔 TxID: <code>{p[2]}</code>\n"
                f"🚦 স্ট্যাটাস: {status_icon} <b>{p[3]}</b>\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            )
        bot.send_message(chat_id, response, parse_mode="HTML")

    elif text == "📞 সাপোর্ট":
        support_text = (
            "┏━━━━━━━━━━━━━━━━━━┓\n"
            "       📞   <b>এডমিন সাপোর্ট</b>   📞\n"
            "┗━━━━━━━━━━━━━━━━━━┛\n\n"
            "💬  টেলিগ্রাম এডমিন: @Mr_Sojol_Ceo\n"
            "📱 হোয়াটসঅ্যাপ: +8801925263571\n\n"
            "পেমেন্ট এড করা বা অর্ডার সংক্রান্ত যেকোনো সমস্যার জন্য সরাসরি এডমিনের সাথে যোগাযোগ করুন।"
        )
        bot.send_message(chat_id, support_text, parse_mode="HTML")

# ----------------- 💳 ডিপোজিট ভেরিফাই -----------------
@bot.callback_query_handler(func=lambda call: call.data == "verify_auto_trx_start")
def start_auto_trx_input(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💵 <b>আপনি কত টাকা (BDT) এড করতে চান? পরিমাণ লিখে পাঠান:</b>\n(যেমন: 50, 100 বা 500)", parse_mode="HTML")
    bot.register_next_step_handler(msg, get_intended_deposit_amount)

def get_intended_deposit_amount(message):
    chat_id = message.chat.id
    amount_str = message.text.strip()

    if not amount_str.replace('.', '', 1).isdigit():
        bot.send_message(chat_id, "❌ <b>ভুল ইনপুট! শুধু টাকার পরিমাণ লিখে পাঠান:</b>", parse_mode="HTML")
        return

    intended_amount = float(amount_str)
    
    msg_text = (
        f"👍 <b>অনুরোধ গৃহীত হয়েছে!</b>\n\n"
        f"💰 <b>আপনার ডিপোজিট পরিমাণ:</b> <b>{intended_amount:.2f} BDT</b>\n\n"
        f"👉 আমাদের বিকাশ/নগদ পার্সোনাল নাম্বারে <b>{intended_amount:.2f} BDT</b> Send Money করার পর পেমেন্টের <b>TrxID (ট্রানজেকশন আইডি)</b> টি এখানে পেস্ট করুন:"
    )
    msg = bot.send_message(chat_id, msg_text, parse_mode="HTML")
    bot.register_next_step_handler(msg, process_auto_trx_claim)

def process_auto_trx_claim(message):
    chat_id = message.chat.id
    user_txid = message.text.strip()

    amount, method = claim_auto_trx(user_txid)

    if amount and method:
        current_bal = get_balance(chat_id)
        new_balance = current_bal + amount
        update_balance(chat_id, new_balance)
        add_payment_to_db(chat_id, method, amount, user_txid, status='Approved')

        bot.send_message(
            chat_id,
            f"✅ <b>পেমেন্ট সফলভাবে ভেরিফাই হয়েছে!</b>\n\n"
            f"💳 <b>মেথড:</b> {method}\n"
            f"💵 <b>প্রাপ্ত টাকা:</b> <b>{amount:.2f} BDT</b>\n"
            f"💰 <b>বর্তমান মোট ব্যালেন্স:</b> <b>{new_balance:.2f} BDT</b> 🎉",
            parse_mode="HTML"
        )

        try:
            bot.send_message(ADMIN_ID, f"🎉 <b>AUTO DEPOSIT SUCCESSFUL!</b>\n\n👤 User: <code>{chat_id}</code>\n💵 Amount: <b>{amount:.2f} BDT</b> ({method})\n🆔 TxID: <code>{user_txid}</code>", parse_mode="HTML")
        except Exception:
            pass
    else:
        bot.send_message(
            chat_id,
            "❌ <b>ট্রানজেকশন আইডি পাওয়া যায়নি বা ইতিপূর্বে ক্লেইম করা হয়েছে!</b>\n\n"
            "১. পেমেন্ট সম্পন্ন করা নিশ্চিত করুন।\n"
            "২. টাকা পাঠানোর ১-২ মিনিট পর আবার ট্রাই করুন।\n"
            "৩. সমস্যা হলে এডমিনের সাথে কথা বলুন।",
            parse_mode="HTML"
        )

# ----------------- ⚡ সার্ভিস হ্যান্ডলিং -----------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def handle_category_selection(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    
    category_key = call.data.replace("cat_", "")
    services_list = get_services_by_category(category_key)
    
    if not services_list:
        bot.send_message(chat_id, "❌ <b>এই ক্যাটাগরিতে এখনো কোনো সার্ভিস যুক্ত করা হয়নি।</b>", parse_mode="HTML")
        return

    margin = get_profit_margin()

    response_text = "✅ <b>𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b> 👑\n\n✨ ✅নিচের সার্ভিস দেখে অর্ডার করুন ✨⚡\n\n"
    
    for service in services_list:
        price_val = service.get("price_per_1k", 0.0)
        display_price = (price_val if price_val is not None else 0.0) * margin

        response_text += (
            f"🆔 <b>{service['id']}</b> ⎯ {service['name']}\n"
            f"💵 দাম: <b>{display_price:.2f} BDT</b> (প্রতি ১০০০টি)\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        )
        
    response_text += "\n✍️ <b>✅🔥আপনি যেই সার্ভিস নিবেন তার আইডি দেন🔥 সবার সামনে যেইট লেখা আছে (যেমন)🆔 1 🆔 2 🆔 3 ।🔥</b>"
    msg = bot.send_message(chat_id, response_text, parse_mode="HTML")
    bot.register_next_step_handler(msg, get_service_id, services_list)

def get_service_id(message, services_list):
    chat_id = message.chat.id
    user_input = message.text.strip()

    selected_service = next((s for s in services_list if str(s["id"]) == user_input), None)
    if not selected_service:
        bot.send_message(chat_id, "🛑 ভুল আইডি! আবার নতুন অর্ডার বাটনে ক্লিক করে চেষ্টা করুন।")
        return

    msg = bot.send_message(chat_id, "🔗 আপনার অর্ডারের **লিংকটি  এখানে পেস্ট করে পাঠান:✅")
    bot.register_next_step_handler(msg, get_link, selected_service)

def get_link(message, selected_service):
    chat_id = message.chat.id
    link = message.text.strip()

    if not link.startswith("http"):
        bot.send_message(chat_id, "🛑 ভুল লিংক! সঠিক লিংক দিয়ে পুনরায় চেষ্টা করুন।")
        return

    msg = bot.send_message(chat_id, "🔢 কত **কোয়ান্টিটি (Quantity)** নিতে চান? (যেমন: ১০০ বা ১০০০):")
    bot.register_next_step_handler(msg, get_quantity, selected_service, link)

def get_quantity(message, selected_service, link):
    chat_id = message.chat.id
    quantity_input = message.text.strip()

    if not quantity_input.isdigit():
        bot.send_message(chat_id, "🛑 ভুল সংখ্যা! শুধুমাত্র সংখ্যা টাইপ করুন।")
        return

    quantity = int(quantity_input)
    bdt_rate_per_1k = selected_service.get("price_per_1k", 0.0) or 10.0
    margin = get_profit_margin()
    
    final_rate_per_1k = bdt_rate_per_1k * margin
    estimated_cost = (quantity / 1000) * final_rate_per_1k

    if estimated_cost < 0.01:
        estimated_cost = 0.01

    user_balance = get_balance(chat_id)

    if user_balance < estimated_cost:
        bot.send_message(
            chat_id,
            f"❌ <b> আপনার অ্যাকাউন্ট এ টাকা নেই💸!</b>\n\n"
            f"অর্ডারের মূল্💸য: {estimated_cost:.2f} BDT\n"
            f"আপনার ব্যালেন্💸স: {user_balance:.2f} BDT",
            parse_mode="HTML"
        )
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_confirm = types.KeyboardButton("✅ কনফার্ম করুন")
    btn_cancel = types.KeyboardButton("❌ বাতিল করুন")
    markup.add(btn_confirm, btn_cancel)

    confirm_msg = (
        f"💵 <b>আপনার অর্ডার  মূল্য: {estimated_cost:.2f} BDT</b>\n\n"
        f"অর্ডারটি    সাবমিট করতে    নিচের  <b>'✅ কনফার্ম করুন'</b> বাটনে ক্লিক করুন।"
    )
    msg = bot.send_message(chat_id, confirm_msg, reply_markup=markup, parse_mode="HTML")
    bot.register_next_step_handler(msg, confirm_order_final, selected_service, link, quantity, estimated_cost)

def confirm_order_final(message, selected_service, link, quantity, estimated_cost):
    chat_id = message.chat.id
    user_choice = message.text.strip()

    if user_choice == "✅ কনফার্ম করুন":
        user_balance = get_balance(chat_id)
        if user_balance < estimated_cost:
            bot.send_message(chat_id, "❌ আপনার অ্যাকাউন্ট এ পর্যাপ্ত ব্যালেন্স নেই।", reply_markup=get_main_menu_markup(chat_id))
            return

        payload = {
            "key": SMMSUN_API_KEY,
            "action": "add",
            "service": selected_service["api_id"],
            "link": link,
            "quantity": quantity,
        }
        
        try:
            response = requests.post(SMMSUN_API_URL, data=payload)
            api_res = response.json()

            if isinstance(api_res, dict) and "order" in api_res:
                new_balance = user_balance - estimated_cost
                update_balance(chat_id, new_balance)
                add_order_to_db(api_res["order"], chat_id, selected_service["name"], quantity, estimated_cost)

                success_text = (
                    f"✅ <b>ORDER PLACED SUCCESSFULLY!</b>\n\n"
                    f"📌 Service: {selected_service['name']}\n"
                    f"🔗 YOUR LINK: {link}\n"
                    f"🔢 QUANTITY: {quantity}\n"
                    f"💳 COST: {estimated_cost:.2f} BDT\n"
                    f"💰 ACCOUNT BALANCE 💸: {new_balance:.2f} BDT\n"
                    f"🆔 ORDER ID : <code>{api_res['order']}</code> ✔️"
                )
                bot.send_message(chat_id, success_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
            else:
                error_msg = api_res.get("error", "Unknown SMM Server error") if isinstance(api_res, dict) else "Invalid SMM Server response"
                bot.send_message(chat_id, f"❌ Failed to order. Server Response: {error_msg}", reply_markup=get_main_menu_markup(chat_id))
                
        except Exception:
            bot.send_message(chat_id, "❌ Connection error with SMM site. Please try again.", reply_markup=get_main_menu_markup(chat_id))

    else:
        bot.send_message(chat_id, "❌ অর্ডারটি বাতিল করা হয়েছে।", reply_markup=get_main_menu_markup(chat_id))

# ----------------- 🚀 RENDER/TERMUX FLASK THREAD -----------------
def start_bot_polling():
    while True:
        try:
            bot.polling(none_stop=True, skip_pending=True, timeout=60)
        except Exception as e:
            time.sleep(5)

if __name__ == "__main__":
    print("🤖 MONIRUL SMM BOT IS RUNNING SUCCESSFULLY...")
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    start_bot_polling()
