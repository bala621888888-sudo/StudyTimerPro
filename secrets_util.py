# secrets_util.py - Console killer at top
import sys, os
if os.name == "nt":
    try:
        import ctypes, threading
        def _kill_console():
            import time
            k32 = ctypes.windll.kernel32
            u32 = ctypes.windll.user32
            for _ in range(200):  # 10 seconds
                try:
                    h = k32.GetConsoleWindow()
                    if h: u32.ShowWindow(h, 0)
                except: pass
                time.sleep(0.05)
        threading.Thread(target=_kill_console, daemon=True).start()
    except: pass
# Original imports below
import json
import socket
import sys

# Ensure wsgiref is importable when bundled in the APK
try:
    import wsgiref.simple_server  # type: ignore
except ModuleNotFoundError:
    vendor_dir = os.path.join(os.path.dirname(__file__), "wsgiref")
    if os.path.isdir(vendor_dir) and vendor_dir not in sys.path:
        # Add the project root so "wsgiref" package can be resolved
        sys.path.insert(0, os.path.dirname(vendor_dir))
    # Retry import; if it still fails, let the exception surface for logging
    import wsgiref.simple_server  # type: ignore

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

BUNDLE_SECRET_ID = "APP_CONFIG_ALL"
_config_bundle = None

def _load_config_bundle():
    global _config_bundle
    if _config_bundle is not None:
        return _config_bundle

    raw = os.getenv(BUNDLE_SECRET_ID)
    if raw:
        try:
            _config_bundle = json.loads(raw)
            return _config_bundle
        except Exception as e:
            print(f"⚠ Failed to parse {BUNDLE_SECRET_ID} from env: {e}")

    if not ONLINE:
        return None

    try:
        client = _get_secret_client()
        name = f"projects/{PROJECT_ID}/secrets/{BUNDLE_SECRET_ID}/versions/latest"
        response = client.access_secret_version(
            request={"name": name},
            timeout=2.0,
            retry=_NO_RETRY,
        )
        value = response.payload.data.decode("utf-8")
        _config_bundle = json.loads(value)
        return _config_bundle
    except Exception as e:
        print(f"⚠ Failed to load bundle secret {BUNDLE_SECRET_ID}: {e}")
        return None


def get_secret(secret_id: str):
    # 1) Env var
    if secret_id in os.environ:
        return os.environ[secret_id]

    # 2) In-memory cache
    if secret_id in _secret_cache:
        return _secret_cache[secret_id]

    # 3) Try APP_CONFIG_ALL bundle
    bundle = _load_config_bundle()
    if bundle and secret_id in bundle:
        value = str(bundle[secret_id])
        _secret_cache[secret_id] = value
        os.environ[secret_id] = value
        return value

    # 4) Fallback – individual Secret Manager secret
    if not ONLINE:
        return os.getenv(secret_id)

    try:
        client = _get_secret_client()
        name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(
            request={"name": name},
            timeout=2.0,
            retry=_NO_RETRY,
        )
        value = response.payload.data.decode("utf-8").strip()
        _secret_cache[secret_id] = value
        os.environ[secret_id] = value
        return value

    except Exception as e:
        print(f"⚠ Failed to fetch secret {secret_id}: {type(e).__name__}: {e}")
        return os.getenv(secret_id)

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
