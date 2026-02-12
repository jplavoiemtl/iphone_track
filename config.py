import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
OWNTRACKS_SERVER_IP = os.getenv("OWNTRACKS_SERVER_IP", "")
OWNTRACKS_SERVER_PORT = os.getenv("OWNTRACKS_SERVER_PORT", "")
OWNTRACKS_USER = os.getenv("OWNTRACKS_USER", "owntrcks")
OWNTRACKS_DEVICE_ID = os.getenv("OWNTRACKS_DEVICE_ID", "")
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "America/Montreal")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "iphone-tracker-local-session-key")
PUSHCUT_WEBHOOK_URL = os.getenv("PUSHCUT_WEBHOOK_URL", "")
