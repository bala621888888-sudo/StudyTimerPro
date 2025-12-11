# dotenv.py
import sys
import os

# 🔒 Hide console immediately
if os.name == "nt":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

import requests
import os

# Global flag to track if credentials are already loaded
_credentials_loaded = False

class FirebaseEnv:
    def __init__(self):
        global _credentials_loaded

        # ✅ Skip reloading if already done
        if _credentials_loaded:
            return

        # ✅ Google API key is now handled securely by backend / Firebase
        self.API_KEY = None  # Managed securely by Firebase backend

        # ✅ Firebase Realtime Database URL can remain here (safe)
        self.DATABASE_URL = "https://leaderboard-98e8c-default-rtdb.asia-southeast1.firebasedatabase.app"

        # Load credentials/config from Firebase (if needed)
        if self._load_from_firebase():
            _credentials_loaded = True  # Only set to True if successful

    
    def _authenticate_anonymous(self):
        """Authenticate anonymously using Firebase backend (no API key in client)."""
        from api_client import api  # ✅ Ensure imported at the top of the file

        try:
            result = api.anonymous_login()  # 🔐 Backend handles Firebase sign-in securely

            if result.get('success'):
                return result.get('idToken')
            else:
                print(f"[AUTH] Anonymous auth failed: {result.get('error')}")
        except Exception as e:
            print(f"[AUTH] Anonymous auth exception: {e}")

        return None

    
    

# dotenv.py
def load_dotenv():
    """
    Stub dotenv loader.
    All secrets are now managed through Google Secret Manager.
    """
    print("[dotenv] Skipping Firebase secret load (migrated to Secret Manager)")
    return True