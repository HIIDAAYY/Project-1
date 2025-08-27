import base64
import string
import random
import requests
import logging
from cryptography.fernet import Fernet
from config import cipher_suite, twilio_client, AGENT_WHATSAPP_NUMBER, TWILIO_WHATSAPP_NUMBER
from tools import variasi_templates, negative_keywords_id, negative_keywords_en, used_follow_ups, follow_up_templates_id, follow_up_templates_en
from langchain_core.messages import HumanMessage
from twilio.twiml.messaging_response import MessagingResponse

# Global variables
# memories = {}  # Hapus kalau pakai LangGraph MemorySaver

# Memory per user (kalau pakai opsi 1; hapus kalau opsi 2)
# def get_memory(user_number):
#     if user_number not in memories:
#         memories[user_number] = ChatMessageHistory()
#     return memories[user_number]

def encrypt_text(text: str) -> str:
    return cipher_suite.encrypt(text.encode()).decode()

def decrypt_text(encrypted: str) -> str:
    return cipher_suite.decrypt(encrypted.encode()).decode()

def moderate_content(content: str) -> bool:
    bad_words = ['badword1', 'badword2']
    return any(word in content.lower() for word in bad_words)

def notify_agent(message: str):
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=f"Escalation: {message}",
            to=AGENT_WHATSAPP_NUMBER
        )
    except Exception as e:
        logging.error(f"Error notify agent: {e}")

def detect_negative_emotion(message: str, lang: str) -> bool:
    keywords = negative_keywords_en if lang == 'en' else negative_keywords_id
    return any(kw in message.lower() for kw in keywords)

def vary_response(response_text: str, user_message: str) -> str:
    lower_text = response_text.lower()
    user_lower = user_message.lower()

    # --- PERBAIKAN DI SINI ---
    # Jika respons sudah merupakan rekomendasi, jangan diubah lagi.
    if "coba" in lower_text and "yuk!" in lower_text:
        return response_text
    # -------------------------

    # Improve extract product_name: Hilangkan kata tanya/stop words dari user_message
    stop_words = ['ada', 'stok', 'warna', 'apa', 'aja', 'berapa', 'info', 'lengkap', 'untuk', 'nih', 'yuk', 'punya', 'jual', 'apaan', '?']
    clean_user_parts = [p for p in user_lower.split() if p not in stop_words]
    product_name = ' '.join(clean_user_parts).strip().capitalize()

    if any(word in lower_text for word in ["tidak ditemukan", "tidak dapat menemukan"]):  # Lebih longgar
        return f"Maaf, kami tidak memiliki {product_name} saat ini."
    if "habis" in lower_text or "tidak ada" in lower_text:
        if "pilihan warna" in lower_text:
            return response_text
        template = random.choice(variasi_templates['stok_habis'])
        return template.format(response_text)
    if "warna" in user_lower or "color" in user_lower:
        if "pilihan warna" in lower_text:
            return response_text
        template = random.choice(variasi_templates['warna'])
        return template.format(response_text)
    if "stok" in user_lower or "ada" in user_lower or "punya" in user_lower or "jual" in user_lower:
        if "Warna:" in response_text:
            response_text = response_text.split("Warna:")[0].strip('. ') + "."
        template = random.choice(variasi_templates['stok_ada'])
        return template.format(response_text)
    template = random.choice(variasi_templates['default'])
    return template.format(response_text)

def add_emojis_and_formatting(text, is_negative=False):
    if is_negative:
        text = text.replace("maaf", "*maaf* 🙏")
        text += " Kami tangani segera ya, Kak."
    if "stok" in text.lower() and "pcs" in text.lower(): # Sedikit disempurnakan
        text = text.strip('. ') + ". 😎"
    if "warna" in text.lower():
        # Menghindari duplikasi emoji
        if "🌈" not in text:
            text = text.strip('. ') + ". 🌈"
    return text

def choose_follow_up(lang: str, user_message: str, response_text: str, user_number: str) -> str:
    if "tidak ditemukan" in response_text.lower() or "tidak memiliki" in response_text.lower() or "habis" in response_text.lower():
        return "Produk apa lagi yang Kakak cari?" if lang == 'id' else "What other product are you looking for?"
    
    follow_up_counts = used_follow_ups.get(user_number, {})
    available_follow_ups = [f for f in (follow_up_templates_en if lang == 'en' else follow_up_templates_id)
                            if follow_up_counts.get(f, 0) < 1]
    if not available_follow_ups:
        used_follow_ups[user_number] = {}
        available_follow_ups = follow_up_templates_en if lang == 'en' else follow_up_templates_id
    
    if "pesanan" in response_text.lower() and "berhasil" in response_text.lower():
        return ""
    if "mau berapa" in response_text.lower() or "jumlahnya" in response_text.lower():
        return ""  

    user_lower = user_message.lower()
    if "warna" in user_lower or "color" in user_lower:
        follow_up = "Mau pilih warna apa, Kak?" if lang == 'id' else "Which color you picking?"
    elif "stok" in user_lower or "ada" in user_lower or "punya" in user_lower or "jual" in user_lower:
        follow_up = "Mau pesan sekarang, Kak?" if lang == 'id' else "Want to order now?"
    else:
        follow_up = random.choice(available_follow_ups)

    used_follow_ups.setdefault(user_number, {}).setdefault(follow_up, 0)
    used_follow_ups[user_number][follow_up] += 1
    return follow_up

def download_twilio_image(media_url: str) -> str:
    # Kode ini tidak berubah
    try:
        response = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        else:
            logging.error(f"Error download image: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Error download image: {e}")
        return None

def send_whatsapp_message(response_text: str, messaging_response: MessagingResponse):
    messaging_response.message(response_text)

def pre_process_message(message: str) -> str:
    """Pre-process user message: Correct typo, handle slang, dan rewrite santai ke standard."""
    lower_msg = message.lower().strip()
    
    # Dict typo umum (tambah lebih banyak kalau perlu berdasarkan test)
    typo_dict = {
        'kemaja': 'kemeja',
        'flannl': 'flanel',
        'flannel': 'flanel',
        'flanelnya': 'flanel',
        'chinno': 'chino',
        'chinonya': 'chino',
        'sepato': 'sepatu',
        'ketz': 'kets',
        'stok': 'stok',  # Tetap, tapi untuk konsistensi
        'warnaa': 'warna',
        'adah': 'ada',
        'ga': 'ga',  # Handle "ga" sebagai negasi, tapi skip untuk sekarang
    }
    
    # Correct typo
    words = lower_msg.split()
    corrected_words = [typo_dict.get(word, word) for word in words]
    corrected_msg = ' '.join(corrected_words)
    
    # Handle slang santai: Hilangkan filler seperti "deh", "aja", "sih" atau rewrite intent
    slang_fillers = ['deh', 'aja', 'sih', 'nih', 'dong', 'banget', 'emg', 'emang', 'emangnya']
    cleaned_words = [word for word in corrected_words if word not in slang_fillers]
    cleaned_msg = ' '.join(cleaned_words)
    
    # Rewrite intent sederhana: Misal "mau [produk] [jumlah]" → "pesan [produk] [jumlah]"
    if 'mau' in cleaned_msg and any(char.isdigit() for char in cleaned_msg):
        cleaned_msg = cleaned_msg.replace('mau', 'pesan')
    if 'beli' in cleaned_msg and any(char.isdigit() for char in cleaned_msg):
        cleaned_msg = cleaned_msg.replace('beli', 'pesan')
    
    # Log untuk debug
    logging.debug(f"Original message: {message}")
    logging.debug(f"Processed message: {cleaned_msg}")
    
    return cleaned_msg