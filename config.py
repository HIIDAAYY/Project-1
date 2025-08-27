import os
from dotenv import load_dotenv
from twilio.rest import Client as TwilioClient
import midtransclient
from cryptography.fernet import Fernet

load_dotenv()

# API Keys dan Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
AGENT_WHATSAPP_NUMBER = os.getenv("AGENT_WHATSAPP_NUMBER")
MIDTRANS_SERVER_KEY = os.getenv("MIDTRANS_SERVER_KEY")
MIDTRANS_CLIENT_KEY = os.getenv("MIDTRANS_CLIENT_KEY")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# Inisialisasi Client
twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
snap = midtransclient.Snap(
    is_production=False,
    server_key=MIDTRANS_SERVER_KEY,
    client_key=MIDTRANS_CLIENT_KEY
)
cipher_suite = Fernet(ENCRYPTION_KEY.encode())

# Global vars lain kalau perlu, misal rate_limits (inisialisasi kosong, diisi di app)
rate_limits = {}