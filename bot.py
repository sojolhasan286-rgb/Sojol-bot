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

# ----------------- à¦†à¦ªà¦¨à¦¾à¦° à¦¬à§‹à¦Ÿà§‡à¦° à¦®à§‚à¦² à¦¸à§‡à¦Ÿà¦¿à¦‚à¦¸ -----------------
BOT_TOKEN = "8899197686:AAGq1I806XgwIzNjdyQada9HykdyGciBO8g"
SMMSUN_API_URL = "https://socialpanel.pro/api/v2"
SMMSUN_API_KEY = "14f3163c337f51c7c90c6232d9428bc2"
MAIN_ADMIN_ID = 6851638362 

USD_TO_BDT = 120.0     # à§§ à¦¡à¦²à¦¾à¦° = à§§à§¨à§¦ à¦•à§Ÿà§‡à¦¨ (à§§ à¦•à§Ÿà§‡à¦¨ = à§§ à¦Ÿà¦¾à¦•à¦¾)
# --------------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "users.db")

# ðŸ”´ à¦¬à¦¾à¦Ÿà¦¨ à¦ªà¦¾à¦¶à¦¾à¦ªà¦¾à¦¶à¦¿ à§¨à¦Ÿà¦¿ à¦•à¦°à§‡ à¦¸à¦¾à¦œà¦¾à¦¨à§‹à¦° à¦¹à§‡à¦²à§à¦ªà¦¾à¦° à¦«à¦¾à¦‚à¦¶à¦¨ (Side-by-Side 2 Columns)
def create_2col_markup(button_list):
    markup = types.InlineKeyboardMarkup()
    for i in range(0, len(button_list), 2):
        if i + 1 < len(button_list):
            markup.row(button_list[i], button_list[i+1])
        else:
            markup.row(button_list[i])
    return markup

# ----------------- à¦¡à¦¾à¦Ÿà¦¾à¦¬à§‡à¦œ à¦¸à§‡à¦Ÿà¦†à¦ª -----------------
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

def get_smm_api_url():
    val = get_setting("smm_api_url")
    return val if val else SMMSUN_API_URL

def get_smm_api_key():
    val = get_setting("smm_api_key")
    return val if val else SMMSUN_API_KEY

def is_admin(chat_id):
    if chat_id == MAIN_ADMIN_ID:
        return True
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def add_co_admin(admin_id):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO admins VALUES (?)", (admin_id,))
    conn.commit()
    conn.close()

def remove_co_admin(admin_id):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
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

# --- à¦œà§Ÿà§‡à¦¨ à¦šà§à¦¯à¦¾à¦¨à§‡à¦² à¦«à¦¾à¦‚à¦¶à¦¨à¦¸à¦®à§‚à¦¹ ---
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

# --- à§©-à¦²à§‡à¦­à§‡à¦² à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¡à¦¾à¦Ÿà¦¾à¦¬à§‡à¦œ à¦¹à§‡à¦²à§à¦ªà¦¾à¦° ---
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
                   (txid.strip().upper(), amount, method))
    conn.commit()
    conn.close()

def claim_auto_trx(txid):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    clean_txid = txid.strip().upper()
    cursor.execute("SELECT amount, method, status FROM auto_transactions WHERE UPPER(txid) = ?", (clean_txid,))
    row = cursor.fetchone()
    if row and row[2] == 'Unclaimed':
        cursor.execute("UPDATE auto_transactions SET status = 'Claimed' WHERE UPPER(txid) = ?", (clean_txid,))
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

# ----------------- ðŸ“± 100% CATCH ALL SMS WEBHOOK -----------------
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
            for code in possible_codes:
                if any(c.isdigit() for c in code) and any(c.isalpha() for c in code):
                    txid = code.strip().upper()
                    break
            else:
                txid = None
        else:
            txid = trx_match.group(1).strip().upper()

        if txid:
            amount = float(amt_match.group(1)) if amt_match else 10.0
            method = "Nagad" if ("Nagad" in full_text or "TxnID" in full_text) else "bKash"

            save_auto_sms_trx(txid, amount, method)

            try:
                bot.send_message(MAIN_ADMIN_ID, f"ðŸ“© <b>{method} Auto SMS Received!</b>\n\nðŸ’µ Amount: <b>{amount:.2f} BDT</b>\nðŸ†” TrxID: <code>{txid}</code>", parse_mode="HTML")
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
            "key": get_smm_api_key(),
            "action": "status",
            "orders": ",".join(map(str, order_ids))
        }
        response = requests.post(get_smm_api_url(), data=payload, timeout=3)
        res = response.json()
        return res if isinstance(res, dict) else {}
    except Exception:
        return {}

# ================== ðŸ‘‘ à¦à¦¡à¦®à¦¿à¦¨ à¦ªà§à¦¯à¦¾à¦¨à§‡à¦² (/admin) ==================

@bot.message_handler(commands=["admin"])
def admin_panel_command(message):
    if not is_admin(message.chat.id):
        return

    btn1 = types.InlineKeyboardButton("âž• à¦®à§‡à¦‡à¦¨ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦® à¦¯à§‹à¦—", callback_data="admin_add_main_cat")
    btn2 = types.InlineKeyboardButton("ðŸ“‚ à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¯à§‹à¦—", callback_data="admin_add_sub_cat")
    btn3 = types.InlineKeyboardButton("ðŸ›’ à¦¨à¦¤à§à¦¨ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¯à§‹à¦—", callback_data="admin_add_service_start")
    btn4 = types.InlineKeyboardButton("ðŸ” à¦‡à¦‰à¦œà¦¾à¦° à¦‡à¦¨à¦«à§‹ à¦“ à¦•à¦¯à¦¼à§‡à¦¨", callback_data="admin_user_info_start")
    btn5 = types.InlineKeyboardButton("ðŸ–¼ï¸ à¦¸à§à¦Ÿà¦¾à¦°à§à¦Ÿ à¦ªà¦¿à¦•à¦šà¦¾à¦° à¦¸à§‡à¦Ÿ", callback_data="admin_set_start_photo")
    btn6 = types.InlineKeyboardButton("ðŸ“ à¦¸à§à¦Ÿà¦¾à¦°à§à¦Ÿ à¦¡à¦¿à¦¸à¦•à§à¦°à¦¿à¦ªà¦¶à¦¨ à¦¸à§‡à¦Ÿ", callback_data="admin_set_welcome_text")
    btn7 = types.InlineKeyboardButton("ðŸ“¢ à¦œà§Ÿà§‡à¦¨ à¦šà§à¦¯à¦¾à¦¨à§‡à¦² à¦¸à§‡à¦Ÿà¦†à¦ª", callback_data="admin_force_channel_menu")
    btn8 = types.InlineKeyboardButton("ðŸ”Œ SMM API à¦à¦¡à¦¿à¦Ÿ", callback_data="admin_set_smm_api")
    btn9 = types.InlineKeyboardButton("ðŸ‘‘ à¦à¦¡à¦®à¦¿à¦¨ à¦¯à§‹à¦—/à¦°à¦¿à¦®à§à¦­", callback_data="admin_manage_co_admins")
    btn10 = types.InlineKeyboardButton("ðŸ—‘ï¸ à¦à¦•à¦Ÿà¦¿ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¡à¦¿à¦²à¦¿à¦Ÿ", callback_data="admin_delete_single_service_start")
    btn11 = types.InlineKeyboardButton("ðŸ’¥ à¦¸à¦•à¦² à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¡à¦¿à¦²à¦¿à¦Ÿ", callback_data="admin_clear_services_confirm")

    markup = create_2col_markup([btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11])

    bot.send_message(
        message.chat.id,
        "ðŸ‘‘ <b>à¦à¦¡à¦®à¦¿à¦¨ à¦•à¦¨à§à¦Ÿà§à¦°à§‹à¦² à¦ªà§à¦¯à¦¾à¦¨à§‡à¦²</b>\n"
        "â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
        "à¦¨à¦¿à¦šà§‡à¦° à¦¬à¦¾à¦Ÿà¦¨ à¦šà§‡à¦ªà§‡ à¦¯à§‡à¦•à§‹à¦¨à§‹ à¦•à¦¾à¦œ à¦¸à¦¿à¦²à§‡à¦•à§à¦Ÿ à¦•à¦°à§à¦¨:",
        reply_markup=markup,
        parse_mode="HTML"
    )

# --- SMM API à¦à¦¡à¦¿à¦Ÿ ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_set_smm_api")
def admin_set_smm_api(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, f"ðŸ”Œ <b>à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ API URL:</b> <code>{get_smm_api_url()}</code>\n<b>à¦¨à¦¤à§à¦¨ API URL à¦Ÿà¦¿ à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:</b>\n(à¦¯à§‡à¦®à¦¨: `https://socialpanel.pro/api/v2`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_api_url)

def save_api_url(message):
    url = message.text.strip()
    set_setting("smm_api_url", url)
    msg = bot.send_message(message.chat.id, "ðŸ”‘ <b>à¦à¦–à¦¨ à¦†à¦ªà¦¨à¦¾à¦° à¦¨à¦¤à§à¦¨ SMM API Key à¦Ÿà¦¿ à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_api_key)

def save_api_key(message):
    key = message.text.strip()
    set_setting("smm_api_key", key)
    bot.send_message(message.chat.id, "âœ… <b>SMM API URL & Key à¦¸à¦«à¦²à¦­à¦¾à¦¬à§‡ à¦†à¦ªà¦¡à§‡à¦Ÿ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡!</b>", parse_mode="HTML")

# --- à¦à¦¡à¦®à¦¿à¦¨ à¦®à§à¦¯à¦¾à¦¨à§‡à¦œà¦®à§‡à¦¨à§à¦Ÿ ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_manage_co_admins")
def admin_manage_co_admins(call):
    if call.message.chat.id != MAIN_ADMIN_ID:
        bot.answer_callback_query(call.id, "âŒ à¦¶à§à¦§à§ à¦®à§‡à¦‡à¦¨ à¦à¦¡à¦®à¦¿à¦¨ à¦à¦Ÿà¦¿ à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦•à¦°à¦¤à§‡ à¦ªà¦¾à¦°à¦¬à§‡!", show_alert=True)
        return
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("âž• à¦¨à¦¤à§à¦¨ à¦à¦¡à¦®à¦¿à¦¨ à¦¯à§‹à¦—", callback_data="coadmin_add")
    btn2 = types.InlineKeyboardButton("âŒ à¦à¦¡à¦®à¦¿à¦¨ à¦°à¦¿à¦®à§à¦­", callback_data="coadmin_remove")
    markup.add(btn1, btn2)

    bot.send_message(MAIN_ADMIN_ID, "ðŸ‘‘ <b>à¦à¦¡à¦®à¦¿à¦¨ à¦®à§à¦¯à¦¾à¦¨à§‡à¦œà¦®à§‡à¦¨à§à¦Ÿ à¦ªà§à¦¯à¦¾à¦¨à§‡à¦²</b>\n\nà¦¨à¦¿à¦šà§‡à¦° à¦¬à¦¾à¦Ÿà¦¨ à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦•à¦°à§à¦¨:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("coadmin_"))
def coadmin_action(call):
    if call.message.chat.id != MAIN_ADMIN_ID: return
    bot.answer_callback_query(call.id)
    action = call.data.replace("coadmin_", "")

    if action == "add":
        msg = bot.send_message(MAIN_ADMIN_ID, "ðŸ‘¤ <b>à¦¯à¦¾à¦•à§‡ à¦à¦¡à¦®à¦¿à¦¨ à¦¬à¦¾à¦¨à¦¾à¦¬à§‡à¦¨, à¦¤à¦¾à¦° à¦Ÿà§‡à¦²à¦¿à¦—à§à¦°à¦¾à¦® à¦‡à¦‰à¦œà¦¾à¦° ID à¦¦à¦¿à¦¨:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_co_admin)
    elif action == "remove":
        msg = bot.send_message(MAIN_ADMIN_ID, "ðŸ‘¤ <b>à¦¯à¦¾à¦•à§‡ à¦à¦¡à¦®à¦¿à¦¨ à¦¥à§‡à¦•à§‡ à¦°à¦¿à¦®à§à¦­ à¦•à¦°à¦¬à§‡à¦¨, à¦¤à¦¾à¦° à¦‡à¦‰à¦œà¦¾à¦° ID à¦¦à¦¿à¦¨:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, remove_co_admin_save)

def save_co_admin(message):
    try:
        aid = int(message.text.strip())
        add_co_admin(aid)
        bot.send_message(MAIN_ADMIN_ID, f"âœ… à¦‡à¦‰à¦œà¦¾à¦° <code>{aid}</code> à¦•à§‡ à¦à¦¡à¦®à¦¿à¦¨ à¦¬à¦¾à¦¨à¦¾à¦¨à§‹ à¦¹à§Ÿà§‡à¦›à§‡!", parse_mode="HTML")
    except ValueError:
        bot.send_message(MAIN_ADMIN_ID, "âŒ à¦­à§à¦² à¦‡à¦‰à¦œà¦¾à¦° ID!")

def remove_co_admin_save(message):
    try:
        aid = int(message.text.strip())
        remove_co_admin(aid)
        bot.send_message(MAIN_ADMIN_ID, f"âœ… à¦‡à¦‰à¦œà¦¾à¦° <code>{aid}</code> à¦•à§‡ à¦à¦¡à¦®à¦¿à¦¨ à¦¥à§‡à¦•à§‡ à¦¸à¦°à¦¿à§Ÿà§‡ à¦¦à§‡à¦“à§Ÿà¦¾ à¦¹à§Ÿà§‡à¦›à§‡!", parse_mode="HTML")
    except ValueError:
        bot.send_message(MAIN_ADMIN_ID, "âŒ à¦­à§à¦² à¦‡à¦‰à¦œà¦¾à¦° ID!")

# --- à¦¸à§à¦Ÿà¦¾à¦°à§à¦Ÿ à¦¡à§‡à¦¸à¦•à§à¦°à¦¿à¦ªà¦¶à¦¨ à¦¸à§‡à¦Ÿà¦¿à¦‚ ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_set_start_photo")
def admin_set_start_photo(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "ðŸ–¼ï¸ <b>à¦¬à§‹à¦Ÿ à¦¸à§à¦Ÿà¦¾à¦°à§à¦Ÿà§‡à¦° à¦«à¦Ÿà§‹ à¦²à¦¿à¦‚à¦• (Direct Image URL) à¦¦à¦¿à¦¨:</b>\n(à¦¯à§‡à¦®à¦¨: `https://i.ibb.co/xxxxx/image.jpg` à¦¬à¦¾ à¦°à¦¿à¦®à§à¦­ à¦•à¦°à¦¤à§‡ `0` à¦ªà¦¾à¦ à¦¾à¦¨):", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_start_photo)

def save_start_photo(message):
    url = message.text.strip()
    if url == "0":
        set_setting("start_photo", "")
        bot.send_message(message.chat.id, "âœ… <b>à¦¸à§à¦Ÿà¦¾à¦°à§à¦Ÿ à¦ªà¦¿à¦•à¦šà¦¾à¦° à¦°à¦¿à¦®à§à¦­ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡!</b>", parse_mode="HTML")
    else:
        set_setting("start_photo", url)
        bot.send_message(message.chat.id, "âœ… <b>à¦¸à§à¦Ÿà¦¾à¦°à§à¦Ÿ à¦ªà¦¿à¦•à¦šà¦¾à¦° à¦¸à¦«à¦²à¦­à¦¾à¦¬à§‡ à¦¸à§‡à¦Ÿ à¦¹à§Ÿà§‡à¦›à§‡!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_welcome_text")
def admin_set_welcome_text(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "ðŸ“ <b>à¦¬à§‹à¦Ÿà§‡à¦° à¦ªà§à¦°à§‹à¦«à¦¾à¦‡à¦² à¦¡à§‡à¦¸à¦•à§à¦°à¦¿à¦ªà¦¶à¦¨ à¦Ÿà§‡à¦•à§à¦¸à¦Ÿ à¦Ÿà¦¾à¦‡à¦ª à¦•à¦°à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:</b>\n(à¦°à¦¿à¦¸à§‡à¦Ÿ à¦•à¦°à¦¤à§‡ `0` à¦ªà¦¾à¦ à¦¾à¦¨)", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_welcome_text)

def save_welcome_text(message):
    txt = message.text.strip()
    if txt == "0":
        set_setting("welcome_text", "")
        bot.send_message(message.chat.id, "âœ… <b>à¦¡à§‡à¦¸à¦•à§à¦°à¦¿à¦ªà¦¶à¦¨ à¦¡à¦¿à¦«à¦²à§à¦Ÿ à¦¸à§‡à¦Ÿà¦¿à¦‚à§Ÿà§‡ à¦«à¦¿à¦°à§‡ à¦—à§‡à¦›à§‡!</b>", parse_mode="HTML")
    else:
        set_setting("welcome_text", txt)
        try:
            bot.set_my_description(txt)
            bot.set_my_short_description(txt)
        except Exception:
            pass
        bot.send_message(message.chat.id, "âœ… <b>à¦¨à¦¤à§à¦¨ à¦ªà§à¦°à§‹à¦«à¦¾à¦‡à¦² à¦¡à§‡à¦¸à¦•à§à¦°à¦¿à¦ªà¦¶à¦¨ à¦¸à§‡à¦­ à¦¹à§Ÿà§‡à¦›à§‡!</b>", parse_mode="HTML")

# --- 1. à¦®à§‡à¦‡à¦¨ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦® à¦¯à§‹à¦— ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_main_cat")
def admin_add_main_cat_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "âœï¸ <b>à¦¨à¦¤à§à¦¨ à¦®à§‡à¦‡à¦¨ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦®à§‡à¦° à¦¨à¦¾à¦® à¦²à¦¿à¦–à§à¦¨:</b>\n(à¦¯à§‡à¦®à¦¨: `ðŸŽµ TikTok Service` à¦¬à¦¾ `ðŸ‘¥ Facebook Service`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_save_main_cat)

def admin_save_main_cat(message):
    mcat_name = message.text.strip()
    add_main_category(mcat_name)
    bot.send_message(message.chat.id, f"âœ… <b>à¦®à§‡à¦‡à¦¨ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦® [{mcat_name}] à¦¤à§ˆà¦°à¦¿ à¦¹à§Ÿà§‡à¦›à§‡!</b>", parse_mode="HTML")

# --- 2. à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¯à§‹à¦— ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_sub_cat")
def admin_add_sub_cat_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)

    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(call.message.chat.id, "âŒ à¦†à¦—à§‡ à¦®à§‡à¦‡à¦¨ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦® à¦¤à§ˆà¦°à¦¿ à¦•à¦°à§à¦¨!", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"ðŸ“ {mc}", callback_data=f"admsubsel_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "ðŸ“ <b>à¦•à§‹à¦¨ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦®à§‡à¦° à¦­à§‡à¦¤à¦°à§‡ à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¯à§‹à¦— à¦•à¦°à¦¬à§‡à¦¨?</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admsubsel_"))
def admin_sub_cat_get_name(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("admsubsel_", "")

    msg = bot.send_message(call.message.chat.id, f"âœï¸ <b>[{mcat_name}] à¦à¦° à¦¨à¦¤à§à¦¨ à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿à¦° à¦¨à¦¾à¦® à¦²à¦¿à¦–à§à¦¨:</b>\n(à¦¯à§‡à¦®à¦¨: `TikTok View` à¦¬à¦¾ `FB Like`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_save_sub_cat, mcat_name)

def admin_save_sub_cat(message, mcat_name):
    sub_name = message.text.strip()
    add_sub_category(mcat_name, sub_name)
    bot.send_message(message.chat.id, f"âœ… <b>[{mcat_name}] -> [{sub_name}] à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¤à§ˆà¦°à¦¿ à¦¹à§Ÿà§‡à¦›à§‡!</b>", parse_mode="HTML")

# --- 3. à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¯à§‹à¦— ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_service_start")
def admin_add_service_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)

    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(call.message.chat.id, "âŒ à¦•à§‹à¦¨à§‹ à¦®à§‡à¦‡à¦¨ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦® à¦¨à§‡à¦‡! à¦†à¦—à§‡ à¦®à§‡à¦‡à¦¨ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦® à¦¯à§‹à¦— à¦•à¦°à§à¦¨à¥¤", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"ðŸ“ {mc}", callback_data=f"admcatm_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "ðŸ“ <b>à¦®à§‡à¦‡à¦¨ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦® à¦¸à¦¿à¦²à§‡à¦•à§à¦Ÿ à¦•à¦°à§à¦¨:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcatm_"))
def admin_step_select_sub_for_service(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("admcatm_", "")

    sub_cats = get_sub_categories(mcat_name)
    if not sub_cats:
        bot.send_message(call.message.chat.id, f"âŒ [{mcat_name}] à¦ à¦•à§‹à¦¨à§‹ à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¨à§‡à¦‡! à¦†à¦—à§‡ à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¯à§‹à¦— à¦•à¦°à§à¦¨à¥¤", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"ðŸ“‚ {sc}", callback_data=f"admcats_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, f"ðŸ“‚ <b>[{mcat_name}] à¦à¦° à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¸à¦¿à¦²à§‡à¦•à§à¦Ÿ à¦•à¦°à§à¦¨:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcats_"))
def admin_step_get_choice_id(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)

    raw_data = call.data.replace("admcats_", "")
    mcat_name, scat_name = raw_data.split("___")

    msg = bot.send_message(call.message.chat.id, f"ðŸ†” <b>[{scat_name}]</b>\nà¦•à¦¾à¦¸à§à¦Ÿà¦®à¦¾à¦° à¦šà§Ÿà§‡à¦¸ ID à¦•à¦¤ à¦¦à§‡à¦¬à§‡à¦¨? (à¦¯à§‡à¦®à¦¨: 1, 2, 3 à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_api_id, mcat_name, scat_name)

def admin_step_get_api_id(message, mcat_name, scat_name):
    id_bot = message.text.strip()
    msg = bot.send_message(message.chat.id, f"ðŸ”Œ à¦“à§Ÿà§‡à¦¬à¦¸à¦¾à¦‡à¦Ÿà§‡à¦° <b>à¦†à¦¸à¦² API ID</b> à¦Ÿà¦¿ à¦•à¦¤? (à¦¯à§‡à¦®à¦¨: 19138):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_direct_coin, mcat_name, scat_name, id_bot)

def admin_step_get_direct_coin(message, mcat_name, scat_name, id_bot):
    api_id = message.text.strip()
    msg = bot.send_message(message.chat.id, "ðŸª™ <b>à¦ªà§à¦°à¦¤à¦¿ à§§à§¦à§¦à§¦à¦Ÿà¦¿à¦° à¦œà¦¨à§à¦¯ à¦•à¦¾à¦¸à§à¦Ÿà¦®à¦¾à¦° à¦¥à§‡à¦•à§‡ à¦•à¦¤ à¦•à§Ÿà§‡à¦¨ (Coin) à¦•à¦¾à¦Ÿà¦¬à§‡à¦¨?</b>\n(à¦¯à§‡à¦®à¦¨: 10, 15 à¦¬à¦¾ 50 à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_min_qty, mcat_name, scat_name, id_bot, api_id)

def admin_step_get_min_qty(message, mcat_name, scat_name, id_bot, api_id):
    try:
        coin_price_per_1k = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "âŒ à¦­à§à¦² à¦•à§Ÿà§‡à¦¨ à¦¦à¦¾à¦®!")
        return

    msg = bot.send_message(message.chat.id, "ðŸ”¢ à¦à¦‡ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸à§‡à¦° à¦œà¦¨à§à¦¯ <b>à¦¸à¦°à§à¦¬à¦¨à¦¿à¦®à§à¦¨ à¦•à§‹à§Ÿà¦¾à¦¨à§à¦Ÿà¦¿à¦Ÿà¦¿ (Min Qty)</b> à¦•à¦¤ à¦¦à§‡à¦¬à§‡à¦¨? (à¦¯à§‡à¦®à¦¨: 10, 100 à¦¬à¦¾ 1000):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_name, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k)

def admin_step_get_name(message, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k):
    try:
        min_qty = int(message.text.strip())
    except ValueError:
        min_qty = 10

    msg = bot.send_message(message.chat.id, "ðŸ“Œ <b>à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸à¦Ÿà¦¿à¦° à¦¨à¦¾à¦® à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_save_service, mcat_name, scat_name, id_bot, api_id, coin_price_per_1k, min_qty)

def admin_step_save_service(message, mcat_name, scat_name, id_bot, api_id, usd_cost, min_qty):
    name = message.text.strip()

    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO services (main_cat, sub_cat, id_bot, api_id, name, price_per_1k, min_qty) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (mcat_name, scat_name, id_bot, api_id, name, usd_cost, min_qty))
    conn.commit()
    conn.close()

    bot.send_message(
        message.chat.id,
        f"âœ… <b>à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸à¦Ÿà¦¿ à¦¸à¦«à¦²à¦­à¦¾à¦¬à§‡ à§©-à¦¸à§à¦¤à¦°à§‡ à¦¯à§à¦•à§à¦¤ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡!</b>\n\n"
        f"ðŸ“ <b>à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦®:</b> <code>{mcat_name}</code>\n"
        f"ðŸ“‚ <b>à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿:</b> <code>{scat_name}</code>\n"
        f"ðŸ†” <b>à¦šà§Ÿà§‡à¦¸ ID:</b> <b>{id_bot}</b> | ðŸ”Œ <b>API ID:</b> <b>{api_id}</b>\n"
        f"ðŸ’° <b>à¦•à§Ÿà§‡à¦¨ à¦ªà§à¦°à¦¾à¦‡à¦œ (à§§à§¦à§¦à§¦à¦Ÿà¦¿):</b> <b>{usd_cost:.2f} Coin</b>\n"
        f"ðŸ”¢ <b>à¦¸à¦°à§à¦¬à¦¨à¦¿à¦®à§à¦¨ à¦…à¦°à§à¦¡à¦¾à¦°:</b> <b>{min_qty} à¦Ÿà¦¿</b>\n"
        f"ðŸ“Œ <b>à¦¨à¦¾à¦®:</b> <b>{name}</b>",
        parse_mode="HTML"
    )

# ---------------- 4. à¦¸à¦¿à¦™à§à¦—à§‡à¦² à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¡à¦¿à¦²à¦¿à¦Ÿ ----------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_delete_single_service_start")
def admin_delete_single_service_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)

    main_cats = get_main_categories()
    btns = [types.InlineKeyboardButton(f"ðŸ“ {mc}", callback_data=f"delmcat_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)

    bot.send_message(call.message.chat.id, "ðŸ—‘ï¸ <b>à¦•à§‹à¦¨ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦®à§‡à¦° à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¡à¦¿à¦²à¦¿à¦Ÿ à¦•à¦°à¦¬à§‡à¦¨?</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmcat_"))
def admin_del_select_sub(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("delmcat_", "")

    sub_cats = get_sub_categories(mcat_name)
    btns = [types.InlineKeyboardButton(f"ðŸ“‚ {sc}", callback_data=f"delscat_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)

    bot.send_message(call.message.chat.id, f"ðŸ—‘ï¸ <b>[{mcat_name}] à¦à¦° à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¸à¦¿à¦²à§‡à¦•à§à¦Ÿ à¦•à¦°à§à¦¨:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delscat_"))
def admin_del_select_id(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    raw_data = call.data.replace("delscat_", "")
    mcat_name, scat_name = raw_data.split("___")

    msg = bot.send_message(call.message.chat.id, f"ðŸ—‘ï¸ <b>[{scat_name}]</b> à¦à¦° à¦šà§Ÿà§‡à¦¸ ID (à¦¯à§‡à¦®à¦¨: 1, 2) à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_process_delete_service, mcat_name, scat_name)

def admin_process_delete_service(message, mcat_name, scat_name):
    id_bot = message.text.strip()
    delete_single_service(mcat_name, scat_name, id_bot)
    bot.send_message(message.chat.id, f"âœ… <b>à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ ID [{id_bot}] à¦¡à¦¿à¦²à¦¿à¦Ÿ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡!</b>", parse_mode="HTML")

# ---------------- 5. à§ªà¦Ÿà¦¿ à¦šà§à¦¯à¦¾à¦¨à§‡à¦² à¦œà§Ÿà§‡à¦¨ à¦¸à§‡à¦Ÿà¦†à¦ª ----------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_force_channel_menu")
def admin_force_channel_menu(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)

    channels = get_force_channels()
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for ch in channels:
        markup.add(types.InlineKeyboardButton(f"âŒ {ch[1]} à¦¡à¦¿à¦²à¦¿à¦Ÿ à¦•à¦°à§à¦¨", callback_data=f"delchan_{ch[0]}"))

    if len(channels) < 4:
        markup.add(types.InlineKeyboardButton("âž• à¦¨à¦¤à§à¦¨ à¦šà§à¦¯à¦¾à¦¨à§‡à¦² à¦¯à§‹à¦— à¦•à¦°à§à¦¨", callback_data="addchan_start"))

    bot.send_message(call.message.chat.id, f"ðŸ“¢ <b>à¦«à§‹à¦°à§à¦¸à¦®à¦¸à§à¦Ÿ à¦œà§Ÿà§‡à¦¨ à¦šà§à¦¯à¦¾à¦¨à§‡à¦² à¦¤à¦¾à¦²à¦¿à¦•à¦¾ ({len(channels)}/4):</b>\n(âš ï¸ à¦¬à§‹à¦Ÿà¦•à§‡ à¦šà§à¦¯à¦¾à¦¨à§‡à¦²à§‡ à¦à¦¡à¦®à¦¿à¦¨ à¦¬à¦¾à¦¨à¦¿à§Ÿà§‡ à¦°à¦¾à¦–à¦¬à§‡à¦¨!)\n\nà¦¨à¦¿à¦šà§‡à¦° à¦¬à¦¾à¦Ÿà¦¨ à¦¦à¦¿à§Ÿà§‡ à¦¯à§‹à¦— à¦¬à¦¾ à¦°à¦¿à¦®à§à¦­ à¦•à¦°à§à¦¨:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "addchan_start")
def addchan_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "ðŸ“¢ <b>à¦šà§à¦¯à¦¾à¦¨à§‡à¦²à§‡à¦° à¦‡à¦‰à¦œà¦¾à¦°à¦¨à§‡à¦® à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:</b>\n(à¦¯à§‡à¦®à¦¨: `@MyChannelName`):", parse_mode="HTML")
    bot.register_next_step_handler(msg, addchan_get_link)

def addchan_get_link(message):
    ch_id = message.text.strip()
    msg = bot.send_message(message.chat.id, f"ðŸ”— <b>à¦šà§à¦¯à¦¾à¦¨à§‡à¦²à¦Ÿà¦¿à¦° à¦²à¦¿à¦‚à¦• (Invite Link) à¦ªà§‡à¦¸à§à¦Ÿ à¦•à¦°à§à¦¨:</b>\n(à¦¯à§‡à¦®à¦¨: `https://t.me/MyChannelName`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, addchan_get_name, ch_id)

def addchan_get_name(message, ch_id):
    link = message.text.strip()
    msg = bot.send_message(message.chat.id, "ðŸ“Œ <b>à¦¬à¦¾à¦Ÿà¦¨à§‡ à¦¦à§‡à¦–à¦¾à¦¨à§‹à¦° à¦œà¦¨à§à¦¯ à¦šà§à¦¯à¦¾à¦¨à§‡à¦²à§‡à¦° à¦¨à¦¾à¦® à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, addchan_save, ch_id, link)

def addchan_save(message, ch_id, link):
    ch_name = message.text.strip()
    add_force_channel(ch_id, ch_name, link)
    bot.send_message(message.chat.id, f"âœ… <b>à¦šà§à¦¯à¦¾à¦¨à§‡à¦² [{ch_name}] à¦¯à§à¦•à§à¦¤ à¦¹à§Ÿà§‡à¦›à§‡!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delchan_"))
def delchan_process(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    ch_id = call.data.replace("delchan_", "")
    delete_force_channel(ch_id)
    bot.send_message(call.message.chat.id, "âœ… <b>à¦šà§à¦¯à¦¾à¦¨à§‡à¦²à¦Ÿà¦¿ à¦°à¦¿à¦®à§à¦­ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡!</b>", parse_mode="HTML")

# ---------------- 6. à¦‡à¦‰à¦œà¦¾à¦° à¦‡à¦¨à¦«à§‹ à¦“ à¦•à§Ÿà§‡à¦¨ à¦à¦¡à¦¿à¦Ÿ ----------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_user_info_start")
def admin_user_info_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "ðŸ” <b>à¦‡à¦‰à¦œà¦¾à¦°à§‡à¦° à¦¤à¦¥à§à¦¯ à¦¦à§‡à¦–à¦¤à§‡ à¦¬à¦¾ à¦•à§Ÿà§‡à¦¨ à¦à¦¡à¦¿à¦Ÿ à¦•à¦°à¦¤à§‡ à¦‡à¦‰à¦œà¦¾à¦° ID à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_process_user_lookup)

def admin_process_user_lookup(message):
    try:
        target_user = int(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "âŒ à¦­à§à¦² à¦‡à¦¨à¦ªà§à¦Ÿ! à¦‡à¦‰à¦œà¦¾à¦° à¦†à¦‡à¦¡à¦¿ à¦¶à§à¦§à§à¦®à¦¾à¦¤à§à¦° à¦¸à¦‚à¦–à§à¦¯à¦¾ à¦¹à§Ÿà¥¤")
        return

    balance = get_balance(target_user)
    total_orders, total_payments = get_user_stats(target_user)

    btn1 = types.InlineKeyboardButton("âž• à¦•à§Ÿà§‡à¦¨ à¦¯à§‹à¦— à¦•à¦°à§à¦¨", callback_data=f"admbal_ADD_{target_user}")
    btn2 = types.InlineKeyboardButton("âœï¸ à¦•à§Ÿà§‡à¦¨ à¦¸à§‡à¦Ÿ/à¦à¦¡à¦¿à¦Ÿ", callback_data=f"admbal_SET_{target_user}")
    markup = create_2col_markup([btn1, btn2])

    info_text = (
        f"ðŸ‘¤ <b>à¦‡à¦‰à¦œà¦¾à¦° à¦…à§à¦¯à¦¾à¦•à¦¾à¦‰à¦¨à§à¦Ÿ à¦‡à¦¨à¦«à¦°à¦®à§‡à¦¶à¦¨</b>\n"
        f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
        f"ðŸ†” <b>à¦‡à¦‰à¦œà¦¾à¦° ID:</b> <code>{target_user}</code>\n"
        f"ðŸ’° <b>à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸:</b> <b>{balance:.2f} Coin</b>\n"
        f"ðŸ›’ <b>à¦®à§‹à¦Ÿ à¦¸à¦®à§à¦ªà¦¨à§à¦¨ à¦…à¦°à§à¦¡à¦¾à¦°:</b> <b>{total_orders} à¦Ÿà¦¿</b>\n"
        f"ðŸ’³ <b>à¦®à§‹à¦Ÿ à¦¸à¦«à¦² à¦¡à¦¿à¦ªà§‹à¦œà¦¿à¦Ÿ:</b> <b>{total_payments} à¦Ÿà¦¿</b>\n"
        f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
        f"ðŸ‘‡ à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸ à¦šà§‡à¦žà§à¦œ à¦•à¦°à¦¤à§‡ à¦¨à¦¿à¦šà§‡à¦° à¦¬à¦¾à¦Ÿà¦¨ à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦•à¦°à§à¦¨:"
    )
    bot.send_message(message.chat.id, info_text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admbal_"))
def admin_process_balance_action(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    
    action_data = call.data.replace("admbal_", "")
    action, target_user = action_data.split("_")
    target_user = int(target_user)

    if action == "ADD":
        msg = bot.send_message(call.message.chat.id, f"ðŸ’µ à¦‡à¦‰à¦œà¦¾à¦° <code>{target_user}</code> à¦à¦° à¦¸à¦¾à¦¥à§‡ <b>à¦•à¦¤ à¦•à§Ÿà§‡à¦¨ (Coin) à¦¯à§‹à¦— à¦•à¦°à¦¬à§‡à¦¨?</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, admin_save_add_balance, target_user)
    elif action == "SET":
        msg = bot.send_message(call.message.chat.id, f"âœï¸ à¦‡à¦‰à¦œà¦¾à¦° <code>{target_user}</code> à¦à¦° <b>à¦¨à¦¤à§à¦¨ à¦•à§Ÿà§‡à¦¨ à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸ à¦•à¦¤ à¦¸à§‡à¦Ÿ à¦•à¦°à¦¬à§‡à¦¨?</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, admin_save_set_balance, target_user)

def admin_save_add_balance(message, target_user):
    try:
        amount = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "âŒ à¦­à§à¦² à¦‡à¦¨à¦ªà§à¦Ÿ!")
        return

    current_bal = get_balance(target_user)
    new_balance = current_bal + amount
    update_balance(target_user, new_balance)

    bot.send_message(message.chat.id, f"âœ… à¦‡à¦‰à¦œà¦¾à¦° <code>{target_user}</code> à¦à¦° à¦…à§à¦¯à¦¾à¦•à¦¾à¦‰à¦¨à§à¦Ÿà§‡ <b>{amount:.2f} Coin</b> à¦¯à§‹à¦— à¦¹à§Ÿà§‡à¦›à§‡à¥¤ à¦¨à¦¤à§à¦¨ à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸: <b>{new_balance:.2f} Coin</b>", parse_mode="HTML")

    try:
        bot.send_message(
            target_user,
            f"ðŸŽ‰ <b>à¦†à¦ªà¦¨à¦¾à¦° à¦…à§à¦¯à¦¾à¦•à¦¾à¦‰à¦¨à§à¦Ÿà§‡ à¦•à§Ÿà§‡à¦¨ à¦¯à§‹à¦— à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡!</b>\n\n"
            f"ðŸ’³ <b>à¦¯à§‹à¦—à¦•à§ƒà¦¤ à¦•à§Ÿà§‡à¦¨:</b> <b>{amount:.2f} Coin</b>\n"
            f"ðŸ’° <b>à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦®à§‹à¦Ÿ à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸:</b> <b>{new_balance:.2f} Coin</b> âœ…",
            parse_mode="HTML"
        )
    except Exception:
        pass

def admin_save_set_balance(message, target_user):
    try:
        new_balance = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "âŒ à¦­à§à¦² à¦‡à¦¨à¦ªà§à¦Ÿ!")
        return

    update_balance(target_user, new_balance)
    bot.send_message(message.chat.id, f"âœ… à¦‡à¦‰à¦œà¦¾à¦° <code>{target_user}</code> à¦à¦° à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸ à¦¸à¦«à¦²à¦­à¦¾à¦¬à§‡ <b>{new_balance:.2f} Coin</b> à¦¸à§‡à¦Ÿ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤", parse_mode="HTML")

    try:
        bot.send_message(
            target_user,
            f"ðŸ“¢ <b>à¦†à¦ªà¦¨à¦¾à¦° à¦…à§à¦¯à¦¾à¦•à¦¾à¦‰à¦¨à§à¦Ÿ à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸ à¦†à¦ªà¦¡à§‡à¦Ÿ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡!</b>\n\n"
            f"ðŸ’° <b>à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦®à§‹à¦Ÿ à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸:</b> <b>{new_balance:.2f} Coin</b> âœ…",
            parse_mode="HTML"
        )
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "admin_users_list")
def admin_users_list_callback(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    all_users = get_all_users()
    response = "ðŸ‘¥ <b>à¦¬à§‹à¦Ÿà§‡à¦° à¦¸à¦•à¦² à¦‡à¦‰à¦œà¦¾à¦°à§‡à¦° à¦¤à¦¾à¦²à¦¿à¦•à¦¾:</b>\n\n"
    for u in all_users:
        response += f"ðŸ‘¤ <b>ID:</b> <code>{u[0]}</code> | <b>à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸:</b> <b>{u[1]:.2f} Coin</b>\n"
    bot.send_message(call.message.chat.id, response, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_clear_services_confirm")
def admin_clear_services_callback(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        conn = sqlite3.connect(DB_FILE, timeout=30)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM services")
        cursor.execute("DELETE FROM main_categories")
        cursor.execute("DELETE FROM sub_categories")
        conn.commit()
        conn.close()
        bot.send_message(call.message.chat.id, "ðŸ—‘ï¸ <b>à¦¸à¦•à¦² à¦ªà§à¦°à¦¾à¦¤à¦¨ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¡à¦¿à¦²à¦¿à¦Ÿ à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"âŒ Error: {str(e)}")

# ===================================================

def get_main_menu_markup(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("ðŸ›’ à¦¨à¦¤à§à¦¨ à¦…à¦°à§à¦¡à¦¾à¦°")
    btn2 = types.KeyboardButton("ðŸ‘¤ à¦†à¦®à¦¾à¦° à¦…à§à¦¯à¦¾à¦•à¦¾à¦‰à¦¨à§à¦Ÿ")
    btn3 = types.KeyboardButton("ðŸ“œ à¦…à¦°à§à¦¡à¦¾à¦° à¦¹à¦¿à¦¸à§à¦Ÿà§à¦°à¦¿")
    btn4 = types.KeyboardButton("ðŸ“Š à¦ªà§‡à¦®à§‡à¦¨à§à¦Ÿ à¦¹à¦¿à¦¸à§à¦Ÿà§à¦°à¦¿")
    btn5 = types.KeyboardButton("ðŸ’³ Buy Coin (à¦Ÿà¦¾à¦•à¦¾ à¦°à¦¿à¦šà¦¾à¦°à§à¦œ)")
    btn6 = types.KeyboardButton("ðŸ“ž à¦¸à¦¾à¦ªà§‹à¦°à§à¦Ÿ")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    return markup

def enforce_force_join(chat_id):
    unjoined = check_user_joined_all(chat_id)
    if unjoined:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in unjoined:
            markup.add(types.InlineKeyboardButton(f"ðŸ“¢ Join {ch[1]}", url=ch[2]))
        markup.add(types.InlineKeyboardButton("âœ… à¦œà§Ÿà§‡à¦¨ à¦¸à¦®à§à¦ªà¦¨à§à¦¨ à¦•à¦°à§‡à¦›à¦¿ (Verify)", callback_data="verify_channel_joins"))

        bot.send_message(
            chat_id,
            "âš ï¸ <b>à¦¬à¦Ÿ à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦•à¦°à¦¤à§‡ à¦¨à¦¿à¦šà§‡à¦° à¦šà§à¦¯à¦¾à¦¨à§‡à¦²à¦—à§à¦²à§‹à¦¤à§‡ à¦œà§Ÿà§‡à¦¨ à¦¹à¦“à§Ÿà¦¾ à¦¬à¦¾à¦§à§à¦¯à¦¤à¦¾à¦®à§‚à¦²à¦•!</b>\n\n"
            "à¦œà§Ÿà§‡à¦¨ à¦¶à§‡à¦· à¦•à¦°à§‡ <b>'âœ… à¦œà§Ÿà§‡à¦¨ à¦¸à¦®à§à¦ªà¦¨à§à¦¨ à¦•à¦°à§‡à¦›à¦¿'</b> à¦¬à¦¾à¦Ÿà¦¨à§‡ à¦šà¦¾à¦ª à¦¦à¦¿à¦¨:",
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
        bot.send_message(chat_id, "ðŸŽ‰ <b>à¦¸à¦¬à¦—à§à¦²à§‹ à¦šà§à¦¯à¦¾à¦¨à§‡à¦²à§‡ à¦œà§Ÿà§‡à¦¨à¦¿à¦‚ à¦­à§‡à¦°à¦¿à¦«à¦¾à¦‡ à¦¹à§Ÿà§‡à¦›à§‡!</b>\nà¦à¦–à¦¨ à¦†à¦ªà¦¨à¦¿ à¦¬à¦Ÿ à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦•à¦°à¦¤à§‡ à¦ªà¦¾à¦°à¦¬à§‡à¦¨à¥¤", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
    else:
        bot.send_message(chat_id, "âŒ <b>à¦†à¦ªà¦¨à¦¿ à¦à¦–à¦¨à§‹ à¦¸à¦¬à¦—à§à¦²à§‹ à¦šà§à¦¯à¦¾à¦¨à§‡à¦²à§‡ à¦œà§Ÿà§‡à¦¨ à¦•à¦°à§‡à¦¨à¦¨à¦¿!</b> à¦…à¦¨à§à¦—à§à¦°à¦¹ à¦•à¦°à§‡ à¦²à¦¿à¦‚à¦•à§‡ à¦—à¦¿à§Ÿà§‡ à¦œà§Ÿà§‡à¦¨ à¦•à¦°à§à¦¨à¥¤", parse_mode="HTML")

@bot.message_handler(commands=["start"])
def start_command(message):
    chat_id = message.chat.id
    add_user(chat_id)
    if enforce_force_join(chat_id):
        send_main_menu(chat_id, message.from_user.first_name)

def send_main_menu(chat_id, first_name):
    safe_name = "à¦‡à¦‰à¦œà¦¾à¦°" if not first_name else first_name.replace("<", "&lt;").replace(">", "&gt;")

    custom_welcome = get_setting("welcome_text")
    if custom_welcome:
        welcome_text = custom_welcome.replace("{name}", safe_name)
    else:
        welcome_text = (
            f"âš¡âœ…<b>à¦†à¦®à¦¾à¦¦à§‡à¦° à¦ªà§à¦°à¦¿à¦®à¦¿à¦¯à¦¼à¦¾à¦® SMM à¦¬à§‹à¦Ÿà§‡ à¦¸à§à¦¬à¦¾à¦—à¦¤à¦®!</b> ðŸ¥°\n"
            f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
            f"à¦¹à§à¦¯à¦¾à¦²à§‹ <b>{safe_name}</b>, à¦†à¦¶à¦¾ à¦•à¦°à¦¿ à¦­à¦¾à¦²à§‹ à¦†à¦›à§‡à¦¨! à¦†à¦®à¦¾à¦¦à§‡à¦° à¦¬à§‹à¦Ÿà§‡ à¦†à¦ªà¦¨à¦¾à¦•à§‡ à¦†à¦¨à§à¦¤à¦°à¦¿à¦• à¦…à¦­à¦¿à¦¨à¦¨à§à¦¦à¦¨à¥¤ à¦à¦–à¦¾à¦¨à§‡ à¦†à¦ªà¦¨à¦¿ à¦¬à¦¾à¦œà¦¾à¦°à§‡à¦° à¦¸à§‡à¦°à¦¾ à¦“ à¦¦à§à¦°à§à¦¤à¦¤à¦® à¦¸à§‹à¦¶à§à¦¯à¦¾à¦² à¦®à¦¿à¦¡à¦¿à¦¯à¦¼à¦¾ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸à¦—à§à¦²à§‹ à¦ªà¦¾à¦¬à§‡à¦¨à¥¤ ðŸš€\n\n"
            f"ðŸ›’ <b>à¦…à¦°à§à¦¡à¦¾à¦° à¦¶à§à¦°à§ à¦•à¦°à¦¤à§‡ à¦¨à¦¿à¦šà§‡à¦° à¦¬à¦¾à¦Ÿà¦¨à¦—à§à¦²à§‹ à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦•à¦°à§à¦¨!</b> ðŸ‘‡"
        )
    
    start_photo = get_setting("start_photo")
    if start_photo:
        try:
            bot.send_photo(chat_id, start_photo, caption=welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
    else:
        bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

# ðŸ”´ à§©-à¦¸à§à¦¤à¦°à§‡à¦° à¦•à¦¾à¦¸à§à¦Ÿà¦®à¦¾à¦° à¦¬à§à¦°à¦¾à¦‰à¦œà¦¿à¦‚ à¦®à§‡à¦¨à§ (In-Place Message Edit)
@bot.message_handler(func=lambda message: True)
def handle_menu_buttons(message):
    chat_id = message.chat.id
    if not enforce_force_join(chat_id):
        return

    text = message.text

    if text == "ðŸ‘¤ à¦†à¦®à¦¾à¦° à¦…à§à¦¯à¦¾à¦•à¦¾à¦‰à¦¨à§à¦Ÿ":
        balance = get_balance(chat_id)
        account_text = (
            f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”“\n"
            f"   ðŸ‘¤ <b>à¦†à¦®à¦¾à¦° à¦…à§à¦¯à¦¾à¦•à¦¾à¦‰à¦¨à§à¦Ÿ à¦¡à§à¦¯à¦¾à¦¶à¦¬à§‹à¦°à§à¦¡</b> ðŸ‘¤\n"
            f"â”—â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”›\n\n"
            f"ðŸ†” <b>à¦†à¦ªà¦¨à¦¾à¦° à¦‡à¦‰à¦œà¦¾à¦° à¦†à¦‡à¦¡à¦¿ :</b> <code>{chat_id}</code>\n"
            f"ðŸ’° <b>à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸ :</b> <b>{balance:.2f} Coin</b>\n"
            f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”"
        )
        bot.send_message(chat_id, account_text, parse_mode="HTML")

    elif text == "ðŸ›’ à¦¨à¦¤à§à¦¨ à¦…à¦°à§à¦¡à¦¾à¦°":
        main_cats = get_main_categories()
        if not main_cats:
            bot.send_message(chat_id, "âŒ <b>à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨à§‡ à¦•à§‹à¦¨à§‹ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¯à§à¦•à§à¦¤ à¦•à¦°à¦¾ à¦¨à§‡à¦‡à¥¤</b>\n\nà¦à¦¡à¦®à¦¿à¦¨ à¦ªà§à¦¯à¦¾à¦¨à§‡à¦² (/admin) à¦¥à§‡à¦•à§‡ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¯à§‹à¦— à¦•à¦°à§à¦¨à¥¤", parse_mode="HTML")
            return

        btns = [types.InlineKeyboardButton(f"âœ¨ {mc}", callback_data=f"mcat_{mc}") for mc in main_cats]
        markup = create_2col_markup(btns)

        bot.send_message(chat_id, "ðŸ’¸ <b>à¦†à¦®à¦¾à¦¦à§‡à¦° à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦® à¦¨à¦¿à¦°à§à¦¬à¦¾à¦šà¦¨ à¦•à¦°à§à¦¨:</b>", reply_markup=markup, parse_mode="HTML")

    elif text == "ðŸ’³ Buy Coin (à¦Ÿà¦¾à¦•à¦¾ à¦°à¦¿à¦šà¦¾à¦°à§à¦œ)":
        deposit_text = (
            "ðŸ’Ž <b>à¦•à§Ÿà§‡à¦¨ à¦°à¦¿à¦šà¦¾à¦°à§à¦œ à¦•à¦°à¦¾à¦° à¦¸à¦¹à¦œ à¦¨à¦¿à§Ÿà¦®</b> ðŸ’Ž\n"
            "ðŸ’¸à§§ à¦•à§Ÿà§‡à¦¨ = à§§ à¦Ÿà¦¾à¦•à¦¾âš¡ðŸ’¸\n\n"
            "â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—\n"
            "ðŸ’³ ð—£ð—”ð—¬ð— ð—˜ð—¡ð—§ ð—œð—¡ð—¦ð—§ð—¥ð—¨ð—–ð—§ð—œð—¢ð—¡ ðŸ’³\n"
            "â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n"
            "ðŸª™ <b>à¦•à§Ÿà§‡à¦¨ à¦ªà§à¦¯à¦¾à¦•à§‡à¦œ à¦²à¦¿à¦¸à§à¦Ÿ:</b>\n"
            "â€¢ 10 Coin = 10 BDT\n"
            "â€¢ 50 Coin = 50 BDT\n"
            "â€¢ 100 Coin = 100 BDT\n"
            "â€¢ 200 Coin = 200 BDT\n"
            "â€¢ 500 Coin = 500 BDT\n\n"
            "ðŸ†” <b>à¦¬à¦¿à¦•à¦¾à¦¶ (à¦ªà¦¾à¦°à§à¦¸à§‹à¦¨à¦¾à¦²):</b> <code>01925263571</code>\n"
            "ðŸ’¸ <b>à¦¨à¦—à¦¦ à¦ªà¦¾à¦°à§à¦¸à§‹à¦¨à¦¾à¦²:</b> <code>01925263571</code>\n\n"
            "âš ï¸ <b>à¦¸à¦°à§à¦¬à¦¨à¦¿à¦®à§à¦¨ à§§à§¦ à¦•à§Ÿà§‡à¦¨ à¦•à¦¿à¦¨à¦¤à§‡ à¦¹à¦¬à§‡à¥¤</b>\n"
            "Send Money à¦•à¦°à¦¾à¦° à¦ªà¦° à¦¨à¦¿à¦šà§‡ à¦¶à§à¦§à§à¦®à¦¾à¦¤à§à¦° TrxID à¦¦à¦¿à¦²à§‡à¦‡ à§§ à¦¸à§‡à¦•à§‡à¦¨à§à¦¡à§‡ à¦…à¦Ÿà§‹ à¦•à§Ÿà§‡à¦¨ à¦¯à§‹à¦— à¦¹à¦¬à§‡!\n\n"
            "ðŸ‘‡ <b>à¦•à§Ÿà§‡à¦¨ à¦•à¦¿à¦¨à¦¤à§‡ à¦¨à¦¿à¦šà§‡à¦° à¦¬à¦¾à¦Ÿà¦¨à§‡ à¦šà¦¾à¦ª à¦¦à¦¿à¦¨:</b>"
        )
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("âš¡ à¦…à¦Ÿà§‹ à¦ªà§‡à¦®à§‡à¦¨à§à¦Ÿ à¦Ÿà§à¦°à¦¾à¦¨à¦œà§‡à¦•à¦¶à¦¨ à¦†à¦‡à¦¡à¦¿ à¦¦à¦¿à¦¨ âœ…", callback_data="verify_auto_trx_start")
        markup.add(btn)
        bot.send_message(chat_id, deposit_text, reply_markup=markup, parse_mode="HTML")

    elif text == "ðŸ“œ à¦…à¦°à§à¦¡à¦¾à¦° à¦¹à¦¿à¦¸à§à¦Ÿà§à¦°à¦¿":
        msg_loading = bot.send_message(chat_id, "â³ <b>à¦²à¦¾à¦‡à¦­ à¦…à¦°à§à¦¡à¦¾à¦° à¦¸à§à¦Ÿà§à¦¯à¦¾à¦Ÿà¦¾à¦¸ à¦²à§‹à¦¡ à¦¹à¦šà§à¦›à§‡...</b>", parse_mode="HTML")
        orders = get_user_orders(chat_id)
        if not orders:
            bot.edit_message_text("ðŸ“­ <b>à¦†à¦ªà¦¨à¦¿ à¦à¦–à¦¨à§‹ à¦•à§‹à¦¨à§‹ à¦…à¦°à§à¦¡à¦¾à¦° à¦•à¦°à§‡à¦¨à¦¨à¦¿à¥¤</b>", chat_id=chat_id, message_id=msg_loading.message_id, parse_mode="HTML")
            return

        order_ids = [o[0] for o in orders]
        statuses = get_multiple_orders_status(order_ids)

        response = "ðŸ“‹ <b>à¦†à¦ªà¦¨à¦¾à¦° à¦¸à¦°à§à¦¬à¦¶à§‡à¦· à§«à¦Ÿà¦¿ à¦…à¦°à§à¦¡à¦¾à¦° à¦à¦¬à¦‚ à¦²à¦¾à¦‡à¦­ à¦¸à§à¦Ÿà§à¦¯à¦¾à¦Ÿà¦¾à¦¸:</b>\n\n"
        for idx, o in enumerate(orders, 1):
            o_id = str(o[0])
            st = statuses.get(o_id, {}).get("status", "Processing") if isinstance(statuses, dict) else "Processing"
            response += (
                f"<b>{idx}. {o[1]}</b>\n"
                f"ðŸ†” <b>à¦…à¦°à§à¦¡à¦¾à¦° à¦†à¦‡à¦¡à¦¿:</b> <code>{o[0]}</code>\n"
                f"ðŸ”¢ <b>à¦•à§‹à§Ÿà¦¾à¦¨à§à¦Ÿà¦¿à¦Ÿà¦¿:</b> <b>{o[2]}</b> | ðŸ’µ <b>à¦–à¦°à¦š:</b> <b>{o[3]:.2f} Coin</b>\n"
                f"ðŸš¦ <b>à¦²à¦¾à¦‡à¦­ à¦¸à§à¦Ÿà§à¦¯à¦¾à¦Ÿà¦¾à¦¸:</b> <b>{st}</b>\n"
                f"âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯\n"
            )
        bot.edit_message_text(response, chat_id=chat_id, message_id=msg_loading.message_id, parse_mode="HTML")

    elif text == "ðŸ“Š à¦ªà§‡à¦®à§‡à¦¨à§à¦Ÿ à¦¹à¦¿à¦¸à§à¦Ÿà§à¦°à¦¿":
        payments = get_user_payments(chat_id)
        if not payments:
            bot.send_message(chat_id, "ðŸ“­  à¦†à¦ªà¦¨à¦¾à¦° à¦•à§‹à¦¨à§‹ à¦ªà§‡à¦®à§‡à¦¨à§à¦Ÿ à¦°à§‡à¦•à¦°à§à¦¡ à¦¨à§‡à¦‡à¥¤")
            return

        response = "ðŸ“Š <b>à¦†à¦ªà¦¨à¦¾à¦° à¦¸à¦°à§à¦¬à¦¶à§‡à¦· à§§à§¦à¦Ÿà¦¿ à¦ªà§‡à¦®à§‡à¦¨à§à¦Ÿ à¦°à¦¿à¦•à§‹à§Ÿà§‡à¦¸à§à¦Ÿ:</b>\n\n"
        for idx, p in enumerate(payments, 1):
            status_icon = "â³" if p[3] == "Pending" else "âœ…"
            response += (
                f"<b>{idx}. {p[0]} à¦¡à¦¿à¦ªà§‹à¦œà¦¿à¦Ÿ</b>\n"
                f"ðŸ’µ à¦ªà¦°à¦¿à¦®à¦¾à¦£: <b>{p[1]:.2f} Coin</b> | ðŸ†” <b>TxID:</b> <code>{p[2]}</code>\n"
                f"ðŸš¦ <b>à¦¸à§à¦Ÿà§à¦¯à¦¾à¦Ÿà¦¾à¦¸:</b> {status_icon} <b>{p[3]}</b>\n"
                f"âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯\n"
            )
        bot.send_message(chat_id, response, parse_mode="HTML")

    elif text == "ðŸ“ž à¦¸à¦¾à¦ªà§‹à¦°à§à¦Ÿ":
        support_text = (
            "â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”“\n"
            "       ðŸ“ž   <b>à¦à¦¡à¦®à¦¿à¦¨ à¦¸à¦¾à¦ªà§‹à¦°à§à¦Ÿ</b>   ðŸ“ž\n"
            "â”—â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”›\n\n"
            "ðŸ’¬  à¦Ÿà§‡à¦²à¦¿à¦—à§à¦°à¦¾à¦® à¦à¦¡à¦®à¦¿à¦¨: @Mr_Sojol_Ceo\n"
            "ðŸ“± à¦¹à§‹à§Ÿà¦¾à¦Ÿà¦¸à¦…à§à¦¯à¦¾à¦ª: +8801925263571\n\n"
            "à¦ªà§‡à¦®à§‡à¦¨à§à¦Ÿ à¦à¦¡ à¦•à¦°à¦¾ à¦¬à¦¾ à¦…à¦°à§à¦¡à¦¾à¦° à¦¸à¦‚à¦•à§à¦°à¦¾à¦¨à§à¦¤ à¦¯à§‡à¦•à§‹à¦¨à§‹ à¦¸à¦®à¦¸à§à¦¯à¦¾à¦° à¦œà¦¨à§à¦¯ à¦¸à¦°à¦¾à¦¸à¦°à¦¿ à¦à¦¡à¦®à¦¿à¦¨à§‡à¦° à¦¸à¦¾à¦¥à§‡ à¦¯à§‹à¦—à¦¾à¦¯à§‹à¦— à¦•à¦°à§à¦¨à¥¤"
        )
        bot.send_message(chat_id, support_text, parse_mode="HTML")

# ðŸ”´ à§¨à§Ÿ à¦²à§‡à¦­à§‡à¦²: à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¹à§à¦¯à¦¾à¦¨à§à¦¡à¦²à¦¿à¦‚
@bot.callback_query_handler(func=lambda call: call.data.startswith("mcat_"))
def handle_main_category_selection(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    bot.answer_callback_query(call.id)
    
    mcat_name = call.data.replace("mcat_", "")
    sub_cats = get_sub_categories(mcat_name)

    if not sub_cats:
        bot.answer_callback_query(call.id, "âŒ à¦à¦‡ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦®à§‡ à¦•à§‹à¦¨à§‹ à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¨à§‡à¦‡!", show_alert=True)
        return

    btns = [types.InlineKeyboardButton(f"ðŸ“‚ {sc}", callback_data=f"scat_{mcat_name}___{sc}") for sc in sub_cats]
    btns.append(types.InlineKeyboardButton("â¬…ï¸ à¦¬à§à¦¯à¦¾à¦• (à¦®à§‡à¦‡à¦¨ à¦ªà§à¦¯à¦¾à¦¨à§‡à¦²)", callback_data="back_to_main_platforms"))
    markup = create_2col_markup(btns)

    try:
        bot.edit_message_text(f"ðŸ“‚ <b>[{mcat_name}] à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¬à§‡à¦›à§‡ à¦¨à¦¿à¦¨:</b>", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except Exception:
        bot.send_message(chat_id, f"ðŸ“‚ <b>[{mcat_name}] à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿ à¦¬à§‡à¦›à§‡ à¦¨à¦¿à¦¨:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main_platforms")
def back_to_main_platforms_callback(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    bot.answer_callback_query(call.id)
    
    main_cats = get_main_categories()
    btns = [types.InlineKeyboardButton(f"âœ¨ {mc}", callback_data=f"mcat_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)

    try:
        bot.edit_message_text("ðŸ’¸ <b>à¦†à¦®à¦¾à¦¦à§‡à¦° à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦® à¦¨à¦¿à¦°à§à¦¬à¦¾à¦šà¦¨ à¦•à¦°à§à¦¨:</b>", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    except Exception:
        bot.send_message(chat_id, "ðŸ’¸ <b>à¦†à¦®à¦¾à¦¦à§‡à¦° à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦ªà§à¦²à§à¦¯à¦¾à¦Ÿà¦«à¦°à§à¦® à¦¨à¦¿à¦°à§à¦¬à¦¾à¦šà¦¨ à¦•à¦°à§à¦¨:</b>", reply_markup=markup, parse_mode="HTML")

# ðŸ”´ à§©à§Ÿ à¦²à§‡à¦­à§‡à¦²: à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦²à¦¿à¦¸à§à¦Ÿ à¦¹à§à¦¯à¦¾à¦¨à§à¦¡à¦²à¦¿à¦‚
@bot.callback_query_handler(func=lambda call: call.data.startswith("scat_"))
def handle_sub_category_selection(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    
    raw_data = call.data.replace("scat_", "")
    mcat_name, scat_name = raw_data.split("___")

    services_list = get_services_by_sub_cat(mcat_name, scat_name)
    
    if not services_list:
        bot.send_message(chat_id, "âŒ <b>à¦à¦‡ à¦¸à¦¾à¦¬-à¦•à§à¦¯à¦¾à¦Ÿà¦¾à¦—à¦°à¦¿à¦¤à§‡ à¦à¦–à¦¨à§‹ à¦•à§‹à¦¨à§‹ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¯à§à¦•à§à¦¤ à¦•à¦°à¦¾ à¦¹à§Ÿà¦¨à¦¿à¥¤</b>", parse_mode="HTML")
        return

    response_text = "âœ… <b>ð—£ð—¥ð—˜ð— ð—œð—¨ð—  ð—¦ð—˜ð—¥ð—©ð—œð—–ð—˜</b> ðŸ‘‘\n\nâœ¨ âœ…à¦¨à¦¿à¦šà§‡à¦° à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¦à§‡à¦–à§‡ à¦…à¦°à§à¦¡à¦¾à¦° à¦•à¦°à§à¦¨ âœ¨âš¡\n\n"
    
    for service in services_list:
        display_price = service.get("price_per_1k", 0.0)

        response_text += (
            f"ðŸ†” <b>{service['id']}</b> âŽ¯ <b>{service['name']}</b>\n"
            f"ðŸ’µ à¦¦à¦¾à¦®: <b>{display_price:.2f} Coin</b> (à¦ªà§à¦°à¦¤à¦¿ à§§à§¦à§¦à§¦à¦Ÿà¦¿)\n"
            f"ðŸ”¢ à¦¸à¦°à§à¦¬à¦¨à¦¿à¦®à§à¦¨ à¦…à¦°à§à¦¡à¦¾à¦°: <b>{service['min_qty']} à¦Ÿà¦¿</b>\n"
            f"âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯âŽ¯\n"
        )
        
    response_text += "\nâœï¸ <b>âœ…ðŸ”¥à¦†à¦ªà¦¨à¦¿ à¦¯à§‡à¦‡ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸ à¦¨à¦¿à¦¬à§‡à¦¨ à¦¤à¦¾à¦° à¦†à¦‡à¦¡à¦¿ à¦¦à§‡à¦¨ðŸ”¥ (à¦¯à§‡à¦®à¦¨)ðŸ†” 1 ðŸ†” 2 ðŸ†” 3 à¥¤ðŸ”¥</b>"
    msg = bot.send_message(chat_id, response_text, parse_mode="HTML")
    bot.register_next_step_handler(msg, get_service_id, services_list)

def get_service_id(message, services_list):
    chat_id = message.chat.id
    user_input = message.text.strip()

    selected_service = next((s for s in services_list if str(s["id"]) == user_input), None)
    if not selected_service:
        bot.send_message(chat_id, "ðŸ›‘ <b>à¦­à§à¦² à¦†à¦‡à¦¡à¦¿! à¦†à¦¬à¦¾à¦° à¦šà§‡à¦·à§à¦Ÿà¦¾ à¦•à¦°à§à¦¨à¥¤</b>", parse_mode="HTML")
        return

    msg = bot.send_message(chat_id, f"ðŸ”— <b>à¦†à¦ªà¦¨à¦¾à¦° à¦…à¦°à§à¦¡à¦¾à¦°à§‡à¦° à¦²à¦¿à¦‚à¦•à¦Ÿà¦¿ à¦à¦–à¦¾à¦¨à§‡ à¦ªà§‡à¦¸à§à¦Ÿ à¦•à¦°à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:</b>\n\nâš ï¸ (à¦¸à¦°à§à¦¬à¦¨à¦¿à¦®à§à¦¨ à¦•à§‹à§Ÿà¦¾à¦¨à§à¦Ÿà¦¿à¦Ÿà¦¿: {selected_service['min_qty']} à¦Ÿà¦¿)", parse_mode="HTML")
    bot.register_next_step_handler(msg, get_link, selected_service)

def get_link(message, selected_service):
    chat_id = message.chat.id
    link = message.text.strip()

    if not link.startswith("http"):
        bot.send_message(chat_id, "ðŸ›‘ <b>à¦­à§à¦² à¦²à¦¿à¦‚à¦•! à¦¸à¦ à¦¿à¦• à¦²à¦¿à¦‚à¦• à¦¦à¦¿à§Ÿà§‡ à¦ªà§à¦¨à¦°à¦¾à§Ÿ à¦šà§‡à¦·à§à¦Ÿà¦¾ à¦•à¦°à§à¦¨à¥¤</b>", parse_mode="HTML")
        return

    msg = bot.send_message(chat_id, f"ðŸ”¢ <b>à¦•à¦¤ à¦•à§‹à§Ÿà¦¾à¦¨à§à¦Ÿà¦¿à¦Ÿà¦¿ (Quantity) à¦¨à¦¿à¦¤à§‡ à¦šà¦¾à¦¨?</b>\n\nâš ï¸ (à¦¸à¦°à§à¦¬à¦¨à¦¿à¦®à§à¦¨: {selected_service['min_qty']} à¦Ÿà¦¿):", parse_mode="HTML")
    bot.register_next_step_handler(msg, get_quantity, selected_service, link)

def get_quantity(message, selected_service, link):
    chat_id = message.chat.id
    quantity_input = message.text.strip()

    if not quantity_input.isdigit():
        bot.send_message(chat_id, "ðŸ›‘ <b>à¦­à§à¦² à¦¸à¦‚à¦–à§à¦¯à¦¾! à¦¶à§à¦§à§à¦®à¦¾à¦¤à§à¦° à¦¸à¦‚à¦–à§à¦¯à¦¾ à¦Ÿà¦¾à¦‡à¦ª à¦•à¦°à§à¦¨à¥¤</b>", parse_mode="HTML")
        return

    quantity = int(quantity_input)
    min_qty = selected_service.get('min_qty', 10)

    if quantity < min_qty:
        bot.send_message(chat_id, f"âŒ <b>à¦à¦‡ à¦¸à¦¾à¦°à§à¦­à¦¿à¦¸à§‡à¦° à¦œà¦¨à§à¦¯ à¦¸à¦°à§à¦¬à¦¨à¦¿à¦®à§à¦¨ {min_qty} à¦Ÿà¦¿ à¦•à§‹à§Ÿà¦¾à¦¨à§à¦Ÿà¦¿à¦Ÿà¦¿ à¦…à¦°à§à¦¡à¦¾à¦° à¦•à¦°à¦¤à§‡ à¦¹à¦¬à§‡!</b>\n\nà¦¨à¦¤à§à¦¨ à¦•à¦°à§‡ à¦šà§‡à¦·à§à¦Ÿà¦¾ à¦•à¦°à§à¦¨à¥¤", parse_mode="HTML")
        return

    bdt_rate_per_1k = selected_service.get("price_per_1k", 0.0) or 10.0
    estimated_cost = (quantity / 1000) * bdt_rate_per_1k

    if estimated_cost < 1.0:
        estimated_cost = 1.0

    user_balance = get_balance(chat_id)

    if user_balance < estimated_cost:
        bot.send_message(
            chat_id,
            f"âŒ <b>à¦†à¦ªà¦¨à¦¾à¦° à¦…à§à¦¯à¦¾à¦•à¦¾à¦‰à¦¨à§à¦Ÿà§‡ à¦ªà¦°à§à¦¯à¦¾à¦ªà§à¦¤ à¦•à§Ÿà§‡à¦¨ à¦¨à§‡à¦‡!</b>\n\n"
            f"à¦…à¦°à§à¦¡à¦¾à¦°à§‡à¦° à¦®à§‚à¦²à§à¦¯: <b>{estimated_cost:.2f} Coin</b>\n"
            f"à¦†à¦ªà¦¨à¦¾à¦° à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸: <b>{user_balance:.2f} Coin</b>",
            parse_mode="HTML"
        )
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_confirm = types.KeyboardButton("âœ… à¦•à¦¨à¦«à¦¾à¦°à§à¦® à¦•à¦°à§à¦¨")
    btn_cancel = types.KeyboardButton("âŒ à¦¬à¦¾à¦¤à¦¿à¦² à¦•à¦°à§à¦¨")
    markup.add(btn_confirm, btn_cancel)

    confirm_msg = (
        f"ðŸ’µ <b>à¦†à¦ªà¦¨à¦¾à¦° à¦…à¦°à§à¦¡à¦¾à¦° à¦®à§‚à¦²à§à¦¯: {estimated_cost:.2f} Coin</b>\n\n"
        f"à¦…à¦°à§à¦¡à¦¾à¦°à¦Ÿà¦¿ à¦¸à¦¾à¦¬à¦®à¦¿à¦Ÿ à¦•à¦°à¦¤à§‡ à¦¨à¦¿à¦šà§‡à¦° <b>'âœ… à¦•à¦¨à¦«à¦¾à¦°à§à¦® à¦•à¦°à§à¦¨'</b> à¦¬à¦¾à¦Ÿà¦¨à§‡ à¦•à§à¦²à¦¿à¦• à¦•à¦°à§à¦¨à¥¤"
    )
    msg = bot.send_message(chat_id, confirm_msg, reply_markup=markup, parse_mode="HTML")
    bot.register_next_step_handler(msg, confirm_order_final, selected_service, link, quantity, estimated_cost)

def confirm_order_final(message, selected_service, link, quantity, estimated_cost):
    chat_id = message.chat.id
    user_choice = message.text.strip()

    if user_choice == "âœ… à¦•à¦¨à¦«à¦¾à¦°à§à¦® à¦•à¦°à§à¦¨":
        user_balance = get_balance(chat_id)
        if user_balance < estimated_cost:
            bot.send_message(chat_id, "âŒ <b>à¦†à¦ªà¦¨à¦¾à¦° à¦…à§à¦¯à¦¾à¦•à¦¾à¦‰à¦¨à§à¦Ÿà§‡ à¦ªà¦°à§à¦¯à¦¾à¦ªà§à¦¤ à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸ à¦¨à§‡à¦‡à¥¤</b>", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
            return

        payload = {
            "key": get_smm_api_key(),
            "action": "add",
            "service": selected_service["api_id"],
            "link": link,
            "quantity": quantity,
        }
        
        try:
            response = requests.post(get_smm_api_url(), data=payload)
            api_res = response.json()

            if isinstance(api_res, dict) and "order" in api_res:
                new_balance = user_balance - estimated_cost
                update_balance(chat_id, new_balance)
                add_order_to_db(api_res["order"], chat_id, selected_service["name"], quantity, estimated_cost)

                success_text = (
                    f"âœ… <b>ORDER PLACED SUCCESSFULLY!</b>\n\n"
                    f"ðŸ“Œ <b>Service:</b> {selected_service['name']}\n"
                    f"ðŸ”— <b>YOUR LINK:</b> {link}\n"
                    f"ðŸ”¢ <b>QUANTITY:</b> {quantity}\n"
                    f"ðŸ’³ <b>COST:</b> <b>{estimated_cost:.2f} Coin</b>\n"
                    f"ðŸ’° <b>REMAINING COIN:</b> <b>{new_balance:.2f} Coin</b>\n"
                    f"ðŸ†” <b>ORDER ID :</b> <code>{api_res['order']}</code> âœ”ï¸"
                )
                bot.send_message(chat_id, success_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
            else:
                error_msg = api_res.get("error", "Unknown SMM Server error") if isinstance(api_res, dict) else "Invalid SMM Server response"
                bot.send_message(chat_id, f"âŒ <b>Failed to order. Server Response:</b> {error_msg}", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
                
        except Exception:
            bot.send_message(chat_id, "âŒ <b>Connection error with SMM site. Please try again.</b>", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

    else:
        bot.send_message(chat_id, "âŒ <b>à¦…à¦°à§à¦¡à¦¾à¦°à¦Ÿà¦¿ à¦¬à¦¾à¦¤à¦¿à¦² à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡à¥¤</b>", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

# ----------------- ðŸ’³ à¦¡à¦¿à¦ªà§‹à¦œà¦¿à¦Ÿ à¦­à§‡à¦°à¦¿à¦«à¦¾à¦‡ -----------------
@bot.callback_query_handler(func=lambda call: call.data == "verify_auto_trx_start")
def start_auto_trx_input(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "ðŸ’µ <b>à¦•à¦¤ à¦•à§Ÿà§‡à¦¨ (Coin) à¦•à¦¿à¦¨à¦¤à§‡ à¦šà¦¾à¦¨? à¦ªà¦°à¦¿à¦®à¦¾à¦£ à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:</b>\n(à¦¯à§‡à¦®à¦¨: 10, 50, 100, 200 à¦¬à¦¾ 500à¥¤ à¦¸à¦°à§à¦¬à¦¨à¦¿à¦®à§à¦¨ à§§à§¦ à¦•à§Ÿà§‡à¦¨):", parse_mode="HTML")
    bot.register_next_step_handler(msg, get_intended_deposit_amount)

def get_intended_deposit_amount(message):
    chat_id = message.chat.id
    amount_str = message.text.strip()

    if not amount_str.replace('.', '', 1).isdigit():
        bot.send_message(chat_id, "âŒ <b>à¦­à§à¦² à¦‡à¦¨à¦ªà§à¦Ÿ! à¦¶à§à¦§à§ à¦¸à¦‚à¦–à§à¦¯à¦¾ à¦²à¦¿à¦–à§‡ à¦ªà¦¾à¦ à¦¾à¦¨:</b>", parse_mode="HTML")
        return

    intended_amount = float(amount_str)
    if intended_amount < 10.0:
        bot.send_message(chat_id, "âŒ <b>à¦¸à¦°à§à¦¬à¦¨à¦¿à¦®à§à¦¨ à§§à§¦ à¦•à§Ÿà§‡à¦¨ à¦•à¦¿à¦¨à¦¤à§‡ à¦¹à¦¬à§‡!</b> à¦†à¦¬à¦¾à¦° à¦šà§‡à¦·à§à¦Ÿà¦¾ à¦•à¦°à§à¦¨à¥¤", parse_mode="HTML")
        return
    
    msg_text = (
        f"ðŸ‘ <b>à¦…à¦¨à§à¦°à§‹à¦§ à¦—à§ƒà¦¹à§€à¦¤ à¦¹à§Ÿà§‡à¦›à§‡!</b>\n\n"
        f"ðŸ’° <b>à¦†à¦ªà¦¨à¦¾à¦° à¦•à§Ÿà§‡à¦¨ à¦ªà¦°à¦¿à¦®à¦¾à¦£:</b> <b>{intended_amount:.2f} Coin ({intended_amount:.2f} BDT)</b>\n\n"
        f"ðŸ‘‰ à¦†à¦®à¦¾à¦¦à§‡à¦° à¦¬à¦¿à¦•à¦¾à¦¶/à¦¨à¦—à¦¦ à¦ªà¦¾à¦°à§à¦¸à§‹à¦¨à¦¾à¦² à¦¨à¦¾à¦®à§à¦¬à¦¾à¦°à§‡ <b>{intended_amount:.2f} BDT</b> Send Money à¦•à¦°à¦¾à¦° à¦ªà¦° à¦ªà§‡à¦®à§‡à¦¨à§à¦Ÿà§‡à¦° <b>TrxID (à¦Ÿà§à¦°à¦¾à¦¨à¦œà§‡à¦•à¦¶à¦¨ à¦†à¦‡à¦¡à¦¿)</b> à¦Ÿà¦¿ à¦à¦–à¦¾à¦¨à§‡ à¦ªà§‡à¦¸à§à¦Ÿ à¦•à¦°à§à¦¨:"
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
            f"âœ… <b>à¦ªà§‡à¦®à§‡à¦¨à§à¦Ÿ à¦¸à¦«à¦²à¦­à¦¾à¦¬à§‡ à¦­à§‡à¦°à¦¿à¦«à¦¾à¦‡ à¦¹à§Ÿà§‡à¦›à§‡!</b>\n\n"
            f"ðŸ’³ <b>à¦®à§‡à¦¥à¦¡:</b> {method}\n"
            f"ðŸª™ <b>à¦ªà§à¦°à¦¾à¦ªà§à¦¤ à¦•à§Ÿà§‡à¦¨:</b> <b>{amount:.2f} Coin</b>\n"
            f"ðŸ’° <b>à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦®à§‹à¦Ÿ à¦¬à§à¦¯à¦¾à¦²à§‡à¦¨à§à¦¸:</b> <b>{new_balance:.2f} Coin</b> ðŸŽ‰",
            parse_mode="HTML"
        )

        try:
            bot.send_message(MAIN_ADMIN_ID, f"ðŸŽ‰ <b>AUTO DEPOSIT SUCCESSFUL!</b>\n\nðŸ‘¤ User: <code>{chat_id}</code>\nðŸª™ Amount: <b>{amount:.2f} Coin</b> ({method})\nðŸ†” TxID: <code>{user_txid}</code>", parse_mode="HTML")
        except Exception:
            pass
    else:
        bot.send_message(
            chat_id,
            "âŒ <b>à¦Ÿà§à¦°à¦¾à¦¨à¦œà§‡à¦•à¦¶à¦¨ à¦†à¦‡à¦¡à¦¿ à¦ªà¦¾à¦“à§Ÿà¦¾ à¦¯à¦¾à§Ÿà¦¨à¦¿ à¦¬à¦¾ à¦‡à¦¤à¦¿à¦ªà§‚à¦°à§à¦¬à§‡ à¦•à§à¦²à§‡à¦‡à¦® à¦•à¦°à¦¾ à¦¹à§Ÿà§‡à¦›à§‡!</b>\n\n"
            "à§§. à¦ªà§‡à¦®à§‡à¦¨à§à¦Ÿ à¦¸à¦®à§à¦ªà¦¨à§à¦¨ à¦•à¦°à¦¾ à¦¨à¦¿à¦¶à§à¦šà¦¿à¦¤ à¦•à¦°à§à¦¨à¥¤\n"
            "à§¨. à¦Ÿà¦¾à¦•à¦¾ à¦ªà¦¾à¦ à¦¾à¦¨à§‹à¦° à§§-à§¨ à¦®à¦¿à¦¨à¦¿à¦Ÿ à¦ªà¦° à¦†à¦¬à¦¾à¦° à¦Ÿà§à¦°à¦¾à¦‡ à¦•à¦°à§à¦¨à¥¤\n"
            "à§©. à¦¸à¦®à¦¸à§à¦¯à¦¾ à¦¹à¦²à§‡ à¦à¦¡à¦®à¦¿à¦¨à§‡à¦° à¦¸à¦¾à¦¥à§‡ à¦•à¦¥à¦¾ à¦¬à¦²à§à¦¨à¥¤",
            parse_mode="HTML"
        )

# ----------------- ðŸš€ RENDER/TERMUX FLASK THREAD -----------------
def start_bot_polling():
    while True:
        try:
            bot.polling(none_stop=True, skip_pending=True, timeout=60)
        except Exception as e:
            time.sleep(5)

if __name__ == "__main__":
    print("ðŸ¤– MONIRUL SMM BOT IS RUNNING SUCCESSFULLY...")
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    start_bot_polling()
