# secrets_util.py
import json
import os
import socket
import gspread
from google.oauth2.service_account import Credentials
from cryptography.fernet import Fernet

# ⚡ NEW: REST-based Secret Manager imports
from google.cloud import secretmanager_v1
from google.api_core.retry import Retry

# Your GCP project ID
PROJECT_ID = "leaderboard-98e8c"

_gspread_client_cache = None
_secret_client = None
_secret_cache = {}

# ✅ Check internet once globally
def internet_available():
    try:
        socket.gethostbyname("google.com")
        return True
    except:
        return False

ONLINE = internet_available()

# ⚡ No retry and short timeout
_NO_RETRY = Retry(
    initial=0.1, maximum=0.1, multiplier=1.0,
    deadline=2.0,
    predicate=lambda exc: False
)

# ⚡ Use REST transport to avoid ALTS delay
def _get_secret_client():
    global _secret_client
    if _secret_client is None:
        _secret_client = secretmanager_v1.SecretManagerServiceClient(
            transport="rest",
            client_options={"api_endpoint": "https://secretmanager.googleapis.com"}
        )
    return _secret_client

# ✅ Fetch secret (Safe: works offline too)
def get_secret(secret_id: str):
    # 1. Check local env first (survives restarts)
    if secret_id in os.environ:
        return os.environ[secret_id]

    # 2. Check memory cache (within same session)
    if secret_id in _secret_cache:
        return _secret_cache[secret_id]

    if not ONLINE:
        return os.getenv(secret_id)

    try:
        client = _get_secret_client()
        name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(
            request={"name": name},
            timeout=2.0,
            retry=_NO_RETRY
        )
        value = response.payload.data.decode("utf-8").strip()
        
        # Save for future
        _secret_cache[secret_id] = value
        os.environ[secret_id] = value  # 🔥 PERSIST CACHE THROUGH RESTARTS
        
        return value

    except Exception as e:
        print(f"⚠ Failed to fetch secret {secret_id}: {type(e).__name__}: {e}")
        return os.getenv(secret_id)

# ✅ GSpread init (already existed)
def get_encrypted_gspread_client():
    """Get gspread client from GCP_GSHEET_CREDS or fallback (cached)."""
    global _gspread_client_cache
    if _gspread_client_cache:
        return _gspread_client_cache

    try:
        # 1. Secret Manager (preferred)
        raw = get_secret("GCP_GSHEET_CREDS") if ONLINE else os.getenv("GCP_GSHEET_CREDS")
        if raw:
            info = json.loads(raw)
            scope = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_info(info, scopes=scope)
            _gspread_client_cache = gspread.authorize(creds)
            return _gspread_client_cache

        # 2. Old encrypted creds fallback
        encryption_key = os.getenv('ENCRYPTION_KEY')
        encrypted_creds = os.getenv('ENCRYPTED_CREDENTIALS')
        if encryption_key and encrypted_creds:
            f = Fernet(encryption_key.encode())
            creds_dict = json.loads(f.decrypt(encrypted_creds.encode()).decode())
            _gspread_client_cache = gspread.service_account_from_dict(creds_dict)
            return _gspread_client_cache

        # 3. Optional file fallback
        lb_path = os.getenv("LB_CREDENTIALS")
        if lb_path and os.path.exists(lb_path):
            _gspread_client_cache = gspread.service_account(filename=lb_path)
            return _gspread_client_cache

        print("⚠ No GSheet credentials found.")
        return None

    except Exception as e:
        print(f"⚠ Failed to init gspread client: {e}")
        return None
