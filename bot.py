# -*- coding: utf-8 -*-
import sqlite3
import requests
import telebot
import time
import os
import re
import urllib.parse
from threading import Thread
from flask import Flask, request, jsonify
from telebot import types

# ----------------- আপনার বোটের মূল সেটিংস -----------------
BOT_TOKEN = "8899197686:AAGq1I806XgwIzNjdyQada9HykdyGciBO8g"
SMMSUN_API_URL = "https://socialpanel.pro/api/v2"
SMMSUN_API_KEY = "14f3163c337f51c7c90c6232d9428bc2"
ADMIN_ID = 6851638362 

USD_TO_BDT = 120.0     # ১ ডলার = ১২০ কয়েন (১ কয়েন = ১ টাকা)
# --------------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "users.db")

# 🔴 বাটন পাশাপাশি ২ টি করে সাজানোর হেল্পার ফাংশন (Side-by-Side 2 Columns)
def create_2col_markup(button_list):
    markup = types.InlineKeyboardMarkup()
    for i in range(0, len(button_list), 2):
        if i + 1 < len(button_list):
            markup.row(button_list[i], button_list[i+1])
        else:
            markup.row(button_list[i])
    return markup

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
        CREATE TABLE IF NOT EXISTS main_categories (
            name TEXT PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sub_categories (
            main_name TEXT,
            sub_name TEXT,
            PRIMARY KEY (main_name, sub_name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            main_cat TEXT,
            sub_cat TEXT,
            id_bot TEXT,
            api_id TEXT,
            name TEXT,
            price_per_1k REAL DEFAULT 0.0,
            min_qty INTEGER DEFAULT 10,
            PRIMARY KEY (main_cat, sub_cat, id_bot)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS force_channels (
            channel_id TEXT PRIMARY KEY,
            channel_name TEXT,
            invite_link TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
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

# --- জয়েন চ্যানেল ফাংশনসমূহ ---
def add_force_channel(channel_id, channel_name, invite_link):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO force_channels VALUES (?, ?, ?)", (channel_id, channel_name, invite_link))
    conn.commit()
    conn.close()

def get_force_channels():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, channel_name, invite_link FROM force_channels")
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_force_channel(channel_id):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM force_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()

def check_user_joined_all(chat_id):
    channels = get_force_channels()
    unjoined = []
    for ch in channels:
        try:
            ch_id = ch[0].strip()
            if not ch_id.startswith('@') and not ch_id.startswith('-100'):
                ch_id = '@' + ch_id
            member = bot.get_chat_member(ch_id, chat_id)
            if member.status not in ['member', 'administrator', 'creator']:
                unjoined.append(ch)
        except Exception:
            pass
    return unjoined

# --- ৩-লেভেল ক্যাটাগরি ও সার্ভিস ডাটাবেজ হেল্পার ---
def add_main_category(name):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO main_categories VALUES (?)", (name,))
    conn.commit()
    conn.close()

def get_main_categories():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM main_categories")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def add_sub_category(main_name, sub_name):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO sub_categories VALUES (?, ?)", (main_name, sub_name))
    conn.commit()
    conn.close()

def get_sub_categories(main_cat):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT sub_name FROM sub_categories WHERE main_name = ?", (main_cat,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_services_by_sub_cat(main_cat, sub_cat):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT id_bot, api_id, name, price_per_1k, min_qty FROM services WHERE main_cat = ? AND sub_cat = ?", (main_cat, sub_cat))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "api_id": r[1], "name": r[2], "price_per_1k": float(r[3]) if r[3] is not None else 0.0, "min_qty": r[4] if r[4] else 10} for r in rows]

def delete_single_service(main_cat, sub_cat, id_bot):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM services WHERE main_cat = ? AND sub_cat = ? AND id_bot = ?", (main_cat, sub_cat, id_bot))
    conn.commit()
    conn.close()

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

init_db()

# ----------------- 📱 RENDER WEBHOOK SERVER (FRAUD-PROOF) -----------------
@app.route('/')
def home():
    return "SMM Bot Server is Alive and 24/7 Running!", 200

@app.route('/sms-webhook', methods=['POST', 'GET'])
def sms_webhook():
    try:
        data = request.form if request.form else (request.json if request.json else request.args)
        
        # 🔴 সিকিউরিটি ফিল্টার: পার্সোনাল নাম্বার (বন্ধুর ফোন) থেকে মেসেজ ফরোয়ার্ড করলে ব্লগ করবে
        sender = data.get('from', '') or data.get('sender', '') or data.get('number', '') or ''
        if re.search(r'^(?:\+88)?01[3-9]\d{8}$', str(sender).strip()):
            return jsonify({"status": "ignored", "reason": "Personal sender forwarding not allowed"}), 200

        sms_text = data.get('text', '') or data.get('message', '') or data.get('msg', '') or str(data)
        sms_text = urllib.parse.unquote(sms_text)

        if "bKash" in sms_text or "TrxID" in sms_text:
            trx_match = re.search(r'TrxID\s*:?\s*([A-Za-z0-9]+)', sms_text, re.IGNORECASE)
            amt_match = re.search(r'Tk\s*:?\s*([0-9,.]+)', sms_text, re.IGNORECASE)
            if trx_match and amt_match:
                txid = trx_match.group(1).strip()
                amount = float(amt_match.group(1).replace(',', ''))
                save_auto_sms_trx(txid, amount, "bKash")
                try:
                    bot.send_message(ADMIN_ID, f"📩 <b>bKash SMS Received!</b>\n\n💵 Amount: <b>{amount:.2f} Coin</b>\n🆔 TxID: <code>{txid}</code>", parse_mode="HTML")
                except Exception:
                    pass

        elif "Nagad" in sms_text or "TxnID" in sms_text:
            trx_match = re.search(r'TxnID\s*:?\s*([A-Za-z0-9]+)', sms_text, re.IGNORECASE)
            amt_match = re.search(r'(?:Amount\s*:?\s*Tk|Tk)\s*:?\s*([0-9,.]+)', sms_text, re.IGNORECASE)
            if trx_match and amt_match:
                txid = trx_match.group(1).strip()
                amount = float(amt_match.group(1).replace(',', ''))
                save_auto_sms_trx(txid, amount, "Nagad")
                try:
                    bot.send_message(ADMIN_ID, f"📩 <b>Nagad SMS Received!</b>\n\n💵 Amount: <b>{amount:.2f} Coin</b>\n🆔 TxID: <code>{txid}</code>", parse_mode="HTML")
                except Exception:
                    pass

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "success", "error": str(e)}), 200

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

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

# ================== 👑 এডমিন প্যানেল (/admin) ==================

@bot.message_handler(commands=["admin"])
def admin_panel_command(message):
    if message.chat.id != ADMIN_ID:
        return

    btn1 = types.InlineKeyboardButton("➕ মেইন প্ল্যাটফর্ম যোগ", callback_data="admin_add_main_cat")
    btn2 = types.InlineKeyboardButton("📂 সাব-ক্যাটাগরি যোগ", callback_data="admin_add_sub_cat")
    btn3 = types.InlineKeyboardButton("🛒 নতুন সার্ভিস যোগ", callback_data="admin_add_service_start")
    btn4 = types.InlineKeyboardButton("🔍 ইউজার ইনফো ও কয়েন", callback_data="admin_user_info_start")
    btn5 = types.InlineKeyboardButton("🖼️ স্টার্ট পিকচার সেট", callback_data="admin_set_start_photo")
    btn6 = types.InlineKeyboardButton("📢 জয়েন চ্যানেল সেটআপ", callback_data="admin_force_channel_menu")
    btn7 = types.InlineKeyboardButton("🗑️ একটি সার্ভিস ডিলিট", callback_data="admin_delete_single_service_start")
    btn8 = types.InlineKeyboardButton("💥 সকল সার্ভিস ডিলিট", callback_data="admin_clear_services_confirm")

    markup = create_2col_markup([btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8])

    bot.send_message(
        ADMIN_ID,
        "👑 <b>এডমিন কন্ট্রোল প্যানেল</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "নিচের বাটন চেপে যেকোনো কাজ সিলেক্ট করুন:",
        reply_markup=markup,
        parse_mode="HTML"
    )

# --- স্টার্ট ছবি সেটিং ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_set_start_photo")
def admin_set_start_photo(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(ADMIN_ID, "🖼️ <b>বোট স্টার্ট করার সময় যে পিকচারটি দেখাতে চান, সেটির ফটো লিংক (Image URL) পাঠান:</b>\n(অথবা `0` পাঠালে পিকচার রিমুভ হয়ে যাবে)", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_start_photo)

def save_start_photo(message):
    url = message.text.strip()
    if url == "0":
        set_setting("start_photo", "")
        bot.send_message(ADMIN_ID, "✅ <b>স্টার্ট পিকচার রিমুভ করা হয়েছে!</b>", parse_mode="HTML")
    else:
        set_setting("start_photo", url)
        bot.send_message(ADMIN_ID, "✅ <b>নতুন স্টার্ট পিকচার সফলভাবে সেট হয়েছে!</b>", parse_mode="HTML")

# --- 1. মেইন প্ল্যাটফর্ম যোগ ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_main_cat")
def admin_add_main_cat_start(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(ADMIN_ID, "✍️ <b>নতুন মেইন প্ল্যাটফর্মের নাম লিখুন:</b>\n(যেমন: `🎵 TikTok Service` বা `👥 Facebook Service`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_save_main_cat)

def admin_save_main_cat(message):
    mcat_name = message.text.strip()
    add_main_category(mcat_name)
    bot.send_message(ADMIN_ID, f"✅ <b>মেইন প্ল্যাটফর্ম [{mcat_name}] সফলভাবে তৈরি হয়েছে!</b>", parse_mode="HTML")

# --- 2. সাব-ক্যাটাগরি যোগ ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_sub_cat")
def admin_add_sub_cat_start(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)

    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(ADMIN_ID, "❌ আগে মেইন প্ল্যাটফর্ম তৈরি করুন!", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"admsubsel_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(ADMIN_ID, "📁 <b>কোন প্ল্যাটফর্মের ভেতরে সাব-ক্যাটাগরি যোগ করবেন?</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admsubsel_"))
def admin_sub_cat_get_name(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("admsubsel_", "")

    msg = bot.send_message(ADMIN_ID, f"✍️ <b>[{mcat_name}] প্ল্যাটফর্মের নতুন সাব-ক্যাটাগরির নাম লিখুন:</b>\n(যেমন: `TikTok View` বা `FB Like`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_save_sub_cat, mcat_name)

def admin_save_sub_cat(message, mcat_name):
    sub_name = message.text.strip()
    add_sub_category(mcat_name, sub_name)
    bot.send_message(ADMIN_ID, f"✅ <b>[{mcat_name}] -> [{sub_name}] সাব-ক্যাটাগরি তৈরি হয়েছে!</b>", parse_mode="HTML")

# --- 3. আসল সার্ভিস যোগ (সরাসরি কয়েন প্রাইজ) ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_service_start")
def admin_add_service_start(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)

    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(ADMIN_ID, "❌ কোনো মেইন প্ল্যাটফর্ম নেই! আগে মেইন প্ল্যাটফর্ম যোগ করুন।", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"admcatm_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(ADMIN_ID, "📁 <b>মেইন প্ল্যাটফর্ম সিলেক্ট করুন:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcatm_"))
def admin_step_select_sub_for_service(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("admcatm_", "")

    sub_cats = get_sub_categories(mcat_name)
    if not sub_cats:
        bot.send_message(ADMIN_ID, f"❌ [{mcat_name}] এ কোনো সাব-ক্যাটাগরি নেই! আগে সাব-ক্যাটাগরি যোগ করুন।", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"📂 {sc}", callback_data=f"admcats_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)
    bot.send_message(ADMIN_ID, f"📂 <b>[{mcat_name}] এর সাব-ক্যাটাগরি সিলেক্ট করুন:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcats_"))
def admin_step_get_choice_id(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)

    raw_data = call.data.replace("admcats_", "")
    mcat_name, scat_name = raw_data.split("___")

    msg = bot.send_message(ADMIN_ID, f"🆔 <b>[{scat_name}]</b>\nকাস্টমার চয়েস ID কত দেবেন? (যেমন: 1, 2, 3 লিখে পাঠান):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_api_id, mcat_name, scat_name)

def admin_step_get_api_id(message, mcat_name, scat_name):
    id_bot = message.text.strip()
    msg = bot.send_message(ADMIN_ID, f"🔌 ওয়েবসাইটের <b>আসল API ID</b> টি কত? (যেমন: 19138):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_direct_coin, mcat_name, scat_name, id_bot)

def admin_step_get_direct_coin(message, mcat_name, scat_name, id_bot):
    api_id = message.text.strip()
    msg = bot.send_message(ADMIN_ID, "🪙 <b>প্রতি ১০০০ (1000) কোয়ান্টিটির জন্য কাস্টমার থেকে কত কয়েন (Coin) কাটবেন?</b>\n(যেমন: 10, 15 বা 50 লিখে পাঠান):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_min_qty, mcat_name, scat_name, id_bot, api_id)

def admin_step_get_min_qty(message, mcat_name, scat_name, id_bot, api_id):
    try:
        coin_price_per_1k = float(message.text.strip())
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ ভুল কয়েন দাম!")
        return

    msg = bot.send_message(ADMIN_ID, "🔢 এই সার্ভিসের জন্য <b>সর্বনিম্ন কোয়ান্টিটি (Min Qty)</b> কত দেবেন? (যেমন: 10, 100 বা 1000):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_name, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k)

def admin_step_get_name(message, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k):
    try:
        min_qty = int(message.text.strip())
    except ValueError:
        min_qty = 10

    msg = bot.send_message(ADMIN_ID, "📌 <b>সার্ভিসটির নাম লিখে পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_save_service, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k, min_qty)

def admin_step_save_service(message, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k, min_qty):
    name = message.text.strip()

    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO services (main_cat, sub_cat, id_bot, api_id, name, price_per_1k, min_qty) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (mcat_name, scat_name, id_bot, api_id, name, coin_price_per_1k, min_qty))
    conn.commit()
    conn.close()

    bot.send_message(
        ADMIN_ID,
        f"✅ <b>সার্ভিসটি সফলভাবে ৩-স্তরে যুক্ত করা হয়েছে!</b>\n\n"
        f"📁 <b>প্ল্যাটফর্ম:</b> <code>{mcat_name}</code>\n"
        f"📂 <b>সাব-ক্যাটাগরি:</b> <code>{scat_name}</code>\n"
        f"🆔 <b>চয়েস ID:</b> <b>{id_bot}</b> | 🔌 <b>API ID:</b> <b>{api_id}</b>\n"
        f"💰 <b>কাস্টমার কয়েন দাম (১০০০টি):</b> <b>{coin_price_per_1k:.2f} Coin</b>\n"
        f"🔢 <b>সর্বনিম্ন অর্ডার:</b> <b>{min_qty} টি</b>\n"
        f"📌 <b>নাম:</b> <b>{name}</b>",
        parse_mode="HTML"
    )

# ---------------- 4. সিঙ্গেল সার্ভিস ডিলিট ----------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_delete_single_service_start")
def admin_delete_single_service_start(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)

    main_cats = get_main_categories()
    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"delmcat_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)

    bot.send_message(ADMIN_ID, "🗑️ <b>কোন প্ল্যাটফর্মের সার্ভিস ডিলিট করবেন?</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmcat_"))
def admin_del_select_sub(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("delmcat_", "")

    sub_cats = get_sub_categories(mcat_name)
    btns = [types.InlineKeyboardButton(f"📂 {sc}", callback_data=f"delscat_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)

    bot.send_message(ADMIN_ID, f"🗑️ <b>[{mcat_name}] এর সাব-ক্যাটাগরি সিলেক্ট করুন:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delscat_"))
def admin_del_select_id(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    raw_data = call.data.replace("delscat_", "")
    mcat_name, scat_name = raw_data.split("___")

    msg = bot.send_message(ADMIN_ID, f"🗑️ <b>[{scat_name}]</b> এর যে সার্ভিসটি ডিলিট করবেন তার <b>কাস্টমার চয়েস ID (যেমন: 1, 2)</b> লিখে পাঠান:", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_process_delete_service, mcat_name, scat_name)

def admin_process_delete_service(message, mcat_name, scat_name):
    id_bot = message.text.strip()
    delete_single_service(mcat_name, scat_name, id_bot)
    bot.send_message(ADMIN_ID, f"✅ <b>[{mcat_name}] -> [{scat_name}] থেকে সার্ভিস ID [{id_bot}] ডিলিট করা হয়েছে!</b>", parse_mode="HTML")

# ---------------- 5. ৪টি চ্যানেল জয়েন সেটআপ ----------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_force_channel_menu")
def admin_force_channel_menu(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)

    channels = get_force_channels()
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for ch in channels:
        markup.add(types.InlineKeyboardButton(f"❌ {ch[1]} ডিলিট করুন", callback_data=f"delchan_{ch[0]}"))

    if len(channels) < 4:
        markup.add(types.InlineKeyboardButton("➕ নতুন চ্যানেল যোগ করুন", callback_data="addchan_start"))

    bot.send_message(ADMIN_ID, f"📢 <b>বর্তমান ফোর্সমস্ট জয়েন চ্যানেল সংখ্যা: {len(channels)}/4</b>\n\n(⚠️ মনে রাখবেন: বোটকে চ্যানেলে এডমিন বানিয়ে রাখতে হবে!)\nনিচের বাটন দিয়ে যোগ বা রিমুভ করুন:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "addchan_start")
def addchan_start(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(ADMIN_ID, "📢 <b>চ্যানেলের ইউজারনেম লিখে পাঠান:</b>\n(যেমন: `@MyChannel`):", parse_mode="HTML")
    bot.register_next_step_handler(msg, addchan_get_link)

def addchan_get_link(message):
    ch_id = message.text.strip()
    msg = bot.send_message(ADMIN_ID, f"🔗 <b>চ্যানেলটির ইনভাইট লিংক পেস্ট করুন:</b>\n(যেমন: `https://t.me/MyChannel`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, addchan_get_name, ch_id)

def addchan_get_name(message, ch_id):
    link = message.text.strip()
    msg = bot.send_message(ADMIN_ID, "📌 <b>চ্যানেলটির সুন্দর নাম লিখে পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, addchan_save, ch_id, link)

def addchan_save(message, ch_id, link):
    ch_name = message.text.strip()
    add_force_channel(ch_id, ch_name, link)
    bot.send_message(ADMIN_ID, f"✅ <b>চ্যানেল [{ch_name}] সফলভাবে যুক্ত হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delchan_"))
def delchan_process(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    ch_id = call.data.replace("delchan_", "")
    delete_force_channel(ch_id)
    bot.send_message(ADMIN_ID, "✅ <b>চ্যানেলটি ডিলিট করা হয়েছে!</b>", parse_mode="HTML")

# ---------------- 6. ইউজার ইনফো ও ব্যালেন্স এডিট ----------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_user_info_start")
def admin_user_info_start(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(ADMIN_ID, "🔍 <b>ইউজারের তথ্য দেখতে বা কয়েন এডিট করতে ইউজার ID লিখে পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_process_user_lookup)

def admin_process_user_lookup(message):
    try:
        target_user = int(message.text.strip())
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ ভুল ইনপুট! ইউজার আইডি শুধুমাত্র সংখ্যা হয়।")
        return

    balance = get_balance(target_user)
    total_orders, total_payments = get_user_stats(target_user)

    btn1 = types.InlineKeyboardButton("➕ কয়েন যোগ করুন", callback_data=f"admbal_ADD_{target_user}")
    btn2 = types.InlineKeyboardButton("✏️ কয়েন সেট/এডিট", callback_data=f"admbal_SET_{target_user}")
    markup = create_2col_markup([btn1, btn2])

    info_text = (
        f"👤 <b>ইউজার অ্যাকাউন্ট ইনফরমেশন</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ইউজার ID:</b> <code>{target_user}</code>\n"
        f"💰 <b>বর্তমান ব্যালেন্স:</b> <b>{balance:.2f} Coin</b>\n"
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
        msg = bot.send_message(ADMIN_ID, f"💵 ইউজার <code>{target_user}</code> এর সাথে <b>কত কয়েন (Coin) যোগ করবেন?</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, admin_save_add_balance, target_user)
    elif action == "SET":
        msg = bot.send_message(ADMIN_ID, f"✏️ ইউজার <code>{target_user}</code> এর <b>নতুন কয়েন ব্যালেন্স কত সেট করবেন?</b>", parse_mode="HTML")
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

    bot.send_message(ADMIN_ID, f"✅ ইউজার <code>{target_user}</code> এর অ্যাকাউন্টে <b>{amount:.2f} Coin</b> যোগ হয়েছে। নতুন ব্যালেন্স: <b>{new_balance:.2f} Coin</b>", parse_mode="HTML")

    try:
        bot.send_message(
            target_user,
            f"🎉 <b>আপনার অ্যাকাউন্টে কয়েন যোগ করা হয়েছে!</b>\n\n"
            f"💳 <b>যোগকৃত কয়েন:</b> <b>{amount:.2f} Coin</b>\n"
            f"💰 <b>বর্তমান মোট ব্যালেন্স:</b> <b>{new_balance:.2f} Coin</b> ✅",
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
    bot.send_message(ADMIN_ID, f"✅ ইউজার <code>{target_user}</code> এর ব্যালেন্স সফলভাবে <b>{new_balance:.2f} Coin</b> সেট করা হয়েছে।", parse_mode="HTML")

    try:
        bot.send_message(
            target_user,
            f"📢 <b>আপনার অ্যাকাউন্ট ব্যালেন্স আপডেট করা হয়েছে!</b>\n\n"
            f"💰 <b>বর্তমান মোট ব্যালেন্স:</b> <b>{new_balance:.2f} Coin</b> ✅",
            parse_mode="HTML"
        )
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "admin_users_list")
def admin_users_list_callback(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    all_users = get_all_users()
    response = "👥 <b>বোটের সকল ইউজারের তালিকা:</b>\n\n"
    for u in all_users:
        response += f"👤 <b>ID:</b> <code>{u[0]}</code> | <b>ব্যালেন্স:</b> <b>{u[1]:.2f} Coin</b>\n"
    bot.send_message(ADMIN_ID, response, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_clear_services_confirm")
def admin_clear_services_callback(call):
    if call.message.chat.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    try:
        conn = sqlite3.connect(DB_FILE, timeout=30)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM services")
        cursor.execute("DELETE FROM main_categories")
        cursor.execute("DELETE FROM sub_categories")
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
    btn5 = types.KeyboardButton("💳 Buy Coin (টাকা রিচার্জ)")
    btn6 = types.KeyboardButton("📞 সাপোর্ট")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    return markup

def enforce_force_join(chat_id):
    unjoined = check_user_joined_all(chat_id)
    if unjoined:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in unjoined:
            markup.add(types.InlineKeyboardButton(f"📢 Join {ch[1]}", url=ch[2]))
        markup.add(types.InlineKeyboardButton("✅ জয়েন সম্পন্ন করেছি (Verify)", callback_data="verify_channel_joins"))

        bot.send_message(
            chat_id,
            "⚠️ <b>বট ব্যবহার করতে নিচের চ্যানেলগুলোতে জয়েন হওয়া বাধ্যতামূলক!</b>\n\n"
            "জয়েন শেষ করে <b>'✅ জয়েন সম্পন্ন করেছি'</b> বাটনে চাপ দিন:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return False
    return True

@bot.callback_query_handler(func=lambda call: call.data == "verify_channel_joins")
def verify_channel_joins_callback(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    unjoined = check_user_joined_all(chat_id)
    if not unjoined:
        bot.send_message(chat_id, "🎉 <b>সবগুলো চ্যানেলে জয়েনিং ভেরিফাই হয়েছে!</b>\nএখন আপনি বট ব্যবহার করতে পারবেন।", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
    else:
        bot.send_message(chat_id, "❌ <b>আপনি এখনো সবগুলো চ্যানেলে জয়েন করেননি!</b> অনুগ্রহ করে লিংকে গিয়ে জয়েন করুন।", parse_mode="HTML")

@bot.message_handler(commands=["start"])
def start_command(message):
    chat_id = message.chat.id
    add_user(chat_id)
    if enforce_force_join(chat_id):
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
    
    start_photo = get_setting("start_photo")
    if start_photo:
        try:
            bot.send_photo(chat_id, start_photo, caption=welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
    else:
        bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

# 🔴 ৩-স্তরের কাস্টমার ব্রাউজিং মেনু (2 Columns Side-by-Side)
@bot.message_handler(func=lambda message: True)
def handle_menu_buttons(message):
    chat_id = message.chat.id
    if not enforce_force_join(chat_id):
        return

    text = message.text

    if text == "👤 আমার অ্যাকাউন্ট":
        balance = get_balance(chat_id)
        account_text = (
            f"┏━━━━━━━━━━━━━━━━━━┓\n"
            f"   👤 <b>আমার অ্যাকাউন্ট ড্যাশবোর্ড</b> 👤\n"
            f"┗━━━━━━━━━━━━━━━━━━┛\n\n"
            f"🆔 আপনার ইউজার আইডি : <code>{chat_id}</code>\n"
            f"💰 বর্তমান ব্যালেন্স : <b>{balance:.2f} Coin</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(chat_id, account_text, parse_mode="HTML")

    elif text == "🛒 নতুন অর্ডার":
        main_cats = get_main_categories()
        if not main_cats:
            bot.send_message(chat_id, "❌ <b>বর্তমানে কোনো সার্ভিস যুক্ত করা নেই।</b>\n\nএডমিন প্যানেল (/admin) থেকে সার্ভিস যোগ করুন।", parse_mode="HTML")
            return

        btns = [types.InlineKeyboardButton(f"✨ {mc}", callback_data=f"mcat_{mc}") for mc in main_cats]
        markup = create_2col_markup(btns)

        bot.send_message(chat_id, "💸 <b>আমাদের সার্ভিস প্ল্যাটফর্ম নির্বাচন করুন:</b>", reply_markup=markup, parse_mode="HTML")

    elif text == "💳 Buy Coin (টাকা রিচার্জ)":
        deposit_text = (
            "💎 <b>কয়েন রিচার্জ করার সহজ নিয়ম</b> 💎\n"
            "💸১ কয়েন = ১ টাকা⚡💸\n\n"
            "╔══════════════════════╗\n"
            "💳 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗜𝗡𝗦𝗧𝗥𝗨𝗖𝗧𝗜𝗢𝗡 💳\n"
            "╚══════════════════════╝\n\n"
            "🪙 <b>কয়েন প্যাকেজ লিস্ট:</b>\n"
            "• 10 Coin = 10 BDT\n"
            "• 50 Coin = 50 BDT\n"
            "• 100 Coin = 100 BDT\n"
            "• 200 Coin = 200 BDT\n"
            "• 500 Coin = 500 BDT\n\n"
            "🆔 <b>বিকাশ (পার্সোনাল):</b> <code>01925263571</code>\n"
            "💸 <b>নগদ পার্সোনাল:</b> <code>01925263571</code>\n\n"
            "⚠️ <b>সর্বনিম্ন ১০ কয়েন কিনতে হবে।</b>\n"
            "Send Money করার পর নিচে শুধুমাত্র TrxID দিলেই ১ সেকেন্ডে অটো কয়েন যোগ হবে!\n\n"
            "👇 <b>কয়েন কিনতে নিচের বাটনে চাপ দিন:</b>"
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
                f"🔢 কোয়ান্টিটি: <b>{o[2]}</b> | 💵 খরচ: <b>{o[3]:.2f} Coin</b>\n"
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
                f"💵 পরিমাণ: <b>{p[1]:.2f} Coin</b> | 🆔 TxID: <code>{p[2]}</code>\n"
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

# 🔴 ২য় লেভেল: সাব-ক্যাটাগরি হ্যান্ডলিং (2 Columns Side-by-Side)
@bot.callback_query_handler(func=lambda call: call.data.startswith("mcat_"))
def handle_main_category_selection(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    
    mcat_name = call.data.replace("mcat_", "")
    sub_cats = get_sub_categories(mcat_name)

    if not sub_cats:
        bot.send_message(chat_id, "❌ <b>এই প্ল্যাটফর্মে এখনো কোনো সাব-ক্যাটাগরি যুক্ত করা হয়নি।</b>", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"📂 {sc}", callback_data=f"scat_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)

    bot.send_message(chat_id, f"📂 <b>[{mcat_name}] ক্যাটাগরি বেছে নিন:</b>", reply_markup=markup, parse_mode="HTML")

# 🔴 ৩য় লেভেল: সার্ভিস লিস্ট হ্যান্ডলিং
@bot.callback_query_handler(func=lambda call: call.data.startswith("scat_"))
def handle_sub_category_selection(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    
    raw_data = call.data.replace("scat_", "")
    mcat_name, scat_name = raw_data.split("___")

    services_list = get_services_by_sub_cat(mcat_name, scat_name)
    
    if not services_list:
        bot.send_message(chat_id, "❌ <b>এই সাব-ক্যাটাগরিতে এখনো কোনো সার্ভিস যুক্ত করা হয়নি।</b>", parse_mode="HTML")
        return

    response_text = "✅ <b>𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b> 👑\n\n✨ ✅নিচের সার্ভিস দেখে অর্ডার করুন ✨⚡\n\n"
    
    for service in services_list:
        display_price = service.get("price_per_1k", 0.0)

        response_text += (
            f"🆔 <b>{service['id']}</b> ⎯ {service['name']}\n"
            f"💵 দাম: <b>{display_price:.2f} Coin</b> (প্রতি ১০০০টি)\n"
            f"🔢 সর্বনিম্ন অর্ডার: <b>{service['min_qty']} টি</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        )
        
    response_text += "\n✍️ <b>✅🔥আপনি যেই সার্ভিস নিবেন তার আইডি দেন🔥 (যেমন)🆔 1 🆔 2 🆔 3 ।🔥</b>"
    msg = bot.send_message(chat_id, response_text, parse_mode="HTML")
    bot.register_next_step_handler(msg, get_service_id, services_list)

def get_service_id(message, services_list):
    chat_id = message.chat.id
    user_input = message.text.strip()

    selected_service = next((s for s in services_list if str(s["id"]) == user_input), None)
    if not selected_service:
        bot.send_message(chat_id, "🛑 ভুল আইডি! আবার নতুন অর্ডার বাটনে ক্লিক করে চেষ্টা করুন।")
        return

    msg = bot.send_message(chat_id, f"🔗 আপনার অর্ডারের **লিংকটি এখানে পেস্ট করে পাঠান:✅\n\n⚠️ (সর্বনিম্ন কোয়ান্টিটি: {selected_service['min_qty']} টি)")
    bot.register_next_step_handler(msg, get_link, selected_service)

def get_link(message, selected_service):
    chat_id = message.chat.id
    link = message.text.strip()

    if not link.startswith("http"):
        bot.send_message(chat_id, "🛑 ভুল লিংক! সঠিক লিংক দিয়ে পুনরায় চেষ্টা করুন।")
        return

    msg = bot.send_message(chat_id, f"🔢 কত **কোয়ান্টিটি (Quantity)** নিতে চান?\n\n⚠️ (সর্বনিম্ন: {selected_service['min_qty']} টি):")
    bot.register_next_step_handler(msg, get_quantity, selected_service, link)

def get_quantity(message, selected_service, link):
    chat_id = message.chat.id
    quantity_input = message.text.strip()

    if not quantity_input.isdigit():
        bot.send_message(chat_id, "🛑 ভুল সংখ্যা! শুধুমাত্র সংখ্যা টাইপ করুন।")
        return

    quantity = int(quantity_input)
    min_qty = selected_service.get('min_qty', 10)

    if quantity < min_qty:
        bot.send_message(chat_id, f"❌ <b>এই সার্ভিসের জন্য সর্বনিম্ন {min_qty} টি কোয়ান্টিটি অর্ডার করতে হবে!</b>\n\nনতুন করে চেষ্টা করুন।", parse_mode="HTML")
        return

    bdt_rate_per_1k = selected_service.get("price_per_1k", 0.0) or 10.0
    estimated_cost = (quantity / 1000) * bdt_rate_per_1k

    if estimated_cost < 1.0:
        estimated_cost = 1.0

    user_balance = get_balance(chat_id)

    if user_balance < estimated_cost:
        bot.send_message(
            chat_id,
            f"❌ <b>আপনার অ্যাকাউন্টে পর্যাপ্ত কয়েন নেই!</b>\n\n"
            f"অর্ডারের মূল্য: <b>{estimated_cost:.2f} Coin</b>\n"
            f"আপনার ব্যালেন্স: <b>{user_balance:.2f} Coin</b>",
            parse_mode="HTML"
        )
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_confirm = types.KeyboardButton("✅ কনফার্ম করুন")
    btn_cancel = types.KeyboardButton("❌ বাতিল করুন")
    markup.add(btn_confirm, btn_cancel)

    confirm_msg = (
        f"💵 <b>আপনার অর্ডার মূল্য: {estimated_cost:.2f} Coin</b>\n\n"
        f"অর্ডারটি সাবমিট করতে নিচের <b>'✅ কনফার্ম করুন'</b> বাটনে ক্লিক করুন।"
    )
    msg = bot.send_message(chat_id, confirm_msg, reply_markup=markup, parse_mode="HTML")
    bot.register_next_step_handler(msg, confirm_order_final, selected_service, link, quantity, estimated_cost)

def confirm_order_final(message, selected_service, link, quantity, estimated_cost):
    chat_id = message.chat.id
    user_choice = message.text.strip()

    if user_choice == "✅ কনফার্ম করুন":
        user_balance = get_balance(chat_id)
        if user_balance < estimated_cost:
            bot.send_message(chat_id, "❌ আপনার অ্যাকাউন্টে পর্যাপ্ত ব্যালেন্স নেই।", reply_markup=get_main_menu_markup(chat_id))
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
                    f"💳 COST: {estimated_cost:.2f} Coin\n"
                    f"💰 REMAINING COIN: {new_balance:.2f} Coin\n"
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

# ----------------- 💳 ডিপোজিট ভেরিফাই -----------------
@bot.callback_query_handler(func=lambda call: call.data == "verify_auto_trx_start")
def start_auto_trx_input(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💵 <b>কত কয়েন (Coin) কিনতে চান? পরিমাণ লিখে পাঠান:</b>\n(যেমন: 10, 50, 100, 200 বা 500। সর্বনিম্ন ১০ কয়েন):", parse_mode="HTML")
    bot.register_next_step_handler(msg, get_intended_deposit_amount)

def get_intended_deposit_amount(message):
    chat_id = message.chat.id
    amount_str = message.text.strip()

    if not amount_str.replace('.', '', 1).isdigit():
        bot.send_message(chat_id, "❌ <b>ভুল ইনপুট! শুধু সংখ্যা লিখে পাঠান:</b>", parse_mode="HTML")
        return

    intended_amount = float(amount_str)
    if intended_amount < 10.0:
        bot.send_message(chat_id, "❌ <b>সর্বনিম্ন ১০ কয়েন কিনতে হবে!</b> আবার চেষ্টা করুন।", parse_mode="HTML")
        return
    
    msg_text = (
        f"👍 <b>অনুরোধ গৃহীত হয়েছে!</b>\n\n"
        f"💰 <b>আপনার কয়েন পরিমাণ:</b> <b>{intended_amount:.2f} Coin ({intended_amount:.2f} BDT)</b>\n\n"
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
            f"🪙 <b>প্রাপ্ত কয়েন:</b> <b>{amount:.2f} Coin</b>\n"
            f"💰 <b>বর্তমান মোট ব্যালেন্স:</b> <b>{new_balance:.2f} Coin</b> 🎉",
            parse_mode="HTML"
        )

        try:
            bot.send_message(ADMIN_ID, f"🎉 <b>AUTO DEPOSIT SUCCESSFUL!</b>\n\n👤 User: <code>{chat_id}</code>\n🪙 Amount: <b>{amount:.2f} Coin</b> ({method})\n🆔 TxID: <code>{user_txid}</code>", parse_mode="HTML")
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
