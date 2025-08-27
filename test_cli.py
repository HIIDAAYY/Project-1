# test_cli.py
import logging
from graph import compiled_graph
from langchain_core.messages import HumanMessage

# Atur logging untuk melihat proses
logging.basicConfig(level=logging.INFO)

def run_chat_session():
    """Memulai sesi chat interaktif di terminal."""
    # Gunakan nomor telepon dummy untuk pengujian
    user_number = "cli-test-user"
    print("🤖 Selamat datang di Terminal Chatbot UrbanStyle!")
    print("Ketik 'exit' untuk keluar.")
    print("-" * 30)

    while True:
        try:
            # Ambil input dari pengguna
            user_message = input("Anda  > ")
            if user_message.lower() == 'exit':
                print("🤖 Sampai jumpa!")
                break

            # Siapkan input untuk graph
            graph_input = {
                "messages": [HumanMessage(content=user_message)],
                "user_number": user_number
            }
            
            # Panggil graph untuk mendapatkan respons
            graph_output = compiled_graph.invoke(graph_input)
            
            # Ambil pesan terakhir dari output sebagai balasan bot
            bot_response = graph_output["messages"][-1].content
            
            print(f"Bot   > {bot_response}")

        except Exception as e:
            print(f"Terjadi error: {e}")

if __name__ == "__main__":
    run_chat_session()