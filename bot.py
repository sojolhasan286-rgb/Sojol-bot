# -*- coding: utf-8 -*-
import sqlite3
import requests
import telebot
import time
import os
import re
import urllib.parse
from threading import Thread
from flask import Flask, request, jsonify, render_template_string
from telebot import types

# ----------------- আপনার বোটের মূল সেটিংস -----------------
BOT_TOKEN = "8305538092:AAEngUxVOgzk5UDQx74i4wjRXfVmKp1A88A"
SMMSUN_API_URL = "https://socialpanel.pro/api/v2"
SMMSUN_API_KEY = "14f3163c337f51c7c90c6232d9428bc2"
MAIN_ADMIN_ID = 6851638362 
# --------------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "users.db")

USER_STATES = {}
FAILED_ATTEMPTS = {}

# 🔴 বাটন হেল্পার ফাংশন
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
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
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
                description TEXT DEFAULT '',
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
        
        try:
            cursor.execute("ALTER TABLE services ADD COLUMN description TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE payments ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError:
            pass
            
        conn.commit()

# --- ডাইনামিক সেটিংস হেলাপার ফাংশনসমূহ ---
def get_setting(key):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None

def set_setting(key, value):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

# --- লাইব্রেরি-স্বাধীন সুরক্ষিত নেক্সট স্টেপ হ্যান্ডলার ক্লিনার (মেমরি লেভেল ফিক্স) ---
def clear_user_steps(chat_id):
    try:
        # মেমরিতে থাকা টেলিগ্রামের ইন্টারনাল নেক্সট স্টেপ ডিকশনারি ক্লিনিং
        if hasattr(bot, 'next_step_handlers'):
            if chat_id in bot.next_step_handlers:
                del bot.next_step_handlers[chat_id]
    except Exception:
        pass

# --- ট্রানজেকশন আইডি ফিল্টার এবং ক্লিনার ---
def clean_transaction_id(txid):
    if not txid:
        return ""
    return re.sub(r'[^A-Z0-9]', '', txid.strip().upper())

def get_bkash_number():
    val = get_setting("bkash_number")
    return val if val else "01925263571"

def get_nagad_number():
    val = get_setting("nagad_number")
    return val if val else "01925263571"

def get_support_username():
    val = get_setting("support_username")
    return val if val else "@Mr_Sojol_Ceo"

def get_support_phone():
    val = get_setting("support_phone")
    return val if val else "+8801925263571"

def get_channel_link():
    val = get_setting("channel_link")
    return val if val else "https://t.me/your_channel"

def get_log_channel_id():
    return get_setting("log_channel_id")

def get_coin_rate():
    val = get_setting("coin_rate_per_1000")
    return float(val) if val else 12.0

def get_bot_domain():
    val = get_setting("bot_domain")
    if val:
        if val.startswith("http://"):
            val = val.replace("http://", "https://")
        return val
    return "https://sojol-bot.onrender.com"

def get_price_list_text():
    val = get_setting("price_list_text")
    return val if val else "💰 <b>বর্তমানে কোনো প্রাইজ লিস্ট সেট করা নেই।</b>"

def get_order_success_note():
    val = get_setting("order_success_note")
    return val if val else ""

def get_smm_api_url():
    val = get_setting("smm_api_url")
    return val if val else SMMSUN_API_URL

def get_smm_api_key():
    val = get_setting("smm_api_key")
    return val if val else SMMSUN_API_KEY

def is_admin(chat_id):
    if chat_id == MAIN_ADMIN_ID:
        return True
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (chat_id,))
        row = cursor.fetchone()
        return row is not None

def add_co_admin(admin_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO admins VALUES (?)", (admin_id,))
        conn.commit()

def remove_co_admin(admin_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
        conn.commit()

def add_user(chat_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (chat_id, balance) VALUES (?, ?)", (chat_id, 0.0))
        conn.commit()

def get_balance(chat_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        return row[0] if row else 0.0

def update_balance(chat_id, new_balance):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (chat_id, balance) VALUES (?, 0.0)", (chat_id,))
        cursor.execute("UPDATE users SET balance = ? WHERE chat_id = ?", (new_balance, chat_id))
        conn.commit()

def get_all_users():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM users")
        return [r[0] for r in cursor.fetchall()]

def get_user_stats(chat_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders WHERE chat_id = ?", (chat_id,))
        total_orders = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM payments WHERE chat_id = ? AND status = 'Approved'", (chat_id,))
        total_payments = cursor.fetchone()[0]
        return total_orders, total_payments

# --- জয়েন চ্যানেল ফাংশনসমূহ ---
def add_force_channel(channel_id, channel_name, invite_link):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO force_channels VALUES (?, ?, ?)", (channel_id, channel_name, invite_link))
        conn.commit()

def get_force_channels():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, channel_name, invite_link FROM force_channels")
        return cursor.fetchall()

def delete_force_channel(channel_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
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

# --- ৩-লেভেল ক্যাটাগরি ডাটাবেজ হেল্পার ---
def add_main_category(name):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO main_categories VALUES (?)", (name,))
        conn.commit()

def get_main_categories():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM main_categories")
        rows = cursor.fetchall()
        return [r[0] for r in rows]

def delete_main_category(name):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM main_categories WHERE name = ?", (name,))
        cursor.execute("DELETE FROM sub_categories WHERE main_name = ?", (name,))
        cursor.execute("DELETE FROM services WHERE main_cat = ?", (name,))
        conn.commit()

def add_sub_category(main_name, sub_name):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO sub_categories VALUES (?, ?)", (main_name, sub_name))
        conn.commit()

def get_sub_categories(main_cat):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT sub_name FROM sub_categories WHERE main_name = ?", (main_cat,))
        rows = cursor.fetchall()
        return [r[0] for r in rows]

def delete_sub_category(main_name, sub_name):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sub_categories WHERE main_name = ? AND sub_name = ?", (main_name, sub_name))
        cursor.execute("DELETE FROM services WHERE main_cat = ? AND sub_cat = ?", (main_name, sub_name))
        conn.commit()

def get_services_by_sub_cat(main_cat, sub_cat):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT id_bot, api_id, name, price_per_1k, min_qty, description FROM services WHERE main_cat = ? AND sub_cat = ?", (main_cat, sub_cat))
        rows = cursor.fetchall()
        return [{"id": r[0], "api_id": r[1], "name": r[2], "price_per_1k": float(r[3]) if r[3] is not None else 0.0, "min_qty": r[4] if r[4] else 10, "description": r[5] if r[5] else ""} for r in rows]

def delete_single_service(main_cat, sub_cat, id_bot):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM services WHERE main_cat = ? AND sub_cat = ? AND id_bot = ?", (main_cat, sub_cat, id_bot))
        conn.commit()

def add_order_to_db(order_id, chat_id, service_name, quantity, cost):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (order_id, chat_id, service_name, quantity, cost) VALUES (?, ?, ?, ?, ?)",
                       (order_id, chat_id, service_name, quantity, cost))
        conn.commit()

def get_user_orders(chat_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT order_id, service_name, quantity, cost FROM orders WHERE chat_id = ? ORDER BY id DESC LIMIT 5", (chat_id,))
        return cursor.fetchall()

def add_payment_to_db(chat_id, method, amount, txid, status='Approved'):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (chat_id, method, amount, txid, status) VALUES (?, ?, ?, ?, ?)",
                       (chat_id, method, amount, txid, status))
        conn.commit()

def save_auto_sms_trx(txid, amount, method):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        clean_tx = clean_transaction_id(txid)
        cursor.execute("INSERT OR IGNORE INTO auto_transactions (txid, amount, method, status) VALUES (?, ?, ?, 'Unclaimed')",
                       (clean_tx, amount, method))
        conn.commit()

def claim_auto_trx(txid):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        clean_tx = clean_transaction_id(txid)
        cursor.execute("SELECT amount, method, status FROM auto_transactions WHERE UPPER(txid) = ?", (clean_tx,))
        row = cursor.fetchone()
        if row and row[2] == 'Unclaimed':
            cursor.execute("UPDATE auto_transactions SET status = 'Claimed' WHERE UPPER(txid) = ?", (clean_tx,))
            conn.commit()
            return float(row[0]), row[1]
        return None, None

def get_user_payments(chat_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT method, amount, txid, status FROM payments WHERE chat_id = ? ORDER BY id DESC LIMIT 10", (chat_id,))
        return cursor.fetchall()

init_db()

# ----------------- 📱 SECURE WEB-APP PAYMENT SYSTEM -----------------
@app.route('/')
def home():
    domain = request.url_root.strip('/')
    if domain.startswith("http://"):
        domain = domain.replace("http://", "https://")
    set_setting("bot_domain", domain)
    return "SMM Bot Server is Alive and 24/7 Running!", 200

# কাস্টম গেটওয়ে পেইজ এইচটিএমএল (অ্যানিমেশন এবং ডিজাইনে আপগ্রেড করা হয়েছে)
@app.route('/payment-page')
def payment_page():
    coins = request.args.get('coins', '1000') # Coins are now treated directly as BDT/Taka
    bdt = request.args.get('bdt', '12')
    bkash_num = request.args.get('bkash', '01925263571')
    nagad_num = request.args.get('nagad', '01925263571')
    
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MR PAY GATEWAY</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { font-family: 'Arial', sans-serif; background: linear-gradient(135deg, #F3F8FF 0%, #E3EFFF 100%); margin: 0; padding: 15px; color: #333; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .container { background-color: #fff; border-radius: 20px; padding: 25px 20px; box-shadow: 0 10px 30px rgba(30,136,229,0.1); text-align: center; width: 100%; max-width: 400px; box-sizing: border-box; transform: scale(0.95); animation: popIn 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards; }
            
            @keyframes popIn {
                to { transform: scale(1); }
            }

            .badge-bdt { font-size: 24px; font-weight: bold; color: #1E88E5; margin: 15px 0; }
            .instructions-banner { padding: 12px; border-radius: 12px; font-size: 13px; margin-bottom: 20px; font-weight: bold; text-align: center; animation: pulse 1.5s infinite; }
            
            @keyframes pulse {
                0% { opacity: 0.9; }
                50% { opacity: 1; transform: scale(1.02); }
                100% { opacity: 0.9; }
            }

            .method-btn { background: linear-gradient(135deg, #1E88E5 0%, #1565C0 100%); color: white; padding: 16px; border-radius: 12px; font-size: 16px; font-weight: bold; border: none; width: 100%; cursor: pointer; transition: all 0.3s; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(30,136,229,0.3); }
            .method-btn:active { transform: scale(0.98); }
            
            .payment-box { display: none; text-align: left; padding: 20px; border-radius: 20px; color: white; box-shadow: 0 10px 25px rgba(0,0,0,0.15); animation: slideUp 0.4s ease forwards; }
            
            @keyframes slideUp {
                from { transform: translateY(30px); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }

            .bkash-theme { background: linear-gradient(135deg, #E2125D 0%, #9F063A 100%); }
            .nagad-theme { background: linear-gradient(135deg, #E11C24 0%, #A30A0E 100%); }
            
            .input-trx { width: calc(100% - 26px); padding: 14px; border-radius: 10px; border: 2px solid rgba(255,255,255,0.3); margin: 15px 0; font-size: 16px; background: rgba(255,255,255,0.1); color: white; outline: none; transition: 0.3s; }
            .input-trx::placeholder { color: rgba(255,255,255,0.6); }
            .input-trx:focus { background: rgba(255,255,255,0.25); border-color: white; }
            
            .copy-row { display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.15); padding: 12px; border-radius: 10px; font-size: 15px; margin-top: 8px; border: 1px dashed rgba(255,255,255,0.4); }
            .copy-btn { background: white; color: #333; border: none; padding: 6px 15px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: bold; transition: 0.2s; }
            .copy-btn:active { transform: scale(0.9); }
            
            .verify-btn { background: #fff; color: #333; width: 100%; padding: 15px; border-radius: 12px; border: none; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); transition: 0.3s; }
            .verify-btn:active { transform: scale(0.97); }
            
            .footer-nav { margin-top: 25px; display: flex; gap: 15px; justify-content: center; }
            .icon-btn { background: #fff; border: 1px solid #e0e0e0; border-radius: 50%; width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; font-size: 22px; cursor: pointer; text-decoration: none; transition: 0.3s; box-shadow: 0 4px 10px rgba(0,0,0,0.03); }
            .icon-btn:active { transform: scale(0.9); }
            
            .gateway-options { display: flex; justify-content: space-between; margin-top: 15px; gap: 15px; }
            .gate-select-btn { border: 1px solid #e2e8f0; background: white; padding: 10px; border-radius: 16px; width: 48%; cursor: pointer; transition: all 0.3s; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 12px rgba(0,0,0,0.02); height: 80px; overflow: hidden; }
            .gate-select-btn:active { transform: scale(0.95); box-shadow: none; }
            .gate-select-btn img { max-height: 100%; max-width: 100%; object-fit: cover; border-radius: 10px; }
            .active-view { display: block !important; }
        </style>
    </head>
    <body>
        <div class="container">
            <!-- ১ম পেইজ: মেথড সিলেকশন -->
            <div id="method-selection-view" class="active-view">
                <button class="method-btn" style="box-shadow:none;">Mobile Banking</button>
                <div class="gateway-options">
                    <div class="gate-select-btn" onclick="switchView('bkash')">
                        <img src="https://files.catbox.moe/54mbuq.jpg" alt="bKash">
                    </div>
                    <div class="gate-select-btn" onclick="switchView('nagad')">
                        <img src="https://files.catbox.moe/m4iobq.jpg" alt="Nagad">
                    </div>
                </div>
                <div class="footer-nav">
                    <a href="https://t.me/Mr_Sojol_Ceo" class="icon-btn">🎧</a>
                    <a href="https://wa.me/8801925263571" class="icon-btn">💬</a>
                    <a href="tel:01925263571" class="icon-btn">📞</a>
                </div>
                <button class="method-btn" style="margin-top:30px; background:#EBF5FB; color:#1E88E5; box-shadow:none;" disabled>Pay {{ bdt }} BDT</button>
            </div>

            <!-- বিকাশ পেমেন্ট পেইজ -->
            <div id="bkash-payment-view" class="payment-box bkash-theme">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px;">
                    <span style="font-weight:bold; font-size:20px;">bKash Personal</span>
                    <span style="font-weight:bold; font-size:20px;">{{ bdt }} BDT</span>
                </div>
                <div class="instructions-banner" style="color:#fff; background:rgba(0,0,0,0.25);">
                    নোটঃ টাকা পাঠানোর ৫-১০ সেকেন্ড পর ভেরিফাই করবেন।
                </div>
                
                <label style="font-size:14px; font-weight:bold; letter-spacing:0.5px;">ট্রানজেকশন আইডি দিন</label>
                <input type="text" id="bkash-trx" class="input-trx" placeholder="ট্রানজেকশন আইডি দিন">

                <div style="font-size:13.5px; line-height:1.7; opacity: 0.95;">
                    <p>• <b>*247#</b> ডায়াল করে আপনার <b>BKASH</b> মোবাইল মেন্যুতে যান অথবা <b>BKASH</b> অ্যাপে যান।</p>
                    <p>• <b>"Send Money"</b> এ ক্লিক করুন।</p>
                    <p>• প্রাপক নাম্বার হিসেবে নিচের নাম্বারটি লিখুন:</p>
                    <div class="copy-row">
                        <span id="bkash-num-val" style="font-weight:bold; font-size:16px; letter-spacing:0.5px;">{{ bkash_num }}</span>
                        <button class="copy-btn" onclick="copyNumber('{{ bkash_num }}')">Copy</button>
                    </div>
                    <p>• পরিমাণ: <b>{{ bdt }} BDT</b> দিয়ে পিন নম্বর দিয়ে সেন্ড করুন।</p>
                    <p>• সফলভাবে পাঠানো সম্পন্ন হলে প্রাপ্ত <b>Transaction ID</b> ওপরে বসিয়ে নিচের বাটনে ক্লিক করুন।</p>
                </div>
                <button class="verify-btn" onclick="verifyTrx('bkash')">VERIFY TRANSACTION</button>
                <button class="verify-btn" style="background:transparent; color:white; border:1px solid rgba(255,255,255,0.4); margin-top:12px; box-shadow:none;" onclick="goHome()">BACK</button>
            </div>

            <!-- নগদ পেমেন্ট পেইজ -->
            <div id="nagad-payment-view" class="payment-box nagad-theme">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px;">
                    <span style="font-weight:bold; font-size:20px;">Nagad Personal</span>
                    <span style="font-weight:bold; font-size:20px;">{{ bdt }} BDT</span>
                </div>
                <div class="instructions-banner" style="color:#fff; background:rgba(0,0,0,0.25);">
                    নোটঃ টাকা পাঠানোর ৫-১০ সেকেন্ড পর ভেরিফাই করবেন।
                </div>
                
                <label style="font-size:14px; font-weight:bold; letter-spacing:0.5px;">ট্রানজেকশন আইডি দিন</label>
                <input type="text" id="nagad-trx" class="input-trx" placeholder="ট্রানজেকশন আইডি দিন">

                <div style="font-size:13.5px; line-height:1.7; opacity: 0.95;">
                    <p>• <b>*167#</b> ডায়াল করে আপনার <b>NAGAD</b> মোবাইল মেন্যুতে যান অথবা <b>NAGAD</b> অ্যাপে যান।</p>
                    <p>• <b>"Send Money"</b> এ ক্লিক করুন।</p>
                    <p>• প্রাপক নাম্বার হিসেবে নিচের নাম্বারটি লিখুন:</p>
                    <div class="copy-row">
                        <span id="nagad-num-val" style="font-weight:bold; font-size:16px; letter-spacing:0.5px;">{{ nagad_num }}</span>
                        <button class="copy-btn" onclick="copyNumber('{{ nagad_num }}')">Copy</button>
                    </div>
                    <p>• পরিমাণ: <b>{{ bdt }} BDT</b> দিয়ে পিন নম্বর দিয়ে সেন্ড করুন।</p>
                    <p>• সফলভাবে পাঠানো সম্পন্ন হলে প্রাপ্ত <b>Transaction ID</b> ওপরে বসিয়ে নিচের বাটনে ক্লিক করুন।</p>
                </div>
                <button class="verify-btn" onclick="verifyTrx('nagad')">VERIFY TRANSACTION</button>
                <button class="verify-btn" style="background:transparent; color:white; border:1px solid rgba(255,255,255,0.4); margin-top:12px; box-shadow:none;" onclick="goHome()">BACK</button>
            </div>

        </div>

        <script>
            const tg = window.Telegram.WebApp;
            tg.expand();

            function switchView(method) {
                document.getElementById('method-selection-view').classList.remove('active-view');
                if (method === 'bkash') {
                    document.getElementById('bkash-payment-view').classList.add('active-view');
                } else {
                    document.getElementById('nagad-payment-view').classList.add('active-view');
                }
            }

            function goHome() {
                document.getElementById('bkash-payment-view').classList.remove('active-view');
                document.getElementById('nagad-payment-view').classList.remove('active-view');
                document.getElementById('method-selection-view').classList.add('active-view');
            }

            function copyNumber(num) {
                navigator.clipboard.writeText(num).then(() => {
                    alert('সফলভাবে নাম্বার কপি করা হয়েছে!');
                });
            }

            function verifyTrx(method) {
                const trx = (method === 'bkash' ? document.getElementById('bkash-trx').value : document.getElementById('nagad-trx').value).trim();
                if (!trx) {
                    alert('অনুগ্রহ করে সঠিক TrxID টাইপ করুন।');
                    return;
                }
                tg.sendData(trx);
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_content, coins=coins, bdt=bdt, bkash_num=bkash_num, nagad_num=nagad_num)

# --- ওয়েব অ্যাপ সাবমিট হ্যান্ডলার ---
@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    chat_id = message.chat.id
    raw_txid = message.web_app_data.data.strip()
    user_txid = clean_transaction_id(raw_txid)

    amount, method = claim_auto_trx(user_txid)

    if amount and method:
        if chat_id in FAILED_ATTEMPTS:
            FAILED_ATTEMPTS.pop(chat_id)

        # ১:১ টাকা সিস্টেম (টাকা সরাসরি ব্যালেন্সে যোগ হবে)
        received_bdt = amount

        current_bal = get_balance(chat_id)
        new_balance = current_bal + received_bdt
        update_balance(chat_id, new_balance)
        add_payment_to_db(chat_id, method, received_bdt, user_txid, status='Approved')

        bot.send_message(
            chat_id,
            f"✅ <b>পেমেন্ট সফলভাবে ভেরিফাই হয়েছে!</b>\n\n"
            f"💳 <b>মেথড:</b> {method}\n"
            f"৳ <b>প্রাপ্ত ব্যালেন্স:</b> <b>৳ {received_bdt:.2f} BDT</b>\n"
            f"💰 <b>বর্তমান মোট ব্যালেন্স:</b> <b>৳ {new_balance:.2f} BDT</b> 🎉",
            reply_markup=get_main_menu_markup(chat_id),
            parse_mode="HTML"
        )

        # এডমিনের কাছে নোটিফিকেশন পাঠানো
        try:
            admin_msg = (
                f"🎉 <b>AUTO DEPOSIT SUCCESSFUL!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>ইউজার আইডি:</b> <code>{chat_id}</code>\n"
                f"💵 <b>টাকা পরিমাণ:</b> <b>{amount:.2f} BDT</b>\n"
                f"💳 <b>মেথড:</b> <b>{method}</b>\n"
                f"🆔 <b>TrxID:</b> <code>{user_txid}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            bot.send_message(MAIN_ADMIN_ID, admin_msg, parse_mode="HTML")
        except Exception:
            pass
    else:
        bot.send_message(
            chat_id,
            "❌ <b>অনুরোধ প্রত্যাখ্যান! অনুগ্রহ করে সঠিক TRX ID দিন এবং পুনরায় চেষ্টা করুন।</b>",
            reply_markup=get_main_menu_markup(chat_id),
            parse_mode="HTML"
        )

# --- 📱 SMS WEBHOOK (মাল্টি-রুট ম্যাপিং ফিক্স এবং ডিবাগিং লগ সহ) -----------------
@app.route('/sms-webhook', methods=['POST', 'GET'], strict_slashes=False)
@app.route('/sms-webhook/<token>', methods=['POST', 'GET'], strict_slashes=False)
def sms_webhook(token=None):
    try:
        # রিকুয়েস্টের সমস্ত কী (Keys) এবং ভ্যালু (Values) এক সাথে মার্জ করে প্রসেসিং
        raw_texts = []
        for k, v in request.args.items():
            raw_texts.append(f"{k}: {v}")
        for k, v in request.form.items():
            raw_texts.append(f"{k}: {v}")
        if request.is_json:
            try:
                js = request.get_json(silent=True)
                if js and isinstance(js, dict):
                    for k, v in js.items():
                        raw_texts.append(f"{k}: {v}")
            except Exception:
                pass
                
        raw_data = ""
        try:
            raw_data = request.get_data(as_text=True)
            if raw_data: raw_texts.append(raw_data)
        except Exception:
            try:
                raw_data = request.get_data().decode('utf-8', errors='ignore')
                if raw_data: raw_texts.append(raw_data)
            except Exception:
                pass
                
        full_text = urllib.parse.unquote(" ".join(raw_texts)).replace('+', ' ')

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

            # ট্রানজেকশন আইডি ফিল্টার ও ক্লিনিং করা
            clean_tx = clean_transaction_id(txid)
            save_auto_sms_trx(clean_tx, amount, method)

            try:
                bot.send_message(MAIN_ADMIN_ID, f"📩 <b>{method} Auto SMS Received!</b>\n\n💵 Amount: <b>{amount:.2f} BDT</b>\n🆔 TrxID: <code>{clean_tx}</code>", parse_mode="HTML")
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

# ================== 👑 এডমিন প্যানেল (/admin) ==================

@bot.message_handler(commands=["admin"])
def admin_panel_command(message):
    if not is_admin(message.chat.id):
        return
        
    # গ্লিচ ফিক্স করতে এবং সাইলেন্ট ক্র্যাশ প্রতিরোধে মেথড ক্লিয়ারিং এবং ট্রাই-ক্লিন ব্লক
    try:
        clear_user_steps(message.chat.id) # পূর্বের আটকে থাকা সব স্টেপ ডিলিট করা
        
        btn1 = types.InlineKeyboardButton("➕ মেইন প্ল্যাটফর্ম যোগ", callback_data="admin_add_main_cat")
        btn2 = types.InlineKeyboardButton("📂 সাব-ক্যাটাগরি যোগ", callback_data="admin_add_sub_cat")
        btn3 = types.InlineKeyboardButton("🛒 নতুন সার্ভিস যোগ", callback_data="admin_add_service_start")
        btn4 = types.InlineKeyboardButton("🔍 ইউজার ইনফো ও কয়েন", callback_data="admin_user_info_start")
        btn5 = types.InlineKeyboardButton("🖼️ স্টার্ট পিকচার সেট", callback_data="admin_set_start_photo")
        btn6 = types.InlineKeyboardButton("📝 স্টার্ট ডিসক্রিপশন সেট", callback_data="admin_set_welcome_text")
        btn7 = types.InlineKeyboardButton("📢 জয়েন চ্যানেল সেটআপ", callback_data="admin_force_channel_menu")
        btn8 = types.InlineKeyboardButton("🔌 SMM API এডিট", callback_data="admin_set_smm_api")
        btn9 = types.InlineKeyboardButton("👑 এডমিন যোগ/রিমুভ", callback_data="admin_manage_co_admins")
        btn10 = types.InlineKeyboardButton("🗑️ একটি সার্ভিস ডিলিট", callback_data="admin_delete_single_service_start")
        btn11 = types.InlineKeyboardButton("🗑️ প্ল্যাটফর্ম ডিলিট", callback_data="admin_del_main_platform_start")
        btn12 = types.InlineKeyboardButton("🗑️ সাব-ক্যাট ডিলিট", callback_data="admin_del_subcategory_start")
        btn13 = types.InlineKeyboardButton("🪙 কয়েন রেট আপডেট", callback_data="admin_set_coin_rate")
        btn14 = types.InlineKeyboardButton("📢 ব্রডকাস্ট মেসেজ", callback_data="admin_broadcast_start")
        btn15 = types.InlineKeyboardButton("📊 লাইভ সেলস ও লাভ", callback_data="admin_live_stats")
        
        # নতুন সেটিংস কনফিগারেশন বাটনসমূহ
        btn16 = types.InlineKeyboardButton("📞 বিকাশ নাম্বার সেট", callback_data="admin_set_bkash")
        btn17 = types.InlineKeyboardButton("📱 নগদ নাম্বার সেট", callback_data="admin_set_nagad")
        btn18 = types.InlineKeyboardButton("👤 সাপোর্ট ইউজার সেট", callback_data="admin_set_sup_user")
        btn19 = types.InlineKeyboardButton("📱 সাপোর্ট ফোন সেট", callback_data="admin_set_sup_phone")
        btn20 = types.InlineKeyboardButton("📦 অর্ডার ফরওয়ার্ড চ্যানেল সেট", callback_data="admin_set_log_chan")
        btn21 = types.InlineKeyboardButton("💰 প্রাইজ লিস্ট টেক্সট সেট", callback_data="admin_set_price_text")
        btn22 = types.InlineKeyboardButton("📝 অর্ডার সাকসেস নোট সেট", callback_data="admin_set_success_note")
        
        btn23 = types.InlineKeyboardButton("💥 সকল সার্ভিস ডিলিট", callback_data="admin_clear_services_confirm")

        markup = create_2col_markup([
            btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, 
            btn11, btn12, btn13, btn14, btn15, btn16, btn17, btn18, btn19, btn20, btn21, btn22, btn23
        ])

        bot.send_message(
            message.chat.id,
            "👑 <b>এডমিন কন্ট্রোল প্যানেল</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "নিচের বাটন চেপে যেকোনো কাজ সিলেক্ট করুন:",
            reply_markup=markup,
            parse_mode="HTML"
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ এডমিন প্যানেল লোড করতে সমস্যা: {str(e)}")

# --- এডমিন সেটিংস হ্যান্ডলারসমূহ (প্রতিটি রুটেই স্টেপ ক্লিয়ারিং যুক্ত) ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_set_bkash")
def admin_set_bkash(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "📞 <b>আপনার নতুন বিকাশ পার্সোনাল নাম্বারটি টাইপ করে পাঠান:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_bkash)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_bkash(message):
    try:
        num = message.text.strip()
        set_setting("bkash_number", num)
        bot.send_message(message.chat.id, f"✅ <b>বিকাশ নাম্বার সফলভাবে সেট করা হয়েছে:</b> <code>{num}</code>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_nagad")
def admin_set_nagad(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "📱 <b>আপনার নতুন নগদ পার্সোনাল নাম্বারটি টাইপ করে পাঠান:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_nagad)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_nagad(message):
    try:
        num = message.text.strip()
        set_setting("nagad_number", num)
        bot.send_message(message.chat.id, f"✅ <b>নগদ নাম্বার সফলভাবে সেট করা হয়েছে:</b> <code>{num}</code>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_sup_user")
def admin_set_sup_user(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "👤 <b>আপনার নতুন সাপোর্ট টেলিগ্রাম ইউজারনেমটি টাইপ করে পাঠান:</b>\n(অবশ্যই @ সহ লিখবেন, যেমন: `@Mr_Sojol_Ceo`)", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_sup_user)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_sup_user(message):
    try:
        username = message.text.strip()
        set_setting("support_username", username)
        bot.send_message(message.chat.id, f"✅ <b>সাপোর্ট ইউজারনেম সফলভাবে সেট করা হয়েছে:</b> <code>{username}</code>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_sup_phone")
def admin_set_sup_phone(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "📱 <b>আপনার নতুন সাপোর্ট হোয়াটসঅ্যাপ/ফোন নাম্বারটি টাইপ করে পাঠান:</b>\n(যেমন: `+8801925263571`)", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_sup_phone)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_sup_phone(message):
    try:
        phone = message.text.strip()
        set_setting("support_phone", phone)
        bot.send_message(message.chat.id, f"✅ <b>সাপোর্ট ফোন নাম্বার সফলভাবে সেট করা হয়েছে:</b> <code>{phone}</code>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_log_chan")
def admin_set_log_chan(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(
            call.message.chat.id, 
            "📦 <b>অর্ডার ফরওয়ার্ড করার জন্য আপনার চ্যানেল বা গ্রুপের ID-টি টাইপ করে পাঠান:</b>\n\n"
            "ℹ️ <i>কিভাবে আইডি পাবেন:</i>\n"
            "১. প্রথমে বোটকে আপনার চ্যানেল বা গ্রুপে অ্যাডমিন হিসেবে যুক্ত করুন এবং মেসেজ পাঠানোর পারমিশন দিন।\n"
            "২. এরপর আপনার চ্যানেলের আইডিটি (যেমন: `-1002345678912`) এখানে টাইপ করে পাঠান।", 
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, save_log_chan)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_log_chan(message):
    try:
        cid = message.text.strip()
        set_setting("log_channel_id", cid)
        bot.send_message(message.chat.id, f"✅ <b>অর্ডার লগ চ্যানেল আইডি সফলভাবে সেট করা হয়েছে:</b> <code>{cid}</code>\n\nএখন থেকে প্রতিটি সফল অর্ডার এই চ্যানেলে স্বয়ংক্রিয়ভাবে ফরওয়ার্ড হয়ে যাবে।", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_price_text")
def admin_set_price_text(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "💰 <b>আপনার বোটের জন্য নতুন কাস্টম প্রাইজ লিস্ট টেক্সটটি টাইপ করে পাঠান:</b>\n(HTML কোড এবং যেকোনো আকর্ষণীয় ইমোজি ব্যবহার করতে পারবেন)", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_price_text)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_price_text(message):
    try:
        txt = message.text.strip()
        set_setting("price_list_text", txt)
        bot.send_message(message.chat.id, "✅ <b>প্রাইজ লিস্ট কাস্টম টেক্সট সফলভাবে সেট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_success_note")
def admin_set_success_note(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "📝 <b>অর্ডার সফল হওয়ার পর নিচে দেখানোর জন্য অতিরিক্ত নোট টেক্সটটি পাঠান:</b>\n(রিসেট করতে `0` পাঠান)", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_success_note)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_success_note(message):
    try:
        txt = message.text.strip()
        if txt == "0":
            set_setting("order_success_note", "")
            bot.send_message(message.chat.id, "✅ <b>অর্ডার সাকসেস নোট রিসেট করা হয়েছে।</b>", parse_mode="HTML")
        else:
            set_setting("order_success_note", txt)
            bot.send_message(message.chat.id, "✅ <b>অর্ডার সাকসেস নোট সফলভাবে সেট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

# --- কয়েন রেট আপডেট ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_set_coin_rate")
def admin_set_coin_rate(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, f"🪙 <b>বর্তমান রেট: ১০০০ কয়েন = {get_coin_rate()} BDT</b>\n\n১০০০ কয়েনের নতুন মূল্য কত টাকা করতে চান? (শুধুমাত্র সংখ্যা যেমন: 12 বা 15 লিখে পাঠান):", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_coin_rate)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_coin_rate(message):
    try:
        new_rate = float(message.text.strip())
        set_setting("coin_rate_per_1000", new_rate)
        bot.send_message(message.chat.id, f"✅ <b>কয়েন রেট সফলভাবে আপডেট করা হয়েছে!</b>\nনতুন রেট: ১০০০ কয়েন = <b>{new_rate:.2f} BDT</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

# --- এডমিন মেসেজ ব্রডকাস্ট ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast_start")
def admin_broadcast_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "📢 <b>বোটের সকল ইউজারের কাছে পাঠানোর জন্য আপনার নোটিশ/মেসেজটি লিখুন:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_broadcast)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def process_broadcast(message):
    try:
        text_to_send = message.text
        users = get_all_users()
        if not users:
            bot.send_message(message.chat.id, "❌ কোনো ইউজার খুঁজে পাওয়া যায়নি!")
            return

        msg_loading = bot.send_message(message.chat.id, "⏳ ব্রডকাস্টিং চালু হচ্ছে...")
        success = 0
        fail = 0

        for uid in users:
            try:
                bot.send_message(uid, text_to_send, parse_mode="HTML")
                success += 1
                time.sleep(0.05)
            except Exception:
                fail += 1

        bot.edit_message_text(f"📢 <b>ব্রডকাস্ট রিপোর্ট সম্পন্ন!</b>\n\n✅ সফলভাবে পাঠানো হয়েছে: <b>{success} জন</b>\n❌ ব্যর্থ হয়েছে (ব্লকড): <b>{fail} জন</b>", chat_id=message.chat.id, message_id=msg_loading.message_id, parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

# --- SMM API এডিট ভ্যালিডেশন সহ ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_set_smm_api")
def admin_set_smm_api(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, f"🔌 <b>বর্তমান API URL:</b> <code>{get_smm_api_url()}</code>\n<b>নতুন API URL টি লিখে পাঠান:</b>\n(যেমন: `https://socialpanel.pro/api/v2`)", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_api_url)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_api_url(message):
    try:
        url = message.text.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            bot.send_message(message.chat.id, "❌ <b>ভুল ইউআরএল! লিংকটি অবশ্যই http:// বা https:// দিয়ে শুরু হতে হবে।</b> পুনরায় চেষ্টা করুন।")
            return
        set_setting("smm_api_url", url)
        msg = bot.send_message(message.chat.id, "🔑 <b>এখন আপনার নতুন SMM API Key টি লিখে পাঠান:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_api_key)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_api_key(message):
    try:
        key = message.text.strip()
        if len(key) < 10:
            bot.send_message(message.chat.id, "❌ <b>ভুল বা অকার্যকর API Key!</b> অনুগ্রহ করে পুনরায় সঠিক কী দিয়ে চেষ্টা করুন।")
            return
        set_setting("smm_api_key", key)
        bot.send_message(message.chat.id, "✅ <b>SMM API URL & Key সফলভাবে আপডেট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

# --- এডমিন প্যানেল থেকে সিঙ্গেল প্ল্যাটফর্ম ডিলিট করা ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_del_main_platform_start")
def admin_del_main_platform_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        main_cats = get_main_categories()
        if not main_cats:
            bot.send_message(call.message.chat.id, "❌ কোনো মেইন প্ল্যাটফর্ম পাওয়া যায়নি।")
            return
        btns = [types.InlineKeyboardButton(f"❌ {mc}", callback_data=f"delmainplatform_{mc}") for mc in main_cats]
        markup = create_2col_markup(btns)
        bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মটি সম্পূর্ণ ডিলিট করতে চান?</b>\n(সতর্কতা: এর ভেতরের সকল সাব-ক্যাটাগরি ও সার্ভিস ডিলিট হয়ে যাবে!)", reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmainplatform_"))
def admin_del_main_platform_confirm(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        mcat_name = call.data.replace("delmainplatform_", "")
        delete_main_category(mcat_name)
        bot.send_message(call.message.chat.id, f"✅ <b>[{mcat_name}] প্ল্যাটফর্মটি এবং এর আওতাধীনstone ডিলিট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

# --- এডমিন প্যানেল থেকে সিঙ্গেল সাব-ক্যাটাগরি ডিলিট করা ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_del_subcategory_start")
def admin_del_subcategory_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        main_cats = get_main_categories()
        if not main_cats:
            bot.send_message(call.message.chat.id, "❌ কোনো মেইন প্ল্যাটফর্ম পাওয়া যায়নি।")
            return
        btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"delsubcatselectmc_{mc}") for mc in main_cats]
        markup = create_2col_markup(btns)
        bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মের সাব-ক্যাটাগরি ডিলিট করবেন?</b>", reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delsubcatselectmc_"))
def admin_del_subcategory_select_sub(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        mcat_name = call.data.replace("delsubcatselectmc_", "")
        sub_cats = get_sub_categories(mcat_name)
        if not sub_cats:
            bot.send_message(call.message.chat.id, f"❌ [{mcat_name}] এ কোনো সাব-ক্যাটাগরি নেই।")
            return
        btns = [types.InlineKeyboardButton(f"❌ {sc}", callback_data=f"delsubcatconfirm_{mcat_name}___{sc}") for sc in sub_cats]
        markup = create_2col_markup(btns)
        bot.send_message(call.message.chat.id, f"🗑️ <b>[{mcat_name}] এর কোন সাব-ক্যাটাগরি ডিলিট করবেন?</b>\n(সতর্কতা: এর আওতাধীন সকল সার্ভিস ডিলিট হয়ে যাবে!)", reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delsubcatconfirm_"))
def admin_del_subcategory_confirm(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        raw_data = call.data.replace("delsubcatconfirm_", "")
        mcat_name, scat_name = raw_data.split("___")
        delete_sub_category(mcat_name, scat_name)
        bot.send_message(call.message.chat.id, f"✅ <b>[{mcat_name}] -> [{scat_name}] সাব-ক্যাটাগরি ও এর সার্ভিসগুলো ডিলিট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

# --- লাইভ সেলস ও লাভ ড্যাশবোর্ড ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_live_stats")
def admin_live_stats_callback(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT SUM(amount) FROM payments 
                WHERE status = 'Approved' AND date(timestamp, 'localtime') = date('now', 'localtime')
            """)
            today_deposit = cursor.fetchone()[0]
            today_deposit = today_deposit if today_deposit else 0.0
            
            cursor.execute("""
                SELECT COUNT(*), SUM(cost) FROM orders 
                WHERE date(timestamp, 'localtime') = date('now', 'localtime')
            """)
            row = cursor.fetchone()
            today_orders_count = row[0] if row[0] else 0
            today_orders_cost = row[1] if row[1] else 0.0
            
        stats_text = (
            f"📊 <b>লাইভ সেলস ও লাভ রিপোর্ট (আজকের)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 <b>মোট ইউজার সংখ্যা:</b> <b>{total_users} জন</b>\n"
            f"💳 <b>আজকের মোট ডিপোজিট:</b> <b>{today_deposit:.2f} BDT</b>\n"
            f"🛒 <b>আজকের মোট অর্ডার:</b> <b>{today_orders_count} টি</b>\n"
            f"💰 <b>আজকের মোট সেলস ভ্যালু:</b> <b>{today_orders_cost:.2f} BDT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>পেমেন্ট এবং অর্ডারের লাইভ ডাটাবেজ ট্র্যাক করে এই হিসেব দেখানো হচ্ছে।</i>"
        )
        bot.send_message(call.message.chat.id, stats_text, parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ স্ট্যাটাস লোড করতে ত্রুটি: {str(e)}")

# --- Admin Management ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_manage_co_admins")
def admin_manage_co_admins(call):
    if call.message.chat.id != MAIN_ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ শুধু মেইন এডমিন এটি ব্যবহার করতে পারবে!", show_alert=True)
        return
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("➕ নতুন এডমিন যোগ", callback_data="coadmin_add")
    btn2 = types.InlineKeyboardButton("❌ এডমিন রিমুভ", callback_data="coadmin_remove")
    markup.add(btn1, btn2)

    bot.send_message(MAIN_ADMIN_ID, "👑 <b>এডমিন ম্যানেজমেন্ট প্যানেল</b>\n\nনিচের বাটন ব্যবহার করুন:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("coadmin_"))
def coadmin_action(call):
    if call.message.chat.id != MAIN_ADMIN_ID: return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    action = call.data.replace("coadmin_", "")

    if action == "add":
        msg = bot.send_message(MAIN_ADMIN_ID, "👤 <b>যাকে এডমিন বানাবেন, তার টেলিগ্রাম ইউজার ID দিন:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_co_admin)
    elif action == "remove":
        msg = bot.send_message(MAIN_ADMIN_ID, "👤 <b>যাকে এডমিন থেকে রিমুভ করবেন, তার ইউজার ID দিন:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, remove_co_admin_save)

def save_co_admin(message):
    try:
        aid = int(message.text.strip())
        add_co_admin(aid)
        bot.send_message(MAIN_ADMIN_ID, f"✅ ইউজার <code>{aid}</code> কে এডমিন বানানো হয়েছে!", parse_mode="HTML")
    except ValueError:
        bot.send_message(MAIN_ADMIN_ID, "❌ ভুল ইউজার ID!")

def remove_co_admin_save(message):
    try:
        aid = int(message.text.strip())
        remove_co_admin(aid)
        bot.send_message(MAIN_ADMIN_ID, f"✅ ইউজার <code>{aid}</code> কে এডমিন থেকে সরিয়ে দেওয়া হয়েছে!", parse_mode="HTML")
    except ValueError:
        bot.send_message(MAIN_ADMIN_ID, "❌ ভুল ইউজার ID!")

# --- Start Description Setting ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_set_start_photo")
def admin_set_start_photo(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "🖼️ <b>বোট স্টার্টের ফটো লিংক (Direct Image URL) দিন:</b>\n(যেমন: `https://i.ibb.co/xxxxx/image.jpg` বা রিমুভ করতে `0` পাঠান):", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_start_photo)

def save_start_photo(message):
    url = message.text.strip()
    if url == "0":
        set_setting("start_photo", "")
        bot.send_message(message.chat.id, "✅ <b>স্টার্ট পিকচার রিমুভ করা হয়েছে!</b>", parse_mode="HTML")
    else:
        set_setting("start_photo", url)
        bot.send_message(message.chat.id, "✅ <b>স্টার্ট পিকচার সফলভাবে সেট হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_welcome_text")
def admin_set_welcome_text(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "📝 <b>বোটের প্রোফাইল ডেসক্রিপশন টেক্সট টাইপ করে পাঠান:</b>\n(রিসেট করতে `0` পাঠান)", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_welcome_text)

def save_welcome_text(message):
    txt = message.text.strip()
    if txt == "0":
        set_setting("welcome_text", "")
        bot.send_message(message.chat.id, "✅ <b>ডেসক্রিপশন ডিফল্ট সেটিংয়ে ফিরে গেছে!</b>", parse_mode="HTML")
    else:
        set_setting("welcome_text", txt)
        try:
            bot.set_my_description(txt)
            bot.set_my_short_description(txt)
        except Exception:
            pass
        bot.send_message(message.chat.id, "✅ <b>নতুন প্রোফাইল ডেসক্রিপশন সেভ হয়েছে!</b>", parse_mode="HTML")

# --- 1. মেইন প্ল্যাটফর্ম যোগ ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_main_cat")
def admin_add_main_cat_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "✍️ <b>নতুন মেইন প্ল্যাটফর্মের নাম লিখুন:</b>\n(যেমন: `🎵 TikTok Service` বা `👥 Facebook Service`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_save_main_cat)

def admin_save_main_cat(message):
    mcat_name = message.text.strip()
    add_main_category(mcat_name)
    bot.send_message(message.chat.id, f"✅ <b>মেইন প্ল্যাটফর্ম [{mcat_name}] তৈরি হয়েছে!</b>", parse_mode="HTML")

# --- 2. সাব-ক্যাটাগরি যোগ ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_sub_cat")
def admin_add_sub_cat_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)

    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(call.message.chat.id, "❌ আগে মেইন প্ল্যাটফর্ম তৈরি করুন!", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"admsubsel_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "📁 <b>কোন প্ল্যাটফর্মের ভেতরে সাব-ক্যাটাগরি যোগ করবেন?</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admsubsel_"))
def admin_sub_cat_get_name(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    mcat_name = call.data.replace("admsubsel_", "")

    msg = bot.send_message(call.message.chat.id, f"✍️ <b>[{mcat_name}] এর নতুন সাব-ক্যাটাগরি (সার্ভিস) নাম লিখুন:</b>\n(যেমন: `TikTok View` বা `FB Like`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_save_sub_cat, mcat_name)

def admin_save_sub_cat(message, mcat_name):
    sub_name = message.text.strip()
    add_sub_category(mcat_name, sub_name)
    bot.send_message(message.chat.id, f"✅ <b>[{mcat_name}] -> [{sub_name}] সাব-ক্যাটাগরি তৈরি হয়েছে!</b>", parse_mode="HTML")

# --- 3. SMM সার্ভিস যোগ (সহজ ক্যাটাগরি ম্যাপিং) ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_add_service_start")
def admin_add_service_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)

    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(call.message.chat.id, "❌ কোনো মেইন প্ল্যাটফর্ম নেই! আগে মেইন প্ল্যাটফর্ম যোগ করুন।", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"admcatm_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "📁 <b>মেইন প্ল্যাটফর্ম সিলেক্ট করুন:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcatm_"))
def admin_step_select_sub_for_service(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    mcat_name = call.data.replace("admcatm_", "")

    sub_cats = get_sub_categories(mcat_name)
    if not sub_cats:
        bot.send_message(call.message.chat.id, f"❌ [{mcat_name}] এ কোনো সাব-ক্যাটাগরি (সার্ভিস) নেই! আগে সাব-ক্যাটাগরি যোগ করুন।", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"📂 {sc}", callback_data=f"admcats_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, f"📂 <b>[{mcat_name}] এর সাব-ক্যাটাগরি (সার্ভিস) সিলেক্ট করুন:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcats_"))
def admin_step_get_api_id(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)

    raw_data = call.data.replace("admcats_", "")
    mcat_name, scat_name = raw_data.split("___")

    msg = bot.send_message(call.message.chat.id, f"🔌 <b>[{scat_name}] এর আসল API ID কত?</b> (যেমন: 19138):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_direct_coin, mcat_name, scat_name)

def admin_step_get_direct_coin(message, mcat_name, scat_name):
    api_id = message.text.strip()
    msg = bot.send_message(message.chat.id, f"🪙 <b>প্রতি ১০০০টির জন্য কাস্টমার থেকে কত টাকা কাটবেন?</b> (যেমন: 10 বা 15):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_min_qty, mcat_name, scat_name, api_id)

def admin_step_get_min_qty(message, mcat_name, scat_name, api_id):
    try:
        coin_price = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল ইনপুট! শুধুমাত্র সংখ্যা টাইপ করুন।")
        return

    msg = bot.send_message(message.chat.id, f"🔢 <b>সর্বনিম্ন কোয়ান্টিটি (Min Qty) কত হবে?</b> (যেমন: 100 বা 1000):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_description, mcat_name, scat_name, api_id, coin_price)

def admin_step_get_description(message, mcat_name, scat_name, api_id, coin_price):
    try:
        min_qty = int(message.text.strip())
    except ValueError:
        min_qty = 10
        
    msg = bot.send_message(message.chat.id, "📝 <b>এই সার্ভিসের জন্য একটি বিবরণ (Description) বা নির্দেশনা লিখুন:</b>\n(না দিতে চাইলে `0` লিখে পাঠান)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_save_direct_service, mcat_name, scat_name, api_id, coin_price, min_qty)

def admin_step_save_direct_service(message, mcat_name, scat_name, api_id, coin_price, min_qty):
    desc = message.text.strip()
    if desc == "0":
        desc = ""

    # চয়েস আইডি বাদ দিয়ে সরাসরি সাব-ক্যাটেগরি ম্যাপিং করে সার্ভিসটি সেভ করা (ডেসক্রিপশন সহ)
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO services (main_cat, sub_cat, id_bot, api_id, name, price_per_1k, min_qty, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (mcat_name, scat_name, "1", api_id, scat_name, coin_price, min_qty, desc))
        conn.commit()

    bot.send_message(
        message.chat.id,
        f"✅ <b>সার্ভিসটি সফলভাবে যুক্ত করা হয়েছে!</b>\n\n"
        f"📁 <b>প্ল্যাটফর্ম:</b> <code>{mcat_name}</code>\n"
        f"📂 <b>সাব-ক্যাটাগরি:</b> <code>{scat_name}</code>\n"
        f"🔌 <b>API ID:</b> <b>{api_id}</b>\n"
        f"💰 <b>কয়েন প্রাইজ (১০০০টি):</b> <b>{coin_price:.2f} BDT</b>\n"
        f"🔢 <b>সর্বনিম্ন অর্ডার:</b> <b>{min_qty} টি</b>\n"
        f"📝 <b>ডেসক্রিপশন:</b> <b>{desc}</b>",
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
    time.sleep(2)
    start_bot_polling()
