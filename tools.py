import os
import logging
import random
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import CharacterTextSplitter
from langchain.tools import Tool
from langchain_core.messages import HumanMessage
from database import get_product_info, create_order  # Import query dari database

llm = ChatOpenAI(model_name="gpt-4o", temperature=0.2)

product_tool = Tool(
    name="get_product_info",
    func=get_product_info,
    description="Dapatkan info stok atau warna produk dari database. Input: 'nama produk tipe_info' ('stok' untuk stok, 'warna' untuk warna, atau 'semua')."
)

order_tool = Tool(
    name="create_order",
    func=create_order,
    description="Buat pesanan baru. Input: 'nama produk jumlah', user_number dari context."
)

faq_retriever = None
try:
    if not os.path.exists("faq.txt"):
        raise FileNotFoundError("File faq.txt tidak ditemukan di direktori proyek.")
    with open("faq.txt", "r", encoding="utf-8") as f:
        faq_text = f.read()
    if not faq_text.strip():
        raise ValueError("File faq.txt kosong.")
    text_splitter = CharacterTextSplitter(
        separator="--------------------------------------",
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    texts = text_splitter.split_text(faq_text)
    embeddings = OpenAIEmbeddings()
    vectorstore = FAISS.from_texts(texts, embeddings)
    faq_retriever = vectorstore.as_retriever()
    logging.info("FAQ berhasil dimuat.")
except Exception as e:
    logging.error(f"Gagal memuat FAQ: {e}")

def faq_retriever_func(x):
    if faq_retriever:
        results = faq_retriever.invoke(x)
        return "\n".join(doc.page_content for doc in results) if isinstance(results, list) else results
    return "FAQ tidak tersedia, silakan hubungi CS kami, Kak."

faq_tool = Tool(
    name="faq_retriever",
    func=faq_retriever_func,
    description="Cari jawaban dari FAQ UrbanStyle ID. Input: pertanyaan."
)

# Tool baru untuk clarify query ambigu (dipanggil kalau perlu)
def clarify_query(input_str: str) -> str:
    """Rewrite atau clarify query ambigu dengan LLM."""
    clarify_prompt = f"Rewrite query ini ke format standard: {input_str}. Handle typo dan infer intent."
    response = llm.invoke(HumanMessage(content=clarify_prompt))
    return response.content

clarify_tool = Tool(
    name="clarify_query",
    func=clarify_query,
    description="Rewrite query ambigu atau dengan typo ke format standard. Input: query user."
)

# Memory dan globals
user_preferences = {}
full_histories = {}
used_follow_ups = {}

# Templates
variasi_templates = {
    'stok_ada': ["Stoknya masih ada, Kak! {}", "Stok tersedia: {}", "Ada stok: {}"],
    'stok_habis': ["Maaf, stok habis, Kak. {}", "Stok kosong, cek lagi nanti: {}"],
    'warna': ["Pilihan warna: {}", "Warna tersedia: {}"],
    'default': ["{}", "{}", "{}"],
    'faq': ["Ini infonya: {}", "Jawabannya: {}", "Detailnya: {}"]
}

follow_up_templates_id = [
    "Ada pertanyaan lain, Kak?",
    "Butuh bantuan lain, Kak?",
    "Mau lihat produk lain, Kak?"
]
follow_up_templates_en = [
    "Any other questions?",
    "Need more help?",
    "Wanna check other products?"
]

negative_keywords_id = ['rusak', 'cacat', 'salah', 'kecewa', 'marah', 'komplain', 'refund']
negative_keywords_en = ['damaged', 'defect', 'wrong', 'disappointed', 'angry', 'complain', 'refund']

# System prompts (tetap dari sebelumnya, dengan improvements)
system_prompt_id = """
Anda adalah agen CS UrbanStyle ID yang ramah dan profesional. Gunakan bahasa Indonesia santai dengan panggilan 'Kak'. Prioritas jawaban:
1. Jika pertanyaan tentang stok, warna, atau info produk, gunakan GET_PRODUCT_INFO dengan input 'nama produk tipe_info' ('stok' untuk stok, 'warna' untuk warna, atau 'semua'). Jika nama produk tidak disebut, coba tebak dari riwayat (contoh: 'kemeja flanel warna').
2. Jika user bilang mau pesan, beli, order, atau sejenisnya diikuti nama produk dan jumlah (misal 'mau sepatu kets 1', 'pesan kemeja flanel 2'), gunakan CREATE_ORDER dengan input 'nama produk jumlah'.
3. Gunakan faq_retriever hanya untuk pertanyaan umum seperti cara pesan, pembayaran, pengiriman, dll.
4. Ingat riwayat chat untuk follow-up, jangan tanya ulang nama produk. Jika ambigu, gunakan CLARIFY_QUERY untuk rewrite.
5. Jika pesan user santai seperti 'Halo' atau 'Hai', balas ramah seperti 'Halo Kak, ada yang bisa dibantu hari ini?'.
6. Jika produk tidak ditemukan, gunakan faq_retriever dan jangan loop.
7. Balas natural seperti manusia, hindari prefix kaku seperti 'Info ini ya Kak:' atau 'Cek nih:'.
8. Handle typo umum seperti 'flannel' jadi 'flanel', slang santai seperti 'mau 1 deh' sebagai order, dan infer intent dari riwayat kalau ambigu.

Contoh Penanganan Query:
- User: "kemaja flannl ada ga?" → Correct typo ke 'kemeja flanel', call GET_PRODUCT_INFO 'kemeja flanel stok', lalu balas natural seperti "Stok kemeja flanel ada 15 pcs. 😎 Mau pesan sekarang, Kak?"
- User: "warnanya apa aja sih?" (setelah query stok kemeja flanel) → Infer last_product 'kemeja flanel', call GET_PRODUCT_INFO 'kemeja flanel warna', balas "Pilihan warna: merah, biru. 🌈 Mau pilih warna apa, Kak?"
- User: "mau sepatu kets 1 deh" → Detect intent order, call CREATE_ORDER 'sepatu kets 1', lalu balas dengan link pembayaran.
- User: "celana chino stok habis? ganti apa ya?" → Call GET_PRODUCT_INFO 'celana chino stok', kalau habis gunakan faq_retriever untuk rekomendasi, balas natural seperti "Maaf stok habis, Kak. Coba cek kemeja flanel yuk!"
- User: "halo, nama saya Andi" → Simpan nama, balas "Halo Kak Andi, ada yang bisa dibantu hari ini? Ada pertanyaan lain, Kak?"
"""

system_prompt_en = """
You are a friendly and professional CS agent for UrbanStyle ID. Use casual English with 'Hey' or 'Hi'. Answer priorities:
1. If the question is about stock, colors, or product info, use GET_PRODUCT_INFO with input 'product name info_type' ('stock' for stock, 'colors' for colors). If no product name, infer from history (e.g., 'flannel shirt colors').
2. If about ordering, use CREATE_ORDER with input 'product name quantity'.
3. Use faq_retriever only for general questions like how to order, payment, shipping, etc.
4. Remember chat history for follow-ups, don't ask for product name again. If ambiguous, ask casually like 'You mean the previous product?'.
5. If the user's message is casual like 'Hello' or 'Hi', reply friendly like 'Hey, how can I help today?'.
6. If product not found, use faq_retriever and don't loop.
7. Reply naturally like a human, avoid stiff prefixes like 'Here's the info:' or 'Check this:'.
"""