import os
import sqlite3
import threading
import time
import random
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from deep_translator import GoogleTranslator
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==========================================
# 0. RENDER UCHUN YOLG'ONCHI VEB-SERVER (PORT XATOSINI YO'Q QILISH)
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running successfully!")

    def log_message(self, format, *args):
        return  # Loglarni keraksiz yozuvlar bilan to'ldirmaslik uchun

def run_health_server():
    # Render avtomatik taqdim etadigan portni oladi, bo'lmasa 10000 ni ishlatadi
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"Fake server {port}-portda ishga tushdi...")
    server.serve_forever()

# ==========================================
# 1. BOT SOZLAMALARI
# ==========================================
API_TOKEN = '8629414647:AAHUlQNffYLXZHxeV_P4Ut3tpUlpfPyMUlo'
GROUP_CHAT_ID = '@testlar_bazasi_ingiliz'   

bot = telebot.TeleBot(API_TOKEN)
translator = GoogleTranslator(source='en', target='uz')
DB_FILE = "clean_database.db"  

IS_LOOP_RUNNING = False

# ==========================================
# 2. MA'LUMOTLAR BAZASI
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, score INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS active_tests (message_id INTEGER PRIMARY KEY, correct_answer TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS solved_tests (user_id INTEGER, message_id INTEGER, PRIMARY KEY (user_id, message_id))')
    conn.commit()
    conn.close()

init_db()

def add_score(user_id, name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT score FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        new_score = row[0] + 1
        cursor.execute("UPDATE users SET name = ?, score = ? WHERE user_id = ?", (name, new_score, user_id))
    else:
        new_score = 1
        cursor.execute("INSERT INTO users (user_id, name, score) VALUES (?, ?, ?)", (user_id, name, new_score))
    conn.commit()
    conn.close()
    return new_score

def get_leaderboard_text():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT name, score FROM users ORDER BY score DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return "📊 Hozircha guruhda hech kim to'g'ri javob berib ball to'plamadi."
    leaderboard_text = "📊 **Guruhdagi eng bilimdonlar reytingi (Top 20):**\n\n"
    medals = {1: "🥇 1-o'rin", 2: "🥈 2-o'rin", 3: "🥉 3-o'rin"}
    for index, (name, score) in enumerate(rows, start=1):
        place_text = medals.get(index, f"🔹 {index}-o'rin")
        leaderboard_text += f"{place_text}: {name} — {score} ball\n"
    return leaderboard_text

# ==========================================
# 3. TEST PARAMETRLARI
# ==========================================
fake_answers = ["olma", "kitob", "uy", "mashina", "yugurmoq", "baxtli", "sovuq", "issiq", "suv", "non", "shahar", "stul", "stol", "deraza", "eshik", "maktab", "ruchka", "daftar", "telefon", "kompyuter", "soat"]

def get_random_word():
    try:
        response = requests.get("https://random-word-api.herokuapp.com/word?number=1")
        if response.status_code == 200: return response.json()[0].capitalize()
    except: return None

# ==========================================
# 4. TUGMALAR ISHLASHI
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("ans_"))
def handle_answer(call):
    conn = None
    try:
        user_id = call.from_user.id
        first_name = call.from_user.first_name if call.from_user.first_name else "Bilimdon"
        last_name = call.from_user.last_name if call.from_user.last_name else ""
        full_name = f"{first_name} {last_name}".strip()
        message_id = call.message.message_id
        selected_answer = call.data.split("ans_")[1]
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM solved_tests WHERE user_id = ? AND message_id = ?", (user_id, message_id))
        if cursor.fetchone():
            bot.answer_callback_query(call.id, "⚠️ Siz bu testga javob berib bo'lgansiz! Faqat 1 marta urinish mumkin.", show_alert=True)
            return
            
        cursor.execute("SELECT correct_answer FROM active_tests WHERE message_id = ?", (message_id,))
        row = cursor.fetchone()
        if not row:
            bot.answer_callback_query(call.id, "⚠️ Bu test topilmadi yoki eskirgan!", show_alert=True)
            return
            
        correct_answer = row[0]
        cursor.execute("INSERT INTO solved_tests (user_id, message_id) VALUES (?, ?)", (user_id, message_id))
        conn.commit()
        
        if selected_answer == correct_answer:
            current_score = add_score(user_id, full_name)
            bot.answer_callback_query(call.id, f"🎉 To'g'ri topdingiz!\nSizning jami ballingiz: {current_score} taga yetdi.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"❌ Noto'g'ri javob! To'g'ri tarjima: {correct_answer.capitalize()} edi.", show_alert=True)
            
    except Exception as e: print(f"Tugma xatosi: {e}")
    finally:
        if conn: conn.close()

# ==========================================
# 5. REYTING BUYRUG'I
# ==========================================
@bot.message_handler(commands=['reyting'])
def send_leaderboard(message):
    try: bot.reply_to(message, get_leaderboard_text(), parse_mode="Markdown")
    except Exception as e: print(f"Reyting buyrug'i xatosi: {e}")

# ==========================================
# 6. TEST GENERATOR TSIKLI
# ==========================================
def test_sending_loop():
    global IS_LOOP_RUNNING
    if IS_LOOP_RUNNING: return
    IS_LOOP_RUNNING = True
    
    time.sleep(10)
    test_counter = 0
    while True:
        try:
            word = get_random_word()
            if not word:
                time.sleep(10)
                continue
            correct_uz = translator.translate(word).lower()
            if word.lower() == correct_uz or correct_uz in fake_answers: continue
            
            options = random.sample(fake_answers, 3) + [correct_uz]
            random.shuffle(options)
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(*[InlineKeyboardButton(text=opt.capitalize(), callback_data=f"ans_{opt}") for opt in options])
            
            msg = bot.send_message(
                chat_id=GROUP_CHAT_ID, 
                text=f"🇬🇧 **{word}** — so'zining to'g'ri tarjimasini toping:", 
                reply_markup=markup, 
                parse_mode="Markdown"
            )
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO active_tests (message_id, correct_answer) VALUES (?, ?)", (msg.message_id, correct_uz))
            conn.commit()
            conn.close()
            
            test_counter += 1
            if test_counter >= 30:
                time.sleep(15)
                bot.send_message(GROUP_CHAT_ID, "🔔 **30 ta test yakunlandi!**\n\n" + get_leaderboard_text(), parse_mode="Markdown")
                test_counter = 0
                time.sleep(900)  
                bot.send_message(GROUP_CHAT_ID, "🚀 **Yangi turnir boshlandi! Ilk savollar yo'lda...**")
                continue
            time.sleep(60)  
        except Exception as e: time.sleep(15)

# ==========================================
# 7. ISHGA TUSHIRISH
# ==========================================
if __name__ == "__main__":
    try:
        bot.remove_webhook()  
        requests.get(f"https://api.telegram.org/bot{API_TOKEN}/deleteWebhook?drop_pending_updates=true")
    except: pass
    
    time.sleep(2)
    
    # 1. Loyiha Render'da BEPUL ishlashi uchun yolg'onchi serverni alohida oqimda yoqamiz
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # 2. Test oqimini yoqish
    threading.Thread(target=test_sending_loop, daemon=True).start()
    
    print("Yangi bot 0 dan toza holatda ishga tushmoqda...")
    bot.infinity_polling(allowed_updates=["message", "callback_query"])
