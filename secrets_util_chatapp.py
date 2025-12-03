# secrets_util.py - OPTIMIZED FOR FAST APP STARTUP + APP_CONFIG_ALL BUNDLE
import json
import os
import sys

# Ensure wsgiref is importable when bundled in the APK
try:
    import wsgiref.simple_server  # type: ignore
except ModuleNotFoundError:
    vendor_dir = os.path.join(os.path.dirname(__file__), "wsgiref")
    if os.path.isdir(vendor_dir) and vendor_dir not in sys.path:
        sys.path.insert(0, os.path.dirname(vendor_dir))
    import wsgiref.simple_server  # type: ignore

import gspread
from google.oauth2.service_account import Credentials
from cryptography.fernet import Fernet

# ⚡ LAZY IMPORT - Only load when needed, not at startup!
_secretmanager_v1 = None
_Retry = None

def _get_secretmanager():
    """Lazy load Secret Manager - only when actually needed"""
    global _secretmanager_v1, _Retry
    if _secretmanager_v1 is None:
        from google.cloud import secretmanager_v1
        from google.api_core.retry import Retry
        _secretmanager_v1 = secretmanager_v1
        _Retry = Retry
    return _secretmanager_v1, _Retry

# Your GCP project ID
PROJECT_ID = "leaderboard-98e8c"

_gspread_client_cache = None
_secret_client = None
_secret_cache = {}

# ✅ New: bundle secret config
BUNDLE_SECRET_ID = "APP_CONFIG_ALL"
_config_bundle = None

# ✅ FAST internet check - non-blocking
def internet_available():
    """Quick check without blocking"""
    try:
        import socket
        socket.setdefaulttimeout(0.5)  # Only wait 0.5 seconds!
        socket.gethostbyname("google.com")
        return True
    except:
        return False

# ⚡ Check only when needed, not at import time
def _is_online():
    """Lazy online check"""
    if not hasattr(_is_online, "_cached"):
        _is_online._cached = internet_available()
    return _is_online._cached

# ⚡ Use REST transport to avoid ALTS delay
def _get_secret_client():
    global _secret_client
    if _secret_client is None:
        secretmanager_v1, Retry = _get_secretmanager()
        _secret_client = secretmanager_v1.SecretManagerServiceClient(
            transport="rest",
            client_options={"api_endpoint": "https://secretmanager.googleapis.com"},
        )
    return _secret_client

# ✅ Load APP_CONFIG_ALL once and cache it
def _load_config_bundle():
    """Load APP_CONFIG_ALL (JSON) once and cache it."""
    global _config_bundle

    if _config_bundle is not None:
        return _config_bundle

    # 1) Try environment variable first (for local dev / overrides)
    raw = os.getenv(BUNDLE_SECRET_ID)
    if raw:
        try:
            _config_bundle = json.loads(raw)
            return _config_bundle
        except Exception as e:
            # If broken JSON in env, just ignore and fall back to GCP
            print(f"⚠ Failed to parse {BUNDLE_SECRET_ID} from env: {e}")

    # 2) If offline, we can't pull bundle from Secret Manager
    if not _is_online():
        return None

    try:
        secretmanager_v1, Retry = _get_secretmanager()
        _NO_RETRY = Retry(
            initial=0.1,
            maximum=0.1,
            multiplier=1.0,
            deadline=1.0,
            predicate=lambda exc: False,
        )

        client = _get_secret_client()
        name = f"projects/{PROJECT_ID}/secrets/{BUNDLE_SECRET_ID}/versions/latest"
        response = client.access_secret_version(
            request={"name": name},
            timeout=1.0,
            retry=_NO_RETRY,
        )
        value = response.payload.data.decode("utf-8")
        _config_bundle = json.loads(value)
        return _config_bundle
    except Exception as e:
        print(f"⚠ Failed to load bundle secret {BUNDLE_SECRET_ID}: {e}")
        return None

# ✅ Fetch secret (Safe: works offline too) - OPTIMIZED + BUNDLE SUPPORT
def get_secret(secret_id: str):
    """Get secret with caching - FAST when cached and bundle-based."""
    # 1. Check memory cache FIRST (instant!)
    if secret_id in _secret_cache:
        return _secret_cache[secret_id]

    # 2. Check local env (also instant!)
    if secret_id in os.environ:
        value = os.environ[secret_id]
        _secret_cache[secret_id] = value
        return value

    # 3. Try APP_CONFIG_ALL bundle (for most keys)
    bundle = _load_config_bundle()
    if bundle and secret_id in bundle:
        value = str(bundle[secret_id])
        _secret_cache[secret_id] = value
        os.environ[secret_id] = value  # cache through restarts if same process
        return value

    # 4. Only try individual Secret Manager secret if online
    if not _is_online():
        return os.getenv(secret_id)

    try:
        secretmanager_v1, Retry = _get_secretmanager()
        _NO_RETRY = Retry(
            initial=0.1,
            maximum=0.1,
            multiplier=1.0,
            deadline=1.0,  # Only wait 1 second
            predicate=lambda exc: False,
        )

        client = _get_secret_client()
        name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(
            request={"name": name},
            timeout=1.0,  # Only wait 1 second
            retry=_NO_RETRY,
        )
        value = response.payload.data.decode("utf-8").strip()

        # Save for future (instant next time!)
        _secret_cache[secret_id] = value
        os.environ[secret_id] = value

        return value

    except Exception:
        # Silently fail and use environment variable as last resort
        return os.getenv(secret_id)

# ✅ GSpread init - OPTIMIZED
def get_encrypted_gspread_client():
    """Get gspread client from GCP_GSHEET_CREDS or fallback (cached)."""
    global _gspread_client_cache

    # Return cached immediately!
    if _gspread_client_cache:
        return _gspread_client_cache

    try:
        # 1. Try environment variable FIRST (instant!)
        raw = os.getenv("GCP_GSHEET_CREDS")

        # 2. Only try Secret Manager if env var not found AND online
        if not raw and _is_online():
            raw = get_secret("GCP_GSHEET_CREDS")

        if raw:
            info = json.loads(raw)
            scope = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_info(info, scopes=scope)
            _gspread_client_cache = gspread.authorize(creds)
            return _gspread_client_cache

        # 3. Old encrypted creds fallback
        encryption_key = os.getenv("ENCRYPTION_KEY")
        encrypted_creds = os.getenv("ENCRYPTED_CREDENTIALS")
        if encryption_key and encrypted_creds:
            f = Fernet(encryption_key.encode())
            creds_dict = json.loads(
                f.decrypt(encrypted_creds.encode()).decode()
            )
            _gspread_client_cache = gspread.service_account_from_dict(creds_dict)
            return _gspread_client_cache

        # 4. Optional file fallback
        lb_path = os.getenv("LB_CREDENTIALS")
        if lb_path and os.path.exists(lb_path):
            _gspread_client_cache = gspread.service_account(filename=lb_path)
            return _gspread_client_cache

        return None

    except Exception:
        return None