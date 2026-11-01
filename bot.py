import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import pandas as pd
import io
import re
import os
import sys
from flask import Flask
from threading import Thread

BOT_TOKEN = os.environ.get('BOT_TOKEN') 
OWNER_ID = int(os.environ.get('OWNER_ID', 123456789))

bot = telebot.TeleBot(BOT_TOKEN)

ALLOWED_USERS = {OWNER_ID}
user_data = {}

def check_access(message):
    return message.chat.id in ALLOWED_USERS

# ================= FIXED NUMBER EXTRACTOR =================
def extract_numbers(file_bytes, filename):
    clean_numbers = []
    
    def process_text(s):
        s = str(s)
        # Kachra hata ke sirf numbers pakadne ki logic
        parts = re.split(r'[a-zA-Z,\n\t|;:_]+', s)
        for p in parts:
            p = p.strip()
            if not p: continue
            
            # Safe split taaki alag-alag numbers aapas me na judein
            sub_parts = re.split(r'\s{2,}', p)
            for sp in sub_parts:
                clean_n = re.sub(r'\D', '', sp)
                if 8 <= len(clean_n) <= 20:
                    clean_numbers.append(clean_n)
                elif len(clean_n) > 20: 
                    for word in sp.split():
                        cn = re.sub(r'\D', '', word)
                        if 8 <= len(cn) <= 20:
                            clean_numbers.append(cn)

    try:
        # dtype=str Excel/CSV ke numbers ko corrupt/scientific notation banne se rokega
        if filename.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
            for col in df.columns:
                for val in df[col].dropna():
                    process_text(val)
                    
        elif filename.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, on_bad_lines='skip')
            for col in df.columns:
                for val in df[col].dropna():
                    process_text(val)
                    
        else:
            text_data = file_bytes.decode('utf-8', errors='ignore')
            process_text(text_data)
            
        return list(dict.fromkeys(clean_numbers))
    except Exception as e:
        print(f"Extraction Error: {e}")
        return []
# ==========================================================

@bot.message_handler(commands=['start'])
def start_command(message):
    if not check_access(message): return
    text = (
        "🤖 **Welcome to CSV/TXT Processing Bot**\n\n"
        "📁 `/Make_CSV` - File bhejo, Software chuno, CC filter karo aur perfect format lo.\n"
        "✂️ `/Split_file` - Sequence files split karne ke liye.\n"
        "📝 `/Make_Txt` - Clean TXT extraction.\n"
        "👤 `/add_user <id>` - Access dene ke liye.\n"
        "🛑 `/Reset` - Stop Process.\n"
        "🔄 `/Restart` - Redeploy."
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['add_user'])
def add_user_command(message):
    if message.chat.id != OWNER_ID: return
    try:
        new_user = int(message.text.split()[1])
        ALLOWED_USERS.add(new_user)
        bot.reply_to(message, f"✅ User {new_user} added.")
    except:
        bot.reply_to(message, "⚠️ Format: /add_user 12345678")

@bot.message_handler(commands=['Reset'])
def reset_command(message):
    if message.chat.id in user_data:
        del user_data[message.chat.id]
    bot.reply_to(message, "🛑 Operations stopped. Memory Cleared.")

@bot.message_handler(commands=['Restart'])
def restart_command(message):
    if message.chat.id != OWNER_ID: return
    bot.reply_to(message, "🔄 Restarting...")
    os.execl(sys.executable, sys.executable, *sys.argv)

@bot.message_handler(commands=['Make_CSV'])
def make_csv_start(message):
    if not check_access(message): return
    msg = bot.reply_to(message, "📥 Send file (TXT, Excel, CSV):")
    bot.register_next_step_handler(msg, process_csv_file)

def process_csv_file(message):
    if message.text == '/Reset': return reset_command(message)
    if not message.document: return
    try:
        bot.reply_to(message, "⏳ Extracting exact numbers without errors...")
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        numbers = extract_numbers(downloaded_file, message.document.file_name)
        if not numbers: return bot.reply_to(message, "❌ No numbers found.")
            
        user_data[message.chat.id] = {'numbers': numbers, 'command': 'Make_CSV'}
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Wati", callback_data="soft_Wati"),
            InlineKeyboardButton("Whinta", callback_data="soft_Whinta"),
            InlineKeyboardButton("Aitoolkit", callback_data="soft_Aitoolkit")
        )
        bot.reply_to(message, f"✅ Found {len(numbers)} contacts.\n\nKonse software ke liye file banani hai?", reply_markup=markup)
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('soft_'))
def software_selection(call):
    software = call.data.split('_')[1]
    user_data[call.message.chat.id]['software'] = software
    msg = bot.edit_message_text(f"✅ Selected: {software}\n\nAb Country Code bhejo (Example: 91, 82):", 
                                call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(msg, process_country_code)

def process_country_code(message):
    if message.text == '/Reset': return reset_command(message)
    cc = message.text.strip().replace('+', '')
    
    numbers = user_data[message.chat.id]['numbers']
    matched_numbers = [n for n in numbers if n.startswith(cc)]
    
    if not matched_numbers:
        return bot.reply_to(message, f"❌ `{cc}` se start hone wala koi number nahi mila!")
        
    user_data[message.chat.id]['matched_numbers'] = matched_numbers
    user_data[message.chat.id]['cc'] = cc
    msg = bot.reply_to(message, f"✅ CC Match: Found {len(matched_numbers)} numbers.\n\nAb File ka Name bhejo:")
    bot.register_next_step_handler(msg, generate_csv_file)

def generate_csv_file(message):
    if message.text == '/Reset': return reset_command(message)
    filename = message.text.strip()
    data = user_data.get(message.chat.id)
    if not data: return 
    
    software = data['software']
    cc = data['cc']
    numbers = data['matched_numbers']
    
    output = io.StringIO()
    if software == 'Wati':
        output.write("Name,CountryCode,Phone\n")
        for num in numbers:
            phone = num[len(cc):] 
            output.write(f"{num},{cc},{phone}\n")
    elif software == 'Whinta':
        output.write("first_name,phone\n")
        for num in numbers:
            output.write(f"{num},{num}\n")
    elif software == 'Aitoolkit':
        output.write("Phone,Number\n")
        for num in numbers:
            output.write(f"{num},{num}\n")

    bio = io.BytesIO(output.getvalue().encode('utf-8'))
    bio.name = f"{filename}.csv"
    bot.send_document(message.chat.id, bio)
    del user_data[message.chat.id]

@bot.message_handler(commands=['Split_file'])
def split_file_start(message):
    if not check_access(message): return
    msg = bot.reply_to(message, "📥 Please send file to split.")
    bot.register_next_step_handler(msg, process_split_file)

def process_split_file(message):
    if message.text == '/Reset': return reset_command(message)
    if not message.document: return 
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    numbers = extract_numbers(downloaded_file, message.document.file_name)
    if not numbers: return bot.reply_to(message, "❌ No numbers.")
    
    user_data[message.chat.id] = {'numbers': numbers}
    msg = bot.reply_to(message, f"✅ Found {len(numbers)} numbers!\n\nKitne number per file chahiye? (e.g., 250)")
    bot.register_next_step_handler(msg, get_split_chunk_size)

def get_split_chunk_size(message):
    if message.text == '/Reset': return reset_command(message)
    try:
        user_data[message.chat.id]['chunk_size'] = int(message.text.strip())
        msg = bot.reply_to(message, "✅ Base Name bhejo (e.g., flame):")
        bot.register_next_step_handler(msg, generate_split_files)
    except:
        msg = bot.reply_to(message, "⚠️ Invalid limit. Try again:")
        bot.register_next_step_handler(msg, get_split_chunk_size)

def generate_split_files(message):
    if message.text == '/Reset': return reset_command(message)
    base_name = message.text.strip()
    data = user_data.get(message.chat.id)
    if not data: return
    
    numbers, chunk_size = data['numbers'], data['chunk_size']
    chunks = [numbers[i:i + chunk_size] for i in range(0, len(numbers), chunk_size)]
    bot.reply_to(message, f"⏳ Creating {len(chunks)} files...")
    
    for idx, chunk in enumerate(chunks):
        bio = io.BytesIO(('\n'.join(chunk)).encode('utf-8'))
        bio.name = f"{base_name} {idx+1}.txt"
        bot.send_document(message.chat.id, bio)
    del user_data[message.chat.id]

@bot.message_handler(commands=['Make_Txt'])
def make_txt_start(message):
    if not check_access(message): return
    msg = bot.reply_to(message, "📥 Please send file for Make_Txt.")
    bot.register_next_step_handler(msg, process_txt_file)

def process_txt_file(message):
    if message.text == '/Reset': return reset_command(message)
    if not message.document: return 
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    numbers = extract_numbers(downloaded_file, message.document.file_name)
    if not numbers: return bot.reply_to(message, "❌ No numbers.")
    
    user_data[message.chat.id] = {'numbers': numbers}
    msg = bot.reply_to(message, f"✅ Found {len(numbers)} numbers.\n\nFile ka name bhejo:")
    bot.register_next_step_handler(msg, generate_txt_file)

def generate_txt_file(message):
    if message.text == '/Reset': return reset_command(message)
    filename = message.text.strip()
    data = user_data.get(message.chat.id)
    if not data: return
    
    bio = io.BytesIO(('\n'.join(data['numbers'])).encode('utf-8'))
    bio.name = f"{filename}.txt"
    bot.send_document(message.chat.id, bio)
    del user_data[message.chat.id]

app = Flask(__name__)
@app.route('/')
def keep_alive(): return "Bot is running!"
def run(): app.run(host='0.0.0.0', port=8080)
if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
