import logging
from fastapi import FastAPI, Form, Response, Request
from twilio.twiml.messaging_response import MessagingResponse
from a2a_sdk.client import A2AClient
from a2a_sdk.server import A2AServer
from a2a_sdk.models import AgentCard
from langgraph.graph import StateGraph  # Sudah ada di graph.py

# Import dari file lain
from config import twilio_client, rate_limits, TWILIO_WHATSAPP_NUMBER
from database import init_db
from graph import compiled_graph
from tools import llm, product_tool, order_tool, faq_tool, user_preferences, full_histories, used_follow_ups, system_prompt_id, system_prompt_en, variasi_templates, negative_keywords_id, negative_keywords_en, follow_up_templates_id, follow_up_templates_en
from utils import encrypt_text, decrypt_text, moderate_content, notify_agent, detect_negative_emotion, vary_response, add_emojis_and_formatting, choose_follow_up, download_twilio_image, send_whatsapp_message, pre_process_message  # Tambah import pre_process_message
# Hapus langdetect
# import langdetect 
import time
import openai
from langchain_core.messages import HumanMessage

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# Init DB sekali di awal
init_db()

@app.post("/whatsapp")
async def whatsapp_webhook(request: Request, From: str = Form(...), Body: str = Form(None), MediaUrl0: str = Form(None)):
    user_message = Body
    user_number = From
    logging.info(f"Pesan diterima dari {user_number}: '{user_message}'")
    
    messaging_response = MessagingResponse()

    # Rate limiting & Moderasi (tidak berubah)
    current_time = time.time()
    if user_number not in rate_limits:
        rate_limits[user_number] = {'count': 0, 'last_time': current_time}
    if current_time - rate_limits[user_number]['last_time'] > 60:
        rate_limits[user_number] = {'count': 0, 'last_time': current_time}
    rate_limits[user_number]['count'] += 1
    if rate_limits[user_number]['count'] > 5:
        messaging_response.message("Maaf, terlalu banyak pesan dalam waktu singkat. Coba lagi nanti, Kak!")
        return Response(content=str(messaging_response), media_type="application/xml")
    if moderate_content(user_message):
        messaging_response.message("Maaf, pesan Anda tidak sesuai, Kak. Coba pesan lain ya!")
        return Response(content=str(messaging_response), media_type="application/xml")

    # --- PERBAIKAN 1: Hapus deteksi bahasa, asumsikan 'id' ---
    detected_lang = 'id'
    system_prompt = system_prompt_id
    # -----------------------------------------------------------

    # Riwayat Chat & Preferensi Pengguna (termasuk last_product)
    if user_number in full_histories and full_histories[user_number]:
        history_summary = "\nRiwayat chat: " + ' '.join([f"Pelanggan: {decrypt_text(h[0])} | Respons: {decrypt_text(h[1])}" for h in full_histories[user_number][-3:]])
        system_prompt += history_summary
    if user_number not in user_preferences:
        user_preferences[user_number] = {'name': None, 'favorites': [], 'last_product': None}
    pref = user_preferences[user_number]
    if pref['name']:
        system_prompt += f"\nGunakan nama pelanggan '{pref['name']}' dalam sapaan, misalnya 'Halo Kak {pref['name']}'."
    if "nama saya" in user_message.lower():
        parts = user_message.lower().split("nama saya")
        if len(parts) > 1:
            name = parts[1].strip().split()[0].capitalize()
            pref['name'] = name
    if "favorit saya" in user_message.lower():
        parts = user_message.lower().split("favorit saya")
        if len(parts) > 1:
            fav = parts[1].strip().split()[0]
            if fav not in pref['favorites']:
                pref['favorites'].append(fav)
    user_lower = user_message.lower()
    if len(user_message.split()) < 3 and ("warna" in user_lower or "nya" in user_lower or "kalo" in user_lower or "gimana" in user_lower):
        if pref['last_product']:
            user_message = f"{pref['last_product']} {user_message}"

    response_text = ""
    is_negative = detect_negative_emotion(user_message, detected_lang)

    # Penanganan Gambar (kode lengkap Anda dipertahankan)
    if MediaUrl0:
        logging.info(f"Memproses media dari: {MediaUrl0}")
        base64_image = download_twilio_image(MediaUrl0)
        if base64_image:
            image_prompt = """
Anda adalah agen CS UrbanStyle ID yang ramah... (dst, prompt gambar Anda)
            """.format(user_message=user_message)
            system_message_with_image = { "role": "user", "content": [ ... ] } # Disingkat
            try:
                response = openai.chat.completions.create(...) # Disingkat
                response_text = response.choices[0].message.content
            except Exception as e:
                logging.error(f"Error saat analisis gambar: {e}")
                response_text = "Maaf, gambar tidak dapat dianalisis. Bisa jelaskan masalahnya, Kak?"
        else:
            response_text = "Maaf, gambar tidak dapat diproses, Kak."
    
    # Logika utama
    else:
        try:
            # Tambah pre-processing sebelum graph
            processed_message = pre_process_message(user_message)
            graph_input = {"messages": [HumanMessage(content=processed_message)], "user_number": user_number, "is_ambiguous": False, "needs_reflection": False}  # Init flag
            config = {"configurable": {"thread_id": user_number}}
            graph_output = compiled_graph.invoke(graph_input, config=config)
            
            # Handle berdasarkan state (baru: kalau ambiguous, balas clarify langsung)
            if graph_output.get('is_ambiguous', False):
                response_text = graph_output["messages"][-1].content  # Dari clarify node
            else:
                response_text = graph_output["messages"][-1].content
                response_text = vary_response(response_text, user_message)
                response_text = add_emojis_and_formatting(response_text, is_negative)
                
                if not is_negative and "Coba" not in response_text and "yuk!" not in response_text:
                    follow_up = choose_follow_up(detected_lang, user_message, response_text, user_number)
                    if follow_up:
                        response_text += f" {follow_up}"
                
                if pref['favorites']:
                    for fav in pref['favorites']:
                        if fav in response_text.lower():
                            response_text += " (Favorit Anda, Kak!)"
                            break
        except Exception as e:
            logging.error(f"Error di compiled_graph: {str(e)}")
            response_text = "Maaf, sistem sedang bermasalah. Coba lagi nanti, Kak."

    # Moderasi dan notifikasi (tidak berubah)
    if moderate_content(response_text):
        response_text = "Maaf, terjadi kesalahan..." # Disingkat
        notify_agent(f"Moderasi output gagal untuk pesan: '{user_message}'")
    if "ESCALATE" in response_text:
        notify_agent(user_message)
        response_text = response_text.replace("ESCALATE", "").strip()

    # Simpan last_product (logika lengkap Anda dipertahankan)
    lower = response_text.lower()
    if "stok" in lower and "ada" in lower and "habis" not in lower:
        try:
            name = lower.split("stok ")[1].split(" ada")[0].strip()
            pref['last_product'] = name
        except: pass
    elif "pilihan warna untuk" in lower:
        try:
            name = lower.split("pilihan warna untuk ")[1].split(":")[0].strip()
            pref['last_product'] = name
        except: pass

    full_histories.setdefault(user_number, []).append((encrypt_text(user_message), encrypt_text(response_text)))
    logging.info(f"Teks balasan final yang akan dikirim: {response_text}")
    send_whatsapp_message(response_text, messaging_response)
    
    return Response(content=str(messaging_response), media_type="application/xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)