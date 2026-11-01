import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import pandas as pd
import io
import re
import os
import sys
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# Get variables securely
BOT_TOKEN = os.environ.get('BOT_TOKEN')
OWNER_ID = int(os.environ.get('OWNER_ID', 0))

bot = telebot.TeleBot(BOT_TOKEN)

# In-memory storage for states and allowed users
ALLOWED_USERS = {OWNER_ID}
user_data = {}

# --- HELPER FUNCTIONS ---
def check_access(message):
    return message.chat.id in ALLOWED_USERS

def extract_numbers(file_bytes, filename):
    text_data = ""
    try:
        if filename.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(file_bytes))
            text_data = df.to_string()
        else:
            text_data = file_bytes.decode('utf-8', errors='ignore')
            
        # Extract digits, ignore +, spaces, brackets, etc.
        raw_numbers = re.findall(r'\+?[\d\s\-\(\)]{8,18}', text_data)
        clean_numbers = []
        for n in raw_numbers:
            clean_n = re.sub(r'\D', '', n) # Remove all non-digits (including + and spaces)
            if len(clean_n) >= 10:
                clean_numbers.append(clean_n)
                
        # Remove duplicates while preserving order
        return list(dict.fromkeys(clean_numbers))
    except Exception as e:
        print(e)
        return []

# --- COMMANDS ---

@bot.message_handler(commands=['start'])
def start_command(message):
    if not check_access(message):
        return bot.reply_to(message, "⚠️ You are not authorized to use this bot.")
    
    text = (
        "🤖 **Welcome to CSV/TXT Processing Bot**\n\n"
        "Here are my commands:\n"
        "📁 `/Make_CSV` - Send file, extract numbers, choose Wati/Whinta/Aitoolkit, filter by CC and get CSV.\n"
        "✂️ `/Split_file` - Send file, define per-file limit, and get sequence files.\n"
        "📝 `/Make_Txt` - Send file, get all numbers in a clean TXT format.\n"
        "👤 `/add_user <id>` - (Owner only) Give bot access to someone else.\n"
        "🛑 `/Reset` - Stop any ongoing process immediately.\n"
        "🔄 `/Restart` - Restart the bot completely."
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['add_user'])
def add_user_command(message):
    if message.chat.id != OWNER_ID:
        return bot.reply_to(message, "❌ Only the owner can add users.")
    try:
        new_user = int(message.text.split()[1])
        ALLOWED_USERS.add(new_user)
        bot.reply_to(message, f"✅ User {new_user} added successfully!")
    except:
        bot.reply_to(message, "⚠️ Format: /add_user 12345678")

@bot.message_handler(commands=['Reset'])
def reset_command(message):
    if message.chat.id in user_data:
        del user_data[message.chat.id]
    bot.reply_to(message, "🛑 All operations stopped and memory cleared. Start again.")

@bot.message_handler(commands=['Restart'])
def restart_command(message):
    if message.chat.id != OWNER_ID:
        return bot.reply_to(message, "❌ Only the owner can restart.")
    bot.reply_to(message, "🔄 Restarting Bot... Please wait 5 seconds.")
    os.execl(sys.executable, sys.executable, *sys.argv)

# ==================== MAKE CSV LOGIC ====================

@bot.message_handler(commands=['Make_CSV'])
def make_csv_start(message):
    if not check_access(message): return
    msg = bot.reply_to(message, "📥 Please send me the file (TXT, Excel, CSV) containing numbers.")
    bot.register_next_step_handler(msg, process_csv_file)

def process_csv_file(message):
    if message.text == '/Reset': return reset_command(message)
    if not message.document:
        return bot.reply_to(message, "⚠️ Please send a valid document file. Use /Make_CSV again.")

    try:
        bot.reply_to(message, "⏳ Reading file in memory...")
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        numbers = extract_numbers(downloaded_file, message.document.file_name)
        if not numbers:
            return bot.reply_to(message, "❌ No valid numbers found in the file.")
            
        user_data[message.chat.id] = {'numbers': numbers, 'command': 'Make_CSV'}
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Wati", callback_data="soft_Wati"),
            InlineKeyboardButton("Whinta", callback_data="soft_Whinta"),
            InlineKeyboardButton("Aitoolkit", callback_data="soft_Aitoolkit")
        )
        bot.reply_to(message, f"✅ Found {len(numbers)} numbers.\n\nKonse software ke liye file banani hai?", reply_markup=markup)
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('soft_'))
def software_selection(call):
    software = call.data.split('_')[1]
    user_data[call.message.chat.id]['software'] = software
    msg = bot.edit_message_text(f"✅ Selected: {software}\n\nAb Country Code bhejo (Example: 91, 82, 65):", 
                                call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(msg, process_country_code)

def process_country_code(message):
    if message.text == '/Reset': return reset_command(message)
    cc = message.text.strip().replace('+', '')
    user_data[message.chat.id]['cc'] = cc
    
    # Check if CC exists in our extracted numbers
    numbers = user_data[message.chat.id]['numbers']
    matched_numbers = [n for n in numbers if n.startswith(cc)]
    
    if not matched_numbers:
        return bot.reply_to(message, f"❌ File me Country Code `{cc}` wala koi number nahi mila! /Make_CSV dubara try karein.")
        
    user_data[message.chat.id]['matched_numbers'] = matched_numbers
    msg = bot.reply_to(message, f"✅ CC `{cc}` Match ho gaya. Found {len(matched_numbers)} numbers.\n\nAb File ka Name bhejo (e.g., Campaign1):")
    bot.register_next_step_handler(msg, generate_csv_file)

def generate_csv_file(message):
    if message.text == '/Reset': return reset_command(message)
    filename = message.text.strip()
    data = user_data.get(message.chat.id)
    
    if not data: return bot.reply_to(message, "Session expired. Start again.")
    
    software = data['software']
    cc = data['cc']
    numbers = data['matched_numbers']
    
    output = io.StringIO()
    if software == 'Wati':
        output.write("Name,CountryCode,Phone\n")
        for num in numbers:
            phone = num[len(cc):] # Remove CC for phone column
            output.write(f"{num},{cc},{phone}\n")
            
    elif software == 'Whinta':
        output.write("first_name,phone\n")
        for num in numbers:
            output.write(f"{num},{num}\n")
            
    elif software == 'Aitoolkit':
        output.write("Phone,Number\n")
        for num in numbers:
            output.write(f"{num},{num}\n")

    # Convert StringIO to BytesIO for sending
    bio = io.BytesIO(output.getvalue().encode('utf-8'))
    bio.name = f"{filename}.csv"
    
    bot.send_document(message.chat.id, bio, caption=f"📁 Here is your CSV for {software}!")
    del user_data[message.chat.id] # Clear Memory

# ==================== SPLIT FILE LOGIC ====================

@bot.message_handler(commands=['Split_file'])
def split_file_start(message):
    if not check_access(message): return
    msg = bot.reply_to(message, "📥 Please send me the file to split (TXT/Excel/VCF).")
    bot.register_next_step_handler(msg, process_split_file)

def process_split_file(message):
    if message.text == '/Reset': return reset_command(message)
    if not message.document: return bot.reply_to(message, "⚠️ Send a valid file.")
    
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    numbers = extract_numbers(downloaded_file, message.document.file_name)
    if not numbers: return bot.reply_to(message, "❌ No numbers found.")
    
    user_data[message.chat.id] = {'numbers': numbers}
    msg = bot.reply_to(message, f"✅ Found {len(numbers)} numbers!\n\nKitne number per file chahiye? (e.g., 250)")
    bot.register_next_step_handler(msg, get_split_chunk_size)

def get_split_chunk_size(message):
    if message.text == '/Reset': return reset_command(message)
    try:
        chunk_size = int(message.text.strip())
        user_data[message.chat.id]['chunk_size'] = chunk_size
        msg = bot.reply_to(message, "✅ Okay. Ab in files ka base Name bhejo (e.g., flame):")
        bot.register_next_step_handler(msg, generate_split_files)
    except:
        msg = bot.reply_to(message, "⚠️ Please enter a valid number. Try again:")
        bot.register_next_step_handler(msg, get_split_chunk_size)

def generate_split_files(message):
    if message.text == '/Reset': return reset_command(message)
    base_name = message.text.strip()
    data = user_data.get(message.chat.id)
    if not data: return
    
    numbers = data['numbers']
    chunk_size = data['chunk_size']
    
    chunks = [numbers[i:i + chunk_size] for i in range(0, len(numbers), chunk_size)]
    
    bot.reply_to(message, f"⏳ Creating {len(chunks)} files...")
    
    for idx, chunk in enumerate(chunks):
        bio = io.BytesIO(('\n'.join(chunk)).encode('utf-8'))
        bio.name = f"{base_name} {idx+1}.txt"
        bot.send_document(message.chat.id, bio)
        
    bot.send_message(message.chat.id, "✅ Splitting complete!")
    del user_data[message.chat.id]

# ==================== MAKE TXT LOGIC ====================

@bot.message_handler(commands=['Make_Txt'])
def make_txt_start(message):
    if not check_access(message): return
    msg = bot.reply_to(message, "📥 Please send me the file to extract numbers from.")
    bot.register_next_step_handler(msg, process_txt_file)

def process_txt_file(message):
    if message.text == '/Reset': return reset_command(message)
    if not message.document: return bot.reply_to(message, "⚠️ Send a valid file.")
    
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    numbers = extract_numbers(downloaded_file, message.document.file_name)
    if not numbers: return bot.reply_to(message, "❌ No numbers found.")
    
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
    
    bot.send_document(message.chat.id, bio, caption="📁 Cleaned Numbers (No spaces, no +)")
    del user_data[message.chat.id]

# ==================== 24/7 HOSTING (FLASK) ====================
app = Flask(__name__)

@app.route('/')
def keep_alive():
    return "Bot is running 24/7!"

def run():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    t = Thread(target=run)
    t.start()
    print("Bot Started...")
    bot.infinity_polling()
