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
BOT_TOKEN = "8386397372:AAG0giAEyymw58ClpPl4QJXmjBkRA9FAfGw"
SMMSUN_API_URL = "https://socialpanel.pro/api/v2"
SMMSUN_API_KEY = "14f3163c337f51c7c90c6232d9428bc2"
MAIN_ADMIN_ID = 6851638362 

USD_TO_BDT = 120.0     # ১ ডলার = ১২০ কয়েন (১ কয়েন = ১ টাকা)
# --------------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "users.db")

# স্প্যাম ট্র্যাকার ডিকশনারি (পূর্বে মিসিং ছিল যার কারণে ক্র্যাশ হতো)
FAILED_ATTEMPTS = {}

# 🔴 বাটন পাশাপাশি ২টি করে সাজানোর হেল্পার ফাংশন
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
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                admin_id INTEGER PRIMARY KEY
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                chat_id INTEGER,
                service_name TEXT,
                quantity INTEGER,
                cost REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                method TEXT,
                amount REAL,
                txid TEXT,
                status TEXT DEFAULT 'Pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
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

def get_setting(key):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None

def set_setting(key, value):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

def get_smm_api_url():
    val = get_setting("smm_api_url")
    return val if val else SMMSUN_API_URL

def get_smm_api_key():
    val = get_setting("smm_api_key")
    return val if val else SMMSUN_API_KEY

def is_admin(chat_id):
    if chat_id == MAIN_ADMIN_ID:
        return True
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (chat_id,))
        return cursor.fetchone() is not None

def add_co_admin(admin_id):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO admins VALUES (?)", (admin_id,))
        conn.commit()

def remove_co_admin(admin_id):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
        conn.commit()

def add_user(chat_id):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (chat_id, balance) VALUES (?, ?)", (chat_id, 0.0))
        conn.commit()

def get_balance(chat_id):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        return row[0] if row else 0.0

def update_balance(chat_id, new_balance):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (chat_id, balance) VALUES (?, 0.0)", (chat_id,))
        cursor.execute("UPDATE users SET balance = ? WHERE chat_id = ?", (new_balance, chat_id))
        conn.commit()

def get_all_users():
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, balance FROM users")
        return cursor.fetchall()

def get_user_stats(chat_id):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders WHERE chat_id = ?", (chat_id,))
        total_orders = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM payments WHERE chat_id = ? AND status = 'Approved'", (chat_id,))
        total_payments = cursor.fetchone()[0]
        return total_orders, total_payments

# --- জয়েন চ্যানেল ---
def add_force_channel(channel_id, channel_name, invite_link):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO force_channels VALUES (?, ?, ?)", (channel_id, channel_name, invite_link))
        conn.commit()

def get_force_channels():
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, channel_name, invite_link FROM force_channels")
        return cursor.fetchall()

def delete_force_channel(channel_id):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM force_channels WHERE channel_id = ?", (channel_id,))
        conn.commit()

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
            unjoined.append(ch)
    return unjoined

# --- ৩-লেভেল ক্যাটাগরি ডাটাবেজ ---
def add_main_category(name):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO main_categories VALUES (?)", (name,))
        conn.commit()

def get_main_categories():
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM main_categories")
        return [r[0] for r in cursor.fetchall()]

def delete_main_category(name):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM main_categories WHERE name = ?", (name,))
        cursor.execute("DELETE FROM sub_categories WHERE main_name = ?", (name,))
        cursor.execute("DELETE FROM services WHERE main_cat = ?", (name,))
        conn.commit()

def add_sub_category(main_name, sub_name):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO sub_categories VALUES (?, ?)", (main_name, sub_name))
        conn.commit()

def get_sub_categories(main_cat):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sub_name FROM sub_categories WHERE main_name = ?", (main_cat,))
        return [r[0] for r in cursor.fetchall()]

def delete_sub_category(main_name, sub_name):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sub_categories WHERE main_name = ? AND sub_name = ?", (main_name, sub_name))
        cursor.execute("DELETE FROM services WHERE main_cat = ? AND sub_cat = ?", (main_name, sub_name))
        conn.commit()

def get_services_by_sub_cat(main_cat, sub_cat):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_bot, api_id, name, price_per_1k, min_qty FROM services WHERE main_cat = ? AND sub_cat = ?", (main_cat, sub_cat))
        return [{"id": r[0], "api_id": r[1], "name": r[2], "price_per_1k": float(r[3]) if r[3] is not None else 0.0, "min_qty": r[4] if r[4] else 10} for r in cursor.fetchall()]

def delete_single_service(main_cat, sub_cat, id_bot):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM services WHERE main_cat = ? AND sub_cat = ? AND id_bot = ?", (main_cat, sub_cat, id_bot))
        conn.commit()

def add_order_to_db(order_id, chat_id, service_name, quantity, cost):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (order_id, chat_id, service_name, quantity, cost) VALUES (?, ?, ?, ?, ?)",
                       (order_id, chat_id, service_name, quantity, cost))
        conn.commit()

def get_user_orders(chat_id):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT order_id, service_name, quantity, cost FROM orders WHERE chat_id = ? ORDER BY id DESC LIMIT 5", (chat_id,))
        return cursor.fetchall()

def add_payment_to_db(chat_id, method, amount, txid, status='Approved'):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (chat_id, method, amount, txid, status) VALUES (?, ?, ?, ?, ?)",
                       (chat_id, method, amount, txid, status))
        conn.commit()

def save_auto_sms_trx(txid, amount, method):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO auto_transactions (txid, amount, method, status) VALUES (?, ?, ?, 'Unclaimed')",
                       (txid.strip().upper(), amount, method))
        conn.commit()

def claim_auto_trx(txid):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        clean_txid = txid.strip().upper()
        cursor.execute("SELECT amount, method, status FROM auto_transactions WHERE UPPER(txid) = ?", (clean_txid,))
        row = cursor.fetchone()
        if row and row[2] == 'Unclaimed':
            cursor.execute("UPDATE auto_transactions SET status = 'Claimed' WHERE UPPER(txid) = ?", (clean_txid,))
            conn.commit()
            return float(row[0]), row[1]
        return None, None

def get_user_payments(chat_id):
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT method, amount, txid, status FROM payments WHERE chat_id = ? ORDER BY id DESC LIMIT 10", (chat_id,))
        return cursor.fetchall()

init_db()

# ----------------- 📱 SECURE SMS WEBHOOK -----------------
@app.route('/')
def home():
    return "SMM Bot Server is Alive and 24/7 Running!", 200

@app.route('/sms-webhook', methods=['POST', 'GET'])
def sms_webhook():
    try:
        raw_parts = []
        if request.args: raw_parts.extend([str(v) for v in request.args.values()])
        if request.form: raw_parts.extend([str(v) for v in request.form.values()])
        if request.json and isinstance(request.json, dict): raw_parts.extend([str(v) for v in request.json.values()])
        
        raw_data = request.get_data(as_text=True)
        if raw_data: raw_parts.append(raw_data)
        
        full_text = urllib.parse.unquote(" ".join(raw_parts)).replace('+', ' ')

        trx_match = re.search(r'(?:TrxID|TxnID|TxID|Trx ID|Txn ID)\s*:?\s*([A-Za-z0-9]{8,14})', full_text, re.IGNORECASE)
        amt_match = re.search(r'(?:Tk|Tk\.|Amount)\s*:?\s*([0-9]+(?:\.[0-9]+)?)', full_text, re.IGNORECASE)

        if not trx_match:
            possible_codes = re.findall(r'\b[A-Za-z0-9]{8,12}\b', full_text)
            txid = None
            for code in possible_codes:
                if any(c.isdigit() for c in code) and any(c.isalpha() for c in code):
                    txid = code.strip().upper()
                    break
        else:
            txid = trx_match.group(1).strip().upper()

        if txid:
            amount = float(amt_match.group(1)) if amt_match else 10.0
            method = "Nagad" if ("Nagad" in full_text or "TxnID" in full_text) else "bKash"
            save_auto_sms_trx(txid, amount, method)

            try:
                bot.send_message(MAIN_ADMIN_ID, f"📩 <b>{method} Auto SMS Received!</b>\n\n💵 Amount: <b>{amount:.2f} BDT</b>\n🆔 TrxID: <code>{txid}</code>")
            except Exception:
                pass

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

def get_multiple_orders_status(order_ids):
    if not order_ids: return {}
    try:
        payload = {"key": get_smm_api_key(), "action": "status", "orders": ",".join(map(str, order_ids))}
        response = requests.post(get_smm_api_url(), data=payload, timeout=5)
        res = response.json()
        return res if isinstance(res, dict) else {}
    except Exception:
        return {}

# ================== 👑 এডমিন প্যানেল (/admin) ==================
@bot.message_handler(commands=["admin"])
def admin_panel_command(message):
    if not is_admin(message.chat.id): return

    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [
        types.InlineKeyboardButton("➕ প্ল্যাটফর্ম যোগ", callback_data="admin_add_main_cat"),
        types.InlineKeyboardButton("📂 সাব-ক্যাট যোগ", callback_data="admin_add_sub_cat"),
        types.InlineKeyboardButton("🛒 সার্ভিস যোগ", callback_data="admin_add_service_start"),
        types.InlineKeyboardButton("🔍 ইউজার ব্যালেন্স", callback_data="admin_user_info_start"),
        types.InlineKeyboardButton("📢 ব্রডকাস্ট মেসেজ", callback_data="admin_broadcast_start"),
        types.InlineKeyboardButton("🖼️ স্টার্ট পিকচার", callback_data="admin_set_start_photo"),
        types.InlineKeyboardButton("📝 স্টার্ট টেক্সট", callback_data="admin_set_welcome_text"),
        types.InlineKeyboardButton("📢 জয়েন চ্যানেল", callback_data="admin_force_channel_menu"),
        types.InlineKeyboardButton("🔌 SMM API এডিট", callback_data="admin_set_smm_api"),
        types.InlineKeyboardButton("👑 এডমিন ম্যানেজ", callback_data="admin_manage_co_admins"),
        types.InlineKeyboardButton("🗑️ সার্ভিস ডিলিট", callback_data="admin_delete_single_service_start"),
        types.InlineKeyboardButton("🗑️ প্ল্যাটফর্ম ডিলিট", callback_data="admin_del_main_platform_start"),
        types.InlineKeyboardButton("🗑️ সাব-ক্যাট ডিলিট", callback_data="admin_del_subcategory_start"),
        types.InlineKeyboardButton("📊 সেলস রিপোর্ট", callback_data="admin_live_stats"),
        types.InlineKeyboardButton("💥 অল ডাটা ক্লিয়ার", callback_data="admin_clear_services_confirm")
    ]
    markup.add(*btns)

    bot.send_message(
        message.chat.id,
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "   👑 <b>এডমিন কন্ট্রোল প্যানেল</b> 👑\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n"
        "যেকোনো অপশন কনফিগার করতে নিচের বাটন ব্যবহার করুন:",
        reply_markup=markup
    )

# --- 📢 ব্রডকাস্ট মেসেজ (এডমিন থেকে অল ইউজার) ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast_start")
def admin_broadcast_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 <b>সকল ইউজারের কাছে কি মেসেজ পাঠাতে চান? তা লিখে বা ফটো সহ পাঠান:</b>")
    bot.register_next_step_handler(msg, process_admin_broadcast)

def process_admin_broadcast(message):
    users = get_all_users()
    sent_count = 0
    fail_count = 0
    bot.send_message(message.chat.id, f"⏳ <b>মেসেজ পাঠানো শুরু হচ্ছে... মোট ইউজার: {len(users)}</b>")
    
    for u in users:
        uid = u[0]
        try:
            if message.text:
                bot.send_message(uid, f"📢 <b>অফিশিয়াল নোটিশ:</b>\n\n{message.text}")
            elif message.photo:
                bot.send_photo(uid, message.photo[-1].file_id, caption=f"📢 <b>অফিশিয়াল নোটিশ:</b>\n\n{message.caption or ''}")
            sent_count += 1
            time.sleep(0.05)
        except Exception:
            fail_count += 1

    bot.send_message(message.chat.id, f"✅ <b>ব্রডকাস্ট সম্পন্ন!</b>\n\n✔️ সফল: <b>{sent_count}</b> জন\n❌ ব্যর্থ (বট ব্লকড): <b>{fail_count}</b> জন")

# --- SMM API এডিট ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_set_smm_api")
def admin_set_smm_api(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, f"🔌 <b>বর্তমান API URL:</b> <code>{get_smm_api_url()}</code>\n<b>নতুন API URL টি লিখে পাঠান:</b>")
    bot.register_next_step_handler(msg, save_api_url)

def save_api_url(message):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        bot.send_message(message.chat.id, "❌ <b>ভুল ইউআরএল! http:// বা https:// থাকতে হবে।</b>")
        return
    set_setting("smm_api_url", url)
    msg = bot.send_message(message.chat.id, "🔑 <b>নতুন SMM API Key টি লিখে পাঠান:</b>")
    bot.register_next_step_handler(msg, save_api_key)

def save_api_key(message):
    key = message.text.strip()
    set_setting("smm_api_key", key)
    bot.send_message(message.chat.id, "✅ <b>SMM API সফলভাবে আপডেট করা হয়েছে!</b>")

# --- এডমিন থেকে প্ল্যাটফর্ম/ক্যাট ডিলিট ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_del_main_platform_start")
def admin_del_main_platform_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(call.message.chat.id, "❌ কোনো মেইন প্ল্যাটফর্ম পাওয়া যায়নি।")
        return
    btns = [types.InlineKeyboardButton(f"❌ {mc}", callback_data=f"delmainplatform_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মটি সম্পূর্ণ ডিলিট করবেন?</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmainplatform_"))
def admin_del_main_platform_confirm(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("delmainplatform_", "")
    delete_main_category(mcat_name)
    bot.send_message(call.message.chat.id, f"✅ <b>[{mcat_name}] প্ল্যাটফর্মটি ডিলিট করা হয়েছে!</b>")

@bot.callback_query_handler(func=lambda call: call.data == "admin_del_subcategory_start")
def admin_del_subcategory_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    main_cats = get_main_categories()
    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"delsubcatselectmc_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মের সাব-ক্যাটাগরি ডিলিট করবেন?</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delsubcatselectmc_"))
def admin_del_subcategory_select_sub(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("delsubcatselectmc_", "")
    sub_cats = get_sub_categories(mcat_name)
    btns = [types.InlineKeyboardButton(f"❌ {sc}", callback_data=f"delsubcatconfirm_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, f"🗑️ <b>[{mcat_name}] এর কোন সাব-ক্যাটাগরি ডিলিট করবেন?</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delsubcatconfirm_"))
def admin_del_subcategory_confirm(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    raw_data = call.data.replace("delsubcatconfirm_", "")
    mcat_name, scat_name = raw_data.split("___")
    delete_sub_category(mcat_name, scat_name)
    bot.send_message(call.message.chat.id, f"✅ <b>[{mcat_name}] -> [{scat_name}] সাব-ক্যাটাগরি ডিলিট হয়েছে!</b>")

# --- সেলস ও লাভ ড্যাশবোর্ড ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_live_stats")
def admin_live_stats_callback(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'Approved' AND date(timestamp, 'localtime') = date('now', 'localtime')")
        today_deposit = cursor.fetchone()[0] or 0.0
        cursor.execute("SELECT COUNT(*), SUM(cost) FROM orders WHERE date(timestamp, 'localtime') = date('now', 'localtime')")
        row = cursor.fetchone()
        today_orders_count = row[0] or 0
        today_orders_cost = row[1] or 0.0
        
    stats_text = (
        f"╭━━━━━━━━━━━━━━━━━━━╮\n"
        f"   📊 <b>আজকের সেলস ড্যাশবোর্ড</b> 📊\n"
        f"╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"👥 মোট ইউজার: <b>{total_users} জন</b>\n"
        f"💳 আজকের ডিপোজিট: <b>{today_deposit:.2f} ৳</b>\n"
        f"🛒 আজকের মোট অর্ডার: <b>{today_orders_count} টি</b>\n"
        f"💰 অর্ডারের মোট খরচ: <b>{today_orders_cost:.2f} Coin</b>"
    )
    bot.send_message(call.message.chat.id, stats_text)

# --- এডমিন ম্যানেজমেন্ট ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_manage_co_admins")
def admin_manage_co_admins(call):
    if call.message.chat.id != MAIN_ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ শুধু মেইন এডমিন এটি দেখতে পারবে!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ এডমিন যোগ", callback_data="coadmin_add"),
        types.InlineKeyboardButton("❌ এডমিন রিমুভ", callback_data="coadmin_remove")
    )
    bot.send_message(MAIN_ADMIN_ID, "👑 <b>এডমিন ম্যানেজমেন্ট প্যানেল:</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("coadmin_"))
def coadmin_action(call):
    if call.message.chat.id != MAIN_ADMIN_ID: return
    bot.answer_callback_query(call.id)
    action = call.data.replace("coadmin_", "")
    if action == "add":
        msg = bot.send_message(MAIN_ADMIN_ID, "👤 <b>যাকে এডমিন বানাবেন তার Telegram ID দিন:</b>")
        bot.register_next_step_handler(msg, lambda m: [add_co_admin(int(m.text.strip())), bot.send_message(MAIN_ADMIN_ID, "✅ এডমিন যুক্ত হয়েছে!")])
    elif action == "remove":
        msg = bot.send_message(MAIN_ADMIN_ID, "👤 <b>যাকে রিমুভ করবেন তার Telegram ID দিন:</b>")
        bot.register_next_step_handler(msg, lambda m: [remove_co_admin(int(m.text.strip())), bot.send_message(MAIN_ADMIN_ID, "✅ এডমিন রিমুভ হয়েছে!")])

# --- স্টার্ট ফটো ও টেক্সট ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_set_start_photo")
def admin_set_start_photo(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🖼️ <b>স্টার্ট ফটো লিংক দিন (রিমুভ করতে 0 পাঠান):</b>")
    bot.register_next_step_handler(msg, lambda m: [set_setting("start_photo", "" if m.text.strip()=="0" else m.text.strip()), bot.send_message(m.chat.id, "✅ স্টার্ট ফটো সেভ হয়েছে!")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_welcome_text")
def admin_set_welcome_text(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📝 <b>স্বাগতম টেক্সট লিখে পাঠান (রিসেট করতে 0 দিন):</b>")
    bot.register_next_step_handler(msg, lambda m: [set_setting("welcome_text", "" if m.text.strip()=="0" else m.text.strip()), bot.send_message(m.chat.id, "✅ ওয়েলকাম টেক্সট সেভ হয়েছে!")])

# --- ১. প্ল্যাটফর্ম তৈরি ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_main_cat")
def admin_add_main_cat_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "✍️ <b>নতুন প্ল্যাটফর্মের নাম লিখুন (যেমন: 🎵 TikTok বা 👥 Facebook):</b>")
    bot.register_next_step_handler(msg, lambda m: [add_main_category(m.text.strip()), bot.send_message(m.chat.id, f"✅ প্ল্যাটফর্ম [{m.text.strip()}] তৈরি হয়েছে!")])

# --- ২. সাব-ক্যাটাগরি তৈরি ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_sub_cat")
def admin_add_sub_cat_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(call.message.chat.id, "❌ আগে প্ল্যাটফর্ম যোগ করুন!")
        return
    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"admsubsel_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "📁 <b>কোন প্ল্যাটফর্মের ভেতর সাব-ক্যাট যোগ করবেন?</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admsubsel_"))
def admin_sub_cat_get_name(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("admsubsel_", "")
    msg = bot.send_message(call.message.chat.id, f"✍️ <b>[{mcat_name}] এর সাব-ক্যাটাগরির নাম লিখুন (যেমন: TikTok Views):</b>")
    bot.register_next_step_handler(msg, lambda m: [add_sub_category(mcat_name, m.text.strip()), bot.send_message(m.chat.id, f"✅ সাব-ক্যাটাগরি [{m.text.strip()}] যোগ হয়েছে!")])

# --- ৩. সার্ভিস তৈরি ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_service_start")
def admin_add_service_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    main_cats = get_main_categories()
    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"admcatm_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "📁 <b>প্ল্যাটফর্ম সিলেক্ট করুন:</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcatm_"))
def admin_step_select_sub_for_service(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("admcatm_", "")
    sub_cats = get_sub_categories(mcat_name)
    if not sub_cats:
        bot.send_message(call.message.chat.id, "❌ কোনো সাব-ক্যাটাগরি নেই!")
        return
    btns = [types.InlineKeyboardButton(f"📂 {sc}", callback_data=f"admcats_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, f"📂 <b>[{mcat_name}] সাব-ক্যাটাগরি সিলেক্ট করুন:</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcats_"))
def admin_step_get_choice_id(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    raw_data = call.data.replace("admcats_", "")
    mcat_name, scat_name = raw_data.split("___")
    msg = bot.send_message(call.message.chat.id, f"🆔 <b>চয়েস ID কত দেবেন? (যেমন: 1, 2, 3):</b>")
    bot.register_next_step_handler(msg, admin_step_get_api_id, mcat_name, scat_name)

def admin_step_get_api_id(message, mcat_name, scat_name):
    id_bot = message.text.strip()
    msg = bot.send_message(message.chat.id, "🔌 <b>ওয়েবসাইটের আসল API ID কত? (যেমন: 19138):</b>")
    bot.register_next_step_handler(msg, admin_step_get_direct_coin, mcat_name, scat_name, id_bot)

def admin_step_get_direct_coin(message, mcat_name, scat_name, id_bot):
    api_id = message.text.strip()
    msg = bot.send_message(message.chat.id, "🪙 <b>প্রতি ১০০০টির জন্য কাস্টমার থেকে কত কয়েন কাটবেন? (যেমন: 15):</b>")
    bot.register_next_step_handler(msg, admin_step_get_min_qty, mcat_name, scat_name, id_bot, api_id)

def admin_step_get_min_qty(message, mcat_name, scat_name, id_bot, api_id):
    try:
        coin_price_per_1k = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল ইনপুট!")
        return
    msg = bot.send_message(message.chat.id, "🔢 <b>সর্বনিম্ন কোয়ান্টিটি (Min Qty) কত? (যেমন: 10 বা 100):</b>")
    bot.register_next_step_handler(msg, admin_step_get_name, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k)

def admin_step_get_name(message, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k):
    try:
        min_qty = int(message.text.strip())
    except ValueError:
        min_qty = 10
    msg = bot.send_message(message.chat.id, "📌 <b>সার্ভিসটির নাম লিখে পাঠান:</b>")
    bot.register_next_step_handler(msg, admin_step_save_service, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k, min_qty)

def admin_step_save_service(message, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k, min_qty):
    name = message.text.strip()
    with sqlite3.connect(DB_FILE, timeout=60) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO services (main_cat, sub_cat, id_bot, api_id, name, price_per_1k, min_qty) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (mcat_name, scat_name, id_bot, api_id, name, coin_price_per_1k, min_qty))
        conn.commit()

    bot.send_message(
        message.chat.id,
        f"✅ <b>সার্ভিস সফলভাবে যুক্ত হয়েছে!</b>\n\n"
        f"📁 প্ল্যাটফর্ম: <b>{mcat_name}</b>\n"
        f"📂 সাব-ক্যাট: <b>{scat_name}</b>\n"
        f"🆔 চয়েস ID: <b>{id_bot}</b> | API ID: <b>{api_id}</b>\n"
        f"🪙 প্রাইজ (1K): <b>{coin_price_per_1k:.2f} Coin</b>\n"
        f"🔢 Min Qty: <b>{min_qty}</b>\n"
        f"📌 নাম: <b>{name}</b>"
    )

# --- ৪. সিঙ্গেল সার্ভিস ডিলিট ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_delete_single_service_start")
def admin_delete_single_service_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    main_cats = get_main_categories()
    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"delmcat_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মের সার্ভিস ডিলিট করবেন?</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmcat_"))
def admin_del_select_sub(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("delmcat_", "")
    sub_cats = get_sub_categories(mcat_name)
    btns = [types.InlineKeyboardButton(f"📂 {sc}", callback_data=f"delscat_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, f"🗑️ <b>[{mcat_name}] এর সাব-ক্যাটাগরি সিলেক্ট করুন:</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delscat_"))
def admin_del_select_id(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    raw_data = call.data.replace("delscat_", "")
    mcat_name, scat_name = raw_data.split("___")
    msg = bot.send_message(call.message.chat.id, f"🗑️ <b>[{scat_name}] এর চয়েস ID (1, 2) লিখে পাঠান:</b>")
    bot.register_next_step_handler(msg, lambda m: [delete_single_service(mcat_name, scat_name, m.text.strip()), bot.send_message(m.chat.id, "✅ সার্ভিস ডিলিট করা হয়েছে!")])

# --- ৫. ৪টি চ্যানেল জয়েন ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_force_channel_menu")
def admin_force_channel_menu(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    channels = get_force_channels()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        markup.add(types.InlineKeyboardButton(f"❌ {ch[1]} ডিলিট করুন", callback_data=f"delchan_{ch[0]}"))
    if len(channels) < 4:
        markup.add(types.InlineKeyboardButton("➕ নতুন চ্যানেল যোগ করুন", callback_data="addchan_start"))
    bot.send_message(call.message.chat.id, f"📢 <b>জয়েন চ্যানেল লিস্ট ({len(channels)}/4):</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "addchan_start")
def addchan_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 <b>চ্যানেল ইউজারনেম দিন (@username):</b>")
    bot.register_next_step_handler(msg, addchan_get_link)

def addchan_get_link(message):
    ch_id = message.text.strip()
    msg = bot.send_message(message.chat.id, "🔗 <b>ইনভাইট লিংক দিন:</b>")
    bot.register_next_step_handler(msg, addchan_get_name, ch_id)

def addchan_get_name(message, ch_id):
    link = message.text.strip()
    msg = bot.send_message(message.chat.id, "📌 <b>বাটনের নাম দিন:</b>")
    bot.register_next_step_handler(msg, lambda m: [add_force_channel(ch_id, m.text.strip(), link), bot.send_message(m.chat.id, "✅ চ্যানেল যুক্ত হয়েছে!")])

@bot.callback_query_handler(func=lambda call: call.data.startswith("delchan_"))
def delchan_process(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    delete_force_channel(call.data.replace("delchan_", ""))
    bot.send_message(call.message.chat.id, "✅ চ্যানেলটি সরানো হয়েছে!")

# --- ৬. ইউজার কয়েন এডিট ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_user_info_start")
def admin_user_info_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔍 <b>ইউজারের Telegram ID লিখে পাঠান:</b>")
    bot.register_next_step_handler(msg, admin_process_user_lookup)

def admin_process_user_lookup(message):
    try:
        target_user = int(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল ID!")
        return

    balance = get_balance(target_user)
    total_orders, total_payments = get_user_stats(target_user)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ কয়েন যোগ", callback_data=f"admbal_ADD_{target_user}"),
        types.InlineKeyboardButton("✏️ কয়েন সেট", callback_data=f"admbal_SET_{target_user}")
    )
    info_text = (
        f"👤 <b>ইউজার প্রোফাইল</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: <code>{target_user}</code>\n"
        f"💰 ব্যালেন্স: <b>{balance:.2f} Coin</b>\n"
        f"🛒 মোট অর্ডার: <b>{total_orders} টি</b>\n"
        f"💳 মোট ডিপোজিট: <b>{total_payments} টি</b>"
    )
    bot.send_message(message.chat.id, info_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admbal_"))
def admin_process_balance_action(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    action, target_user = call.data.replace("admbal_", "").split("_")
    target_user = int(target_user)

    if action == "ADD":
        msg = bot.send_message(call.message.chat.id, f"💵 ইউজার <code>{target_user}</code> কে <b>কত কয়েন যোগ করবেন?</b>")
        bot.register_next_step_handler(msg, admin_save_add_balance, target_user)
    elif action == "SET":
        msg = bot.send_message(call.message.chat.id, f"✏️ ইউজার <code>{target_user}</code> এর <b>ব্যালেন্স কত সেট করবেন?</b>")
        bot.register_next_step_handler(msg, admin_save_set_balance, target_user)

def admin_save_add_balance(message, target_user):
    try:
        amount = float(message.text.strip())
        new_balance = get_balance(target_user) + amount
        update_balance(target_user, new_balance)
        bot.send_message(message.chat.id, f"✅ সফল! বর্তমান ব্যালেন্স: <b>{new_balance:.2f} Coin</b>")
        bot.send_message(target_user, f"🎉 <b>আপনার অ্যাকাউন্টে {amount:.2f} Coin যোগ হয়েছে!</b>\nবর্তমান ব্যালেন্স: <b>{new_balance:.2f} Coin</b>")
    except Exception:
        bot.send_message(message.chat.id, "❌ ব্যালেন্স যোগ করা যায়নি।")

def admin_save_set_balance(message, target_user):
    try:
        new_balance = float(message.text.strip())
        update_balance(target_user, new_balance)
        bot.send_message(message.chat.id, f"✅ সফল! নতুন ব্যালেন্স: <b>{new_balance:.2f} Coin</b>")
        bot.send_message(target_user, f"📢 <b>আপনার ব্যালেন্স আপডেট হয়ে {new_balance:.2f} Coin করা হয়েছে।</b>")
    except Exception:
        bot.send_message(message.chat.id, "❌ ব্যালেন্স সেট করা যায়নি।")

# --- ক্লিয়ার ডাটা ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_clear_services_confirm")
def admin_clear_services_callback(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔐 <b>সকল সার্ভিস ও ক্যাটাগরি ডিলিট করতে পিন (12345) লিখুন:</b>")
    bot.register_next_step_handler(msg, process_clear_services_pin)

def process_clear_services_pin(message):
    if message.text.strip() == "12345":
        with sqlite3.connect(DB_FILE, timeout=60) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM services")
            cursor.execute("DELETE FROM main_categories")
            cursor.execute("DELETE FROM sub_categories")
            conn.commit()
        bot.send_message(message.chat.id, "🗑️ <b>সকল ক্যাটাগরি ও সার্ভিস ডিলিট করা হয়েছে!</b>")
    else:
        bot.send_message(message.chat.id, "❌ ভুল পিন কোড!")

# ================== 📱 ইউজার প্যানেল ও মেনু ==================

def get_main_menu_markup(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🛒 নতুন অর্ডার"),
        types.KeyboardButton("👤 আমার অ্যাকাউন্ট"),
        types.KeyboardButton("📜 অর্ডার হিস্ট্রি"),
        types.KeyboardButton("📊 পেমেন্ট হিস্ট্রি"),
        types.KeyboardButton("💳 Buy Coin (টাকা রিচার্জ)"),
        types.KeyboardButton("📞 সাপোর্ট")
    )
    return markup

def enforce_force_join(chat_id):
    unjoined = check_user_joined_all(chat_id)
    if unjoined:
        markup = types.InlineKeyboardMarkup()
        for ch in unjoined:
            markup.add(types.InlineKeyboardButton(f"📢 Join {ch[1]}", url=ch[2]))
        markup.add(types.InlineKeyboardButton("✅ জয়েন সম্পন্ন করেছি", callback_data="verify_channel_joins"))
        bot.send_message(
            chat_id,
            "⚠️ <b>বটটি ব্যবহার করতে নিচের চ্যানেলগুলোতে জয়েন থাকতে হবে:</b>",
            reply_markup=markup
        )
        return False
    return True

@bot.callback_query_handler(func=lambda call: call.data == "verify_channel_joins")
def verify_channel_joins_callback(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    if not check_user_joined_all(chat_id):
        bot.send_message(chat_id, "🎉 <b>ভেরিফিকেশন সফল হয়েছে!</b>", reply_markup=get_main_menu_markup(chat_id))
    else:
        bot.send_message(chat_id, "❌ আপনি এখনো সবগুলো চ্যানেলে জয়েন করেননি!")

@bot.message_handler(commands=["start"])
def start_command(message):
    chat_id = message.chat.id
    add_user(chat_id)
    if enforce_force_join(chat_id):
        send_main_menu(chat_id, message.from_user.first_name)

def send_main_menu(chat_id, first_name):
    safe_name = "ইউজার" if not first_name else first_name.replace("<", "&lt;").replace(">", "&gt;")
    custom_welcome = get_setting("welcome_text")
    welcome_text = custom_welcome.replace("{name}", safe_name) if custom_welcome else (
        f"👋 হ্যালো <b>{safe_name}</b>, স্বাগতম আমাদের <b>SMM বোটে</b>!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <i>এখানে সবচেয়ে কম মূল্যে সকল সোশ্যাল মিডিয়া সার্ভিস পাবেন।</i>\n\n"
        f"👇 <b>সেবা নিতে নিচের বাটনগুলো ব্যবহার করুন:</b>"
    )
    start_photo = get_setting("start_photo")
    if start_photo:
        try:
            bot.send_photo(chat_id, start_photo, caption=welcome_text, reply_markup=get_main_menu_markup(chat_id))
            return
        except Exception:
            pass
    bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_markup(chat_id))

# 🔴 বট মেনু হ্যান্ডলিং
@bot.message_handler(func=lambda message: True)
def handle_menu_buttons(message):
    chat_id = message.chat.id
    if not enforce_force_join(chat_id): return
    text = message.text

    if text == "👤 আমার অ্যাকাউন্ট":
        balance = get_balance(chat_id)
        bot.send_message(
            chat_id,
            f"╭━━━━━━━━━━━━━━━━━━━╮\n"
            f"   👤 <b>আমার অ্যাকাউন্ট ড্যাশবোর্ড</b>\n"
            f"╰━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"🆔 <b>ইউজার আইডি :</b> <code>{chat_id}</code>\n"
            f"💰 <b>বর্তমান ব্যালেন্স :</b> <b>{balance:.2f} Coin</b>\n"
            f"⚡ <i>১ কয়েন = ১ টাকা</i>"
        )

    elif text == "🛒 নতুন অর্ডার":
        show_platforms(chat_id)

    elif text == "💳 Buy Coin (টাকা রিচার্জ)":
        deposit_text = (
            "╭━━━━━━━━━━━━━━━━━━━╮\n"
            "   💎 <b>কয়েন রিচার্জ পদ্ধতি</b> 💎\n"
            "╰━━━━━━━━━━━━━━━━━━━╯\n"
            "💸 <b>১ কয়েন = ১ টাকা</b>\n\n"
            "📱 <b>বিকাশ (Personal):</b> <code>01925263571</code>\n"
            "📱 <b>নগদ (Personal):</b> <code>01925263571</code>\n\n"
            "⚠️ <b>সর্বনিম্ন ১০ কয়েন কিনতে হবে।</b>\n"
            "টাকা পাঠিয়ে নিচের বাটনে ক্লিক করে TrxID সাবমিট করলেই ইনস্ট্যান্ট কয়েন যোগ হবে!"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⚡ TrxID দিয়ে কয়েন নিন", callback_data="verify_auto_trx_start"))
        bot.send_message(chat_id, deposit_text, reply_markup=markup)

    elif text == "📜 অর্ডার হিস্ট্রি":
        orders = get_user_orders(chat_id)
        if not orders:
            bot.send_message(chat_id, "📭 <b>আপনি এখনো কোনো অর্ডার করেননি।</b>")
            return
        order_ids = [o[0] for o in orders]
        statuses = get_multiple_orders_status(order_ids)
        response = "📋 <b>সর্বশেষ ৫টি অর্ডারের স্ট্যাটাস:</b>\n\n"
        for idx, o in enumerate(orders, 1):
            st = statuses.get(str(o[0]), {}).get("status", "Processing") if isinstance(statuses, dict) else "Processing"
            response += (
                f"<b>{idx}. {o[1]}</b>\n"
                f"🆔 আইডি: <code>{o[0]}</code> | 🔢 কোয়ান্টিটি: <b>{o[2]}</b>\n"
                f"💵 খরচ: <b>{o[3]:.2f} Coin</b> | 🚦 স্ট্যাটাস: <b>{st}</b>\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            )
        bot.send_message(chat_id, response)

    elif text == "📊 পেমেন্ট হিস্ট্রি":
        payments = get_user_payments(chat_id)
        if not payments:
            bot.send_message(chat_id, "📭 কোনো পেমেন্ট রেকর্ড পাওয়া যায়নি।")
            return
        response = "📊 <b>সর্বশেষ পেমেন্ট হিস্ট্রি:</b>\n\n"
        for idx, p in enumerate(payments, 1):
            response += f"<b>{idx}. {p[0]}</b> ⎯ <b>{p[1]:.2f} Coin</b>\n🆔 TrxID: <code>{p[2]}</code> | স্ট্যাটাস: <b>{p[3]}</b>\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        bot.send_message(chat_id, response)

    elif text == "📞 সাপোর্ট":
        bot.send_message(
            chat_id,
            "╭━━━━━━━━━━━━━━━━━━━╮\n"
            "      📞 <b>এডমিন হেল্পলাইন</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
            "💬 টেলিগ্রাম: @Mr_Sojol_Ceo\n"
            "📱 হোয়াটসঅ্যাপ: +8801925263571\n\n"
            "<i>যেকোনো সমস্যায় এডমিনের সাথে যোগাযোগ করুন।</i>"
        )

# ----------------- ৩-লেভেল অর্ডার নেভিগেশন ও ব্যাক বাটন -----------------

def show_platforms(chat_id, message_id=None):
    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(chat_id, "❌ বর্তমানে কোনো সার্ভিস চালু নেই।")
        return
    btns = [types.InlineKeyboardButton(f"✨ {mc}", callback_data=f"mcat_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    text = "📂 <b>সোশ্যাল মিডিয়া প্ল্যাটফর্ম নির্বাচন করুন:</b>"
    if message_id:
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            return
        except Exception:
            pass
    bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mcat_"))
def handle_main_category(call):
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("mcat_", "")
    sub_cats = get_sub_categories(mcat_name)
    if not sub_cats:
        bot.answer_callback_query(call.id, "❌ কোনো সাব-ক্যাটাগরি নেই!", show_alert=True)
        return
    btns = [types.InlineKeyboardButton(f"📁 {sc}", callback_data=f"scat_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)
    markup.add(types.InlineKeyboardButton("⬅️ পিছনে যান (প্ল্যাটফর্ম লিস্ট)", callback_data="back_to_platforms"))
    
    bot.edit_message_text(f"📁 <b>[{mcat_name}]</b> এর সাব-ক্যাটাগরি সিলেক্ট করুন:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_platforms")
def back_to_platforms_callback(call):
    bot.answer_callback_query(call.id)
    show_platforms(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("scat_"))
def handle_sub_category(call):
    bot.answer_callback_query(call.id)
    raw_data = call.data.replace("scat_", "")
    mcat_name, scat_name = raw_data.split("___")
    services_list = get_services_by_sub_cat(mcat_name, scat_name)
    
    if not services_list:
        bot.send_message(call.message.chat.id, "❌ এই ক্যাটাগরিতে সার্ভিস নেই।")
        return

    response_text = f"╭━━━━━━━━━━━━━━━━━━━╮\n   ✨ <b>{scat_name} সার্ভিসসমূহ</b> ✨\n╰━━━━━━━━━━━━━━━━━━━╯\n\n"
    for s in services_list:
        response_text += (
            f"🆔 <b>আইডি: {s['id']}</b> ⎯ {s['name']}\n"
            f"💰 মূল্য: <b>{s['price_per_1k']:.2f} Coin</b> (1K)\n"
            f"🔢 সর্বনিম্ন: <b>{s['min_qty']} টি</b>\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        )
    response_text += "\n✍️ <b>যেই সার্ভিসটি নিতে চান তার আইডি (যেমন: 1, 2) লিখে পাঠান:</b>"
    
    msg = bot.send_message(call.message.chat.id, response_text)
    bot.register_next_step_handler(msg, get_service_id, services_list)

def get_service_id(message, services_list):
    user_input = message.text.strip()
    selected_service = next((s for s in services_list if str(s["id"]) == user_input), None)
    if not selected_service:
        bot.send_message(message.chat.id, "❌ ভুল আইডি! পুনরায় চেষ্টা করুন।")
        return

    msg = bot.send_message(message.chat.id, f"🔗 <b>আপনার লিংকটি পাঠান:</b>\n(সর্বনিম্ন অর্ডার: {selected_service['min_qty']} টি)")
    bot.register_next_step_handler(msg, get_link, selected_service)

def get_link(message, selected_service):
    link = message.text.strip()
    if not link.startswith("http"):
        bot.send_message(message.chat.id, "❌ সঠিক লিংক পাঠান (http/https সহ)।")
        return
    msg = bot.send_message(message.chat.id, f"🔢 <b>কোয়ান্টিটি (Quantity) লিখুন:</b>\n(সর্বনিম্ন: {selected_service['min_qty']} টি)")
    bot.register_next_step_handler(msg, get_quantity, selected_service, link)

def get_quantity(message, selected_service, link):
    if not message.text.strip().isdigit():
        bot.send_message(message.chat.id, "❌ শুধুমাত্র সংখ্যা লিখুন।")
        return

    qty = int(message.text.strip())
    if qty < selected_service['min_qty']:
        bot.send_message(message.chat.id, f"❌ সর্বনিম্ন {selected_service['min_qty']} টি অর্ডার করতে হবে!")
        return

    cost = max(1.0, (qty / 1000.0) * selected_service['price_per_1k'])
    user_bal = get_balance(message.chat.id)

    if user_bal < cost:
        bot.send_message(message.chat.id, f"❌ <b>অপর্যাপ্ত ব্যালেন্স!</b>\nপ্রয়োজন: <b>{cost:.2f} Coin</b>\nব্যালেন্স: <b>{user_bal:.2f} Coin</b>")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("✅ কনফার্ম করুন"), types.KeyboardButton("❌ বাতিল করুন"))
    msg = bot.send_message(message.chat.id, f"💵 মোট মূল্য: <b>{cost:.2f} Coin</b>\nকনফার্ম করতে নিচের বাটনে চাপুন:", reply_markup=markup)
    bot.register_next_step_handler(msg, confirm_order_final, selected_service, link, qty, cost)

def confirm_order_final(message, selected_service, link, quantity, estimated_cost):
    chat_id = message.chat.id
    if message.text.strip() == "✅ কনফার্ম করুন":
        user_balance = get_balance(chat_id)
        if user_balance < estimated_cost:
            bot.send_message(chat_id, "❌ পর্যাপ্ত ব্যালেন্স নেই।", reply_markup=get_main_menu_markup(chat_id))
            return

        payload = {
            "key": get_smm_api_key(),
            "action": "add",
            "service": selected_service["api_id"],
            "link": link,
            "quantity": quantity,
        }
        try:
            res = requests.post(get_smm_api_url(), data=payload, timeout=15).json()
            if isinstance(res, dict) and "order" in res:
                new_bal = user_balance - estimated_cost
                update_balance(chat_id, new_bal)
                add_order_to_db(res["order"], chat_id, selected_service["name"], quantity, estimated_cost)

                bot.send_message(
                    chat_id,
                    f"🎉 <b>অর্ডার সফল হয়েছে!</b>\n\n"
                    f"📌 সার্ভিস: <b>{selected_service['name']}</b>\n"
                    f"🔢 পরিমাণ: <b>{quantity}</b> | 💵 খরচ: <b>{estimated_cost:.2f} Coin</b>\n"
                    f"🆔 অর্ডার ID: <code>{res['order']}</code>\n"
                    f"💰 অবশিষ্ট ব্যালেন্স: <b>{new_bal:.2f} Coin</b>",
                    reply_markup=get_main_menu_markup(chat_id)
                )
            else:
                bot.send_message(chat_id, f"❌ অর্ডার ব্যর্থ: {res.get('error', 'সার্ভার ত্রুটি')}", reply_markup=get_main_menu_markup(chat_id))
        except Exception:
            bot.send_message(chat_id, "❌ API সার্ভার সংযোগে সমস্যা হয়েছে!", reply_markup=get_main_menu_markup(chat_id))
    else:
        bot.send_message(chat_id, "❌ অর্ডারটি বাতিল করা হয়েছে।", reply_markup=get_main_menu_markup(chat_id))

# ----------------- 💳 অটো ডিপোজিট ভেরিফিকেশন -----------------
@bot.callback_query_handler(func=lambda call: call.data == "verify_auto_trx_start")
def start_auto_trx_input(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    msg = bot.send_message(chat_id, "👉 বিকাশ/নগদে টাকা পাঠানোর পর প্রাপ্ত <b>TrxID (Transaction ID)</b> টি এখানে লিখে পাঠান:")
    bot.register_next_step_handler(msg, process_auto_trx_claim)

def process_auto_trx_claim(message):
    chat_id = message.chat.id
    user_txid = message.text.strip().upper()

    if len(user_txid) < 8 or len(user_txid) > 15:
        bot.send_message(chat_id, "❌ ভুল TrxID ফরম্যাট! সঠিক আইডি দিন।")
        return

    amount, method = claim_auto_trx(user_txid)
    if amount and method:
        new_balance = get_balance(chat_id) + amount
        update_balance(chat_id, new_balance)
        add_payment_to_db(chat_id, method, amount, user_txid, status='Approved')

        bot.send_message(
            chat_id,
            f"🎉 <b>পেমেন্ট সফলভাবে যোগ হয়েছে!</b>\n\n"
            f"💳 মেথড: <b>{method}</b>\n"
            f"🪙 প্রাপ্ত কয়েন: <b>{amount:.2f} Coin</b>\n"
            f"💰 বর্তমান ব্যালেন্স: <b>{new_balance:.2f} Coin</b>"
        )
        try:
            bot.send_message(MAIN_ADMIN_ID, f"🔔 <b>Auto Deposit Success!</b>\n👤 User: <code>{chat_id}</code>\n🪙 Amount: <b>{amount:.2f}</b> ({method})\n🆔 TxID: <code>{user_txid}</code>")
        except Exception:
            pass
    else:
        bot.send_message(
            chat_id,
            "❌ <b>ট্রানজেকশন আইডি পাওয়া যায়নি অথবা ইতিমধ্যে ক্লেইম করা হয়েছে!</b>\n\n"
            "১. টাকা পাঠানোর ১-২ মিনিট পর ট্রাই করুন।\n"
            "২. সমস্যা হলে এডমিনের সাথে যোগাযোগ করুন।"
        )

# ----------------- 🚀 FLASK & BOT THREAD -----------------
def start_bot_polling():
    while True:
        try:
            bot.polling(none_stop=True, skip_pending=True, timeout=60)
        except Exception:
            time.sleep(3)

if __name__ == "__main__":
    print("🤖 SMM BOT IS RUNNING SUCCESSFULLY...")
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    start_bot_polling()
