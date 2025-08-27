# test_bot_responses.py (Versi Perbaikan)
import pytest
from graph import compiled_graph
from langchain_core.messages import HumanMessage
from utils import vary_response, add_emojis_and_formatting, choose_follow_up

# FUNGSI PEMBANTU (Sama seperti sebelumnya)
def get_final_bot_response(user_message: str, user_number: str = "test-user") -> str:
    graph_input = {"messages": [HumanMessage(content=user_message)], "user_number": user_number}
    graph_output = compiled_graph.invoke(graph_input)
    raw_response = graph_output["messages"][-1].content
    
    final_response = raw_response
    if "Coba" not in raw_response and "yuk!" not in raw_response:
        varied_response = vary_response(raw_response, user_message)
        formatted_response = add_emojis_and_formatting(varied_response, is_negative=False)
        follow_up = choose_follow_up('id', user_message, formatted_response, user_number)
        
        final_response = formatted_response
        if follow_up:
            final_response += f" {follow_up}"

    return final_response.strip()

# DAFTAR SKENARIO TES (SUDAH DIPERBARUI)
# Harapan outputnya sekarang adalah bagian inti dari pesan yang tidak random.
test_scenarios = [
    # Skenario 1: Stok diperbarui ke 13 dan hanya cek bagian penting
    ("kemeja flanelnya ada?", "Stok kemeja flanel ada 13 pcs"),
    
    # Skenario 2: Hanya cek bagian penting
    ("sepatu kets ada?", "Stok sepatu kets ada 5 pcs"),
    
    # Skenario 3: Ini sudah PASS, jadi biarkan sama persis
    ("celana chino ada?", "Maaf stok celana chino habis, Kak. Coba kemeja flanel atau sepatu kets yuk!"),
    
    # Skenario 4: Hanya cek bagian penting, follow-up akan kita perbaiki di Langkah 2
    ("jual jaket denim?", "Maaf, kami tidak memiliki jaket denim saat ini. Produk apa lagi yang Kakak cari?"),

    # Skenario 5: Hanya cek bagian penting
    ("warna sepatu kets apa aja?", "Pilihan warna untuk sepatu kets: putih"),
]

# FUNGSI TES UTAMA (SUDAH DIPERBARUI)
@pytest.mark.parametrize("user_input, expected_output_part", test_scenarios)
def test_various_scenarios(user_input, expected_output_part):
    """
    Menjalankan semua skenario tes dan memeriksa apakah bagian penting dari
    respons bot ada di dalam output aktual.
    """
    actual_output = get_final_bot_response(user_input)
    # Kita gunakan 'in' untuk membuat tes lebih fleksibel terhadap variasi
    assert expected_output_part in actual_output