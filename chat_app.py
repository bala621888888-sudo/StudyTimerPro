#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# CRITICAL: Prevent any sys.path or os.chdir() modifications
import sys
import os
import math

# SET UP FILE LOGGING (prints don't show in logcat)
log_file = None
original_print = print  # SAVE original print first!

try:
    log_dir = "/data/data/com.flet.chat_app/files"
    log_path = os.path.join(log_dir, "fcm_debug.log")
    log_file = open(log_path, "w", buffering=1)
    
    def log_print(*args, **kwargs):
        """Print to both stdout and file"""
        message = " ".join(str(arg) for arg in args)
        original_print(message, **kwargs)  # Use saved original
        if log_file:
            log_file.write(message + "\n")
            log_file.flush()
    
    # Replace print
    print = log_print
    print("="*50)
    print("FCM DEBUG LOG STARTED")
    print(f"Log file: {log_path}")
    print("="*50)
except Exception as e:
    original_print(f"Logging setup failed: {e}")

# BLOCK any code that tries to change working directory on Android
original_chdir = os.chdir

def safe_chdir(path):
    """Prevent chdir on Android"""
    try:
        import platform
        if platform.system() == "Android":
            print(f"⚠️ BLOCKED os.chdir({path}) on Android")
            return  # Do nothing on Android
    except:
        pass
    original_chdir(path)

os.chdir = safe_chdir

import flet as ft
import requests
import json
import time
import os
import threading
import random
import smtplib
import sys
import traceback
import queue
from secrets_util import get_secret, get_encrypted_gspread_client
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Flet icons fallback (older builds may not expose ft.icons)
try:
    ICONS = ft.icons
except AttributeError:  # pragma: no cover - compatibility shim
    class _Icons:
        NOTIFICATIONS = "notifications"

    ICONS = _Icons()

# Message listener system
active_listeners = {}  # Store active listeners
message_queue = queue.Queue()  # Queue for UI updates
listener_lock = threading.Lock()

# -------------------- FCM TOKEN LOADER --------------------
import os

def get_fcm_token_from_file():
    """
    Load FCM token stored by Flutter / Kotlin inside internal app folder.
    Tries multiple paths to ensure compatibility.
    """
    possible_paths = [
        # Dart via path_provider (new way)
        "/data/user/0/com.flet.chat_app/app_flutter/.chatapp/fcm_token.txt",
        "/data/data/com.flet.chat_app/app_flutter/.chatapp/fcm_token.txt",

        # If you later actually use com.chatapp.mobile:
        "/data/user/0/com.chatapp.mobile/app_flutter/.chatapp/fcm_token.txt",
        "/data/data/com.chatapp.mobile/app_flutter/.chatapp/fcm_token.txt",

        # Kotlin MainActivity via filesDir (current behaviour)
        "/data/user/0/com.flet.chat_app/files/.chatapp/fcm_token.txt",
        "/data/data/com.flet.chat_app/files/.chatapp/fcm_token.txt",
        "/data/user/0/com.chatapp.mobile/files/.chatapp/fcm_token.txt",
        "/data/data/com.chatapp.mobile/files/.chatapp/fcm_token.txt",
    ]

    for token_path in possible_paths:
        try:
            if os.path.exists(token_path):
                with open(token_path, "r") as f:
                    token = f.read().strip()
                    if token:
                        return token
        except Exception as e:
            pass
    return None

# Global error handler for APK builds
def setup_error_handling(page):
    """Setup global error handler"""
    def handle_error(e):
        error_msg = f"Error: {str(e)}\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        try:
            if page:
                page.clean()
                page.add(
                    ft.Container(
                        content=ft.Column([
                            ft.Text("App Error", size=20, color="red", weight="bold"),
                            ft.Container(
                                content=ft.Text(error_msg, size=12, selectable=True),
                                padding=10,
                                bgcolor="#FFE5E5",
                                border_radius=10
                            ),
                            ft.ElevatedButton("Close", on_click=lambda e: sys.exit(0))
                        ], scroll="auto", horizontal_alignment="center"),
                        padding=20,
                        expand=True
                    )
                )
                page.update()
        except:
            pass
    
    return handle_error
    


# Safe environment variable getter
def get_env_var(key, default):
    """Safely get environment variables with fallback"""
    try:
        value = os.environ.get(key)
        if value and value.strip():
            return value
        return default
    except:
        return default

# Rest of your existing code...

# Firebase Configuration
FIREBASE_CONFIG = {
    "apiKey": os.environ.get("FIREBASE_API_KEY", "AIzaSyBTu-DqEjSnat7HhNeuboWxNnoryy7-6m4"),
    "authDomain": "leaderboard-98e8c.firebaseapp.com",
    "databaseURL": "https://leaderboard-98e8c-default-rtdb.asia-southeast1.firebasedatabase.app",
    "projectId": "leaderboard-98e8c",
    "storageBucket": "leaderboard-98e8c.firebasestorage.app"
}

# Email Configuration for OTP
EMAIL_CONFIG = {
    "sender_email": os.environ.get("SENDER_EMAIL", "studytimerpro@gmail.com"),
    "sender_password": os.environ.get("SENDER_PASSWORD", "iubj mluu oiro prhd"),
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587
}

ADMIN_EMAIL = "bala6218888@gmail.com"
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB in bytes

# ============================================
# FCM CONFIGURATION
# ============================================
def _load_fcm_service_account():
    """
    Load Firebase service account JSON.

    Priority:
    1) FIREBASE_SERVICE_ACCOUNT or FCM_SERVICE_ACCOUNT env var (PC/dev)
    2) Secret Manager value (FCM_SERVICE_ACCOUNT)
    3) assets/firebase_service_account.json (inside APK)
    """
    # 1) Environment variable - for local dev / desktop
    for env_key in ("FIREBASE_SERVICE_ACCOUNT", "FCM_SERVICE_ACCOUNT"):
        env_value = os.environ.get(env_key)
        if env_value and env_value.strip():
            print(f"✅ Loaded FCM service account from env: {env_key}.")
            return env_value

    # 2) Secret Manager (works when GitHub Actions injects FCM_SERVICE_ACCOUNT)
    try:
        secret_value = get_secret("FCM_SERVICE_ACCOUNT")
        if secret_value and secret_value.strip():
            print("✅ Loaded FCM service account from Secret Manager: FCM_SERVICE_ACCOUNT.")
            return secret_value
    except Exception as e:
        print(f"⚠️ Error loading FCM service account from Secret Manager: {e}")

    # 3) Asset file - for packaged mobile app
    try:
        assets_dir = os.environ.get("FLET_ASSETS_DIR", "assets")
        candidates = [
            os.path.join(assets_dir, "firebase_service_account.json"),
            os.path.join(os.path.dirname(__file__), "assets", "firebase_service_account.json"),
        ]
        for path in candidates:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    print(f"✅ Loaded FCM service account from file: {path}")
                    return f.read()
    except Exception as e:
        print(f"⚠️ Error loading FCM service account: {e}")

    print("⚠️ No FCM service account found. Push notifications disabled.")
    return ""


FCM_SERVICE_ACCOUNT = _load_fcm_service_account()

# ============================================
# FCM V1 SENDER CLASS - Push Notifications
# ============================================
class FCMSender:
    """
    Firebase Cloud Messaging V1 API Sender
    Uses OAuth 2.0 service account authentication (not legacy server key)
    """
    def __init__(self, service_account_json):
        """
        Initialize FCM sender with service account
        Args:
            service_account_json: Service account JSON string or dict
        """
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
            import json
            
            # Parse service account JSON
            if isinstance(service_account_json, str):
                service_account_info = json.loads(service_account_json)
            else:
                service_account_info = service_account_json
            
            # Create credentials
            self.credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/firebase.messaging']
            )
            
            # Extract project ID
            self.project_id = service_account_info.get('project_id')
            if not self.project_id:
                raise ValueError("Could not extract project_id from service account")
            
            self.fcm_url = f'https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send'
            print(f"✅ FCM V1 initialized for project: {self.project_id}")
            
        except ImportError:
            print("⚠️ google-auth package not installed. FCM notifications disabled.")
            print("   Run: pip install google-auth google-auth-oauthlib")
            self.credentials = None
            self.project_id = None
            self.fcm_url = None
        except Exception as e:
            print(f"❌ Failed to initialize FCM: {e}")
            self.credentials = None
            self.project_id = None
            self.fcm_url = None
    
    def _get_access_token(self):
        """Get OAuth 2.0 access token"""
        if not self.credentials:
            return None
        try:
            from google.auth.transport.requests import Request
            self.credentials.refresh(Request())
            return self.credentials.token
        except Exception as e:
            print(f"Error getting access token: {e}")
            return None
    
    def send_notification(self, fcm_token, title, body, data=None):
        """
        Send notification to a single device
        Args:
            fcm_token: Device FCM token
            title: Notification title
            body: Notification body  
            data: Optional data payload (dict)
        Returns:
            bool: True if successful
        """
        if not self.fcm_url or not fcm_token:
            print(f"❌ [FCM SEND] Missing URL or token")
            print(f"   fcm_url: {self.fcm_url}")
            print(f"   fcm_token: {'Present' if fcm_token else 'Missing'}")
            return False

        access_token = self._get_access_token()
        if not access_token:
            print(f"❌ [FCM SEND] Failed to get access token")
            return False

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json; charset=UTF-8',
        }
        
        message = {
            'message': {
                'token': fcm_token,
                'notification': {
                    'title': title,
                    'body': body
                },
                'android': {
                    'priority': 'high',
                    'notification': {
                        'sound': 'default',
                        'click_action': 'FLUTTER_NOTIFICATION_CLICK'
                    }
                }
            }
        }
        
        # Add custom data if provided
        if data:
            message['message']['data'] = {k: str(v) for k, v in data.items()}
            print(f"📦 [FCM SEND] Added data payload: {data}")
        
        print(f"🌐 [FCM SEND] Sending to: {self.fcm_url}")
        try:
            response = requests.post(self.fcm_url, headers=headers, json=message, timeout=10)
            print(f"📊 [FCM SEND] Response status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"✅ [FCM SEND] Notification sent successfully!")
                print(f"   Response: {response.json()}")
                return True
            else:
                print(f"❌ [FCM SEND] Failed with status {response.status_code}")
                print(f"   Error: {response.text}")
                return False
        except Exception as e:
            print(f"❌ [FCM SEND] Exception: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def send_to_multiple(self, fcm_tokens, title, body, data=None):
        """
        Send notification to multiple devices
        Args:
            fcm_tokens: List of FCM tokens
            title: Notification title
            body: Notification body
            data: Optional data payload
        Returns:
            dict: Results with success/failure counts
        """
        results = {'success': 0, 'failure': 0}
        
        for token in fcm_tokens:
            if self.send_notification(token, title, body, data):
                results['success'] += 1
            else:
                results['failure'] += 1
        
        return results

# Initialize global FCM sender
fcm_sender = None
print("\n🔥 [FCM INIT] Starting FCM initialization...")
print(f"   Service account present: {bool(FCM_SERVICE_ACCOUNT)}")

if FCM_SERVICE_ACCOUNT:
    try:
        print("🔄 [FCM INIT] Creating FCMSender instance...")
        fcm_sender = FCMSender(FCM_SERVICE_ACCOUNT)
        
        if fcm_sender and fcm_sender.credentials and fcm_sender.project_id:
            print(f"✅ [FCM INIT] FCM initialized successfully!")
            print(f"   Project ID: {fcm_sender.project_id}")
            print(f"   FCM URL: {fcm_sender.fcm_url}")
            print(f"   Credentials: OK")
        else:
            print("❌ [FCM INIT] FCM object created but missing credentials")
            print(f"   fcm_sender: {fcm_sender}")
            print(f"   credentials: {fcm_sender.credentials if fcm_sender else 'N/A'}")
            print(f"   project_id: {fcm_sender.project_id if fcm_sender else 'N/A'}")
            fcm_sender = None
            
    except Exception as e:
        print(f"❌ [FCM INIT] FCM initialization failed: {e}")
        import traceback
        traceback.print_exc()
        fcm_sender = None
else:
    print("⚠️ [FCM INIT] FCM_SERVICE_ACCOUNT not set. Notifications disabled.")
    
print(f"📊 [FCM INIT] Final fcm_sender state: {'READY' if fcm_sender else 'NULL'}\n")
    
# ============================================
# MESSAGE LISTENER CLASS - Real-time updates
# ============================================
class MessageListener:
    """Firebase real-time message listener using polling"""
    
    def __init__(self, chat_id, callback, db_instance):
        self.chat_id = chat_id
        self.callback = callback
        self.db = db_instance
        self.running = False
        self.thread = None
        self.last_message_count = 0
        self.last_check = 0
    
    def start(self):
        """Start listening for new messages"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        print(f"[LISTENER] Started for chat {self.chat_id}")
    
    def stop(self):
        """Stop listening"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        print(f"[LISTENER] Stopped for chat {self.chat_id}")
    
    def _listen_loop(self):
        """Background loop to check for new messages"""
        while self.running:
            try:
                # Only check every 3 seconds to reduce load
                current_time = time.time()
                if current_time - self.last_check < 3:
                    time.sleep(0.5)
                    continue
                
                self.last_check = current_time
                
                # Fetch latest messages
                messages = self.db.get_messages(self.chat_id)
                
                if messages:
                    message_count = len(messages)
                    
                    # Check if there are new messages
                    if message_count > self.last_message_count:
                        print(f"[LISTENER] New messages detected: {message_count} (was {self.last_message_count})")
                        self.last_message_count = message_count
                        
                        # Put update request in queue for UI thread
                        message_queue.put({
                            'type': 'update_messages',
                            'chat_id': self.chat_id,
                            'messages': messages
                        })
                    else:
                        self.last_message_count = message_count
                
                # Sleep before next check
                time.sleep(1)
                
            except Exception as e:
                print(f"[LISTENER ERROR] {e}")
                time.sleep(2)  # Wait longer on error

"""
Cache-First Loading Strategy for Chat App
Replace the relevant sections in your code with these improved versions.
Shows cached data immediately, then syncs with server in background.
"""

# Add these lines after your imports and before FirebaseAuth class
import pickle

# ============================================
# CACHE MANAGER CLASS - Add this entire section
# ============================================
class CacheManager:
    """Manages all app caching with offline support"""
    
    CACHE_VERSION = "v1"
    
    @staticmethod
    def get_cache_file(cache_type):
        """Get cache file path for different data types"""
        cache_files = {
            'users': CACHE_DIR / 'users_cache.pkl',
            'groups': CACHE_DIR / 'groups_cache.pkl',
            'group_members': CACHE_DIR / 'group_members_cache.pkl',
            'private_chats': CACHE_DIR / 'private_chats_cache.pkl',
            'group_info': CACHE_DIR / 'group_info_cache.pkl'
        }
        return cache_files.get(cache_type)
    
    @staticmethod
    def save_to_cache(cache_type, data):
        """Save data to cache with timestamp"""
        try:
            cache_file = CacheManager.get_cache_file(cache_type)
            if cache_file:
                cache_data = {
                    'version': CacheManager.CACHE_VERSION,
                    'timestamp': time.time(),
                    'data': data
                }
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_file, 'wb') as f:
                    pickle.dump(cache_data, f)
                return True
        except Exception as e:
            print(f"Cache save error ({cache_type}): {e}")
        return False
    
    @staticmethod
    def sanitize_data(data):
        """Remove NaN values from cached data"""
        import math
        
        if isinstance(data, dict):
            return {k: CacheManager.sanitize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [CacheManager.sanitize_data(item) for item in data]
        elif isinstance(data, float):
            if math.isnan(data) or math.isinf(data):
                return 0
            return data
        return data
    
    @staticmethod
    def load_from_cache(cache_type):
        """Load data from cache if available"""
        try:
            cache_file = CacheManager.get_cache_file(cache_type)
            if cache_file and cache_file.exists():
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                
                if cache_data.get('version') != CacheManager.CACHE_VERSION:
                    return None
                
                # 🔥 SANITIZE BEFORE RETURNING
                data = cache_data.get('data')
                return CacheManager.sanitize_data(data)
        except Exception as e:
            print(f"Cache load error ({cache_type}): {e}")
        return None

# ============================================
# NETWORK CHECKER - Add this too
# ============================================
class NetworkChecker:
    """Check internet connectivity"""
    
    @staticmethod
    def is_online():
        """Quick check if internet is available"""
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return True
        except:
            return False

class FirebaseAuth:
    def __init__(self, api_key):
        self.api_key = api_key
        self.user_id = None
        self.id_token = None
        self.refresh_token = None
        self.email = None
        
    def sign_up(self, email, password):
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={self.api_key}"
        payload = {"email": email, "password": password, "returnSecureToken": True}
        
        try:
            response = requests.post(url, json=payload)
            data = response.json()
            
            if response.status_code == 200:
                self.user_id = data['localId']
                self.id_token = data['idToken']
                self.refresh_token = data.get('refreshToken')
                self.email = email
                return True, "Account created successfully!"
            else:
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                return False, error_msg
        except Exception as e:
            return False, str(e)
    
    def sign_in(self, email, password):
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.api_key}"
        payload = {"email": email, "password": password, "returnSecureToken": True}
        
        try:
            response = requests.post(url, json=payload)
            data = response.json()
            
            if response.status_code == 200:
                self.user_id = data['localId']
                self.id_token = data['idToken']
                self.refresh_token = data.get('refreshToken')
                self.email = email
                return True, "Signed in successfully!"
            else:
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                return False, error_msg
        except Exception as e:
            return False, str(e)
    
    def refresh_id_token(self):
        """Refresh the ID token using refresh token"""
        if not self.refresh_token:
            return False
        
        url = f"https://securetoken.googleapis.com/v1/token?key={self.api_key}"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        
        try:
            response = requests.post(url, json=payload)
            data = response.json()
            
            if response.status_code == 200:
                self.id_token = data['id_token']
                self.refresh_token = data['refresh_token']
                self.user_id = data['user_id']
                return True
            return False
        except:
            return False

class OTPManager:
    def __init__(self):
        self.otp_storage = {}  # email: {"otp": code, "timestamp": time}
    
    def generate_otp(self):
        """Generate 6-digit OTP"""
        return str(random.randint(100000, 999999))
    
    def send_otp(self, email, otp):
        """Send OTP via email with retry logic"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                msg = MIMEMultipart()
                msg['From'] = EMAIL_CONFIG['sender_email']
                msg['To'] = email
                msg['Subject'] = "Your Chat App Login OTP"
                
                body = f"""
                <html>
                    <body style="font-family: Arial, sans-serif; padding: 20px;">
                        <h2 style="color: #2196F3;">Chat App Login</h2>
                        <p>Your OTP code is:</p>
                        <h1 style="color: #4CAF50; font-size: 48px; letter-spacing: 10px;">{otp}</h1>
                        <p>This code will expire in 5 minutes.</p>
                        <p style="color: #666;">If you didn't request this code, please ignore this email.</p>
                    </body>
                </html>
                """
                
                msg.attach(MIMEText(body, 'html'))
                
                # Create new SMTP connection for each attempt
                server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'], timeout=10)
                server.starttls()
                server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
                server.send_message(msg)
                server.quit()
                
                # Store OTP with timestamp
                self.otp_storage[email] = {
                    "otp": otp,
                    "timestamp": time.time()
                }
                
                return True
                
            except smtplib.SMTPAuthenticationError as e:
                print(f"SMTP Authentication Error (Attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False
                
            except smtplib.SMTPException as e:
                print(f"SMTP Error (Attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False
                
            except Exception as e:
                print(f"Error sending OTP (Attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False
        
        return False
    
    def verify_otp(self, email, entered_otp):
        """Verify OTP - expires after 5 minutes"""
        if email not in self.otp_storage:
            return False
        
        stored_data = self.otp_storage[email]
        
        # Check if OTP expired (5 minutes)
        if time.time() - stored_data['timestamp'] > 300:
            del self.otp_storage[email]
            return False
        
        # Verify OTP
        if stored_data['otp'] == entered_otp:
            del self.otp_storage[email]  # Remove after successful verification
            return True
        
        return False
        
class SMSReader:
    def __init__(self):
        self.last_otp = None
        self.monitoring = False
        self.receiver = None
    
    def start_monitoring(self, callback):
        """Start monitoring for SMS with OTP - mobile only"""
        try:
            import platform
            if platform.system() != 'Android':
                return False
            
            from android.permissions import request_permissions, Permission, check_permission
            from android.broadcast import BroadcastReceiver
            from jnius import autoclass
            
            # Check if permissions are already granted
            if not check_permission(Permission.RECEIVE_SMS) or not check_permission(Permission.READ_SMS):
                # Request SMS permissions
                request_permissions([Permission.RECEIVE_SMS, Permission.READ_SMS])
                time.sleep(1)  # Wait for permission dialog
            
            SmsMessage = autoclass('android.telephony.SmsMessage')
            
            def on_sms_received(context, intent):
                try:
                    messages = intent.getParcelableArrayExtra("pdus")
                    if not messages:
                        return
                        
                    for message in messages:
                        sms = SmsMessage.createFromPdu(message)
                        sender = sms.getOriginatingAddress()
                        body = sms.getMessageBody()
                        
                        # Extract 6-digit OTP from message
                        import re
                        otp_match = re.search(r'\b(\d{6})\b', body)
                        
                        if otp_match:
                            otp_code = otp_match.group(1)
                            self.last_otp = otp_code
                            callback(otp_code)
                            break
                except Exception as e:
                    print(f"SMS read error: {e}")
            
            # Register broadcast receiver
            self.receiver = BroadcastReceiver(on_sms_received, actions=['android.provider.Telephony.SMS_RECEIVED'])
            self.receiver.start()
            self.monitoring = True
            return True
            
        except Exception as e:
            print(f"SMS monitoring not available: {e}")
            return False
    
    def stop_monitoring(self):
        """Stop monitoring SMS"""
        self.monitoring = False
        try:
            if self.receiver:
                self.receiver.stop()
        except:
            pass

class ClipboardMonitor:
    def __init__(self, page):
        self.page = page
        self.monitoring = False
        self.last_value = ""
        self.thread = None
    
    def start_monitoring(self, callback):
        """Monitor clipboard for OTP codes"""
        self.monitoring = True
        
        def monitor_loop():
            import re
            while self.monitoring:
                try:
                    # Get clipboard content
                    clipboard_text = self.page.get_clipboard()
                    
                    if clipboard_text and clipboard_text != self.last_value:
                        self.last_value = clipboard_text
                        
                        # Look for 6-digit OTP
                        otp_match = re.search(r'\b(\d{6})\b', clipboard_text)
                        if otp_match:
                            otp_code = otp_match.group(1)
                            callback(otp_code)
                    
                    time.sleep(1)  # Check every second
                except Exception as e:
                    print(f"Clipboard monitor error: {e}")
                    time.sleep(1)
        
        self.thread = threading.Thread(target=monitor_loop, daemon=True)
        self.thread.start()
        return True
    
    def stop_monitoring(self):
        self.monitoring = False

class CredentialsManager:
    @staticmethod
    def save_credentials(email, refresh_token, username):
        """Save credentials locally"""
        try:
            credentials = {
                "email": email,
                "refresh_token": refresh_token,
                "username": username
            }
            with open(CREDENTIALS_FILE, 'w') as f:
                json.dump(credentials, f)
            return True
        except:
            return False
    
    @staticmethod
    def load_credentials():
        """Load saved credentials"""
        try:
            if CREDENTIALS_FILE.exists():
                with open(CREDENTIALS_FILE, 'r') as f:
                    return json.load(f)
            return None
        except:
            return None
    
    @staticmethod
    def clear_credentials():
        """Clear saved credentials (logout)"""
        try:
            if CREDENTIALS_FILE.exists():
                CREDENTIALS_FILE.unlink()
            return True
        except:
            return False
            
class ImageCache:
    @staticmethod
    def get_cache_path(image_url, cache_type="profile"):
        """Generate cache file path from URL"""
        import hashlib
        url_hash = hashlib.md5(image_url.encode()).hexdigest()
        cache_dir = CACHE_DIR if cache_type == "profile" else GROUP_ICON_CACHE_DIR
        return cache_dir / f"{url_hash}.jpg"
    
    @staticmethod
    def get_cached_image(image_url, cache_type="profile"):
        """Get cached image path if exists"""
        if not image_url:
            return None
        
        path = ImageCache.get_cache_path(image_url, cache_type)
        if path.exists():
            return str(path)
        return None
    
    @staticmethod
    def download_image(image_url, callback, cache_type="profile"):
        """Download image in background and cache it"""
        if not image_url:
            return
        
        def download_thread():
            try:
                response = requests.get(image_url, timeout=10)
                if response.status_code == 200:
                    path = ImageCache.get_cache_path(image_url, cache_type)
                    with open(path, "wb") as f:
                        f.write(response.content)
                    
                    # Callback with cached path
                    if callback:
                        callback(str(path))
            except Exception as e:
                print(f"Image download error: {e}")
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    @staticmethod
    def clear_cache():
        """Clear all cached images"""
        try:
            import shutil
            if CACHE_DIR.exists():
                shutil.rmtree(CACHE_DIR)
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if GROUP_ICON_CACHE_DIR.exists():
                shutil.rmtree(GROUP_ICON_CACHE_DIR)
                GROUP_ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            return True
        except:
            return False

class FirebaseStorage:
    def __init__(self, bucket_name, auth_token):
        self.bucket_name = bucket_name
        self.auth_token = auth_token
    
    def upload_file(self, file_path, file_name, file_data):
        """Upload file to Firebase Storage"""
        try:
            # Use simple upload API without auth token issues
            encoded_path = file_path.replace('/', '%2F')
            
            # Upload URL - simplified
            upload_url = f"https://firebasestorage.googleapis.com/v0/b/{self.bucket_name}/o?name={file_path}"
            
            response = requests.post(
                upload_url,
                data=file_data,
                headers={"Content-Type": "application/octet-stream"}
            )
            
            if response.status_code == 200:
                # Generate public download URL
                download_url = f"https://firebasestorage.googleapis.com/v0/b/{self.bucket_name}/o/{encoded_path}?alt=media"
                return True, download_url
            else:
                error_info = f"Status {response.status_code}"
                try:
                    error_data = response.json()
                    error_info = error_data.get('error', {}).get('message', error_info)
                except:
                    error_info = response.text[:100] if response.text else error_info
                
                return False, f"Upload failed: {error_info}"
                    
        except Exception as e:
            return False, f"Error: {str(e)}"
            
class FCMNotificationSender:
    def __init__(self):
        self.access_token = None
        self.token_expiry = 0
        
    def get_access_token(self):
        """Get OAuth2 access token from service account"""
        try:
            import json
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
            
            # Check if token is still valid
            if self.access_token and time.time() < self.token_expiry:
                return self.access_token
            
            # Parse service account JSON
            service_account_info = json.loads(FCM_SERVICE_ACCOUNT)
            
            # Create credentials
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/firebase.messaging']
            )
            
            # Refresh token
            credentials.refresh(Request())
            
            self.access_token = credentials.token
            self.token_expiry = time.time() + 3000  # Token valid for ~50 minutes
            
            return self.access_token
            
        except Exception as e:
            print(f"Error getting access token: {e}")
            return None
    
    def send_notification(self, fcm_token, title, body, data=None):
        """Send FCM notification using V1 API"""
        try:
            access_token = self.get_access_token()
            if not access_token:
                print("Failed to get access token")
                return False
            
            project_id = "leaderboard-98e8c"
            url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            message = {
                "message": {
                    "token": fcm_token,
                    "notification": {
                        "title": title,
                        "body": body
                    },
                    "android": {
                        "priority": "high",
                        "notification": {
                            "sound": "default",
                            "click_action": "FLUTTER_NOTIFICATION_CLICK",
                            "channel_id": "chat_messages"
                        }
                    },
                    "data": data or {}
                }
            }
            
            response = requests.post(url, headers=headers, json=message)
            
            if response.status_code == 200:
                print(f"Notification sent successfully to {title}")
                return True
            else:
                print(f"FCM error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error sending FCM notification: {e}")
            return False

class FirebaseDatabase:
    def __init__(self, database_url, auth_token):
        self.database_url = database_url
        self.auth_token = auth_token
        
    def get_all_groups(self):
        """Get all groups from Firebase"""
        url = f"{self.database_url}/groups.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                groups_data = response.json()
                if groups_data:
                    groups_list = []
                    for group_id, group_data in groups_data.items():
                        info = group_data.get('info', {})
                        members = group_data.get('members', {})
                        
                        groups_list.append({
                            'id': group_id,
                            'name': info.get('name', 'Unnamed Group'),
                            'description': info.get('description', ''),
                            'icon': info.get('icon', '👥'),
                            'icon_url': info.get('icon_url'),
                            'created_by': info.get('created_by'),
                            'created_at': info.get('created_at', 0),
                            'member_count': len(members),
                            'members': members
                        })
                    
                    groups_list.sort(key=lambda x: x.get('created_at', 0), reverse=True)
                    return groups_list
                return []
            return []
        except Exception as e:
            print(f"Error fetching groups: {e}")
            return []

    def get_group_info_by_id(self, group_id):
        """Get info for a specific group"""
        url = f"{self.database_url}/groups/{group_id}/info.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                info = response.json()
                if info:
                    return info
            return {"name": "Group", "description": "", "icon": "👥", "icon_url": None}
        except:
            return {"name": "Group", "description": "", "icon": "👥", "icon_url": None}

    def get_group_members_by_id(self, group_id):
        """Get members for a specific group"""
        url = f"{self.database_url}/groups/{group_id}/members.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                members = response.json()
                if members:
                    member_list = []
                    for user_id, member_data in members.items():
                        member_data['id'] = user_id
                        member_list.append(member_data)
                    return member_list
                return []
            return []
        except:
            return []

    def get_group_messages_by_id(self, group_id, limit=50):
        """Get messages for a specific group"""
        url = f"{self.database_url}/groups/{group_id}/messages.json?auth={self.auth_token}"
        print(f"[DEBUG] get_group_messages_by_id called for group_id={group_id}, url={url}")
        try:
            response = requests.get(url)
            print(f"[DEBUG] get_group_messages_by_id status={response.status_code}")
            if response.status_code == 200:
                messages = response.json() or {}
                if messages:
                    try:
                        print(f"[DEBUG] get_group_messages_by_id raw keys={list(messages.keys())[:5]}")
                    except Exception:
                        pass
                    message_list = []
                    for msg_id, msg_data in messages.items():
                        if not isinstance(msg_data, dict):
                            continue
                        msg_data["id"] = msg_id
                        message_list.append(msg_data)
                    message_list.sort(key=lambda x: x.get("timestamp", 0))
                    if len(message_list) > limit:
                        message_list = message_list[-limit:]
                    return message_list
                else:
                    print("[DEBUG] get_group_messages_by_id: no messages in JSON")
                    return []
            else:
                print("[DEBUG] get_group_messages_by_id: non-200 status, returning []")
                return []
        except Exception as e:
            print(f"[DEBUG] get_group_messages_by_id exception: {e}")
            return []

    def send_group_message_by_id(self, group_id, sender_id, sender_username, message_text, is_admin=False, file_url=None, file_name=None, file_size=None):
        """Send message to a specific group"""
        url = f"{self.database_url}/groups/{group_id}/messages.json?auth={self.auth_token}"
        print(f"[DEBUG] send_group_message_by_id url={url}")
        message_data = {
            "sender_id": sender_id,
            "sender_username": sender_username,
            "text": message_text,
            "timestamp": int(time.time() * 1000),
            "is_admin": is_admin,
        }
        if file_url:
            message_data["file_url"] = file_url
            message_data["file_name"] = file_name
            message_data["file_size"] = file_size
        try:
            response = requests.post(url, json=message_data)
            print(f"[DEBUG] send_group_message_by_id status={response.status_code}, text={response.text[:200]}")
            
            if response.status_code == 200:
                # ✅ Send FCM notification to all group members
                self._send_group_chat_notification(group_id, sender_id, sender_username, message_text)
                return True
            return False
        except Exception as e:
            print(f"[DEBUG] send_group_message_by_id exception: {e}")
            return False
    
    def _send_group_chat_notification(self, group_id, sender_id, sender_username, message_text):
        """Send FCM notification to all group members except sender"""
        if not fcm_sender:
            return
        
        try:
            # Get group members
            members = self.get_group_members_by_id(group_id)
            if not members:
                return
            
            # Get group info
            group_info = self.get_group_info_by_id(group_id)
            group_name = group_info.get('name', 'Group')
            
            # Get FCM tokens for all members except sender
            member_ids = [m['id'] for m in members if m['id'] != sender_id]
            fcm_tokens = self.get_multiple_fcm_tokens(member_ids)
            
            if not fcm_tokens:
                return
            
            # Truncate message if too long
            body = message_text[:100] + "..." if len(message_text) > 100 else message_text
            
            # Send notifications in background thread
            def send_notifications_async():
                results = fcm_sender.send_to_multiple(
                    fcm_tokens=fcm_tokens,
                    title=f"👥 {group_name}",
                    body=f"{sender_username}: {body}",
                    data={
                        'type': 'group_message',
                        'group_id': group_id,
                        'group_name': group_name,
                        'sender_id': sender_id,
                        'sender_name': sender_username
                    }
                )
            threading.Thread(target=send_notifications_async, daemon=True).start()
            
        except Exception as e:
            print(f"Error sending group notification: {e}")

    def update_group_info_by_id(self, group_id, name, description, icon, icon_url=None, category="None"):
        """Update info for a specific group"""
        url = f"{self.database_url}/groups/{group_id}/info.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url)
            existing = response.json() or {}
            
            existing.update({
                "name": name,
                "description": description,
                "icon": icon,
                "icon_url": icon_url,
                "category": category
            })
            
            response = requests.put(url, json=existing)
            return response.status_code == 200
        except:
            return False
    
    def delete_group_by_id(self, group_id):
        """Delete a specific group and all its data"""
        url = f"{self.database_url}/groups/{group_id}.json?auth={self.auth_token}"
        
        try:
            response = requests.delete(url)
            return response.status_code == 200
        except:
            return False

    def add_member_to_group(self, group_id, user_id, username, is_admin=False):
        """Add member to a specific group"""
        url = f"{self.database_url}/groups/{group_id}/members/{user_id}.json?auth={self.auth_token}"
        member_data = {
            "username": username,
            "joined_at": int(time.time() * 1000),
            "is_admin": is_admin
        }
        
        try:
            response = requests.put(url, json=member_data)
            return response.status_code == 200
        except:
            return False

    def remove_member_from_group(self, group_id, user_id):
        """Remove member from a specific group"""
        url = f"{self.database_url}/groups/{group_id}/members/{user_id}.json?auth={self.auth_token}"
        
        try:
            response = requests.delete(url)
            return response.status_code == 200
        except:
            return False

    def toggle_admin_in_group(self, group_id, user_id, is_admin):
        """Toggle admin status in a specific group"""
        url = f"{self.database_url}/groups/{group_id}/members/{user_id}/is_admin.json?auth={self.auth_token}"
        
        try:
            response = requests.put(url, json=is_admin)
            return response.status_code == 200
        except:
            return False
        
    def send_fcm_notification(self, user_id, title, body, data=None):
        """Send FCM push notification to a specific user"""
        try:
            # Get user's FCM token from database
            token_url = f"{self.database_url}/user_tokens/{user_id}/fcm_token.json?auth={self.auth_token}"
            response = requests.get(token_url)
            
            if response.status_code != 200 or not response.json():
                return False
            
            fcm_token = response.json()
            
            # Use FCM V1 API
            fcm_sender = FCMNotificationSender()
            return fcm_sender.send_notification(fcm_token, title, body, data)
            
        except Exception as e:
            print(f"FCM notification error: {e}")
            return False

    def store_fcm_token(self, user_id, fcm_token):
        """Store user's FCM token"""
        url = f"{self.database_url}/user_tokens/{user_id}/fcm_token.json?auth={self.auth_token}"
        
        try:
            response = requests.put(url, json=fcm_token)
            return response.status_code == 200
        except:
            return False

   
    def get_messages(self, chat_id, limit=20):
        url = f"{self.database_url}/chats/{chat_id}/messages.json?auth={self.auth_token}&orderBy=\"timestamp\"&limitToLast={limit}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                messages = response.json()
                if messages:
                    message_list = []
                    for msg_id, msg_data in messages.items():
                        msg_data['id'] = msg_id
                        message_list.append(msg_data)
                    message_list.sort(key=lambda x: x.get('timestamp', 0))
                    return message_list
                return []
            return []
        except:
            return []

    def send_message(self, chat_id, sender_id, sender_username, message_text, is_admin=False, file_url=None, file_name=None, file_size=None, seen=False):
        url = f"{self.database_url}/chats/{chat_id}/messages.json?auth={self.auth_token}"
        message_data = {
            "sender_id": sender_id,
            "sender_username": sender_username,
            "text": message_text,
            "timestamp": int(time.time() * 1000),
            "is_admin": is_admin,
            "seen": seen
        }
        
        if file_url:
            message_data["file_url"] = file_url
            message_data["file_name"] = file_name
            message_data["file_size"] = file_size
        
        try:
            response = requests.post(url, json=message_data)
            if response.status_code == 200:
                # ✅ Send FCM notification to recipient
                self._send_private_chat_notification(chat_id, sender_id, sender_username, message_text)
                return True
            return False
        except:
            return False
    
    def _send_private_chat_notification(self, chat_id, sender_id, sender_username, message_text):
        """Send FCM notification for private chat message"""
        if not fcm_sender:
            return
        
        try:
            # Get both participants from chat ID
            user_ids = chat_id.split('_')
            recipient_id = user_ids[0] if user_ids[1] == sender_id else user_ids[1]
            
            # Get recipient's FCM token
            recipient_token = self.get_fcm_token(recipient_id)

            if not recipient_token:
                return
            
            # Truncate message if too long
            body = message_text[:100] + "..." if len(message_text) > 100 else message_text
            
            # Send notification in background thread
            def send_notification_async():
                result = fcm_sender.send_notification(
                    fcm_token=recipient_token,
                    title=f"💬 {sender_username}",
                    body=body,
                    data={
                        'type': 'private_message',
                        'chat_id': chat_id,
                        'sender_id': sender_id,
                        'sender_name': sender_username
                    }
                )
            threading.Thread(target=send_notification_async, daemon=True).start()
        except Exception as e:
            pass
    
    def get_chat_status(self, chat_id):
        """Get chat request status"""
        url = f"{self.database_url}/chats/{chat_id}/status.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                status = response.json()
                return status if status else "pending"
            return "pending"
        except:
            return "pending"
    
    def update_chat_status(self, chat_id, status):
        """Update chat request status (pending/accepted)"""
        url = f"{self.database_url}/chats/{chat_id}/status.json?auth={self.auth_token}"
        
        try:
            response = requests.put(url, json=status)
            return response.status_code == 200
        except:
            return False
    
    def get_chat_requester(self, chat_id):
        """Get the user who initiated the chat"""
        url = f"{self.database_url}/chats/{chat_id}/requester.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None
    
    def set_chat_requester(self, chat_id, user_id):
        """Set the user who initiated the chat"""
        url = f"{self.database_url}/chats/{chat_id}/requester.json?auth={self.auth_token}"
        
        try:
            response = requests.put(url, json=user_id)
            return response.status_code == 200
        except:
            return False
    
    def get_messages(self, chat_id):
        url = f"{self.database_url}/chats/{chat_id}/messages.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                messages = response.json()
                if messages:
                    message_list = []
                    for msg_id, msg_data in messages.items():
                        msg_data['id'] = msg_id
                        message_list.append(msg_data)
                    message_list.sort(key=lambda x: x.get('timestamp', 0))
                    return message_list
                return []
            return []
        except:
            return []
    
    
    def create_user_profile(self, user_id, email, username, profile_image_url=None):
        url = f"{self.database_url}/users/{user_id}.json?auth={self.auth_token}"
        profile_data = {
            "email": email,
            "username": username,
            "created_at": int(time.time() * 1000)
        }
        
        if profile_image_url:
            profile_data["profile_image_url"] = profile_image_url
        
        try:
            response = requests.put(url, json=profile_data)
            return response.status_code == 200
        except:
            return False
    
    def update_user_profile(self, user_id, username, profile_image_url=None):
        """Update user profile"""
        url = f"{self.database_url}/users/{user_id}.json?auth={self.auth_token}"
        
        # Get existing profile first
        try:
            response = requests.get(url)
            if response.status_code == 200:
                existing_data = response.json() or {}
            else:
                existing_data = {}
        except:
            existing_data = {}
        
        # Update fields
        existing_data["username"] = username
        if profile_image_url:
            existing_data["profile_image_url"] = profile_image_url
        
        try:
            response = requests.put(url, json=existing_data)
            return response.status_code == 200
        except:
            return False
    
    def get_user_profile(self, user_id):
        url = f"{self.database_url}/users/{user_id}.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                profile = response.json()
                return profile
            return None
        except:
            return None
    
    def get_all_users(self):
        url = f"{self.database_url}/users.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                users = response.json()
                if users:
                    user_list = []
                    seen_ids = set()
                    
                    for user_id, user_data in users.items():
                        # Skip duplicates
                        if user_id in seen_ids:
                            continue
                        
                        seen_ids.add(user_id)
                        user_data['id'] = user_id
                        
                        # Ensure username exists
                        if not user_data.get('username'):
                            user_data['username'] = user_data.get('email', 'Unknown').split('@')[0]
                        
                        user_list.append(user_data)
                    
                    return user_list
                return []
            return []
        except Exception as e:
            print(f"Error fetching users: {e}")
            return []
    
    # ============================================
    # FCM TOKEN MANAGEMENT METHODS
    # ============================================
    def save_fcm_token(self, user_id, fcm_token):
        """
        Save user's FCM token to Firebase
        Args:
            user_id: User ID
            fcm_token: FCM device token
        Returns:
            bool: True if successful
        """
        url = f"{self.database_url}/users/{user_id}/fcm_token.json?auth={self.auth_token}"

        try:
            response = requests.put(url, json=fcm_token, timeout=10)

            if response.status_code == 200:
                return True
            else:
                return False
        except Exception:
            return False
    
    def get_fcm_token(self, user_id):
        """
        Get user's FCM token from Firebase
        Args:
            user_id: User ID
        Returns:
            str: FCM token or None
        """
        url = f"{self.database_url}/users/{user_id}/fcm_token.json?auth={self.auth_token}"

        try:
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                return None
        except Exception:
            return None
    
    def get_multiple_fcm_tokens(self, user_ids):
        """
        Get FCM tokens for multiple users
        Args:
            user_ids: List of user IDs
        Returns:
            list: List of FCM tokens (excluding None values)
        """
        tokens = []
        for user_id in user_ids:
            token = self.get_fcm_token(user_id)
            if token:
                tokens.append(token)
        return tokens
    
    def mark_messages_as_seen(self, chat_id, user_id):
        """Mark all messages in a chat as seen by the user"""
        url = f"{self.database_url}/chats/{chat_id}/messages.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                messages = response.json()
                if messages:
                    for msg_id, msg_data in messages.items():
                        # Mark as seen if message is not from current user and not already seen
                        if msg_data.get('sender_id') != user_id and not msg_data.get('seen', False):
                            seen_url = f"{self.database_url}/chats/{chat_id}/messages/{msg_id}/seen.json?auth={self.auth_token}"
                            requests.put(seen_url, json=True)
            return True
        except:
            return False
    
    def store_user_token(self, user_id, email, username, refresh_token):
        """Store user refresh token in database for OTP login"""
        url = f"{self.database_url}/user_tokens/{user_id}.json?auth={self.auth_token}"
        token_data = {
            "email": email,
            "username": username,
            "refresh_token": refresh_token,
            "updated_at": int(time.time() * 1000)
        }
        
        try:
            response = requests.put(url, json=token_data)
            return response.status_code == 200
        except:
            return False
    
    def get_user_by_email(self, email):
        """Get user data by email"""
        url = f"{self.database_url}/user_tokens.json?auth={self.auth_token}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                users = response.json()
                if users:
                    for user_id, user_data in users.items():
                        if user_data.get('email') == email:
                            user_data['id'] = user_id
                            return user_data
            return None
        except:
            return None

def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

# ============================================
# LISTENER MANAGEMENT FUNCTIONS
# ============================================
def start_message_listener(chat_id, db_instance, page_ref):
    """Start a real-time listener for a chat"""
    global active_listeners
    
    with listener_lock:
        # Stop existing listener for this chat
        if chat_id in active_listeners:
            active_listeners[chat_id].stop()
        
        # Create and start new listener
        def on_new_messages(messages):
            """Callback when new messages arrive"""
            try:
                # This will be called from background thread
                # Queue it for UI thread processing
                message_queue.put({
                    'type': 'update_messages',
                    'chat_id': chat_id,
                    'messages': messages
                })
            except Exception as e:
                print(f"[CALLBACK ERROR] {e}")
        
        listener = MessageListener(chat_id, on_new_messages, db_instance)
        listener.start()
        active_listeners[chat_id] = listener
        
        print(f"[DEBUG] Listener started for chat: {chat_id}")

def stop_message_listener(chat_id):
    """Stop the listener for a chat"""
    global active_listeners
    
    with listener_lock:
        if chat_id in active_listeners:
            active_listeners[chat_id].stop()
            del active_listeners[chat_id]
            print(f"[DEBUG] Listener stopped for chat: {chat_id}")

def stop_all_listeners():
    """Stop all active listeners"""
    global active_listeners
    
    with listener_lock:
        for listener in active_listeners.values():
            listener.stop()
        active_listeners.clear()
        print("[DEBUG] All listeners stopped")

def process_message_queue_func(page_ref, display_messages_func, current_chat_ref):
    """Process queued message updates on UI thread"""
    try:
        while not message_queue.empty():
            update = message_queue.get_nowait()
            
            if update['type'] == 'update_messages':
                # Check if we're still on the same chat
                if update['chat_id'] == current_chat_ref.get('id'):
                    print(f"[QUEUE] Processing update for chat {update['chat_id']}")
                    display_messages_func(update['messages'])
                    page_ref.update()
    except queue.Empty:
        pass
    except Exception as e:
        print(f"[QUEUE ERROR] {e}")

# ============================================
# GOOGLE SHEETS MANAGER FOR PROMOTER REGISTRATION
# ============================================
def _load_gsheet_creds_json():
    """Load Google Sheets service account JSON.

    Priority:
    1) GCP_GSHEET_CREDS env var (PC / dev)
    2) assets/gsheet_creds.json inside packaged app (APK)
    """
    try:
        # 1) Environment variable
        env_val = os.environ.get("GCP_GSHEET_CREDS")
        if env_val and env_val.strip():
            print("✅ Loaded Google Sheets creds from env")
            return env_val

        # 2) Secret Manager (via secrets_util)
        secret_val = get_secret("GCP_GSHEET_CREDS")
        if secret_val and secret_val.strip():
            print("✅ Loaded Google Sheets creds from Secret Manager")
            return secret_val

        # 3) Assets file (for mobile APK)
        assets_dir = os.environ.get("FLET_ASSETS_DIR") or "assets"
        candidates = [
            os.path.join(assets_dir, "gsheet_creds.json"),
            os.path.join("assets", "gsheet_creds.json"),
            os.path.join(os.path.dirname(__file__), "assets", "gsheet_creds.json"),
        ]
        for p in candidates:
            try:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        print(f"✅ Loaded Google Sheets creds from file: {p}")
                        return f.read()
            except Exception as ex:
                print(f"⚠️ Error reading creds file {p}: {ex}")
    except Exception as e:
        print(f"⚠️ Error loading Google Sheets creds: {e}")

    print("⚠️ No Google Sheets creds found. Promoter stats disabled.")
    return ""

def _load_gsheet_sheet_id():
    """Load Google Sheets ID.

    Priority:
    1) GOOGLE_SHEET_ID env var (PC / dev)
    2) assets/gsheet_config.json inside packaged app (APK)
    """
    try:
        env_val = os.environ.get("GOOGLE_SHEET_ID")
        if env_val and env_val.strip():
            print("✅ Loaded Google Sheet ID from env")
            return env_val.strip()

        secret_val = get_secret("GOOGLE_SHEET_ID")
        if secret_val and secret_val.strip():
            print("✅ Loaded Google Sheet ID from Secret Manager")
            return secret_val.strip()

        assets_dir = os.environ.get("FLET_ASSETS_DIR") or "assets"
        candidates = [
            os.path.join(assets_dir, "gsheet_config.json"),
            os.path.join("assets", "gsheet_config.json"),
            os.path.join(os.path.dirname(__file__), "assets", "gsheet_config.json"),
        ]
        for p in candidates:
            try:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        try:
                            cfg = json.load(f)
                        except Exception as jex:
                            print(f"⚠️ Error parsing gsheet_config.json at {p}: {jex}")
                            cfg = {}
                    sid = (cfg.get("sheet_id") or "").strip()
                    if sid:
                        print(f"✅ Loaded Google Sheet ID from file: {p}")
                        return sid
            except Exception as ex:
                print(f"⚠️ Error reading sheet id file {p}: {ex}")
    except Exception as e:
        print(f"⚠️ Error loading Google Sheet ID: {e}")

    print("⚠️ No Google Sheet ID found. Promoter stats disabled.")
    return ""


class GoogleSheetsManager:
    """
    Manages Google Sheets operations for promoter registration
    Uses service account authentication
    """
    def __init__(self):
        self.client = None
        self.sheet_id = _load_gsheet_sheet_id()
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize gspread client with service account credentials"""
        try:
            # Prefer shared client that supports Secret Manager
            self.client = get_encrypted_gspread_client()
            if self.client:
                print("✅ Google Sheets client initialized via secrets_util")
                return

            import gspread
            from google.oauth2.service_account import Credentials

            # Get credentials from environment or assets
            creds_json = _load_gsheet_creds_json()
            if not creds_json:
                print("⚠️ GCP_GSHEET_CREDS not found (env or assets)")
                return

            # Parse credentials
            creds_dict = json.loads(creds_json)

            # Define required scopes
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]

            # Create credentials
            credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)

            # Initialize gspread client
            self.client = gspread.authorize(credentials)
            print("✅ Google Sheets client initialized from raw credentials")

        except Exception as e:
            print(f"❌ Google Sheets init error: {e}")
            self.client = None
    
    def verify_and_register_promoter(self, activation_key, email, upi_id):
        """
        Verify activation key and register promoter
        
        Args:
            activation_key: Activation key to verify (Column A)
            email: Promoter's email (Column C)
            upi_id: Promoter's UPI ID (Column D)
        
        Returns:
            tuple: (success: bool, message: str, referral_id: str or None)
        """
        try:
            if not self.client or not self.sheet_id:
                return False, "Google Sheets not configured", None
            
            # Open spreadsheet and worksheet
            spreadsheet = self.client.open_by_key(self.sheet_id)
            worksheet = spreadsheet.worksheet("promoters")
            
            # Get all values from worksheet
            all_values = worksheet.get_all_values()
            
            if len(all_values) < 2:  # No data rows
                return False, "Invalid activation key. Contact admin.", None
            
            # Find activation key in column A (skip header row)
            for row_idx, row in enumerate(all_values[1:], start=2):  # Start from row 2
                if len(row) >= 5:  # Ensure row has enough columns
                    key_in_sheet = row[0].strip()  # Column A
                    email_in_sheet = row[2].strip() if len(row) > 2 else ""  # Column C
                    upi_in_sheet = row[3].strip() if len(row) > 3 else ""  # Column D
                    referral_id = row[4].strip() if len(row) > 4 else ""  # Column E
                    
                    if key_in_sheet == activation_key:
                        # Check if already registered
                        if email_in_sheet or upi_in_sheet:
                            return False, "Already registered as promoter", None
                        
                        # Update email and UPI ID
                        worksheet.update_cell(row_idx, 3, email)  # Column C
                        worksheet.update_cell(row_idx, 4, upi_id)  # Column D
                        
                        print(f"✅ Promoter registered: {email} -> Referral ID: {referral_id}")
                        return True, "Registration successful", referral_id
            
            # Activation key not found
            return False, "Invalid activation key. Contact admin.", None
            
        except Exception as e:
            print(f"❌ Promoter registration error: {e}")
            return False, f"Error: {str(e)}", None
    
    def get_promoter_stats(self, referral_id):
        """
        Get promoter statistics from referral_program worksheet
        
        Args:
            referral_id: Referral ID to look up (Column E from promoters sheet)
        
        Returns:
            dict with stats or None if not found
            {
                'earnings': float,
                'paid': float,
                'pending': float,
                'installs': int,
                'subscriptions': int,
                'subscribers': list of dicts with username and date
            }
        """
        try:
            if not self.client or not self.sheet_id:
                return None
            
            # Open spreadsheet and referral_program worksheet
            spreadsheet = self.client.open_by_key(self.sheet_id)
            worksheet = spreadsheet.worksheet("referral_program")
            
            # Get all values
            all_values = worksheet.get_all_values()

            if len(all_values) < 2:
                return None

            # Map headers to indexes so we can handle column order changes
            header = [h.strip().lower() for h in all_values[0]] if all_values else []

            def find_index(possible_names, fallback_index):
                for name in possible_names:
                    if name in header:
                        return header.index(name)
                return fallback_index

            referral_idx = find_index(["referral_id", "referral id"], 4)
            installs_idx = find_index(["install_count", "install count", "installs"], 12)
            subscription_idx = find_index(["subscription_count", "subscription count", "subscriptions"], 14)
            subscribers_idx = find_index(["subscribed_users", "subscribers", "subscribed users"], 15)
            earnings_idx = find_index(["total_earnings", "total earnings", "earnings"], 16)
            paid_idx = find_index(["paid_amount", "paid amount", "paid"], 17)

            # Find referral_id in the worksheet
            for row_idx, row in enumerate(all_values[1:], start=2):
                # Check if this row matches our referral_id using the mapped column
                row_referral_id = row[referral_idx].strip() if len(row) > referral_idx else ""

                if row_referral_id == referral_id:
                    try:
                        earnings = float(row[earnings_idx]) if len(row) > earnings_idx and row[earnings_idx] else 0.0
                    except:
                        earnings = 0.0

                    try:
                        paid = float(row[paid_idx]) if len(row) > paid_idx and row[paid_idx] else 0.0
                    except:
                        paid = 0.0

                    pending = earnings - paid

                    try:
                        installs = int(row[installs_idx]) if len(row) > installs_idx and row[installs_idx] else 0
                    except:
                        installs = 0

                    try:
                        subscriptions = int(row[subscription_idx]) if len(row) > subscription_idx and row[subscription_idx] else 0
                    except:
                        subscriptions = 0

                    # Parse Subscribed_Users - supports comma or newline separated values
                    subscribers = []
                    subscribed_users_str = row[subscribers_idx] if len(row) > subscribers_idx else ""
                    print(f"🔍 Reading subscribers from index {subscribers_idx}: '{subscribed_users_str}'")

                    if subscribed_users_str:
                        user_entries = subscribed_users_str.replace("\n", ",").split(',')
                        for entry in user_entries:
                            username = entry.strip()
                            if username:  # Only add non-empty usernames
                                subscribers.append({
                                    'username': username
                                })

                    print(f"✅ Parsed {len(subscribers)} subscribers: {[s['username'] for s in subscribers]}")

                    return {
                        'earnings': earnings,
                        'paid': paid,
                        'pending': pending,
                        'installs': installs,
                        'subscriptions': subscriptions,
                        'subscribers': subscribers
                    }

            # Referral ID not found
            print(f"⚠️ Referral ID {referral_id} not found in referral_program sheet")
            return None
            
        except Exception as e:
            print(f"❌ Error fetching promoter stats: {e}")
            return None

    def _ensure_promote_referral_structure(self, worksheet, existing_headers=None):
        """Ensure promote referral sheet has Introducer ID, Activation Key, and Approval columns at the end."""
        try:
            headers = existing_headers or worksheet.row_values(1)
            headers = headers if headers else []

            normalized = []
            introducer_label = None
            activation_label = None
            approval_label = None

            for h in headers:
                hl = h.strip().lower() if h else ""
                if "introducer" in hl and not introducer_label:
                    introducer_label = h.strip() or "Introducer ID"
                    continue
                if hl == "activation key" and not activation_label:
                    activation_label = "Activation Key"
                    continue
                if "approval" in hl and not approval_label:
                    approval_label = "Approval"
                    continue
                normalized.append(h)

            if not introducer_label:
                introducer_label = "Introducer ID"
            if not activation_label:
                activation_label = "Activation Key"
            if not approval_label:
                approval_label = "Approval"

            normalized.extend([introducer_label, activation_label, approval_label])

            if len(normalized) > worksheet.col_count:
                worksheet.add_cols(len(normalized) - worksheet.col_count)

            worksheet.update('A1', [normalized])

            return normalized
        except Exception as e:
            print(f"⚠️ Failed to normalize promote referral headers: {e}")
            return existing_headers or []

    def submit_promoter_referral(self, referral_data):
        """Append promoter referral details to the 'promote referral' worksheet"""
        try:
            if not self.client or not self.sheet_id:
                return False, "Google Sheets not configured"

            spreadsheet = self.client.open_by_key(self.sheet_id)

            try:
                worksheet = spreadsheet.worksheet("promote referral")
            except Exception as e:
                print(f"ℹ️ Worksheet 'promote referral' not found. Creating new worksheet: {e}")
                worksheet = spreadsheet.add_worksheet(title="promote referral", rows=100, cols=20)
                headers = [
                    "Timestamp",
                    "Promoter Full Name",
                    "Primary Platform",
                    "Platform Profile Link",
                    "Estimated Followers / Members",
                    "Contact Email ID",
                    "Phone Number",
                    "Reason for Referral",
                    "Promotion Type",
                    "Additional Information",
                    "Introducer ID",
                    "Activation Key",
                    "Approval",
                ]
                worksheet.append_row(headers)

            headers = worksheet.row_values(1)
            headers = self._ensure_promote_referral_structure(worksheet, headers)
            header_map = [h.strip().lower() for h in headers]

            ist_timezone = timezone(timedelta(hours=5, minutes=30))
            timestamp = datetime.now(ist_timezone).strftime("%Y-%m-%d %H:%M")

            row_data = [
                "" for _ in headers
            ]

            def set_field(possible_names, value):
                for name in possible_names:
                    if name in header_map:
                        row_data[header_map.index(name)] = value
                        return

            set_field(["timestamp"], timestamp)
            set_field(["promoter full name", "full name"], referral_data.get("full_name", ""))
            set_field(["primary platform"], referral_data.get("primary_platform", ""))
            set_field(["platform profile link", "profile link"], referral_data.get("profile_link", ""))
            set_field(["estimated followers / members", "estimated followers", "followers"], referral_data.get("followers", ""))
            set_field(["contact email id", "email"], referral_data.get("email", ""))
            set_field(["phone number", "phone"], referral_data.get("phone", ""))
            set_field(["reason for referral", "referral reason"], referral_data.get("referral_reason", ""))
            set_field(["promotion type"], referral_data.get("promotion_type", ""))
            set_field(["additional information", "additional info"], referral_data.get("additional_info", ""))
            set_field(["introducer id", "referrer id", "referral id"], referral_data.get("introducer_id", ""))

            set_field(["activation key"], "")
            set_field(["approval"], "")

            worksheet.append_row(row_data)
            print(f"✅ Promoter referral saved: {row_data}")
            return True, ""

        except Exception as e:
            print(f"❌ Error submitting promoter referral: {e}")
            return False, "Failed to submit promoter referral. Please try again."

    def get_downline_data(self, introducer_id):
        """Fetch approved referred promoters and their subscription counts."""
        try:
            if not self.client or not self.sheet_id or not introducer_id:
                return None

            spreadsheet = self.client.open_by_key(self.sheet_id)

            try:
                referral_ws = spreadsheet.worksheet("promote referral")
            except Exception as e:
                print(f"❌ promote referral sheet missing: {e}")
                return None

            headers = referral_ws.row_values(1)
            headers = self._ensure_promote_referral_structure(referral_ws, headers)
            header_lower = [h.strip().lower() for h in headers]

            def idx(possible_names):
                for name in possible_names:
                    if name in header_lower:
                        return header_lower.index(name)
                return None

            intro_idx = idx(["introducer id", "introducer", "referrer id", "referral id"])
            approval_idx = idx(["approval", "approved"])
            name_idx = idx(["promoter full name", "full name", "name"])
            platform_idx = idx(["primary platform", "platform"])
            profile_idx = idx(["platform profile link", "profile link", "link"])
            email_idx = idx(["contact email id", "email", "contact email"])

            referral_rows = referral_ws.get_all_values()[1:]

            filtered_referrals = []
            for row in referral_rows:
                intro_val = row[intro_idx].strip() if intro_idx is not None and len(row) > intro_idx else ""
                approval_val = row[approval_idx].strip().lower() if approval_idx is not None and len(row) > approval_idx else ""

                if intro_val and intro_val.strip().lower() == introducer_id.strip().lower() and approval_val == "true":
                    filtered_referrals.append({
                        "name": row[name_idx].strip() if name_idx is not None and len(row) > name_idx else "",
                        "platform": row[platform_idx].strip() if platform_idx is not None and len(row) > platform_idx else "",
                        "profile_link": row[profile_idx].strip() if profile_idx is not None and len(row) > profile_idx else "",
                        "email": row[email_idx].strip() if email_idx is not None and len(row) > email_idx else "",
                    })

            if not filtered_referrals:
                return {"entries": [], "total_bonus": 0, "total_subscriptions": 0}

            try:
                promoters_ws = spreadsheet.worksheet("promoters")
                promoters_data = promoters_ws.get_all_values()
                promoters_headers = [h.strip().lower() for h in (promoters_data[0] if promoters_data else [])]
                prom_email_idx = None
                prom_referral_idx = None
                prom_subs_idx = None

                def prom_idx(names):
                    for n in names:
                        if n in promoters_headers:
                            return promoters_headers.index(n)
                    return None

                prom_email_idx = prom_idx(["email", "contact email", "contact email id"])
                prom_referral_idx = prom_idx(["referral_id", "referral id"])
                prom_subs_idx = prom_idx(["subscription_count", "subscription count", "subscriptions", "subscribers", "total subscriptions"])

                promoters_rows = promoters_data[1:] if len(promoters_data) > 1 else []
            except Exception as e:
                print(f"⚠️ Failed to load promoters sheet for downline: {e}")
                promoters_rows = []
                prom_email_idx = prom_referral_idx = prom_subs_idx = None

            referral_program_map = {}
            try:
                referral_program_ws = spreadsheet.worksheet("referral_program")
                rp_values = referral_program_ws.get_all_values()
                rp_headers = [h.strip().lower() for h in (rp_values[0] if rp_values else [])]

                def rp_idx(names, fallback=None):
                    for n in names:
                        if n in rp_headers:
                            return rp_headers.index(n)
                    return fallback

                rp_referral_idx = rp_idx(["referral_id", "referral id"], 4)
                rp_subs_idx = rp_idx(["subscription_count", "subscription count", "subscriptions"], 14)

                for rp_row in rp_values[1:]:
                    if len(rp_row) > max(rp_referral_idx or 0, rp_subs_idx or 0):
                        rid = rp_row[rp_referral_idx].strip() if rp_referral_idx is not None and len(rp_row) > rp_referral_idx else ""
                        subs_val = rp_row[rp_subs_idx] if rp_subs_idx is not None and len(rp_row) > rp_subs_idx else "0"
                        try:
                            referral_program_map[rid] = int(float(subs_val)) if subs_val else 0
                        except:
                            referral_program_map[rid] = 0
            except Exception as e:
                print(f"⚠️ Failed to load referral_program sheet for downline: {e}")

            def find_promoter_row_by_email(email):
                if not email or prom_email_idx is None:
                    return None
                for prow in promoters_rows:
                    if len(prow) > prom_email_idx and prow[prom_email_idx].strip().lower() == email.strip().lower():
                        return prow
                return None

            entries = []
            total_bonus = 0
            total_subscriptions = 0

            for ref in filtered_referrals:
                promoter_row = find_promoter_row_by_email(ref.get("email"))
                subscription_count = 0
                referral_id = ""

                if promoter_row:
                    if prom_subs_idx is not None and len(promoter_row) > prom_subs_idx:
                        try:
                            subscription_count = int(float(promoter_row[prom_subs_idx])) if promoter_row[prom_subs_idx] else 0
                        except:
                            subscription_count = 0
                    if prom_referral_idx is not None and len(promoter_row) > prom_referral_idx:
                        referral_id = promoter_row[prom_referral_idx].strip()

                if subscription_count == 0 and referral_id:
                    subscription_count = referral_program_map.get(referral_id, 0)

                bonus = math.floor(subscription_count / 10) * 100
                total_bonus += bonus
                total_subscriptions += subscription_count

                entries.append({
                    "name": ref.get("name", ""),
                    "platform": ref.get("platform", ""),
                    "profile_link": ref.get("profile_link", ""),
                    "email": ref.get("email", ""),
                    "subscription_count": subscription_count,
                    "bonus": bonus,
                })

            return {
                "entries": entries,
                "total_bonus": total_bonus,
                "total_subscriptions": total_subscriptions,
            }

        except Exception as e:
            print(f"❌ Error loading downline data: {e}")
            return None

    def assign_activation_keys_for_approved_referrals(self, introducer_id):
        """Assign activation keys to approved referrals lacking keys for a given introducer."""
        assigned = []
        try:
            if not self.client or not self.sheet_id or not introducer_id:
                return assigned

            spreadsheet = self.client.open_by_key(self.sheet_id)

            try:
                referral_ws = spreadsheet.worksheet("promote referral")
            except Exception as e:
                print(f"❌ promote referral sheet missing: {e}")
                return assigned

            referral_headers = referral_ws.row_values(1)
            referral_headers = self._ensure_promote_referral_structure(referral_ws, referral_headers)
            referral_lower = [h.strip().lower() for h in referral_headers]

            def idx(names):
                for name in names:
                    if name in referral_lower:
                        return referral_lower.index(name)
                return None

            intro_idx = idx(["introducer id", "introducer", "referrer id", "referral id"])
            approval_idx = idx(["approval", "approved"])
            activation_idx = idx(["activation key"])
            name_idx = idx(["promoter full name", "full name", "name"])

            if intro_idx is None or approval_idx is None or activation_idx is None:
                return assigned

            referral_rows = referral_ws.get_all_values()[1:]

            try:
                promoters_ws = spreadsheet.worksheet("promoters")
                promoters_rows = promoters_ws.get_all_values()
            except Exception as e:
                print(f"❌ promoters sheet missing: {e}")
                return assigned

            promoters_data_rows = promoters_rows[1:] if len(promoters_rows) > 1 else []

            def find_fresh_activation_key():
                for p_row_idx, prow in enumerate(promoters_data_rows, start=2):
                    key_val = prow[0].strip() if len(prow) > 0 else ""
                    status_val = prow[5].strip() if len(prow) > 5 else ""
                    if key_val and not status_val:
                        return key_val, p_row_idx
                return None, None

            for row_idx, row in enumerate(referral_rows, start=2):
                intro_val = row[intro_idx].strip().lower() if len(row) > intro_idx else ""
                approval_val = row[approval_idx].strip().lower() if len(row) > approval_idx else ""
                activation_val = row[activation_idx].strip() if len(row) > activation_idx else ""

                if intro_val == introducer_id.strip().lower() and approval_val == "true" and not activation_val:
                    fresh_key, promoter_row_idx = find_fresh_activation_key()

                    if not fresh_key:
                        print("No fresh activation keys available")
                        continue

                    referral_ws.update_cell(row_idx, activation_idx + 1, fresh_key)
                    promoters_ws.update_cell(promoter_row_idx, 6, "TRUE")
                    try:
                        promoters_data_rows[promoter_row_idx - 2][5] = "TRUE"
                    except Exception:
                        pass

                    assigned.append({
                        "name": row[name_idx].strip() if name_idx is not None and len(row) > name_idx else "Promoter",
                        "activation_key": fresh_key
                    })

            return assigned
        except Exception as e:
            print(f"❌ Error assigning activation keys: {e}")
            return assigned

# Initialize Google Sheets Manager
gsheet_manager = GoogleSheetsManager()

def main(page: ft.Page):
    global CREDENTIALS_FILE, CACHE_DIR, GROUP_ICON_CACHE_DIR, USER_LIST_CACHE_FILE
    
    # ============================================
    # 🔥 CRITICAL FIX: Global NaN Protection
    # ============================================
    import math
    
    def sanitize_value(value):
        """Remove NaN/Infinity from any value before passing to Flet"""
        if value is None:
            return None
        
        # Handle numbers
        if isinstance(value, (int, float)):
            if math.isnan(value) or math.isinf(value):
                return 0
            return value
        
        # Handle strings
        if isinstance(value, str):
            return value
        
        # Handle lists
        if isinstance(value, list):
            return [sanitize_value(item) for item in value]
        
        # Handle dicts
        if isinstance(value, dict):
            return {k: sanitize_value(v) for k, v in value.items()}
        
        return value
    
    # Monkey-patch Flet's update to sanitize all data
    original_update = page.update
    
    def safe_update(*args, **kwargs):  
        try:
            original_update(*args, **kwargs)  
        except Exception as e:
            error_msg = str(e)
            if "NaN" in error_msg or "encodable" in error_msg:
                print("🔥 CAUGHT NaN ERROR - Attempting recovery")
                print(f"Error: {error_msg}")
                
                # Show error to user
                page.clean()
                page.add(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.ERROR, size=60, color="red"),
                            ft.Text("Data Error Detected", size=18, weight="bold"),
                            ft.Text("Invalid numeric value found", size=14),
                            ft.Text(str(e)[:200], size=10, color="grey"),
                            ft.Container(height=20),
                            ft.ElevatedButton(
                                "Restart App",
                                on_click=lambda _: show_startup_screen(),
                                bgcolor="blue",
                                color="white"
                            )
                        ], horizontal_alignment="center", spacing=10),
                        padding=30,
                        expand=True,
                        alignment=ft.alignment.center
                    )
                )
                original_update()
            else:
                raise
    
    page.update = safe_update

    # ============================================
    # CRITICAL: Set page properties FIRST
    # ============================================
    page.title = "Chat App"
    page.padding = 0
    
    # ✅ ADD THIS: Initialize FCM on app start
    def init_fcm_on_startup():
        """Initialize FCM when app starts"""
        try:
            import time
            time.sleep(2)  # Wait for Flutter to be ready

            # Try to get token from storage
            page.client_storage.get("fcm_token")
        except Exception:
            pass
    
    # Run FCM init in background
    threading.Thread(target=init_fcm_on_startup, daemon=True).start()
    
    # ============================================
    # SHOW LOADING IMMEDIATELY (before storage)
    # ============================================
    loading_container = ft.Container(
        content=ft.Column([
            ft.ProgressRing(width=50, height=50),
            ft.Text("Initializing storage...", size=16)
        ], horizontal_alignment="center", spacing=20),
        expand=True,
        alignment=ft.alignment.center
    )
    page.add(loading_container)
    page.update()
    
    # ============================================
    # FORCE A DELAY - Let Flet/Android settle
    # ============================================
    import time
    time.sleep(1.0)  # CRITICAL: Give Android time to initialize
    
    # ============================================
    # STORAGE INITIALIZATION WITH EXTREME ERROR HANDLING
    # ============================================
    base_dir = None
    storage_error = None
    
    try:
        # Try method 1: Use client_storage_dir (Android safe)
        if hasattr(page, "client_storage_dir"):
            client_dir = getattr(page, "client_storage_dir", None)
            if client_dir and str(client_dir).strip():
                base_dir = Path(client_dir)
                print(f"✓ Method 1 - Using client_storage_dir: {base_dir}")
    except Exception as e:
        print(f"✗ Method 1 failed: {e}")
        storage_error = str(e)
    
    # Fallback method 2: Try getting from page.platform
    if base_dir is None:
        try:
            import platform
            if platform.system() == "Android":
                # Android fallback - use app's files directory
                import os
                app_files = "/data/user/0/com.flet.chat_app/files"
                if os.path.exists(app_files):
                    base_dir = Path(app_files) / ".chatapp"
                    print(f"✓ Method 2 - Using Android fallback: {base_dir}")
        except Exception as e:
            print(f"✗ Method 2 failed: {e}")
            storage_error = str(e)
    
    # Fallback method 3: Desktop/temp directory
    if base_dir is None:
        try:
            import tempfile
            temp_dir = tempfile.gettempdir()
            base_dir = Path(temp_dir) / "chatapp_data"
            print(f"✓ Method 3 - Using temp directory: {base_dir}")
        except Exception as e:
            print(f"✗ Method 3 failed: {e}")
            storage_error = str(e)
    
    # FINAL CHECK: Did we get a valid directory?
    if base_dir is None:
        print("✗✗✗ CRITICAL: All storage methods failed!")
        page.clean()
        page.add(
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.ERROR, size=80, color="red"),
                    ft.Text("STORAGE INITIALIZATION FAILED", size=18, weight="bold", color="red"),
                    ft.Text(f"Error: {storage_error or 'Unknown error'}", size=12, color="grey"),
                    ft.Text("Please contact support", size=14),
                    ft.ElevatedButton("Exit", on_click=lambda _: exit(0), bgcolor="red", color="white")
                ], horizontal_alignment="center", spacing=15),
                padding=30,
                expand=True,
                alignment=ft.alignment.center
            )
        )
        page.update()
        return  # STOP EXECUTION
    
    # ============================================
    # CREATE DIRECTORY STRUCTURE
    # ============================================
    try:
        # Create main directory
        base_dir.mkdir(parents=True, exist_ok=True)
        print(f"✓ Created base directory: {base_dir}")
        
        # Create cache directories
        cache_root = base_dir / "cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        
        profile_cache = cache_root / "profile"
        profile_cache.mkdir(parents=True, exist_ok=True)
        
        group_cache = cache_root / "group"
        group_cache.mkdir(parents=True, exist_ok=True)
        
        print("✓ All cache directories created")
        
        # Set global variables
        CREDENTIALS_FILE = base_dir / "credentials.json"
        CACHE_DIR = profile_cache
        GROUP_ICON_CACHE_DIR = group_cache
        USER_LIST_CACHE_FILE = cache_root / "users.json"
        
        # Verify we can write to these locations
        test_file = base_dir / ".test_write"
        test_file.write_text("test")
        test_file.unlink()
        
        print("✓✓✓ STORAGE FULLY INITIALIZED AND VERIFIED ✓✓✓")
        print(f"    Base: {base_dir}")
        print(f"    Credentials: {CREDENTIALS_FILE}")
        print(f"    Cache: {CACHE_DIR}")
        
    except PermissionError as pe:
        print(f"✗✗✗ PERMISSION DENIED: {pe}")
        page.clean()
        page.add(
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.LOCK, size=80, color="orange"),
                    ft.Text("PERMISSION DENIED", size=18, weight="bold"),
                    ft.Text(f"Cannot write to: {base_dir}", size=12, color="grey"),
                    ft.Text("Try reinstalling the app", size=14),
                    ft.ElevatedButton("Exit", on_click=lambda _: exit(0), bgcolor="orange", color="white")
                ], horizontal_alignment="center", spacing=15),
                padding=30,
                expand=True,
                alignment=ft.alignment.center
            )
        )
        page.update()
        return
        
    except Exception as e:
        print(f"✗✗✗ DIRECTORY CREATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        page.clean()
        page.add(
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.FOLDER_OFF, size=80, color="red"),
                    ft.Text("DIRECTORY ERROR", size=18, weight="bold"),
                    ft.Text(str(e), size=12, color="grey"),
                    ft.ElevatedButton("Exit", on_click=lambda _: exit(0), bgcolor="red", color="white")
                ], horizontal_alignment="center", spacing=15),
                padding=30,
                expand=True,
                alignment=ft.alignment.center
            )
        )
        page.update()
        return
    
    # ============================================
    # UPDATE LOADING MESSAGE
    # ============================================
    loading_container.content = ft.Column([
        ft.ProgressRing(width=50, height=50),
        ft.Text("Connecting to Firebase...", size=16)
    ], horizontal_alignment="center", spacing=20)
    page.update()
    
    # ============================================
    # INITIALIZE APP STATE (must be before Firebase)
    # ============================================
    navigation_stack = []
    db = None
    storage = None
    current_chat_id = None
    current_chat_user = None
    current_group_id = None
    is_admin = False
    user_is_group_admin = False
    current_username = None
    group_info = {}
    refresh_control = {"active": False, "thread": None}
    active_screen = {"current": None}
    uploading_files = {"status": False}
    all_groups = []
    refresh_timer = None  # UI-based auto refresh timer (group + private chat)

    current_group_id = None
    all_members_cache = []
    load_group_messages_callback = None  # Will be set when entering group chat
    upload_counter = {"count": 0}  # Counter for generating unique upload IDs
    
    # ============================================
    # UI COMPONENT DEFINITIONS
    # ============================================
    # Define UI components that will be used across multiple functions
    group_messages_list = ft.Column(scroll="auto", expand=True, spacing=10, auto_scroll=True)
    group_message_input = ft.TextField(
        hint_text="Type a message to the group...", 
        expand=True, 
        multiline=True, 
        max_lines=3,
        min_lines=1,
        height=None
    )
    group_header_text = ft.Text("", size=18, weight="bold")
    group_member_count = ft.Text("", size=12)
    group_displayed_message_ids = set()
    group_chat_header = ft.Row(spacing=10)
    
    messages_list = ft.Column(scroll="auto", expand=True, spacing=10, auto_scroll=True)
    message_input = ft.TextField(hint_text="Type a message...", expand=True, multiline=True, max_lines=3)
    chat_header = ft.Row(spacing=10)
    
    # Build private chat screen
    chat_screen = ft.Container(
        content=ft.Column([
            ft.Container(
                content=chat_header,
                padding=ft.padding.only(left=10, right=10, top=30, bottom=10),
                bgcolor="#E3F2FD"
            ),
            ft.Container(content=messages_list, padding=20, expand=True),
            ft.Container(
                content=ft.Row([
                    ft.IconButton("attach_file", on_click=lambda e: private_chat_file_picker.pick_files(), tooltip="Attach file"),
                    message_input,
                    ft.ElevatedButton("Send", bgcolor="blue", color="white", on_click=lambda e: send_message())
                ], spacing=10),
                padding=10
            )
        ], spacing=0),
        expand=True
    )
    
    # ============================================
    # INITIALIZE FIREBASE
    # ============================================
    try:
        auth = FirebaseAuth(FIREBASE_CONFIG['apiKey'])
        otp_manager = OTPManager()
        print("✓ Firebase initialized successfully")
    except Exception as e:
        print(f"✗ Firebase initialization failed: {e}")
        page.clean()
        page.add(
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.CLOUD_OFF, size=60, color="orange"),
                    ft.Text("Connection Error", size=20, weight="bold"),
                    ft.Text("Cannot connect to Firebase", size=14),
                    ft.Text("Check your internet connection", size=12, color="grey"),
                    ft.ElevatedButton("Retry", on_click=lambda e: page.window_close())
                ], horizontal_alignment="center", spacing=20),
                padding=40, 
                expand=True, 
                alignment=ft.alignment.center
            )
        )
        page.update()
        return
    
    # ============================================
    # CLEAR LOADING SCREEN - NOW START APP
    # ============================================
    page.clean()
    print("✓✓✓ ALL INITIALIZATION COMPLETE - STARTING APP ✓✓✓")
   
    def show_startup_screen():
        page.clean()
        page.add(
            ft.Container(
                content=ft.Column([
                    ft.ProgressRing(width=40, height=40),
                    ft.Text("Auto login...", size=16),
                ], horizontal_alignment="center", alignment="center", spacing=20),
                alignment=ft.alignment.center,
                expand=True
            )
        )
        page.update()
    
    def show_notification(title, message):
        """Show desktop/mobile notification"""
        try:
            # Use SnackBar for both desktop and mobile
            snack = ft.SnackBar(
                content=ft.Row([
                    ft.Icon("notifications", color="white", size=20),
                    ft.Column([
                        ft.Text(title, weight="bold", color="white", size=14),
                        ft.Text(message, color="white", size=12)
                    ], spacing=2, expand=True)
                ], spacing=10),
                bgcolor="#2196F3",
                duration=4000,
                action="View",
                action_color="white"
            )
            page.overlay.append(snack)
            snack.open = True
            page.update()
        except Exception as e:
            print(f"Notification error: {e}")
    
    def show_snackbar(message):
        try:
            snack = ft.SnackBar(content=ft.Text(message))
            page.overlay.append(snack)
            snack.open = True
            page.update()
        except:
            pass
    
    def handle_back_navigation(e=None):
        """Handle Android back button and swipe back - OPTIMIZED"""
        if len(navigation_stack) > 0:
            stop_auto_refresh()
            previous_view = navigation_stack.pop()
            previous_view()
            return True  # Indicate we handled the back action
        else:
            # Stack is empty - allow app to close
            return False
        
    # Set up back button handler
    page.on_keyboard_event = (
        lambda e: handle_back_navigation(e) if e.key == "Escape" else None
    )

    # Android hardware back button support
    try:
        page.window_prevent_close = True
        
        def on_window_event(e):
            if e.data == "close":
                # Try to navigate back first
                handled = handle_back_navigation(None)
                if not handled:
                    # Navigation stack empty, allow close
                    page.window_destroy()
        
        page.on_window_event = on_window_event
    except Exception as ex:
        print(f"Back button setup: {ex}")
    
    # Auto-login check - NON-BLOCKING VERSION
    def check_auto_login():
        """Try auto-login in background - doesn't block UI"""
        nonlocal db, storage, is_admin, current_username, user_is_group_admin, group_info
        
        credentials = CredentialsManager.load_credentials()
        if credentials and credentials.get('email') and credentials.get('refresh_token'):
            print("Attempting auto-login...")
            
            auth.email = credentials['email']
            auth.refresh_token = credentials['refresh_token']
            
            try:
                # Add timeout to prevent hanging
                import socket
                old_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(5)  # 5 second timeout
                
                if auth.refresh_id_token():
                    db = FirebaseDatabase(FIREBASE_CONFIG['databaseURL'], auth.id_token)
                    storage = FirebaseStorage(FIREBASE_CONFIG['storageBucket'], auth.id_token)
                    current_username = credentials.get('username', 'User')
                    is_admin = (auth.email == ADMIN_EMAIL)
                    
                    # Group membership will be checked when group is selected

                    
                    user_is_group_admin = False
                    
                    group_info = {}
                    print("✓ Auto-login successful")
                    show_main_menu()
                    
                    # Restore timeout
                    socket.setdefaulttimeout(old_timeout)
                    return
                
                # Restore timeout if refresh failed
                socket.setdefaulttimeout(old_timeout)
            except Exception as e:
                print(f"Auto-login failed: {e}")
        
        # If failed, show login
        CredentialsManager.clear_credentials()
        show_login_view()
        
    profile_file_picker = ft.FilePicker()
    group_icon_file_picker = ft.FilePicker()
    private_chat_file_picker = ft.FilePicker()
    group_chat_file_picker = ft.FilePicker()

    page.overlay.extend([
        profile_file_picker,
        group_icon_file_picker,
        private_chat_file_picker,
        group_chat_file_picker
    ])
        
    # OTP Views for Sign In and Sign Up
    signin_email_field = ft.TextField(
        label="Email",
        autofocus=False,
        keyboard_type=ft.KeyboardType.EMAIL
    )

    signup_email_field = ft.TextField(
        label="Email",
        autofocus=False,
        keyboard_type=ft.KeyboardType.EMAIL
    )

    signup_username_field = ft.TextField(
        label="Username",
        autofocus=False
    )

    otp_code_field = ft.TextField(
        label="Enter 6-digit OTP",
        max_length=6,
        autofocus=False,
        keyboard_type=ft.KeyboardType.NUMBER
    )
    
    pending_otp_data = {"email": None, "username": None, "is_signup": False}
    
    def resend_otp(e):
        email = pending_otp_data["email"]
        if not email:
            show_snackbar("No email found")
            return
        
        show_snackbar("Resending OTP...")
        page.update()
        
        otp = otp_manager.generate_otp()
        
        # Run in background thread
        def resend_otp_thread():
            success = otp_manager.send_otp(email, otp)
            
            if success:
                show_snackbar("OTP resent to your email!")
            else:
                show_snackbar("Failed to resend OTP. Please check your internet connection and try again.")
        
        threading.Thread(target=resend_otp_thread, daemon=True).start()
        
    def register_fcm_token():
        """Register FCM token for push notifications"""
        try:
            # Get FCM token from client storage (set by Flutter)
            fcm_token = get_fcm_token_from_file()

            if fcm_token and auth.user_id:
                db.store_fcm_token(auth.user_id, fcm_token)
        except Exception:
            pass
    
    def send_otp_for_signin(e):
        if not signin_email_field.value:
            show_snackbar("Please enter email")
            return
        
        show_snackbar("Sending OTP...")
        page.update()
        
        otp = otp_manager.generate_otp()
        
        # Run OTP sending in background thread to avoid blocking UI
        def send_otp_thread():
            success = otp_manager.send_otp(signin_email_field.value, otp)
            
            if success:
                pending_otp_data["email"] = signin_email_field.value
                pending_otp_data["username"] = None  # Will be fetched during verification
                pending_otp_data["is_signup"] = False
                show_snackbar("OTP sent to your email!")
                show_otp_verify_view()
            else:
                show_snackbar("Failed to send OTP. Please check your internet connection and try again.")
        
        threading.Thread(target=send_otp_thread, daemon=True).start()
    
    def send_otp_for_signup(e):
        if not signup_email_field.value or not signup_username_field.value:
            show_snackbar("Please fill all fields")
            return
        
        show_snackbar("Sending OTP...")
        page.update()
        
        otp = otp_manager.generate_otp()
        
        # Run OTP sending in background thread to avoid blocking UI
        def send_otp_thread():
            success = otp_manager.send_otp(signup_email_field.value, otp)
            
            if success:
                pending_otp_data["email"] = signup_email_field.value
                pending_otp_data["username"] = signup_username_field.value
                pending_otp_data["is_signup"] = True
                show_snackbar("OTP sent to your email!")
                show_otp_verify_view()
            else:
                show_snackbar("Failed to send OTP. Please check your internet connection and try again.")
        
        threading.Thread(target=send_otp_thread, daemon=True).start()
    
    def verify_otp_and_proceed(e):
        nonlocal db, storage, is_admin, current_username, user_is_group_admin, group_info
        
        if not otp_code_field.value:
            show_snackbar("Please enter OTP")
            return
        
        email = pending_otp_data["email"]
        username = pending_otp_data["username"]
        is_signup = pending_otp_data["is_signup"]
        
        if otp_manager.verify_otp(email, otp_code_field.value):
            show_snackbar("OTP verified!")
            
            if is_signup:
                # Create new account
                show_snackbar("Creating account...")
                
                # Generate a consistent password based on email (so we can recover it)
                import hashlib
                temp_password = hashlib.sha256(email.encode()).hexdigest()[:16]
                
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        success, message = auth.sign_up(email, temp_password)
                        
                        if success:
                            db = FirebaseDatabase(FIREBASE_CONFIG['databaseURL'], auth.id_token)
                            storage = FirebaseStorage(FIREBASE_CONFIG['storageBucket'], auth.id_token)
                            db.create_user_profile(auth.user_id, auth.email, username)
                            db.store_user_token(auth.user_id, auth.email, username, auth.refresh_token)
                            
                            current_username = username
                            is_admin = (auth.email == ADMIN_EMAIL)
                            user_is_group_admin = False
                            group_info = {}
                            CredentialsManager.save_credentials(auth.email, auth.refresh_token, current_username)
                            
                            show_snackbar("Account created successfully!")
                            show_main_menu()
                            return
                        else:
                            # If email exists in Firebase Auth, try to sign in instead
                            if "EMAIL_EXISTS" in message:
                                show_snackbar("Email exists, attempting sign in...")
                                success_signin, message_signin = auth.sign_in(email, temp_password)
                                
                                if success_signin:
                                    db = FirebaseDatabase(FIREBASE_CONFIG['databaseURL'], auth.id_token)
                                    storage = FirebaseStorage(FIREBASE_CONFIG['storageBucket'], auth.id_token)
                                    
                                    # Check if profile exists
                                    profile = db.get_user_profile(auth.user_id)
                                    if profile and profile.get('username'):
                                        current_username = profile['username']
                                    else:
                                        current_username = username
                                        db.create_user_profile(auth.user_id, auth.email, username)
                                    
                                    db.store_user_token(auth.user_id, auth.email, current_username, auth.refresh_token)
                                    
                                    is_admin = (auth.email == ADMIN_EMAIL)
                                    user_is_group_admin = False
                                    
                                    # Group membership will be checked when group is selected

                                    
                                    user_is_group_admin = False
                                    
                                    group_info = {}
                                    CredentialsManager.save_credentials(auth.email, auth.refresh_token, current_username)
                                    
                                    show_snackbar("Account recovered successfully!")
                                    show_main_menu()
                                    return
                                else:
                                    show_snackbar("Email exists but cannot sign in. Please delete the user from Firebase Authentication console and try again.")
                                    return
                            else:
                                show_snackbar(f"Signup failed: {message}")
                                return
                    except Exception as network_error:
                        if attempt < max_retries - 1:
                            show_snackbar(f"Connection issue, retrying... ({attempt + 1}/{max_retries})")
                            time.sleep(2)
                        else:
                            show_snackbar("Network error. Please check your internet connection and try again.")
                            return
            else:
                # Sign in existing user
                show_snackbar("Logging in...")
                page.update()
                
                # Try local credentials first (using refresh token)
                saved_creds = CredentialsManager.load_credentials()
                
                if saved_creds and saved_creds.get('email') == email:
                    auth.email = email
                    auth.refresh_token = saved_creds['refresh_token']
                    
                    if auth.refresh_id_token():
                        db = FirebaseDatabase(FIREBASE_CONFIG['databaseURL'], auth.id_token)
                        storage = FirebaseStorage(FIREBASE_CONFIG['storageBucket'], auth.id_token)
                        current_username = saved_creds['username']
                        is_admin = (auth.email == ADMIN_EMAIL)
                        
                        # Group membership will be checked when group is selected

                        
                        user_is_group_admin = False
                        
                        group_info = {}
                        show_snackbar("Login successful!")
                        show_main_menu()
                        return
                
                # If local credentials don't work, try using the consistent password
                import hashlib
                temp_password = hashlib.sha256(email.encode()).hexdigest()[:16]
                
                # Try multiple times with delay for network issues
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        show_snackbar(f"Attempting to sign in... ({attempt + 1}/{max_retries})")
                        page.update()
                        
                        success_signin, message_signin = auth.sign_in(email, temp_password)
                        
                        if success_signin:
                            db = FirebaseDatabase(FIREBASE_CONFIG['databaseURL'], auth.id_token)
                            storage = FirebaseStorage(FIREBASE_CONFIG['storageBucket'], auth.id_token)
                            
                            profile = db.get_user_profile(auth.user_id)
                            if profile and profile.get('username'):
                                current_username = profile['username']
                            else:
                                current_username = email.split('@')[0]
                                db.create_user_profile(auth.user_id, auth.email, current_username)
                            
                            db.store_user_token(auth.user_id, auth.email, current_username, auth.refresh_token)
                            
                            is_admin = (auth.email == ADMIN_EMAIL)
                            user_is_group_admin = False
                            
                            # Group membership will be checked when group is selected

                            
                            user_is_group_admin = False
                            
                            group_info = {}
                            CredentialsManager.save_credentials(auth.email, auth.refresh_token, current_username)
                            
                            show_snackbar("Login successful!")
                            show_main_menu()
                            return
                        else:
                            # Check specific error
                            if "USER_NOT_FOUND" in message_signin or "INVALID" in message_signin:
                                if attempt < max_retries - 1:
                                    show_snackbar(f"Connection issue, retrying... ({attempt + 1}/{max_retries})")
                                    time.sleep(2)
                                    continue
                                else:
                                    show_snackbar("Account not found. Please sign up first or check your connection.")
                                    time.sleep(1)
                                    show_login_view()
                                    return
                            else:
                                show_snackbar(f"Sign in error: {message_signin}")
                                return
                                
                    except Exception as network_error:
                        print(f"Network error during sign in (Attempt {attempt + 1}): {network_error}")
                        if attempt < max_retries - 1:
                            show_snackbar(f"Connection issue, retrying... ({attempt + 1}/{max_retries})")
                            time.sleep(2)
                            continue
                        else:
                            show_snackbar("Network error. Please check your internet connection and try again.")
                            time.sleep(1)
                            show_login_view()
                            return
        else:
            show_snackbar("Invalid or expired OTP")
    
    # Replace the entire show_login_view function (around line 590):
    def show_login_view():
        def clear_local_cache(e):
            try:
                CredentialsManager.clear_credentials()
                ImageCache.clear_cache()
                show_snackbar("Cache cleared! Please try logging in again.")
            except:
                show_snackbar("Failed to clear cache")
        
        navigation_stack.clear()
        page.clean()
        
        login_view = ft.Container(
            content=ft.Column([
                ft.Container(height=30),
                ft.Text("💬", size=60),
                ft.Text("Chat App", size=28, weight="bold"),
                ft.Container(height=20),
                # 🔥 FIX: Use proper tab structure without scroll conflicts
                ft.Tabs(
                    selected_index=0,
                    animation_duration=300,
                    height=400,  # 🔥 Fixed height prevents infinite scroll
                    tabs=[
                        ft.Tab(
                            text="Sign In",
                            content=ft.Container(
                                content=ft.Column([
                                    ft.Container(height=20),
                                    ft.Text("Sign in with OTP", size=18, weight="bold"),
                                    ft.Container(height=20),
                                    signin_email_field,
                                    ft.Container(height=20),
                                    ft.ElevatedButton(
                                        "Send OTP", 
                                        width=200, 
                                        on_click=send_otp_for_signin
                                    ),
                                ], 
                                horizontal_alignment="center",
                                spacing=0  # 🔥 Use Container(height=X) for spacing instead
                                ),
                                padding=20,
                                alignment=ft.alignment.top_center  # 🔥 Align to top
                            )
                        ),
                        ft.Tab(
                            text="Sign Up",
                            content=ft.Container(
                                content=ft.Column([
                                    ft.Container(height=20),
                                    ft.Text("Create new account", size=18, weight="bold"),
                                    ft.Container(height=20),
                                    signup_email_field,
                                    ft.Container(height=15),
                                    signup_username_field,
                                    ft.Container(height=20),
                                    ft.ElevatedButton(
                                        "Send OTP", 
                                        width=200, 
                                        on_click=send_otp_for_signup
                                    ),
                                ], 
                                horizontal_alignment="center",
                                spacing=0
                                ),
                                padding=20,
                                alignment=ft.alignment.top_center
                            )
                        )
                    ]
                )
            ], 
            horizontal_alignment="center",
            spacing=0  # 🔥 No spacing here either
            ),
            padding=20,
            expand=True,
            alignment=ft.alignment.center
        )
        
        page.add(login_view)
        page.update()
    
    def show_otp_verify_view():
        page.clean()
        
        # Initialize both monitors
        sms_reader = SMSReader()
        clipboard_monitor = ClipboardMonitor(page)
        
        # Status indicators
        sms_status = {"active": False, "text": "Checking..."}
        clipboard_status = {"active": False, "text": "Active"}
        
        status_text = ft.Text("", size=11, color="blue")
        
        def update_status():
            """Update status display"""
            methods = []
            if sms_status["active"]:
                methods.append("📱 SMS Auto-detect")
            if clipboard_status["active"]:
                methods.append("📋 Clipboard Monitor")
            
            if methods:
                status_text.value = f"Auto-fill enabled: {' + '.join(methods)}"
                status_text.color = "green"
            else:
                status_text.value = "Manual entry mode"
                status_text.color = "orange"
            page.update()
        
        def on_otp_detected(otp_code, source=""):
            """Called when OTP is detected from any source"""
            try:
                otp_code_field.value = otp_code
                page.update()
                show_snackbar(f"OTP detected from {source}!")
                # Auto-verify after 0.5 seconds
                time.sleep(0.5)
                verify_otp_and_proceed(None)
            except Exception as e:
                print(f"Auto-verify error: {e}")
        
        def cleanup_monitors():
            """Stop all monitors"""
            sms_reader.stop_monitoring()
            clipboard_monitor.stop_monitoring()
        
        # Start SMS monitoring (Android only)
        sms_monitoring = sms_reader.start_monitoring(lambda code: on_otp_detected(code, "SMS"))
        sms_status["active"] = sms_monitoring
        
        # Start clipboard monitoring (all platforms)
        clipboard_monitoring = clipboard_monitor.start_monitoring(lambda code: on_otp_detected(code, "clipboard"))
        clipboard_status["active"] = clipboard_monitoring
        
        # Update status display
        update_status()
        
        otp_verify_view = ft.Container(
            content=ft.Column([
                ft.Container(height=100),
                ft.Text("🔐", size=60),
                ft.Text("Verify OTP", size=28, weight="bold"),
                ft.Container(height=20),
                ft.Text(f"OTP sent to {pending_otp_data['email']}", size=14, color="grey"),
                ft.Container(height=15),
                status_text,
                ft.Container(height=5),
                ft.Text("💡 OTP will auto-fill from SMS or copied text", size=10, color="grey", italic=True),
                ft.Container(height=30),
                otp_code_field,
                ft.Container(height=20),
                ft.ElevatedButton("Verify & Continue", expand=True, on_click=verify_otp_and_proceed),
                ft.Container(height=10),
                ft.TextButton("Resend OTP", expand=True, on_click=resend_otp),
                ft.Container(height=10),
                ft.TextButton("Back to Login", expand=True, on_click=lambda e: (cleanup_monitors(), show_login_view())),
            ], horizontal_alignment="center", alignment="center"),
            padding=20,
            expand=True
        )
        
        page.add(otp_verify_view)
        page.update()
    
    def stop_auto_refresh():
        """Stop auto-refresh thread"""
        refresh_control["active"] = False
        active_screen["current"] = None 
    
    def show_main_menu():
        nonlocal current_username  # Make sure we can modify it
        
        # Safety check: Ensure current_username is a valid string, but don't override if it exists
        if current_username is None or (isinstance(current_username, str) and len(current_username) == 0):
            # Try to get from profile first
            try:
                temp_profile = db.get_user_profile(auth.user_id)
                if temp_profile and temp_profile.get('username'):
                    current_username = temp_profile['username']
                else:
                    current_username = "User"
            except:
                current_username = "User"
        elif not isinstance(current_username, str):
            current_username = "User"
        
        stop_auto_refresh()
        stop_all_listeners()  # Stop all message listeners when going to main menu
        active_screen["current"] = None
        navigation_stack.clear()
        page.clean()
        
        # ✅ ADD THIS HELPER
        def safe_int(val, default=0):
            """Convert to safe integer"""
            try:
                if val is None or val != val:  # None or NaN
                    return default
                return int(float(val))
            except:
                return default
        
        # ADD THESE CACHE TRACKING DICTIONARIES HERE:
        members_cache = {"loaded": False}
        private_chats_cache = {"loaded": False, "data": []}
        
        def safe_number(value, default=0):
            """Ensure no NaN or Infinity values"""
            import math
            
            try:
                if value is None:
                    return default
                
                # Convert to number
                if isinstance(value, str):
                    value = float(value)
                
                num_val = float(value)
                
                # Check for NaN or Infinity
                if math.isnan(num_val) or math.isinf(num_val):
                    print(f"⚠️ NaN/Inf detected: {value}, using default: {default}")
                    return default
                
                # Return appropriate type
                if isinstance(value, int) or (isinstance(value, float) and num_val.is_integer()):
                    return int(num_val)
                return num_val
                
            except (ValueError, TypeError, AttributeError) as e:
                print(f"⚠️ Invalid number: {value}, error: {e}, using default: {default}")
                return default
        
        # ADD OFFLINE INDICATOR:
        offline_banner = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CLOUD_OFF, size=16, color="white"),
                ft.Text("You're offline - showing cached data", size=12, color="white")
            ], spacing=8),
            bgcolor="orange",
            padding=10,
            visible=False  # Hidden by default
        )
        def update_offline_status():
            """Check and update offline status"""
            is_offline = not NetworkChecker.is_online()
            offline_banner.visible = is_offline
            page.update()
        
        # Check status every 10 seconds
        def monitor_connection():
            while active_screen.get("current") is None:  # While on main menu
                update_offline_status()
                time.sleep(10)
        
        threading.Thread(target=monitor_connection, daemon=True).start()
        update_offline_status()  # Check immediately
        
        # Load current user profile
        profile = db.get_user_profile(auth.user_id)
        profile_image_url = profile.get("profile_image_url") if profile else None
        
        # Ensure display_username is always a string
        if profile and isinstance(profile, dict):
            display_username = profile.get("username", current_username)
        else:
            display_username = current_username
        
        # Additional safety check
        if not display_username or not isinstance(display_username, str):
            display_username = current_username if isinstance(current_username, str) else "User"
        
        # ============================================
        # 📱 GET AND SAVE FCM TOKEN FROM FLUTTER
        # ============================================
        def save_fcm_token_to_firebase():
            """Wait for FCM token from Flutter and save to Firebase."""
            import time

            try:
                max_attempts = 15     # e.g. try for ~30 seconds
                delay_seconds = 2

                for attempt in range(1, max_attempts + 1):
                    fcm_token = get_fcm_token_from_file()

                    if fcm_token:
                        # Save token in background thread
                        def save_token():
                            success = db.save_fcm_token(auth.user_id, fcm_token)

                        threading.Thread(target=save_token, daemon=True).start()
                        return

                    time.sleep(delay_seconds)

            except Exception:
                pass

        # Save FCM token (async, doesn't block UI)
        threading.Thread(target=save_fcm_token_to_firebase, daemon=True).start()

        # ---------------- PROFILE TOP RIGHT ICON (FIXED for mobile) ----------------
        profile_avatar_ref = {"widget": None}  # Store reference for updates
        
        
        def create_profile_avatar():
            """Create profile avatar widget - works on mobile"""
            # Get first letter safely
            try:
                if display_username and isinstance(display_username, str) and len(display_username) > 0:
                    first_letter = display_username[0].upper()
                else:
                    first_letter = "U"
            except:
                first_letter = "U"
            
            # Always start with letter avatar (fast, always works)
            letter_avatar = ft.Container(
                content=ft.Container(
                    content=ft.Text(
                        first_letter, 
                        size=14, 
                        weight="bold",
                        color="white"
                    ),
                    width=36,
                    height=36,
                    bgcolor="#2196F3",
                    border_radius=18,
                    alignment=ft.alignment.center
                ),
                on_click=lambda e: show_edit_profile(),
                tooltip="Edit Profile"
            )
            
            # If we have a profile image URL, try to load it
            if profile_image_url:
                # Check cache first
                cached = ImageCache.get_cached_image(profile_image_url, "profile")
                if cached:
                    # Use cached image immediately
                    return ft.Container(
                        content=ft.Image(
                            src=cached,
                            width=36,
                            height=36,
                            fit=ft.ImageFit.COVER,
                            border_radius=18,
                            error_content=ft.Container(
                                content=ft.Text(
                                    first_letter,
                                    size=14,
                                    weight="bold",
                                    color="white"
                                ),
                                width=36,
                                height=36,
                                bgcolor="#2196F3",
                                border_radius=18,
                                alignment=ft.alignment.center
                            )
                        ),
                        on_click=lambda e: show_edit_profile(),
                        tooltip="Edit Profile"
                    )
                else:
                    # Start download in background, show letter avatar meanwhile
                    def download_and_update():
                        try:
                            import requests
                            response = requests.get(profile_image_url, timeout=3)
                            if response.status_code == 200:
                                path = ImageCache.get_cache_path(profile_image_url, "profile")
                                with open(path, "wb") as f:
                                    f.write(response.content)
                        except:
                            pass
                    
                    threading.Thread(target=download_and_update, daemon=True).start()
            
            return letter_avatar
        
        profile_avatar_ref["widget"] = create_profile_avatar()

        # ---------------- TOP BAR (CRITICAL FIX - Ensure all numeric values are safe) ----------------
       
        system_notifications = []
        unread_system_notifications = {"count": 0}
        unread_private_messages = {"count": 0}
        activate_tab_ref = {"fn": None}

        notification_badge_text = ft.Text(
            "0", size=10, color="white", weight="bold"
        )

        notification_badge_container = ft.Container(
            content=notification_badge_text,
            bgcolor="red",
            width=18,
            height=18,
            border_radius=9,
            alignment=ft.alignment.center,
            right=0,
            top=0,
            visible=False,
        )

        def update_notification_badge():
            total_unread = unread_system_notifications["count"] + unread_private_messages["count"]
            notification_badge_text.value = str(total_unread)
            notification_badge_container.visible = total_unread > 0
            if notification_badge_container.page:
                notification_badge_container.update()

        def open_notifications_dialog(e=None):
            unread_system_notifications["count"] = 0
            update_notification_badge()

            notification_items = []

            if system_notifications:
                for item in reversed(system_notifications):
                    notification_items.append(
                        ft.ListTile(
                            title=ft.Text(item.get("title", "Notification"), weight="bold"),
                            subtitle=ft.Text(item.get("message", "")),
                        )
                    )
            else:
                notification_items.append(ft.Text("No system notifications yet.", size=12, color="grey"))

            notification_items.append(ft.Divider())

            notification_items.append(
                ft.Row(
                    [
                        ft.Text(
                            f"Unread private messages: {unread_private_messages['count']}",
                            size=12,
                        ),
                        ft.TextButton(
                            "Open Private Chats",
                            on_click=lambda ev: activate_tab_ref["fn"](3) if activate_tab_ref.get("fn") else None,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )

            dialog = ft.AlertDialog(
                title=ft.Text("Notifications", size=18, weight="bold"),
                content=ft.Container(
                    content=ft.Column(notification_items, scroll="auto", width=360),
                    width=380,
                ),
                actions=[ft.TextButton("Close", on_click=lambda ev: setattr(dialog, "open", False) or page.update())],
                actions_alignment=ft.MainAxisAlignment.END,
            )

            if dialog not in page.overlay:
                page.overlay.append(dialog)
            page.dialog = dialog
            dialog.open = True
            page.update()

        notification_icon_button = ft.IconButton(
            icon=ICONS.NOTIFICATIONS,
            tooltip="Notifications",
            on_click=open_notifications_dialog,
        )

        # Allow clicks anywhere on the stack (including the badge) to open notifications
        notification_badge_container.on_click = open_notifications_dialog

        notification_icon_stack = ft.GestureDetector(
            on_tap=open_notifications_dialog,
            content=ft.Stack(
                [
                    notification_icon_button,
                    notification_badge_container,
                ],
                width=36,
                height=36,
            ),
        )

        try:
            safe_username = str(display_username) if display_username else "User"
            safe_email = str(auth.email) if auth.email else ""

            top_bar = ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(safe_username, size=15, weight="bold"),
                            ft.Text(safe_email, size=10, color="grey")
                        ],
                        spacing=0,  # ✅ Plain integer
                        expand=True
                    ),
                    ft.Row(
                        [notification_icon_stack, profile_avatar_ref["widget"]],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=10,  # ✅ Plain integer
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER
            )
        except Exception as e:
            print(f"❌ Top bar error: {e}")
            import traceback
            traceback.print_exc()
            top_bar = ft.Row([ft.Text("Menu", size=20, weight="bold")])

        # ========== HELPER FUNCTIONS (define first) ==========
    
        
        def send_message_request(user):
            """Check if chat exists, if accepted open directly, else show request dialog"""
            
            # Create chat ID
            chat_id = create_chat_id(auth.user_id, user['id'])
            
            # Check if chat already exists and is accepted
            status = db.get_chat_status(chat_id)
            requester = db.get_chat_requester(chat_id)
            if status == "rejected":
                show_snackbar("Your previous message request was rejected.")
                return

            
            if status == "accepted":
                # Chat already accepted - open directly
                show_snackbar(f"Opening chat with {user.get('username', 'User')}...")
                open_chat(user)
                return
            
            # Chat doesn't exist or is pending - show request dialog
            request_message = ft.TextField(
                label="Message",
                multiline=True,
                max_lines=3,
                hint_text="Hi! I'd like to connect with you...",
                autofocus=False,
                width=280,
                height=120
            )
            
            def send_request(e):
                if not request_message.value or not request_message.value.strip():
                    show_snackbar("Please enter a message")
                    return
                
                # Check again in case status changed
                current_status = db.get_chat_status(chat_id)
                if current_status == "accepted":
                    show_snackbar("Chat already exists!")
                    dialog.open = False
                    page.update()
                    open_chat(user)
                    return
                
                # Send first message (this creates the chat request)
                success = db.send_message(
                    chat_id,
                    auth.user_id,
                    current_username,
                    request_message.value.strip(),
                    is_admin=(is_admin or user_is_group_admin),
                    seen=False
                )
                
                if success:
                    # Set requester
                    db.set_chat_requester(chat_id, auth.user_id)
                    db.update_chat_status(chat_id, "pending")
                    
                    # Send notification
                    threading.Thread(
                        target=db.send_fcm_notification,
                        args=(
                            user['id'],
                            f"💬 Message Request from {current_username}",
                            request_message.value.strip()[:100],
                            {
                                "chat_id": chat_id,
                                "sender_id": auth.user_id,
                                "type": "message_request"
                            }
                        ),
                        daemon=True
                    ).start()
                    
                    show_snackbar("Message request sent!")
                    dialog.open = False
                    page.update()
                else:
                    show_snackbar("Failed to send request")
            
            def close_dialog(e):
                dialog.open = False
                page.update()
            
            dialog = ft.AlertDialog(
                title=ft.Text(f"Send request to {user.get('username', 'User')}"),
                content=ft.Container(
                    content=request_message,
                    width=300,
                    height=150
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=close_dialog),
                    ft.ElevatedButton(
                        "Send Request", 
                        on_click=send_request, 
                        bgcolor="#2196F3", 
                        color="white"
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END
            )
            
            page.overlay.append(dialog)
            dialog.open = True
            page.update()
        
        # ========== TAB CONTENT SCREENS ==========

        # TAB 1 → GROUP LIST (CACHE-FIRST - Fixed)
        groups_list_column = ft.Column(scroll="auto", expand=True, spacing=10)
        

        def load_groups_list(force_refresh=False):
            """Load all available groups - CACHE FIRST"""
            
            groups_list_column.controls.clear()
            
            cached_data = CacheManager.load_from_cache('groups')
            
            if cached_data and not force_refresh:
                display_groups_from_cache(cached_data)
            else:
                if not NetworkChecker.is_online():
                    groups_list_column.controls.append(
                        ft.Container(
                            content=ft.Column([
                                ft.Icon(ft.Icons.CLOUD_OFF, size=50, color="orange"),
                                ft.Text("You're offline", size=16, weight="bold"),
                                ft.Text("Connect to internet to load groups", size=12, color="grey"),
                            ], horizontal_alignment="center", spacing=10),
                            padding=40
                        )
                    )
                    page.update()
                    return
                    
                groups_list_column.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.ProgressRing(width=20, height=20),
                            ft.Text("Loading groups...", size=14)
                        ], spacing=10),
                        padding=20
                    )
                )
                page.update()
            
            def refresh_from_network():
                try:
                    if not NetworkChecker.is_online():
                        if not cached_data:
                            groups_list_column.controls.clear()
                            groups_list_column.controls.append(
                                ft.Container(
                                    content=ft.Column([
                                        ft.Icon(ft.Icons.CLOUD_OFF, size=50, color="orange"),
                                        ft.Text("You're offline", size=16, weight="bold"),
                                    ], horizontal_alignment="center", spacing=10),
                                    padding=40
                                )
                            )
                            page.update()
                        return
                    
                    all_groups_data = db.get_all_groups()
                    CacheManager.save_to_cache('groups', all_groups_data)
                    display_groups_from_cache(all_groups_data)
                    
                except Exception as e:
                    print(f"Network refresh error: {e}")
                    if not cached_data:
                        groups_list_column.controls.clear()
                        groups_list_column.controls.append(
                            ft.Container(content=ft.Text("Error loading groups", color="red"), padding=20)
                        )
                        page.update()
            
            threading.Thread(target=refresh_from_network, daemon=True).start()

        def display_groups_from_cache(groups_data):
            """Display groups from cached data"""
            try:
                groups_list_column.controls.clear()
                
                if not isinstance(groups_data, list):
                    groups_data = []
                
                if not groups_data or len(groups_data) == 0:
                    groups_list_column.controls.append(
                        ft.Container(
                            content=ft.Column([
                                ft.Icon(ft.Icons.GROUP_ADD, size=60, color="grey"),
                                ft.Text("No groups yet", size=16, color="grey"),
                                ft.Text("Admin can create groups from Settings", size=12, color="grey")
                            ], horizontal_alignment="center", spacing=10),
                            padding=40
                        )
                    )
                    page.update()
                    return
                
                for group in groups_data:
                    group_id = group.get('id')
                    group_name = group.get('name', 'Unnamed Group')
                    group_desc = group.get('description', '')
                    group_icon_url = group.get('icon_url')
                    group_icon_emoji = group.get('icon', '👥')
                    member_count = group.get('member_count', 0)
                    
                    if group_icon_url:
                        cached_icon = ImageCache.get_cached_image(group_icon_url, "group")
                        if cached_icon:
                            group_icon_widget = ft.Image(
                                src=cached_icon, width=50, height=50, 
                                fit=ft.ImageFit.COVER, border_radius=25
                            )
                        else:
                            group_icon_widget = ft.Text(group_icon_emoji, size=32)
                            ImageCache.download_image(group_icon_url, None, "group")
                    else:
                        group_icon_widget = ft.Text(group_icon_emoji, size=32)
                    
                    group_card = ft.Container(
                        content=ft.Row([
                            group_icon_widget,
                            ft.Column([
                                ft.Text(group_name, size=16, weight="bold"),
                                ft.Text(f"{member_count} members", size=12, color="grey"),
                                ft.Text((group_desc[:50] + "...") if len(group_desc) > 50 else group_desc, 
                                       size=11, color="grey")
                            ], spacing=2, expand=True),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, color="grey")
                        ], spacing=15),
                        padding=15,
                        border=ft.border.all(1, "#E0E0E0"),
                        border_radius=10,
                        on_click=lambda e, gid=group_id: open_specific_group_chat(gid)
                    )
                    
                    groups_list_column.controls.append(group_card)
                
                page.update()
                
            except Exception as e:
                print(f"Display error: {e}")
                import traceback
                traceback.print_exc()
                
        def open_group_chat_by_id(group_id):
            """Compatibility wrapper: route to the new specific-group system."""
            return open_specific_group_chat(group_id)
    
        def show_group_chat_screen(group_id, group_info_data, members, user_is_admin_in_group):
            """Compatibility wrapper: route to the new specific-group chat screen."""
            return show_specific_group_chat(group_id, group_info_data, members, user_is_admin_in_group)
    
        def load_group_messages_by_id(group_id):
            """Compatibility wrapper: route to the new specific-group message loader."""
            return load_specific_group_messages(group_id)
    
        def auto_refresh_group_messages_by_id(group_id):
            """Compatibility wrapper: route to the new specific-group auto-refresh loop."""
            return auto_refresh_specific_group_messages(group_id)
    
        def open_specific_group_chat(group_id):
            """Open a specific group chat"""
            
            nonlocal current_group_id
            current_group_id = group_id
            
            # Check if this is the old default group
            # Load group info for new groups
            group_info_data = db.get_group_info_by_id(group_id)
            members = db.get_group_members_by_id(group_id)
            
            # Check if user is member
            is_member = any(m['id'] == auth.user_id for m in members)
            
            if not is_member:
                show_snackbar("You are not a member of this group")
                return
            
            # Check if user is admin of this group
            user_is_group_admin_check = False
            for member in members:
                if member['id'] == auth.user_id:
                    user_is_group_admin_check = member.get('is_admin', False)
                    break
            
            # Show group chat
            show_specific_group_chat(group_id, group_info_data, members, user_is_group_admin_check)


        def show_specific_group_chat(group_id, group_info_data, members, user_is_admin_in_group):
            """Show chat screen for a specific group"""
            nonlocal current_group_id, group_info, user_is_group_admin
            
            active_screen["current"] = "group_chat"
            current_group_id = group_id
            user_is_group_admin = user_is_admin_in_group
            
            navigation_stack.clear()
            navigation_stack.append(show_main_menu)
            
            # Build group header
            group_icon_widget = None
            if group_info_data.get('icon_url'):
                cached_icon = ImageCache.get_cached_image(group_info_data['icon_url'], "group")
                if cached_icon:
                    group_icon_widget = ft.Image(src=cached_icon, width=40, height=40, fit=ft.ImageFit.COVER, border_radius=20)
                else:
                    group_icon_widget = ft.Text(group_info_data.get('icon', '👥'), size=30)
            else:
                group_icon_widget = ft.Text(group_info_data.get('icon', '👥'), size=30)
            
            group_header_text.value = f"{group_info_data.get('name', 'Group')}"
            group_member_count.value = f"{len(members)} members"
            
            # Show group info dialog function
            def show_group_info_dialog(e):
                members_preview = ft.Column(spacing=5)
                for member in members[:15]:
                    uname = member.get("username", "User")
                    is_admin_badge = " 👑" if member.get("is_admin") else ""
                    members_preview.controls.append(
                        ft.Text(f"• {uname}{is_admin_badge}", size=13)
                    )
                
                if len(members) > 15:
                    members_preview.controls.append(
                        ft.Text(f"... and {len(members) - 15} more", size=12, color="grey", italic=True)
                    )
                
                # Admin buttons
                admin_buttons = []
                if is_admin or user_is_group_admin:
                    # Edit group info
                    admin_buttons = [
                        ft.Container(height=15),
                        ft.ElevatedButton(
                            "✏️ Edit Group Info",
                            on_click=lambda e: (setattr(dialog, 'open', False), page.update(), show_edit_specific_group_info(group_id)),
                            bgcolor="#FF9800",
                            color="white"
                        ),
                        ft.Container(height=10),
                        ft.ElevatedButton(
                            "👥 Manage Members",
                            on_click=lambda e: (setattr(dialog, 'open', False), page.update(), show_specific_group_management(group_id)),
                            bgcolor="#9C27B0",
                            color="white"
                        ),
                        ft.Container(height=10),
                    ]

                    # Leave group button (any member can leave)
                    def confirm_leave_group_from_info(e):
                        def do_leave(ev):
                            confirm_dialog.open = False
                            page.update()
                            ok = db.remove_member_from_group(group_id, auth.user_id)
                            if ok:
                                show_snackbar("You left the group")
                                show_main_menu()
                            else:
                                show_snackbar("Failed to leave group")

                        def cancel(ev):
                            confirm_dialog.open = False
                            page.update()

                        confirm_dialog = ft.AlertDialog(
                            title=ft.Text("Leave group?", size=18, weight="bold"),
                            content=ft.Text(
                                "You will be removed from this group.",
                                size=14,
                            ),
                            actions=[
                                ft.TextButton("Cancel", on_click=cancel),
                                ft.ElevatedButton("Leave", on_click=do_leave, bgcolor="red", color="white"),
                            ],
                            actions_alignment=ft.MainAxisAlignment.END,
                        )
                        page.dialog = confirm_dialog
                        confirm_dialog.open = True
                        page.update()

                    admin_buttons.append(
                        ft.ElevatedButton(
                            "🚪 Leave Group",
                            on_click=confirm_leave_group_from_info,
                        )
                    )

                    # Delete group button (only for admins)
                    def confirm_delete_group_from_info(e):
                        print(f"[DEBUG] Delete Group button clicked in Group Info for group_id={group_id}")
                        ok = db.delete_group_by_id(group_id)
                        print(f"[DEBUG] delete_group_by_id returned {ok} in Group Info")
                        if ok:
                            show_snackbar("Group deleted")
                            CacheManager.save_to_cache('groups', [])
                            show_main_menu()
                        else:
                            show_snackbar("Failed to delete group")

                    admin_buttons.append(
                        ft.ElevatedButton(
                            "🗑 Delete Group",
                            on_click=confirm_delete_group_from_info,
                        )
                    )
                dialog = ft.AlertDialog(
                    title=ft.Text("Group Info"),
                    content=ft.Container(
                        content=ft.Column([
                            ft.Container(
                                content=group_icon_widget if group_info_data.get('icon_url') else ft.Text(group_info_data.get('icon', '👥'), size=50),
                                alignment=ft.alignment.center
                            ),
                            ft.Container(height=10),
                            ft.Text(group_info_data.get("name", "Group"), size=20, weight="bold", text_align="center"),
                            ft.Text(group_info_data.get("description", ""), size=13, color="grey", text_align="center"),
                            ft.Container(height=15),
                            ft.Text(f"{len(members)} Members", size=15, weight="bold"),
                            ft.Container(height=5),
                            ft.Container(
                                content=members_preview,
                                height=200,
                                padding=10,
                                border=ft.border.all(1, "#E0E0E0"),
                                border_radius=8
                            ),
                            *admin_buttons
                        ], horizontal_alignment="center", scroll="auto"),
                        width=350,
                        height=500
                    ),
                    actions=[
                        ft.TextButton("Close", on_click=lambda e: (setattr(dialog, 'open', False), page.update()))
                    ]
                )
                
                page.overlay.append(dialog)
                dialog.open = True
                page.update()
            
            # Update header
            group_chat_header.controls.clear()
            group_chat_header.controls.extend([
                ft.IconButton(ft.Icons.ARROW_BACK, on_click=back_to_main_menu),
                ft.Container(
                    content=ft.Row([
                        group_icon_widget,
                        ft.Column([group_header_text, group_member_count], spacing=2, expand=True)
                    ], spacing=10),
                    on_click=show_group_info_dialog,
                    expand=True
                ),
                ft.IconButton(
                    icon=ft.Icons.INFO_OUTLINE,
                    on_click=show_group_info_dialog,
                    tooltip="Group Info"
                )
            ])
            group_messages_list.controls.clear()
            group_displayed_message_ids.clear()
            
            page.clean()
            page.add(group_chat_screen)
            
            # Set the callback so file uploads can refresh messages
            nonlocal load_group_messages_callback
            load_group_messages_callback = lambda: load_specific_group_messages(group_id)
            
            # Load messages for this specific group
            load_specific_group_messages(group_id)
            
            # Start real-time listener for this group
            start_message_listener(group_id, db, page)
            print(f"[DEBUG] Started listener for group chat: {group_id}")
            


        def load_specific_group_messages(group_id):
            """Load messages for a specific group (always rebuild UI)"""
            try:
                messages = db.get_group_messages_by_id(group_id)

                # Always rebuild the message list to avoid stale / empty UI when re-entering
                group_displayed_message_ids.clear()
                group_messages_list.controls.clear()

                if not messages:
                    group_messages_list.controls.append(
                        ft.Container(content=ft.Text("No messages yet. Start the conversation!"), padding=20)
                    )
                else:
                    for msg in messages:
                        is_me = msg['sender_id'] == auth.user_id
                        is_msg_admin = msg.get('is_admin', False)
                        timestamp = datetime.fromtimestamp(msg['timestamp'] / 1000)
                        time_str = timestamp.strftime('%I:%M %p')

                        sender_name = msg.get('sender_username', 'Unknown')

                        # Coloring
                        if is_me and is_msg_admin:
                            bg_color = '#FFD54F'
                        elif is_msg_admin:
                            bg_color = '#FFF176'
                        elif is_me:
                            bg_color = '#BBDEFB'
                        else:
                            bg_color = '#E0E0E0'

                        message_content = []

                        if not is_me:
                            admin_badge = ft.Container(
                                content=ft.Text('ADMIN', size=10, color='white', weight='bold'),
                                bgcolor='#F44336',
                                visible=is_msg_admin,
                                padding=3,
                                border_radius=5,
                            )
                            title_row = ft.Row(
                                [
                                    ft.Text(sender_name, size=13, weight='bold'),
                                    admin_badge,
                                ],
                                spacing=5,
                            )
                            message_content.append(title_row)


                        # Main text
                        if msg.get('text'):
                            message_content.append(ft.Text(msg['text'], size=14))

                        # File attachment (image or other)
                        if msg.get('file_url') and msg.get('file_name'):
                            file_url = msg['file_url']
                            file_name = msg['file_name']

                            is_image = any(file_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'])

                            if is_image:
                                image_preview = ft.Image(
                                    src=file_url,
                                    width=250,
                                    fit=ft.ImageFit.CONTAIN,
                                    border_radius=10
                                )
                                message_content.append(
                                    ft.Container(
                                        content=image_preview,
                                        on_click=lambda e, url=file_url, name=file_name: show_image_fullscreen(url, name)
                                    )
                                )
                            else:
                                file_button = ft.ElevatedButton(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.ATTACH_FILE),
                                        ft.Text(file_name, size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
                                    ], spacing=5),
                                    on_click=lambda e, url=file_url, name=file_name: download_file(url, name)
                                )
                                message_content.append(file_button)

                        # Time
                        message_content.append(ft.Text(time_str, size=10, color='grey'))

                        message_card = ft.Container(
                            content=ft.Column(message_content, spacing=3),
                            bgcolor=bg_color,
                            padding=10,
                            border_radius=10,
                            margin=ft.margin.only(top=5, bottom=5, left=10, right=10),
                            alignment=ft.alignment.center_left if not is_me else ft.alignment.center_right
                        )

                        row = ft.Row(
                            controls=[message_card],
                            alignment=ft.MainAxisAlignment.END if is_me else ft.MainAxisAlignment.START
                        )
                        group_messages_list.controls.append(row)

                page.update()
            except Exception as ex:
                print(f"Error loading group messages: {ex}")
        
        def process_group_message_queue(group_id):
            """Process queued message updates for group chat"""
            try:
                while not message_queue.empty():
                    update = message_queue.get_nowait()
                    
                    if update['type'] == 'update_messages':
                        # Check if we're still on the same group
                        if update['chat_id'] == group_id and active_screen["current"] == "group_chat":
                            print(f"[QUEUE] Processing update for group {update['chat_id']}")
                            load_specific_group_messages(group_id)
            except queue.Empty:
                pass
            except Exception as e:
                print(f"[GROUP QUEUE ERROR] {e}")
        
        def auto_refresh_specific_group_messages(group_id):
            """Auto-refresh messages for a specific group using queue"""
            while refresh_control["active"]:
                try:
                    # Process message queue instead of reloading
                    process_group_message_queue(group_id)
                    time.sleep(0.5)
                except:
                    pass

        def show_group_management_screen(group_id):
            """Compatibility wrapper: route to the new specific-group management screen."""
            return show_specific_group_management(group_id)
    
        def show_edit_specific_group_info(group_id):
            """Edit info for a specific group"""
            stop_auto_refresh()
            navigation_stack.append(lambda e: open_specific_group_chat(group_id))
            
            # Get current group info
            group_info_data = db.get_group_info_by_id(group_id)
            if not group_info_data:
                show_snackbar("Failed to load group info")
                return
            
            # Input fields
            group_name_field = ft.TextField(
                label="Group Name",
                value=group_info_data.get('name', ''),
                border_color="blue",
                width=300
            )
            
            group_desc_field = ft.TextField(
                label="Description",
                value=group_info_data.get('description', ''),
                border_color="blue",
                multiline=True,
                min_lines=2,
                max_lines=4,
                width=300
            )
            
            group_category_dropdown = ft.Dropdown(
                label="Category",
                width=300,
                options=[
                    ft.dropdown.Option("None"),
                    ft.dropdown.Option("Bronze"),
                    ft.dropdown.Option("Gold"),
                    ft.dropdown.Option("Platinum"),
                ],
                value=group_info_data.get('category', 'None')
            )
            
            # Profile picture upload
            current_icon = group_info_data.get('icon', '👥')
            group_pic_url = group_info_data.get('icon_url', '')
            profile_pic_display = ft.Container(
                content=ft.Image(src=group_pic_url, width=100, height=100, fit=ft.ImageFit.COVER, border_radius=50) if group_pic_url else ft.Text(current_icon, size=60),
                width=100,
                height=100,
                border_radius=50,
                bgcolor="#E3F2FD"
            )
            
            uploaded_pic_url = [group_pic_url]  # Use list to store mutable reference
            
            def on_pic_selected(e: ft.FilePickerResultEvent):
                if e.files and len(e.files) > 0:
                    file = e.files[0]
                    
                    if file.size > 5 * 1024 * 1024:  # 5MB limit
                        show_snackbar("Image too large! Max: 5MB")
                        return
                    
                    # Upload in background
                    def upload_pic():
                        try:
                            with open(file.path, 'rb') as f:
                                file_data = f.read()
                            
                            file_path = f"group_icons/{group_id}_{int(time.time())}.jpg"
                            success, result = storage.upload_file(file_path, file.name, file_data)
                            
                            if success:
                                uploaded_pic_url[0] = result
                                profile_pic_display.content = ft.Image(src=result, width=100, height=100, fit=ft.ImageFit.COVER, border_radius=50)
                                page.update()
                                show_snackbar("Profile picture uploaded!")
                            else:
                                show_snackbar(f"Upload failed: {result}")
                        except Exception as ex:
                            show_snackbar(f"Upload error: {str(ex)}")
                    
                    threading.Thread(target=upload_pic, daemon=True).start()
            
            pic_picker = ft.FilePicker(on_result=on_pic_selected)
            page.overlay.append(pic_picker)
            
            def save_changes(e):
                if not group_name_field.value or not group_name_field.value.strip():
                    show_snackbar("Group name cannot be empty!")
                    return
                
                # Save to database (keep existing icon)
                success = db.update_group_info_by_id(
                    group_id,
                    group_name_field.value.strip(),
                    group_desc_field.value.strip(),
                    group_info_data.get('icon', '👥'),  # Keep existing icon
                    uploaded_pic_url[0] if uploaded_pic_url[0] else None,
                    group_category_dropdown.value or "None"
                )
                
                if success:
                    show_snackbar("Group info updated!")
                    # Go back to group chat
                    open_specific_group_chat(group_id)
                else:
                    show_snackbar("Failed to update group info")
            
            def delete_group_confirm(e):
                """Show confirmation dialog before deleting group"""
                def do_delete(e):
                    dialog.open = False
                    page.update()
                    
                    # Delete the group
                    success = db.delete_group_by_id(group_id)
                    if success:
                        show_snackbar("Group deleted successfully")
                        show_main_menu()  # Go back to main menu
                    else:
                        show_snackbar("Failed to delete group")
                
                def cancel_delete(e):
                    dialog.open = False
                    page.update()
                
                dialog = ft.AlertDialog(
                    title=ft.Text("Delete Group?", size=20, weight="bold"),
                    content=ft.Text(
                        f"Are you sure you want to delete '{group_info_data.get('name', 'this group')}'?\n\n"
                        "This will remove all messages and cannot be undone!",
                        size=14
                    ),
                    actions=[
                        ft.TextButton("Cancel", on_click=cancel_delete),
                        ft.ElevatedButton(
                            "Delete", 
                            on_click=do_delete,
                            bgcolor="red",
                            color="white"
                        )
                    ],
                    actions_alignment=ft.MainAxisAlignment.END
                )
                
                page.overlay.append(dialog)
                dialog.open = True
                page.update()
            
            edit_screen = ft.Container(
                content=ft.Column([
                    ft.Container(
                        content=ft.Row([
                            ft.IconButton("arrow_back", on_click=lambda e: handle_back_navigation(e)),
                            ft.Text("Edit Group Info", size=24, weight="bold", expand=True)
                        ], alignment="spaceBetween"),
                        padding=ft.padding.only(left=20, right=20, top=40, bottom=20),
                        bgcolor="#E3F2FD"
                    ),
                    ft.Container(
                        content=ft.Column([
                            # Profile Picture Section
                            ft.Text("Group Profile Picture", size=18, weight="bold"),
                            profile_pic_display,
                            ft.ElevatedButton(
                                "Upload Picture",
                                icon=ft.Icons.UPLOAD,
                                on_click=lambda e: pic_picker.pick_files(allow_multiple=False, allowed_extensions=["jpg", "jpeg", "png"]),
                                bgcolor="#2196F3",
                                color="white"
                            ),
                            ft.Container(height=20),
                            
                            # Name and Description
                            group_name_field,
                            ft.Container(height=10),
                            group_desc_field,
                            ft.Container(height=10),
                            
                            # Category Dropdown
                            group_category_dropdown,
                            ft.Container(height=30),
                            
                            # Save Button
                            ft.ElevatedButton(
                                "Save Changes",
                                on_click=save_changes,
                                bgcolor="green",
                                color="white",
                                width=300
                            ),
                            
                            ft.Container(height=40),
                            ft.Divider(),
                            ft.Container(height=20),
                            
                            # Delete Group Section
                            ft.Text("Danger Zone", size=18, weight="bold", color="red"),
                            ft.Text("Deleting the group will remove all messages permanently", size=12, color="grey"),
                            ft.Container(height=10),
                            ft.ElevatedButton(
                                "🗑️ Delete Group",
                                on_click=delete_group_confirm,
                                bgcolor="red",
                                color="white",
                                width=300
                            )
                        ], horizontal_alignment="center", scroll="auto"),
                        padding=20,
                        expand=True
                    )
                ], spacing=0),
                expand=True
            )
            
            page.clean()
            page.add(edit_screen)
            page.update()



        def show_specific_group_management(group_id):
            """Manage members for a specific group (new system)"""
            # Stop any running group auto-refresh while we are on the management screen
            stop_auto_refresh()

            # When user presses back (hardware / ESC), go back to this group's chat
            navigation_stack.append(lambda e=None: open_specific_group_chat(group_id))

            # Fetch current members from database
            try:
                members = db.get_group_members_by_id(group_id) or []
            except Exception as ex:
                print(f"Error getting group members: {ex}")
                members = []

            members_column = ft.Column(scroll="auto", expand=True, spacing=5)

            def reload_members():
                """Reload member list from DB and refresh UI"""
                nonlocal members
                try:
                    members = db.get_group_members_by_id(group_id) or []
                except Exception as ex:
                    print(f"Error refreshing members: {ex}")
                build_members_ui()

            def build_members_ui():
                members_column.controls.clear()

                if not members:
                    members_column.controls.append(
                        ft.Container(
                            content=ft.Text("No members in this group.", size=14, color="grey"),
                            padding=20
                        )
                    )
                else:
                    for member in members:
                        uname = member.get("username", "User")
                        uid = member.get("id", "unknown_id")
                        is_admin_member = member.get("is_admin", False)

                        role_chip = ft.Container(
                            content=ft.Text(
                                "ADMIN" if is_admin_member else "MEMBER",
                                size=10,
                                color="white"
                            ),
                            bgcolor="#388E3C" if is_admin_member else "#616161",
                            padding=ft.padding.symmetric(horizontal=8, vertical=2),
                            border_radius=10
                        )

                        actions = []

                        # Only group admins or global admins can manage others
                        if user_is_group_admin or is_admin:
                            if uid != auth.user_id:
                                # Toggle admin button
                                def make_toggle_admin_handler(target_id, current_is_admin):
                                    def handler(e):
                                        new_val = not current_is_admin
                                        success = db.toggle_admin_in_group(group_id, target_id, new_val)
                                        if success:
                                            show_snackbar("Admin status updated")
                                            reload_members()
                                        else:
                                            show_snackbar("Failed to update admin status")
                                    return handler

                                toggle_admin_btn = ft.TextButton(
                                    "Make Admin" if not is_admin_member else "Remove Admin",
                                    on_click=make_toggle_admin_handler(uid, is_admin_member),
                                )

                                # Remove member button
                                def make_remove_handler(target_id, target_name):
                                    def handler(e):
                                        def do_remove(ev):
                                            confirm_dialog.open = False
                                            page.update()
                                            ok = db.remove_member_from_group(group_id, target_id)
                                            if ok:
                                                show_snackbar(f"Removed {target_name} from group")
                                                reload_members()
                                            else:
                                                show_snackbar("Failed to remove member")

                                        def cancel(ev):
                                            confirm_dialog.open = False
                                            page.update()

                                        confirm_dialog = ft.AlertDialog(
                                            title=ft.Text("Remove member?", size=18, weight="bold"),
                                            content=ft.Text(
                                                f"Remove {target_name} from this group? They will lose access to messages.",
                                                size=14
                                            ),
                                            actions=[
                                                ft.TextButton("Cancel", on_click=cancel),
                                                ft.ElevatedButton("Remove", on_click=do_remove, bgcolor="red", color="white"),
                                            ],
                                            actions_alignment=ft.MainAxisAlignment.END,
                                        )
                                        page.dialog = confirm_dialog
                                        confirm_dialog.open = True
                                        page.update()
                                    return handler

                                remove_btn = ft.TextButton(
                                    "Remove",
                                    on_click=make_remove_handler(uid, uname),
                                )

                                actions.extend([toggle_admin_btn, remove_btn])

                        members_column.controls.append(
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.CircleAvatar(content=ft.Text(uname[:1].upper())),
                                        ft.Column(
                                            [
                                                ft.Text(uname, size=14, weight="bold"),
                                                ft.Text(uid, size=11, color="grey"),
                                            ],
                                            spacing=0,
                                            expand=True,
                                        ),
                                        role_chip,
                                        *actions,
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                padding=10,
                                border=ft.border.all(1, "#E0E0E0"),
                                border_radius=8,
                            )
                        )

                page.update()

            # Build initial members list
            build_members_ui()

            # "Leave group" + "Delete group" (danger zone)
            danger_controls = []

            # Leave group button (any member)
            def confirm_leave_group(e):
                def do_leave(ev):
                    dialog.open = False
                    page.update()
                    ok = db.remove_member_from_group(group_id, auth.user_id)
                    if ok:
                        show_snackbar("You left the group")
                        # Go back to main menu; groups list will update on next open
                        show_main_menu()
                    else:
                        show_snackbar("Failed to leave group")

                def cancel(ev):
                    dialog.open = False
                    page.update()

                dialog = ft.AlertDialog(
                    title=ft.Text("Leave group?", size=18, weight="bold"),
                    content=ft.Text("Are you sure you want to leave this group?", size=14),
                    actions=[
                        ft.TextButton("Cancel", on_click=cancel),
                        ft.ElevatedButton("Leave", on_click=do_leave, bgcolor="red", color="white"),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                page.dialog = dialog
                dialog.open = True
                page.update()

            danger_controls.append(
                ft.ElevatedButton(
                    "🚪 Leave Group",
                    on_click=confirm_leave_group,
                    bgcolor="#FF7043",
                    color="white",
                    width=250,
                )
            )

            # Delete group only for admins
            if user_is_group_admin or is_admin:
                def confirm_delete_group(e):
                    def do_delete(ev):
                        dialog.open = False
                        page.update()
                        ok = db.delete_group_by_id(group_id)
                        if ok:
                            show_snackbar("Group deleted")
                            show_main_menu()
                        else:
                            show_snackbar("Failed to delete group")

                    def cancel(ev):
                        dialog.open = False
                        page.update()

                    dialog = ft.AlertDialog(
                        title=ft.Text("Delete group?", size=18, weight="bold"),
                        content=ft.Text(
                            "This will remove all messages and cannot be undone.",
                            size=14,
                        ),
                        actions=[
                            ft.TextButton("Cancel", on_click=cancel),
                            ft.ElevatedButton("Delete", on_click=do_delete, bgcolor="red", color="white"),
                        ],
                        actions_alignment=ft.MainAxisAlignment.END,
                    )
                    page.dialog = dialog
                    dialog.open = True
                    page.update()

                danger_controls.append(
                    ft.ElevatedButton(
                        "🗑️ Delete Group",
                        on_click=confirm_delete_group,
                        bgcolor="red",
                        color="white",
                        width=250,
                    )
                )

            # Header with back button
            header = ft.Container(
                content=ft.Row(
                    [
                        ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: handle_back_navigation(e)),
                        ft.Text("Manage Members", size=20, weight="bold"),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
                padding=ft.padding.only(left=10, right=10, top=30, bottom=10),
                bgcolor="#E3F2FD",
            )

            danger_section = ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Danger Zone", size=16, weight="bold", color="red"),
                        ft.Text(
                            "Leave the group or delete it completely.",
                            size=12,
                            color="grey"
                        ),
                        ft.Container(height=10),
                        *danger_controls,
                    ],
                    spacing=6,
                ),
                padding=10,
            )

            manage_screen = ft.Container(
                content=ft.Column(
                    [
                        header,
                        ft.Container(content=members_column, expand=True, padding=10),
                        danger_section,
                    ],
                    expand=True,
                ),
                expand=True,
            )

            page.clean()
            page.add(manage_screen)
            page.update()

        # =============================================
        # =============================================
        # TAB 0: PROMOTER REGISTRATION & DASHBOARD
        # =============================================
        
        # Check if user is already registered as promoter
        promoter_status = profile.get("promoter_status", {}) if profile else {}
        is_registered_promoter = promoter_status.get("registered", False)
        promoter_referral_id = promoter_status.get("referral_id", "")
        
        # State for showing registration form
        show_registration_form = {"visible": False}

        # Stats container (will be updated when stats are loaded)
        stats_container = ft.Column([], spacing=10)

        # Refer a Promoter form fields
        promoter_full_name_field = ft.TextField(label="Promoter Full Name", width=420, autofocus=True)
        primary_platform_dropdown = ft.Dropdown(
            label="Primary Platform (where you have most followers)",
            options=[
                ft.dropdown.Option("YouTube"),
                ft.dropdown.Option("Instagram"),
                ft.dropdown.Option("Telegram"),
                ft.dropdown.Option("WhatsApp"),
                ft.dropdown.Option("Facebook"),
                ft.dropdown.Option("TikTok"),
                ft.dropdown.Option("Twitter (X)"),
                ft.dropdown.Option("Other"),
            ],
            width=420,
        )
        platform_profile_link_field = ft.TextField(
            label="Platform Profile Link",
            hint_text="https://instagram.com/username",
            width=420,
        )
        estimated_followers_field = ft.TextField(
            label="Estimated Followers / Members",
            keyboard_type=ft.KeyboardType.NUMBER,
            width=420,
        )
        contact_email_field = ft.TextField(label="Contact Email ID", width=420)
        phone_number_field = ft.TextField(label="Phone Number (Optional)", width=420)
        referral_reason_field = ft.TextField(
            label="Why are you referring this promoter?",
            multiline=True,
            min_lines=3,
            width=420,
        )
        promotion_type_options = [
            "YouTube Review",
            "Short Video / Reel",
            "Telegram Promotion",
            "WhatsApp Group",
            "Instagram Story",
            "Paid Ads",
            "Other",
        ]
        promotion_type_checkboxes = [
            ft.Checkbox(label=option, value=False) for option in promotion_type_options
        ]
        additional_info_field = ft.TextField(
            label="Additional Information (Optional)",
            multiline=True,
            min_lines=2,
            width=420,
        )

        def reset_referral_errors():
            promoter_full_name_field.error_text = None
            primary_platform_dropdown.error_text = None
            platform_profile_link_field.error_text = None
            estimated_followers_field.error_text = None
            contact_email_field.error_text = None
            referral_reason_field.error_text = None

        def clear_referral_form_fields():
            promoter_full_name_field.value = ""
            primary_platform_dropdown.value = None
            platform_profile_link_field.value = ""
            estimated_followers_field.value = ""
            contact_email_field.value = ""
            phone_number_field.value = ""
            referral_reason_field.value = ""
            additional_info_field.value = ""
            for checkbox in promotion_type_checkboxes:
                checkbox.value = False

        def close_referral_dialog(e=None):
            referral_dialog.open = False
            page.update()

        def submit_promoter_referral(e):
            reset_referral_errors()
            valid = True

            if not promoter_full_name_field.value:
                promoter_full_name_field.error_text = "Required"
                valid = False

            if not primary_platform_dropdown.value:
                primary_platform_dropdown.error_text = "Required"
                valid = False

            profile_link = platform_profile_link_field.value or ""
            if not profile_link.strip():
                platform_profile_link_field.error_text = "Required"
                valid = False

            if not estimated_followers_field.value:
                estimated_followers_field.error_text = "Required"
                valid = False

            email_value = (contact_email_field.value or "").strip()
            if not email_value or "@" not in email_value or "." not in email_value:
                contact_email_field.error_text = "Enter a valid email"
                valid = False

            if not referral_reason_field.value:
                referral_reason_field.error_text = "Required"
                valid = False

            selected_promotions = [
                checkbox.label for checkbox in promotion_type_checkboxes if checkbox.value
            ]
            if not selected_promotions:
                show_snackbar("Please select at least one Promotion Type")
                valid = False

            if not valid:
                page.update()
                return

            referral_payload = {
                "full_name": promoter_full_name_field.value.strip(),
                "primary_platform": primary_platform_dropdown.value,
                "profile_link": profile_link.strip(),
                "followers": estimated_followers_field.value.strip(),
                "email": email_value,
                "phone": (phone_number_field.value or "").strip(),
                "referral_reason": referral_reason_field.value.strip(),
                "promotion_type": ", ".join(selected_promotions),
                "additional_info": (additional_info_field.value or "").strip(),
                "introducer_id": promoter_referral_id,
            }

            success, message = gsheet_manager.submit_promoter_referral(referral_payload)

            if success:
                show_snackbar("Promoter referral submitted successfully.")
                clear_referral_form_fields()
                referral_dialog.open = False
            else:
                show_snackbar(message or "Failed to submit promoter referral. Please try again.")

            page.update()

        referral_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Refer a Promoter", size=20, weight="bold"),
            content=ft.Container(
                width=500,
                content=ft.Column(
                    [
                        promoter_full_name_field,
                        primary_platform_dropdown,
                        platform_profile_link_field,
                        estimated_followers_field,
                        contact_email_field,
                        phone_number_field,
                        referral_reason_field,
                        ft.Column(
                            [
                                ft.Text("Promotion Type", weight="bold"),
                                ft.Row(
                                    promotion_type_checkboxes,
                                    wrap=True,
                                    spacing=10,
                                    run_spacing=10,
                                ),
                            ],
                            spacing=6,
                        ),
                        additional_info_field,
                    ],
                    spacing=12,
                    tight=True,
                    scroll="auto",
                ),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=close_referral_dialog),
                ft.FilledButton("Submit", on_click=submit_promoter_referral),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def open_referral_dialog(e):
            reset_referral_errors()
            if referral_dialog not in page.overlay:
                page.overlay.append(referral_dialog)
            referral_dialog.open = True
            page.update()

        refer_promoter_button = ft.OutlinedButton(
            "Refer a Promoter",
            icon=ft.Icons.PERSON_ADD_ALT,
            on_click=open_referral_dialog,
        )
        
        def show_subscribers_popup(subscribers):
            """Show popup with list of subscribers"""
            print(f"🔍 show_subscribers_popup called with {len(subscribers) if subscribers else 0} subscribers")
            print(f"📋 Subscriber data: {subscribers}")
            
            if not subscribers:
                show_snackbar("No subscribers yet")
                return
            
            subscriber_list = []
            for sub in subscribers:
                print(f"  Adding subscriber: {sub}")
                subscriber_list.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.PERSON, size=20, color="blue"),
                            ft.Text(sub['username'], size=14, weight="bold")
                        ], spacing=10),
                        padding=10,
                        border=ft.border.all(1, "#E0E0E0"),
                        border_radius=8
                    )
                )
            
            def close_dialog(e):
                dialog.open = False
                page.update()
            
            dialog = ft.AlertDialog(
                title=ft.Text(f"Subscribers ({len(subscribers)})", size=18, weight="bold"),
                content=ft.Container(
                    content=ft.Column(
                        subscriber_list,
                        spacing=10,
                        scroll="auto"
                    ),
                    width=400,
                    height=400
                ),
                actions=[
                    ft.TextButton("Close", on_click=close_dialog)
                ],
                actions_alignment=ft.MainAxisAlignment.END
            )
            
            # Use overlay so dialog works consistently on desktop and mobile
            if dialog not in page.overlay:
                page.overlay.append(dialog)
            dialog.open = True
            page.update()
            print(f"✅ Popup displayed with {len(subscriber_list)} subscriber entries")

        # Downline dialog elements
        downline_list_column = ft.Column(spacing=10, expand=True, scroll="auto")
        downline_summary_text = ft.Text("", size=14, weight="bold")
        downline_total_subs_text = ft.Text("", size=12, color="grey")
        downline_status_text = ft.Text("", size=12, color="grey")

        downline_dialog = ft.AlertDialog(
            modal=True,
            content=ft.Container(width=520, height=520),
            actions=[ft.TextButton("Close", on_click=lambda e: (setattr(downline_dialog, "open", False), page.update()))],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def show_downline_view(e=None):
            """Display downline details for the current promoter."""
            if not promoter_referral_id:
                show_snackbar("Register as a promoter to view downline.")
                return

            downline_list_column.controls.clear()
            downline_status_text.value = "Loading downline..."
            downline_summary_text.value = ""
            downline_total_subs_text.value = ""

            description_block = ft.Container(
                content=ft.Column([
                    ft.Text("Your Downline", size=20, weight="bold"),
                    ft.Text(
                        "You earn ₹100 bonus for every 10 new subscriptions from each approved referred promoter.",
                        size=13,
                        color="grey",
                        text_align="left",
                        width=480,
                    ),
                ], spacing=6),
                padding=5,
            )

            def update_dialog_content():
                downline_dialog.content = ft.Container(
                    width=520,
                    height=520,
                    padding=10,
                    content=ft.Column([
                        description_block,
                        ft.Divider(),
                        downline_status_text,
                        ft.Container(
                            content=downline_list_column,
                            expand=True,
                        ),
                        ft.Divider(),
                        downline_summary_text,
                        downline_total_subs_text,
                    ], spacing=10, expand=True),
                )
                if downline_dialog not in page.overlay:
                    page.overlay.append(downline_dialog)
                downline_dialog.open = True
                page.update()

            update_dialog_content()

            def load_downline_thread():
                try:
                    downline_data = gsheet_manager.get_downline_data(promoter_referral_id)
                    downline_list_column.controls.clear()

                    if not downline_data or not downline_data.get("entries"):
                        downline_status_text.value = "No approved downline promoters yet. Refer promoters to start earning downline bonus."
                        downline_summary_text.value = "Total Downline Bonus: ₹0"
                        downline_total_subs_text.value = "Total Downline Subscriptions: 0"
                        page.update()
                        return

                    downline_status_text.value = ""
                    for entry in downline_data.get("entries", []):
                        downline_list_column.controls.append(
                            ft.Container(
                                content=ft.Column([
                                    ft.Text(entry.get("name", "Unnamed"), size=15, weight="bold"),
                                    ft.Text(entry.get("platform", ""), size=12, color="grey"),
                                    ft.Text(entry.get("profile_link", ""), size=12, color="blue", selectable=True),
                                    ft.Text(f"Subscriptions: {entry.get('subscription_count', 0)}", size=13, weight="w600"),
                                    ft.Text(f"Downline Bonus: ₹{entry.get('bonus', 0)}", size=13, weight="bold", color="purple"),
                                ], spacing=4),
                                padding=12,
                                bgcolor="#F5F5F5",
                                border_radius=10,
                            )
                        )

                    total_bonus = downline_data.get("total_bonus", 0)
                    total_subs = downline_data.get("total_subscriptions", 0)
                    downline_summary_text.value = f"Total Downline Bonus: ₹{total_bonus}"
                    downline_total_subs_text.value = f"Total Downline Subscriptions: {total_subs}"

                except Exception as err:
                    print(f"❌ Error loading downline dialog: {err}")
                    downline_status_text.value = "Failed to load downline data. Please try again."
                    show_snackbar("Failed to load downline data. Please try again.")
                finally:
                    update_dialog_content()
                    page.update()

            threading.Thread(target=load_downline_thread, daemon=True).start()
        
        def load_promoter_stats():
            """Load and display promoter statistics"""
            if not promoter_referral_id:
                return
            
            stats_container.controls.clear()
            stats_container.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.ProgressRing(width=20, height=20),
                        ft.Text("Loading stats...", size=14)
                    ], spacing=10),
                    padding=10
                )
            )
            page.update()

            def fetch_stats_thread():
                stats = gsheet_manager.get_promoter_stats(promoter_referral_id)
                downline_bonus = 0
                try:
                    downline_data = gsheet_manager.get_downline_data(promoter_referral_id)
                    if downline_data:
                        downline_bonus = downline_data.get("total_bonus", 0) or 0
                except Exception as downline_error:
                    print(f"⚠️ Failed to load downline bonus: {downline_error}")

                stats_container.controls.clear()

                if stats:
                    total_earnings = stats['earnings'] + downline_bonus

                    # Create stats cards
                    stats_container.controls.extend([
                        # Earnings Section
                        ft.Container(
                            content=ft.Column([
                                ft.Text("💰 Earnings", size=16, weight="bold"),
                                ft.Row([
                                    ft.Container(
                                        content=ft.Column([
                                            ft.Text("Total", size=12, color="grey"),
                                            ft.Text(f"₹{stats['earnings']:.2f}", size=18, weight="bold", color="green")
                                        ], horizontal_alignment="center", spacing=2),
                                        expand=True
                                    ),
                                    ft.Container(
                                        content=ft.Column([
                                            ft.Text("Paid", size=12, color="grey"),
                                            ft.Text(f"₹{stats['paid']:.2f}", size=18, weight="bold", color="blue")
                                        ], horizontal_alignment="center", spacing=2),
                                        expand=True
                                    ),
                                    ft.Container(
                                        content=ft.Column([
                                            ft.Text("Pending", size=12, color="grey"),
                                            ft.Text(f"₹{stats['pending']:.2f}", size=18, weight="bold", color="orange")
                                        ], horizontal_alignment="center", spacing=2),
                                        expand=True
                                    )
                                ], spacing=10),
                                ft.Container(height=6),
                                ft.Row([
                                    ft.Text("Downline Bonus", size=12, color="grey"),
                                    ft.Text(f"₹{downline_bonus:.2f}", size=16, weight="w600", color="purple")
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                ft.Row([
                                    ft.Text("Total Earnings", size=12, color="grey"),
                                    ft.Text(f"₹{total_earnings:.2f}", size=16, weight="bold", color="green")
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ], spacing=10),
                            padding=15,
                            bgcolor="#E8F5E9",
                            border_radius=10
                        ),
                        
                        # Performance Section
                        ft.Container(
                            content=ft.Column([
                                ft.Text("📊 Performance", size=16, weight="bold"),
                                ft.Row([
                                    ft.Container(
                                        content=ft.Column([
                                            ft.Icon(ft.Icons.DOWNLOAD, size=30, color="blue"),
                                            ft.Text(str(stats['installs']), size=20, weight="bold"),
                                            ft.Text("Installs", size=12, color="grey")
                                        ], horizontal_alignment="center", spacing=2),
                                        expand=True
                                    ),
                                    ft.Container(
                                        content=ft.Column([
                                            ft.Icon(ft.Icons.STAR, size=30, color="orange"),
                                            ft.Text(str(stats['subscriptions']), size=20, weight="bold"),
                                            ft.Text("Subscriptions", size=12, color="grey")
                                        ], horizontal_alignment="center", spacing=2),
                                        expand=True
                                    )
                                ], spacing=10)
                            ], spacing=10),
                            padding=15,
                            bgcolor="#FFF3E0",
                            border_radius=10
                        ),
                        
                        # Subscribers Button
                        ft.Container(
                            content=ft.ElevatedButton(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.PEOPLE, size=20),
                                    ft.Text(f"View Subscribers ({len(stats['subscribers'])})", size=14)
                                ], spacing=10),
                                on_click=lambda e: (
                                    print(f"🖱️ View Subscribers button clicked"),
                                    print(f"📊 Stats data: {stats['subscribers']}"),
                                    show_subscribers_popup(stats['subscribers'])
                                )[-1],
                                bgcolor="#2196F3",
                                color="white",
                                width=300
                            ),
                            alignment=ft.alignment.center
                        ),

                        # Downline button
                        ft.Container(
                            content=ft.ElevatedButton(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.GROUP_ADD, size=20),
                                    ft.Text("Your Downline", size=14)
                                ], spacing=10),
                                on_click=show_downline_view,
                                bgcolor="#673AB7",
                                color="white",
                                width=300
                            ),
                            alignment=ft.alignment.center
                        )
                    ])
                else:
                    stats_container.controls.append(
                        ft.Container(
                            content=ft.Text("No stats available yet", size=14, color="grey"),
                            padding=10
                        )
                    )
                
                page.update()
            
            threading.Thread(target=fetch_stats_thread, daemon=True).start()
        
        # Registration form fields
        activation_key_field = ft.TextField(
            label="Activation Key",
            width=300,
            hint_text="Enter your activation key"
        )
        email_field_promoter = ft.TextField(
            label="Email (for notifications)",
            width=300,
            hint_text="email@example.com"
        )
        upi_field = ft.TextField(
            label="UPI ID (for payments)",
            width=300,
            hint_text="yourname@upi"
        )
        
        promoter_status_text = ft.Text("", size=14)
        
        def show_registration_form_ui(e):
            """Show the registration form"""
            show_registration_form["visible"] = True
            refresh_promoter_screen()
        
        def hide_registration_form_ui(e):
            """Hide the registration form"""
            show_registration_form["visible"] = False
            activation_key_field.value = ""
            email_field_promoter.value = ""
            upi_field.value = ""
            promoter_status_text.value = ""
            refresh_promoter_screen()
        
        def register_as_promoter(e):
            """Handle promoter registration"""
            activation_key = activation_key_field.value
            email_promo = email_field_promoter.value
            upi_id = upi_field.value
            
            # Validate inputs
            if not activation_key or not activation_key.strip():
                promoter_status_text.value = "Please enter activation key"
                promoter_status_text.color = "red"
                page.update()
                return
            
            if not email_promo or not email_promo.strip():
                promoter_status_text.value = "Please enter email"
                promoter_status_text.color = "red"
                page.update()
                return
            
            if not upi_id or not upi_id.strip():
                promoter_status_text.value = "Please enter UPI ID"
                promoter_status_text.color = "red"
                page.update()
                return
            
            # Show loading
            promoter_status_text.value = "Verifying..."
            promoter_status_text.color = "blue"
            page.update()
            
            # Verify and register in background thread
            def register_thread():
                success, message, referral_id = gsheet_manager.verify_and_register_promoter(
                    activation_key.strip(),
                    email_promo.strip(),
                    upi_id.strip()
                )
                
                if success:
                    print(f"✅ Promoter registered: {activation_key.strip()} -> Referral ID: {referral_id}")
                    
                    # ✅ FIX: Get existing profile first, then add promoter status
                    profile_url = f"{db.database_url}/users/{auth.user_id}.json?auth={db.auth_token}"
                    
                    try:
                        # Get existing profile
                        response = requests.get(profile_url)
                        if response.status_code == 200:
                            existing_profile = response.json() or {}
                        else:
                            existing_profile = {}
                    except:
                        existing_profile = {}
                    
                    # Add promoter status to profile
                    existing_profile["promoter_status"] = {
                        "registered": True,
                        "referral_id": referral_id,
                        "activation_key": activation_key.strip(),
                        "email": email_promo.strip(),
                        "upi_id": upi_id.strip(),
                        "registered_at": datetime.now().isoformat()
                    }
                    
                    # ✅ Save complete profile with PUT to ensure it's saved
                    try:
                        response = requests.put(profile_url, json=existing_profile)
                        if response.status_code == 200:
                            print(f"✅ Saved to Firebase: {existing_profile['promoter_status']}")
                            
                            # Verify it was saved
                            verify_response = requests.get(profile_url)
                            if verify_response.status_code == 200:
                                verify_data = verify_response.json()
                                print(f"🔍 Verification read: {verify_data.get('promoter_status') if verify_data else 'None'}")
                        else:
                            print(f"⚠️ Failed to save to Firebase: {response.status_code}")
                    except Exception as e:
                        print(f"❌ Error saving to Firebase: {e}")
                    
                    # Update local state
                    nonlocal is_registered_promoter, promoter_referral_id, promoter_status
                    is_registered_promoter = True
                    promoter_referral_id = referral_id
                    promoter_status = existing_profile["promoter_status"]
                    
                    # 🎯 AUTO-JOIN BRONZE CATEGORY GROUPS
                    try:
                        print("🔍 Checking for Bronze category groups to auto-join...")
                        groups_url = f"{db.database_url}/groups.json?auth={db.auth_token}"
                        groups_response = requests.get(groups_url, timeout=10)
                        
                        if groups_response.status_code == 200:
                            all_groups = groups_response.json() or {}
                            joined_count = 0
                            
                            for gid, group_data in all_groups.items():
                                if isinstance(group_data, dict) and 'info' in group_data:
                                    group_info = group_data['info']
                                    category = group_info.get('category', 'None')
                                    
                                    if category == 'Bronze':
                                        # Check if not already a member
                                        members = group_data.get('members', {})
                                        if auth.user_id not in members:
                                            # Add user to group
                                            member_url = f"{db.database_url}/groups/{gid}/members/{auth.user_id}.json?auth={db.auth_token}"
                                            member_data = {
                                                "username": current_username,
                                                "joined_at": int(time.time() * 1000),
                                                "is_admin": False
                                            }
                                            member_response = requests.put(member_url, json=member_data, timeout=10)
                                            
                                            if member_response.status_code == 200:
                                                joined_count += 1
                                                print(f"✅ Auto-joined Bronze group: {group_info.get('name', gid)}")
                            
                            if joined_count > 0:
                                print(f"🎉 Successfully auto-joined {joined_count} Bronze category group(s)!")
                            else:
                                print("ℹ️ No Bronze category groups found to join")
                    except Exception as e:
                        print(f"⚠️ Error auto-joining Bronze groups: {e}")
                    
                    # Hide form and show dashboard
                    show_registration_form["visible"] = False
                    
                    # Show success message
                    show_snackbar(f"✅ Registered successfully! Referral ID: {referral_id}")
                    
                    # Refresh promoter screen to show dashboard
                    refresh_promoter_screen()
                else:
                    promoter_status_text.value = f"❌ {message}"
                    promoter_status_text.color = "red"
                    page.update()
            
            threading.Thread(target=register_thread, daemon=True).start()
        
        def reload_promoter_status():
            """Reload promoter status from Firebase profile - FIXED"""
            nonlocal is_registered_promoter, promoter_referral_id, promoter_status
            
            try:
                print(f"🔄 Reloading promoter status for user: {auth.user_id}")
                
                # ✅ Read directly from Firebase REST API
                profile_url = f"{db.database_url}/users/{auth.user_id}.json?auth={db.auth_token}"
                response = requests.get(profile_url)
                
                if response.status_code == 200:
                    fresh_profile = response.json()
                    print(f"📊 Raw profile data from Firebase: {fresh_profile}")
                    
                    if fresh_profile and isinstance(fresh_profile, dict):
                        if "promoter_status" in fresh_profile:
                            promoter_status = fresh_profile["promoter_status"]
                            is_registered_promoter = promoter_status.get("registered", False)
                            promoter_referral_id = promoter_status.get("referral_id", "")
                            
                            print(f"✅ Reloaded promoter status: registered={is_registered_promoter}, referral_id={promoter_referral_id}")
                        else:
                            print("⚠️ No promoter_status found in profile")
                            is_registered_promoter = False
                            promoter_referral_id = ""
                            promoter_status = {}
                    else:
                        print("⚠️ Profile data is empty or invalid")
                        is_registered_promoter = False
                        promoter_referral_id = ""
                        promoter_status = {}
                else:
                    print(f"⚠️ Could not reload promoter status - HTTP {response.status_code}")
                    is_registered_promoter = False
                    promoter_referral_id = ""
                    promoter_status = {}
            except Exception as e:
                print(f"❌ Error reloading promoter status: {e}")
                import traceback
                traceback.print_exc()
        
        def refresh_promoter_screen():
            """Refresh the promoter screen content"""
            # Always reload status from Firebase first
            reload_promoter_status()

            promoter_content.controls.clear()

            update_notification_badge()

            new_assignments = []
            if is_registered_promoter and promoter_referral_id:
                new_assignments = gsheet_manager.assign_activation_keys_for_approved_referrals(promoter_referral_id)
                for assignment in new_assignments:
                    system_notifications.append(
                        {
                            "title": "New downline activation key",
                            "message": (
                                f"Your referred promoter {assignment.get('name', 'Promoter')} has been approved. "
                                f"Activation key: {assignment.get('activation_key', '')}. "
                                "Ask them to use it in the 'Register as Promoter' screen."
                            ),
                        }
                    )
                    unread_system_notifications["count"] += 1
                if new_assignments:
                    update_notification_badge()

            promoter_content.controls.append(
                ft.Container(
                    content=ft.Row(
                        [refer_promoter_button],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                    width=page.width,
                )
            )

            if is_registered_promoter:
                # Show dashboard with stats
                promoter_content.controls.extend([
                    ft.Container(height=20),
                    ft.Icon(ft.Icons.VERIFIED, size=60, color="green"),
                    ft.Text("Promoter Dashboard", size=24, weight="bold"),
                    ft.Container(height=10),
                    
                    # Referral ID Card
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Your Referral ID", size=14, weight="bold", color="grey"),
                            ft.Text(promoter_referral_id, size=22, weight="bold", color="blue", selectable=True)
                        ], horizontal_alignment="center", spacing=5),
                        padding=15,
                        bgcolor="#E3F2FD",
                        border_radius=10,
                        width=350
                    ),
                    
                    ft.Container(height=20),
                    
                    # Stats container
                    stats_container,
                    
                    ft.Container(height=10),
                    
                ])
                
                # Load stats initially
                load_promoter_stats()
            else:
                # Show register button or registration form
                if show_registration_form["visible"]:
                    # Show registration form
                    promoter_content.controls.extend([
                        ft.Container(height=20),
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            on_click=hide_registration_form_ui,
                            tooltip="Back"
                        ),
                        ft.Icon(ft.Icons.WALLET, size=60, color="blue"),
                        ft.Text("Register as Promoter", size=24, weight="bold"),
                        ft.Container(height=10),
                        ft.Text("Earn by promoting our app!", size=14, color="grey"),
                        ft.Container(height=20),
                        activation_key_field,
                        email_field_promoter,
                        upi_field,
                        ft.Container(height=10),
                        promoter_status_text,
                        ft.Container(height=20),
                        ft.ElevatedButton(
                            "Submit Registration",
                            on_click=register_as_promoter,
                            bgcolor="blue",
                            color="white",
                            width=300
                        )
                    ])
                else:
                    # Show register button
                    promoter_content.controls.extend([
                        ft.Container(height=80),
                        ft.Icon(ft.Icons.WALLET, size=80, color="blue"),
                        ft.Text("Become a Promoter", size=26, weight="bold"),
                        ft.Container(height=20),
                        ft.Text(
                            "Earn money by promoting our app to your friends and followers!",
                            size=14,
                            color="grey",
                            text_align="center",
                            width=350
                        ),
                        ft.Container(height=30),
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.CHECK_CIRCLE, color="green", size=20),
                                    ft.Text("Earn for every install", size=14)
                                ], spacing=10),
                                ft.Row([
                                    ft.Icon(ft.Icons.CHECK_CIRCLE, color="green", size=20),
                                    ft.Text("Get paid for subscriptions", size=14)
                                ], spacing=10),
                                ft.Row([
                                    ft.Icon(ft.Icons.CHECK_CIRCLE, color="green", size=20),
                                    ft.Text("Track your earnings", size=14)
                                ], spacing=10),
                            ], spacing=10),
                            padding=20,
                            bgcolor="#F5F5F5",
                            border_radius=10
                        ),
                        ft.Container(height=30),
                        ft.ElevatedButton(
                            "Register as Promoter",
                            icon=ft.Icons.ARROW_FORWARD,
                            on_click=show_registration_form_ui,
                            bgcolor="blue",
                            color="white",
                            width=300,
                            height=50
                        )
                    ])
            
            page.update()
        
        # Main promoter content container
        promoter_content = ft.Column(
            [],
            horizontal_alignment="center",
            scroll="auto",
            spacing=10
        )
        
        # Build initial screen
        refresh_promoter_screen()
        
        # Screen promoter container
        screen_promoter = ft.Container(
            content=promoter_content,
            padding=20,
            expand=True
        )

        screen_groups = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Text("Groups", size=20, weight="bold", expand=True)
                    ]),
                    padding=15
                ),
                ft.Container(
                    content=groups_list_column, 
                    padding=10, 
                    expand=True
                )
            ], spacing=0),
            expand=True
        )

        # Load immediately when creating main menu
        # This should be called AFTER screen_groups is defined
        load_groups_list()

        # TAB 2 → ALL MEMBERS (OPTIMIZED - faster loading)
        all_members_column = ft.Column(scroll="auto", expand=True, spacing=5)
        
        
        def load_all_members(force_refresh=False):
            """Load all members - CACHE FIRST"""
            
            members_cache["loaded"] = True
            all_members_column.controls.clear()
            
            # Step 1: Load from cache IMMEDIATELY
            cached_members = CacheManager.load_from_cache('group_members')
            
            if cached_members and not force_refresh:
                # Show cached data right away
                display_members_from_cache(cached_members)
            else:
                # IMPROVED: Check if online
                if not NetworkChecker.is_online():
                    all_members_column.controls.append(
                        ft.Container(
                            content=ft.Column([
                                ft.Icon(ft.Icons.CLOUD_OFF, size=50, color="orange"),
                                ft.Text("You're offline", size=16, weight="bold"),
                                ft.Text("Connect to internet to load members", size=12, color="grey"),
                            ], horizontal_alignment="center", spacing=10),
                            padding=40
                        )
                    )
                    page.update()
                    return
                
                # Show loading
                all_members_column.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.ProgressRing(width=20, height=20),
                            ft.Text("Loading members...", size=14)
                        ], spacing=10),
                        padding=20
                    )
                )
                page.update()
            
            # Step 2: Update from network in background
            def refresh_members():
                try:
                    if not NetworkChecker.is_online():
                        print("Offline - using cache only")
                        if not cached_members:
                            all_members_column.controls.clear()
                            all_members_column.controls.append(
                                ft.Container(
                                    content=ft.Column([
                                        ft.Icon(ft.Icons.CLOUD_OFF, size=50, color="orange"),
                                        ft.Text("You're offline", size=16, weight="bold"),
                                    ], horizontal_alignment="center", spacing=10),
                                    padding=40
                                )
                            )
                            page.update()
                        return
                    
                    # Fetch fresh data - get all members from all groups
                    all_groups = db.get_all_groups()
                    members_dict = {}  # Use dict to avoid duplicates by user_id
                    
                    for group in all_groups:
                        group_id = group.get('id')
                        if group_id:
                            group_members = db.get_group_members_by_id(group_id)
                            for member in group_members:
                                user_id = member.get('id')
                                if user_id and user_id not in members_dict:
                                    members_dict[user_id] = {
                                        'id': user_id,
                                        'username': member.get('username', 'Unknown'),
                                        'email': member.get('email', ''),
                                        'is_admin': member.get('is_admin', False),
                                        'profile_image_url': member.get('profile_image_url', '')
                                    }
                                elif user_id and member.get('is_admin', False):
                                    # If user is admin in any group, mark them as admin
                                    members_dict[user_id]['is_admin'] = True
                    
                    members = list(members_dict.values())
                    
                    # Save to cache
                    CacheManager.save_to_cache('group_members', members)
                    
                    # Update UI
                    display_members_from_cache(members)
                    
                except Exception as e:
                    print(f"Members refresh error: {e}")
                    if not cached_members:
                        all_members_column.controls.clear()
                        all_members_column.controls.append(
                            ft.Container(content=ft.Text("Error loading members", color="red"), padding=20)
                        )
                        page.update()
            
            threading.Thread(target=refresh_members, daemon=True).start()
            
        # ADD THIS - Create the screen_members container:
        screen_members = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Text("Members", size=20, weight="bold", expand=True)
                    ]),
                    padding=15
                ),
                ft.Container(
                    content=all_members_column, 
                    padding=10, 
                    expand=True
                )
            ], spacing=0),
            expand=True
        )

        # Add this NEW function after load_all_members
        def display_members_from_cache(members):
            """Display members from cache"""
            all_members_column.controls.clear()
            
            if not members:
                all_members_column.controls.append(
                    ft.Container(content=ft.Text("No members yet"), padding=20)
                )
                page.update()
                return
            
            # Sort: admins first, then alphabetically by username
            sorted_members = sorted(members, key=lambda u: (
                not u.get("is_admin", False),  # False sorts before True, so admins come first
                (u.get("username") or u.get("email", "User").split("@")[0]).lower()
            ))
            
            for user in sorted_members:
                if user['id'] == auth.user_id:
                    continue
                
                uname = user.get("username") or user.get("email", "User").split("@")[0]
                is_admin_badge = user.get("is_admin", False)
                
                # Avatar
                avatar = ft.Container(
                    content=ft.Text(uname[0].upper(), size=16, color="white"),
                    width=40, height=40, bgcolor="#2196F3", border_radius=20,
                    alignment=ft.alignment.center
                )
                
                # Load profile image from cache
                user_profile = db.get_user_profile(user['id'])
                if user_profile and user_profile.get('profile_image_url'):
                    cached_path = ImageCache.get_cached_image(user_profile['profile_image_url'], "profile")
                    if cached_path:
                        avatar = ft.Image(
                            src=cached_path, width=40, height=40,
                            fit=ft.ImageFit.COVER, border_radius=20
                        )
                
                member_row = ft.Container(
                    content=ft.Row([
                        avatar,
                        ft.Column([
                            ft.Row([
                                ft.Text(uname, size=14, weight="bold"),
                                ft.Text(" 👑", size=12) if is_admin_badge else ft.Container()
                            ], spacing=5),
                            ft.Text(user.get("email", ""), size=11, color="grey")
                        ], spacing=2, expand=True),
                        ft.IconButton(
                            icon=ft.Icons.MESSAGE,
                            icon_color="#2196F3",
                            on_click=lambda e, u=user: send_message_request(u)
                        )
                    ], spacing=10),
                    padding=10,
                    border=ft.border.only(bottom=ft.border.BorderSide(1, "#E0E0E0"))
                )
                all_members_column.controls.append(member_row)
            
            page.update()

        # TAB 3 → PRIVATE CHATS (FIXED - removed duplicate code)
        private_chats_column = ft.Column(scroll="auto", expand=True, spacing=5)

        def load_private_chats(force_refresh=False):
            """Load private chats - CACHE FIRST"""
            
            private_chats_cache["loaded"] = True 
            
            private_chats_column.controls.clear()
            
            # Step 1: Load from cache immediately
            cached_chats = CacheManager.load_from_cache('private_chats')
            
            if cached_chats and not force_refresh:
                private_chats_cache["data"] = cached_chats  # ADD THIS
                private_chats_cache["loaded"] = True  # ADD THIS
                display_private_chats_from_cache(cached_chats)
            else:
                private_chats_column.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.ProgressRing(width=20, height=20),
                            ft.Text("Loading chats...", size=14)
                        ], spacing=10),
                        padding=20
                    )
                )
                page.update()
            
            # Step 2: Update from network (ONLY ONE background thread)

            def refresh_chats():
                try:
                    if not NetworkChecker.is_online():
                        print("Offline - using cache only")
                        if not cached_chats:
                            private_chats_column.controls.clear()
                            private_chats_column.controls.append(
                                ft.Container(
                                    content=ft.Column([
                                        ft.Icon(ft.Icons.CLOUD_OFF, size=50, color="orange"),
                                        ft.Text("You're offline", size=16, weight="bold"),
                                    ], horizontal_alignment="center", spacing=10),
                                    padding=40
                                )
                            )
                            page.update()
                        return

                    all_users = db.get_all_users()
                    accepted_chats = []

                    for user in all_users:
                        if user['id'] == auth.user_id:
                            continue

                        chat_id = create_chat_id(auth.user_id, user['id'])
                        status = db.get_chat_status(chat_id)
                        requester = db.get_chat_requester(chat_id)

                        include_chat = False
                        is_request = False

                        # Show accepted chats for both sides
                        if status == "accepted":
                            include_chat = True
                        # Show pending chats only to the receiver as a 'request'
                        elif status == "pending" and requester and requester != auth.user_id:
                            include_chat = True
                            is_request = True

                        if include_chat:
                            messages = db.get_messages(chat_id)
                            last_msg = messages[-1] if messages else None

                            unread_count = sum(
                                1 for msg in messages
                                if msg.get('sender_id') != auth.user_id
                                and not msg.get('seen', False)
                            )

                            accepted_chats.append({
                                'user': user,
                                'last_msg': last_msg,
                                'unread': unread_count,
                                'chat_id': chat_id,
                                'status': status,
                                'is_request': is_request,
                            })

                    # Save to cache
                    CacheManager.save_to_cache('private_chats', accepted_chats)

                    # Store in cache dict
                    private_chats_cache["data"] = accepted_chats
                    private_chats_cache["loaded"] = True

                    try:
                        unread_private_messages["count"] = sum(
                            int(chat.get('unread', 0) or 0) for chat in accepted_chats
                        )
                    except Exception:
                        unread_private_messages["count"] = 0
                    update_notification_badge()

                    # Display
                    display_private_chats_from_cache(accepted_chats)

                except Exception as e:
                    print(f"Chats refresh error: {e}")
                    if not cached_chats:
                        private_chats_column.controls.clear()
                        private_chats_column.controls.append(
                            ft.Container(content=ft.Text("Error loading chats", color="red"), padding=20)
                        )
                        page.update()
                refresh_chats()


        def display_private_chats_from_cache(accepted_chats):
            """Display private chats from data (accepted + pending requests)"""
            private_chats_column.controls.clear()

            try:
                unread_private_messages["count"] = sum(
                    int(chat.get('unread', 0) or 0) for chat in accepted_chats
                )
            except Exception:
                unread_private_messages["count"] = 0
            update_notification_badge()

            # Count pending requests (only those where this user is receiver)
            pending_count = sum(
                1 for c in accepted_chats
                if c.get('status') == 'pending' and c.get('is_request')
            )

            # Update Private tab icon (index 2)
            try:
                if pending_count > 0:
                    bottom_nav.destinations[2].icon = ft.Icon(ft.Icons.PERSON_OUTLINED, color="red")
                else:
                    bottom_nav.destinations[2].icon = ft.Icon(ft.Icons.PERSON_OUTLINED)
                bottom_nav.update()
            except Exception as e:
                print(f"Private tab badge update error: {e}")

            if not accepted_chats:
                private_chats_column.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE, size=60, color="grey"),
                            ft.Text("No conversations yet", size=16, color="grey"),
                            ft.Text("Send message requests from Members tab", size=12, color="grey")
                        ], horizontal_alignment="center", spacing=10),
                        padding=40
                    )
                )
            else:
                # Sort by last message time
                accepted_chats.sort(
                    key=lambda x: x['last_msg']['timestamp'] if x['last_msg'] else 0,
                    reverse=True
                )

                for chat_data in accepted_chats:
                    user = chat_data['user']
                    last_msg = chat_data['last_msg']
                    unread = chat_data['unread']
                    status = chat_data.get('status')
                    is_request = chat_data.get('is_request', False)

                    # 🔥 DEBUG: Check for NaN
                    print(f"DEBUG - Unread value: {unread}, type: {type(unread)}")
                    if isinstance(unread, float):
                        import math
                        if math.isnan(unread):
                            print(f"🔥 FOUND NaN in unread count for user {user.get('username')}")
                            unread = 0

                    uname = user.get('username', user.get('email', 'User').split('@')[0])

                    # Avatar from cache
                    cached_path = None
                    user_profile = db.get_user_profile(user['id'])
                    if user_profile and user_profile.get('profile_image_url'):
                        cached_path = ImageCache.get_cached_image(user_profile['profile_image_url'], "profile")

                    if cached_path:
                        avatar = ft.Image(
                            src=cached_path,
                            width=50,
                            height=50,
                            fit=ft.ImageFit.COVER,
                            border_radius=25
                        )
                    else:
                        avatar = ft.Container(
                            content=ft.Text(uname[0].upper(), size=18, color="white"),
                            width=50,
                            height=50,
                            bgcolor="#2196F3",
                            border_radius=25,
                            alignment=ft.alignment.center
                        )

                    # Last message / subtitle
                    if last_msg:
                        last_text = last_msg.get('text', 'Attachment')[:40]
                        try:
                            timestamp = datetime.fromtimestamp(last_msg['timestamp'] / 1000)
                            time_str = timestamp.strftime("%I:%M %p")
                        except Exception as e:
                            print(f"Time parse error in private chats: {e}")
                            time_str = ""
                    else:
                        if is_request:
                            last_text = "Message request pending"
                        else:
                            last_text = "No messages yet"
                        time_str = ""

                    # If this is a pending request, decorate the subtitle
                    if is_request:
                        last_text = "🔔 Message request - tap to review"

                    # Unread badge (safe)
                    import math
                    unread_count_safe = 0
                    try:
                        unread_count_safe = int(unread) if unread and not math.isnan(float(unread)) else 0
                    except Exception:
                        unread_count_safe = 0

                    unread_badge = ft.Container(
                        content=ft.Text(str(unread_count_safe), size=10, color="white", weight="bold"),
                        bgcolor="red",
                        border_radius=10,
                        padding=ft.padding.only(left=6, right=6, top=2, bottom=2),
                        visible=(unread_count_safe > 0)
                    )

                    chat_row = ft.Container(
                        content=ft.Row([
                            avatar,
                            ft.Column([
                                ft.Text(uname, size=15, weight="bold"),
                                ft.Text(last_text, size=12, color="grey")
                            ], spacing=2, expand=True),
                            ft.Column([
                                ft.Text(time_str, size=10, color="grey"),
                                unread_badge
                            ], horizontal_alignment="end", spacing=5)
                        ], spacing=10),
                        padding=12,
                        border=ft.border.only(bottom=ft.border.BorderSide(1, "#E0E0E0")),
                        on_click=lambda e, u=user: open_chat(u)
                    )

                    private_chats_column.controls.append(chat_row)

            page.update()
        screen_private_chat = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Text("Private Chats", size=20, weight="bold", expand=True)
                    ]),
                    padding=15
                ),
                ft.Container(
                    content=private_chats_column,
                    padding=10,
                    expand=True
                )
            ], spacing=0),
            expand=True
        )

        # TAB 4 → SETTINGS (with Create Group button for admin)
        settings_buttons = []
        
        if is_admin:
            settings_buttons.append(
                ft.ElevatedButton(
                    "➕ Create New Group",
                    icon=ft.Icons.ADD_CIRCLE,
                    on_click=lambda e: show_create_group(),
                    width=250,
                    bgcolor="#4CAF50",
                    color="white"
                )
            )
        
        settings_buttons.append(ft.Container(height=10))
        settings_buttons.append(
            ft.TextButton("Logout", on_click=lambda e: handle_logout())
        )
        
        screen_settings = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Text("Settings", size=20, weight="bold"),
                        padding=15
                    ),
                    ft.Container(height=20),
                    *settings_buttons
                ],
                horizontal_alignment="center"
            ),
            expand=True
        )

        # ========== BOTTOM NAVIGATION (CRITICAL FIX) ==========
        selected_index = 0
        bottom_nav = None

        page_controller = getattr(ft, "PageController", None)
        page_controller = page_controller() if page_controller else None

        # SELECT WHICH SCREEN TO SHOW (with optimized lazy loading)

        def activate_tab(new_index):
            """Update selection, load data, and sync the bottom nav."""
            nonlocal selected_index
            selected_index = new_index
            try:
                if bottom_nav:
                    bottom_nav.selected_index = selected_index
            except Exception as nav_ex:
                print(f"[NAV SYNC] {nav_ex}")

            activate_tab_ref["fn"] = activate_tab

            if not page_view_cls:
                try:
                    tab_placeholder.content = tab_pages[selected_index]
                except Exception as tab_ex:
                    print(f"[TAB FALLBACK] {tab_ex}")

            if selected_index == 0:
                refresh_promoter_screen()
            elif selected_index == 1:
                # Groups already loaded
                pass
            elif selected_index == 2:
                if not members_cache["loaded"]:
                    load_all_members()
            elif selected_index == 3:
                active_screen["current"] = "chat_list"
                if not users_list.controls:
                    try:
                        load_users()
                    except Exception as ex:
                        print(f"[PRIVATE TAB AUTO-LOAD ERROR] {ex}")
            page.update()

        def switch_tab(e):
            try:
                # Ensure index is a valid integer
                new_index = int(e.control.selected_index)
                if 0 <= new_index <= 4:  # Valid range (5 tabs now)
                    if page_controller:
                        page_controller.animate_to_page(
                            new_index,
                            duration=400,
                            curve=ft.AnimationCurve.EASE_IN_OUT,
                        )
                    else:
                        activate_tab(new_index)
            except Exception as ex:
                print(f"Tab switch error: {ex}")

        try:
            bottom_nav = ft.NavigationBar(
                selected_index=0,
                destinations=[
                    ft.NavigationBarDestination(
                        icon=ft.Icons.WALLET_OUTLINED,
                        selected_icon=ft.Icons.WALLET,
                        label="Promoter"
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.CHAT_OUTLINED,
                        selected_icon=ft.Icons.CHAT,
                        label="Groups"
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.PEOPLE_OUTLINED,
                        selected_icon=ft.Icons.PEOPLE,
                        label="Members"
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.PERSON_OUTLINED,
                        selected_icon=ft.Icons.PERSON,
                        label="Private"
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.SETTINGS_OUTLINED,
                        selected_icon=ft.Icons.SETTINGS,
                        label="Settings"
                    ),
                ],
                on_change=switch_tab
            )
        except Exception as e:
            print(f"Error creating bottom nav: {e}")
            bottom_nav = ft.Container()  # Fallback

        # Global swipe and pull-to-refresh handlers
        def refresh_current_tab(e=None):
            """Pull-to-refresh handler for current tab"""
            try:
                if selected_index == 0:
                    # Promoter tab
                    refresh_promoter_screen()
                elif selected_index == 1:
                    # Groups tab
                    load_groups_list(force_refresh=True)
                elif selected_index == 2:
                    # Members tab
                    load_all_members(force_refresh=True)
                elif selected_index == 3:
                    # Private tab: chat list or private chats
                    try:
                        current_screen = active_screen.get("current")
                        if current_screen == "chat_list":
                            load_users()
                        elif current_screen == "private_chats":
                            load_private_chats(force_refresh=True)
                    except Exception as ex:
                        print(f"[PULL REFRESH PRIVATE] {ex}")
                elif selected_index == 4:
                    # Settings tab - nothing to refresh yet
                    pass
            except Exception as ex:
                print(f"[PULL REFRESH ERROR] {ex}")

        def _handle_pan_end(e):
            """Swipe left/right to switch tabs"""
            try:
                vx = getattr(e, "velocity_x", 0) or 0
                threshold = 300  # Adjust sensitivity if needed
                # Swipe left -> next tab
                if vx < -threshold and selected_index < 4 and page_controller:
                    page_controller.animate_to_page(
                        selected_index + 1,
                        duration=400,
                        curve=ft.AnimationCurve.EASE_IN_OUT,
                    )
                # Swipe right -> previous tab
                elif vx > threshold and selected_index > 0 and page_controller:
                    page_controller.animate_to_page(
                        selected_index - 1,
                        duration=400,
                        curve=ft.AnimationCurve.EASE_IN_OUT,
                    )
            except Exception as ex:
                print(f"[SWIPE NAV ERROR] {ex}")

        async def _handle_refresh(e):
            """Show pull-to-refresh animation and reload current tab"""
            try:
                refresh_current_tab()
                page.update()
            except Exception as ex:
                print(f"[REFRESH INDICATOR] {ex}")

        # Build horizontal pager for WhatsApp-like slide transitions
        tab_pages = [
            ft.Container(content=screen_promoter, expand=True),
            ft.Container(content=screen_groups, expand=True),
            ft.Container(content=screen_members, expand=True),
            ft.Container(content=chat_list_view, expand=True),
            ft.Container(content=screen_settings, expand=True),
        ]

        page_view_cls = getattr(ft, "PageView", None)
        tab_placeholder = ft.Container(expand=True)

        def _handle_page_change(e):
            try:
                new_index = int(e.data)
                activate_tab(new_index)
            except Exception as ex:
                print(f"[PAGE VIEW CHANGE] {ex}")

        page_physics_cls = getattr(ft, "PageScrollPhysics", None)
        page_physics = page_physics_cls() if page_physics_cls else None

        if page_view_cls:
            pager_content = page_view_cls(
                expand=True,
                controller=page_controller,
                scroll_direction=ft.Axis.HORIZONTAL,
                on_page_changed=_handle_page_change,
                physics=page_physics,
                controls=tab_pages,
            )
        else:
            print("[PAGE VIEW] ft.PageView not available; falling back to single-view container")
            tab_placeholder.content = tab_pages[selected_index]
            pager_content = tab_placeholder

        main_gesture_content = ft.GestureDetector(
            on_pan_end=_handle_pan_end,
            content=pager_content,
        )

        refresh_indicator_cls = getattr(ft, "RefreshIndicator", None)
        if refresh_indicator_cls is not None:
            main_content = refresh_indicator_cls(
                on_refresh=_handle_refresh,
                child=main_gesture_content,
            )
        else:
            print("[REFRESH INDICATOR] ft.RefreshIndicator not available; using plain container")
            main_content = main_gesture_content

        main_area = ft.Container(
            expand=True,
            content=main_content,
        )
        activate_tab(0)

        # FINAL PAGE LAYOUT (add offline banner)
        page.add(
            ft.Column(
                [
                    # Safe area for Android status bar
                    ft.Container(height=30),
                    
                    # ADD OFFLINE BANNER HERE:
                    offline_banner,
                    
                    # Top bar
                    ft.Container(
                        content=top_bar,
                        padding=15,
                        bgcolor="#E3F2FD"
                    ),
                    
                    # Main content area
                    main_area,
                    
                    # Bottom nav
                    ft.Container(
                        content=bottom_nav,
                        bgcolor="white"
                    )
                ],
                spacing=0,
                expand=True
            )
        )
        # Final page update
        page.update()

        # Load private chats data in background
        threading.Thread(target=load_private_chats, daemon=True).start()
        # Load private chats data
        
        
        def show_group_details(group_data, members):
            """Show group details with options"""
            stop_auto_refresh()
            navigation_stack.clear()
            navigation_stack.append(show_main_menu)
            page.clean()
            
            # Group icon
            group_icon_url = group_data.get("icon_url")
            group_icon_emoji = group_data.get("icon", "👥")
            
            if group_icon_url:
                cached_icon = ImageCache.get_cached_image(group_icon_url, "group")
                if cached_icon:
                    group_icon = ft.Image(src=cached_icon, width=100, height=100, fit=ft.ImageFit.COVER, border_radius=50)
                else:
                    group_icon = ft.Text(group_icon_emoji, size=60)
            else:
                group_icon = ft.Text(group_icon_emoji, size=60)
            
            # Members list preview
            members_preview = ft.Column(spacing=5)
            for member in members[:10]:  # Show first 10
                uname = member.get("username", "User")
                is_admin_badge = " 👑" if member.get("is_admin") else ""
                members_preview.controls.append(
                    ft.Text(f"• {uname}{is_admin_badge}", size=13)
                )
            
            if len(members) > 10:
                members_preview.controls.append(
                    ft.Text(f"... and {len(members) - 10} more", size=12, color="grey", italic=True)
                )
            
            # Action buttons
            action_buttons = [
                ft.ElevatedButton(
                    "💬 Open Chat",
                    icon=ft.Icons.CHAT,
                    on_click=lambda e: open_group_chat(),
                    width=200,
                    bgcolor="#2196F3",
                    color="white"
                )
            ]
            
            # Admin-only buttons
            if is_admin or user_is_group_admin:
                action_buttons.extend([
                    ft.Container(height=10),
                    ft.ElevatedButton(
                        "✏️ Edit Group Info",
                        icon=ft.Icons.EDIT,
                        on_click=lambda e: show_edit_group_info(),
                        width=200,
                        bgcolor="#FF9800",
                        color="white"
                    ),
                    ft.Container(height=10),
                    ft.ElevatedButton(
                        "👥 Manage Members",
                        icon=ft.Icons.PEOPLE,
                        on_click=lambda e: show_group_management(),
                        width=200,
                        bgcolor="#9C27B0",
                        color="white"
                    )
                ])
            
            group_details_view = ft.Container(
                content=ft.Column([
                    ft.Container(
                        content=ft.Row([
                            ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: handle_back_navigation(e)),
                            ft.Text("Group Details", size=20, weight="bold", expand=True),
                        ]),
                        padding=ft.padding.only(left=20, right=20, top=40, bottom=20),
                        bgcolor="#E3F2FD"
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Container(height=20),
                            group_icon,
                            ft.Container(height=20),
                            ft.Text(group_data.get("name", "Group"), size=24, weight="bold", text_align="center"),
                            ft.Text(group_data.get("description", ""), size=14, color="grey", text_align="center"),
                            ft.Container(height=20),
                            ft.Text(f"{len(members)} Members", size=16, weight="bold"),
                            ft.Container(height=10),
                            ft.Container(
                                content=members_preview,
                                padding=15,
                                border=ft.border.all(1, "#E0E0E0"),
                                border_radius=10,
                                bgcolor="#F5F5F5"
                            ),
                            ft.Container(height=30),
                            *action_buttons
                        ], horizontal_alignment="center", scroll="auto"),
                        padding=20,
                        expand=True
                    )
                ], spacing=0),
                expand=True
            )
            
            page.add(group_details_view)
            page.update()
        
        def open_group_chat():
            """Open the group chat"""
            nonlocal group_info
            group_info = {}
    def handle_logout():
        CredentialsManager.clear_credentials()
        show_snackbar("Logged out successfully")
        show_login_view()
    
    # Edit Profile
    edit_username_field = ft.TextField(
        label="Username", 
        width=300,  # 🔥 Add explicit width
        height=56,  # 🔥 Add explicit height
        expand=False  # 🔥 Change from True
    )
    edit_profile_image_preview = ft.Image(width=120, height=120, fit=ft.ImageFit.COVER, border_radius=60, visible=False)
    selected_profile_image_data = {"url": None}
    
    def pick_profile_image(e):
        profile_file_picker.pick_files(
            allowed_extensions=["jpg", "jpeg", "png", "gif", "webp"],
            allow_multiple=False
        )

    def on_profile_image_selected(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            try:
                file = e.files[0]
                
                if file.size > MAX_FILE_SIZE:
                    show_snackbar(f"File too large! Max size: {format_file_size(MAX_FILE_SIZE)}")
                    return
                
                with open(file.path, 'rb') as f:
                    file_data = f.read()
                
                show_snackbar("Uploading profile image...")
                file_path = f"profile_images/{auth.user_id}_{int(time.time())}_{file.name}"
                success, result = storage.upload_file(file_path, file.name, file_data)
                
                if success:
                    selected_profile_image_data["url"] = result
                    edit_profile_image_preview.src = result
                    edit_profile_image_preview.visible = True
                    show_snackbar("Profile image uploaded!")
                    page.update()
                else:
                    show_snackbar(f"Upload failed: {result}")
            except Exception as ex:
                show_snackbar(f"Error: {str(ex)}")
    
    profile_file_picker.on_result = on_profile_image_selected
    
    def save_profile(e):
        nonlocal current_username
        
        if not edit_username_field.value:
            show_snackbar("Username cannot be empty")
            return
        
        profile_image_url = selected_profile_image_data.get("url")
        
        # ✅ FIX: Get existing profile first to preserve all fields including promoter_status
        profile_url = f"{db.database_url}/users/{auth.user_id}.json?auth={db.auth_token}"
        
        try:
            # Get existing profile
            response = requests.get(profile_url)
            if response.status_code == 200:
                existing_profile = response.json() or {}
            else:
                existing_profile = {}
        except:
            existing_profile = {}
        
        # ✅ Update only the fields we're editing (preserves promoter_status!)
        existing_profile["username"] = edit_username_field.value
        if profile_image_url:
            existing_profile["profile_image_url"] = profile_image_url
        
        # ✅ Save complete profile with PUT
        try:
            response = requests.put(profile_url, json=existing_profile)
            success = response.status_code == 200
            
            if success:
                print(f"✅ Profile updated. Promoter status preserved: {existing_profile.get('promoter_status')}")
            else:
                print(f"⚠️ Failed to update profile: {response.status_code}")
        except:
            success = False
        
        if success:
            current_username = edit_username_field.value
            
            # Update stored credentials
            CredentialsManager.save_credentials(auth.email, auth.refresh_token, current_username)
            
            # Update token storage
            db.store_user_token(auth.user_id, auth.email, current_username, auth.refresh_token)
            
            show_snackbar("Profile updated!")
            show_main_menu()
        else:
            show_snackbar("Failed to update profile")
    
    def show_edit_profile():
        stop_auto_refresh()
        navigation_stack.append(show_main_menu)
        page.clean()
        
        # Load current profile
        profile = db.get_user_profile(auth.user_id)
        edit_username_field.value = current_username
        
        if profile and profile.get('profile_image_url'):
            selected_profile_image_data["url"] = profile['profile_image_url']
            edit_profile_image_preview.src = profile['profile_image_url']
            edit_profile_image_preview.visible = True
        else:
            edit_profile_image_preview.visible = False
            selected_profile_image_data["url"] = None
        
        edit_profile_view = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.IconButton("arrow_back", on_click=lambda e: handle_back_navigation(e)),
                        ft.Text("Edit Profile", size=20, weight="bold", expand=True),
                    ]),
                    padding=ft.padding.only(left=20, right=20, top=40, bottom=20),
                    bgcolor="#E3F2FD"
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Container(height=20),
                        ft.Text("Profile Settings", size=24, weight="bold"),
                        ft.Container(height=30),
                        ft.Container(content=edit_profile_image_preview, alignment=ft.alignment.center),
                        ft.Container(height=15),
                        ft.ElevatedButton("Choose Profile Image", on_click=pick_profile_image, bgcolor="#2196F3", color="white"),
                        ft.Container(height=30),
                        edit_username_field,
                        ft.Container(height=30),
                        ft.ElevatedButton("Save Changes", expand=True, bgcolor="green", color="white", on_click=save_profile)
                    ], horizontal_alignment="center", scroll="auto"),
                    padding=20,
                    expand=True
                )
            ], spacing=0),
            expand=True
        )
        
        page.add(edit_profile_view)
        page.update()
    
    # Edit Group Info
    group_name_field = ft.TextField(
        label="Group Name", 
        width=300, 
        height=56,
        expand=False
    )
    group_desc_field = ft.TextField(
        label="Description", 
        width=300, 
        height=120,  # Taller for multiline
        expand=False, 
        multiline=True, 
        max_lines=3
    )
    group_icon_field = ft.TextField(
        label="Icon (emoji)", 
        width=300, 
        height=56,
        expand=False
    )
    group_category_field = ft.Dropdown(
        label="Category",
        width=300,
        options=[
            ft.dropdown.Option("None"),
            ft.dropdown.Option("Bronze"),
            ft.dropdown.Option("Gold"),
            ft.dropdown.Option("Platinum"),
        ],
        value="None"
    )
    group_icon_preview = ft.Image(width=100, height=100, fit=ft.ImageFit.COVER, border_radius=50, visible=False)
    selected_group_icon_data = {"url": None, "data": None}
    
    def pick_group_icon(e):
        group_icon_file_picker.pick_files(
            allowed_extensions=["jpg", "jpeg", "png", "gif", "webp"],
            allow_multiple=False
        )

    
    def on_group_icon_selected(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            try:
                file = e.files[0]
                
                if file.size > MAX_FILE_SIZE:
                    show_snackbar(f"File too large! Max size: {format_file_size(MAX_FILE_SIZE)}")
                    return
                
                with open(file.path, 'rb') as f:
                    file_data = f.read()
                
                show_snackbar("Uploading icon...")
                file_path = f"group_icons/{auth.user_id}_{int(time.time())}_{file.name}"
                success, result = storage.upload_file(file_path, file.name, file_data)
                
                if success:
                    selected_group_icon_data["url"] = result
                    group_icon_preview.src = result
                    group_icon_preview.visible = True
                    group_icon_field.value = ""
                    show_snackbar("Icon uploaded!")
                    page.update()
                else:
                    show_snackbar(f"Upload failed: {result}")
            except Exception as ex:
                show_snackbar(f"Error: {str(ex)}")
    
    group_icon_file_picker.on_result = on_group_icon_selected
    
    def save_group_info(e):
        if not group_name_field.value or not group_desc_field.value:
            show_snackbar("Please fill name and description")
            return
        
        if not current_group_id:
            show_snackbar("No group selected")
            return
        
        icon_value = group_icon_field.value if group_icon_field.value else "👥"
        icon_url = selected_group_icon_data["url"]
        category_value = group_category_field.value or "None"
        
        success = db.update_group_info_by_id(current_group_id, group_name_field.value, group_desc_field.value, icon_value, icon_url, category_value)
        
        if success:
            nonlocal group_info
            group_info = {}
            selected_group_icon_data["url"] = None
            show_snackbar("Group info updated!")
            show_main_menu()
        else:
            show_snackbar("Failed to update group info")
    
    
    def show_create_group():
        """Create a new group (admin only)"""
        stop_auto_refresh()
        navigation_stack.clear()
        navigation_stack.append(show_main_menu)
        page.clean()
        
        new_group_name = ft.TextField(label="Group Name", width=None, expand=True)
        new_group_desc = ft.TextField(label="Description", width=None, expand=True, multiline=True, max_lines=3)
        new_group_icon = ft.TextField(label="Icon (emoji)", width=None, expand=True, value="👥")
        new_group_category = ft.Dropdown(
            label="Category",
            width=None,
            expand=True,
            options=[
                ft.dropdown.Option("None"),
                ft.dropdown.Option("Bronze"),
                ft.dropdown.Option("Gold"),
                ft.dropdown.Option("Platinum"),
            ],
            value="None"
        )
        
        status_text = ft.Text("", size=12, color="blue")
        
        def create_group_action(e):
            if not new_group_name.value or not new_group_desc.value:
                show_snackbar("Please fill in group name and description")
                return
            
            status_text.value = "Creating group..."
            status_text.color = "blue"
            page.update()
            
            # Generate unique group ID
            group_id = f"group_{auth.user_id}_{int(time.time() * 1000)}"
            
            # Create new group in Firebase
            url = f"{FIREBASE_CONFIG['databaseURL']}/groups/{group_id}.json?auth={db.auth_token}"
            
            group_data = {
                "info": {
                    "name": new_group_name.value,
                    "description": new_group_desc.value,
                    "icon": new_group_icon.value or "👥",
                    "icon_url": None,
                    "category": new_group_category.value or "None",
                    "created_by": auth.user_id,
                    "created_at": int(time.time() * 1000)
                },
                "members": {
                    auth.user_id: {
                        "username": current_username,
                        "joined_at": int(time.time() * 1000),
                        "is_admin": True
                    }
                }
            }
            
            try:
                response = requests.put(url, json=group_data, timeout=10)
                
                print(f"Response status: {response.status_code}")
                print(f"Response: {response.text[:200]}")
                
                if response.status_code == 200:
                    status_text.value = "✅ Group created successfully!"
                    status_text.color = "green"
                    page.update()
                    
                    show_snackbar("✅ Group created successfully!")
                    
                    # Clear cache to force refresh
                    try:
                        cache_file = CacheManager.get_cache_file('groups')
                        if cache_file and cache_file.exists():
                            cache_file.unlink()
                    except:
                        pass
                    
                    time.sleep(1)
                    show_main_menu()
                else:
                    error_detail = response.text[:100] if response.text else "Unknown error"
                    status_text.value = f"❌ Failed: {error_detail}"
                    status_text.color = "red"
                    page.update()
                    show_snackbar(f"❌ Failed to create group")
                    print(f"Full error: {response.text}")
                    
            except Exception as ex:
                import traceback
                error_msg = traceback.format_exc()
                print(f"Create group error: {error_msg}")
                status_text.value = f"❌ Error: {str(ex)}"
                status_text.color = "red"
                page.update()
                show_snackbar(f"Error: {str(ex)}")
        
            # Clear cache to force refresh
            CacheManager.save_to_cache('groups', [])
            show_main_menu()
        
        create_group_view = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: handle_back_navigation(e)),
                        ft.Text("Create New Group", size=20, weight="bold", expand=True),
                    ]),
                    padding=ft.padding.only(left=20, right=20, top=40, bottom=20),
                    bgcolor="#E3F2FD"
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Container(height=20),
                        ft.Text("🆕 New Group", size=24, weight="bold"),
                        ft.Container(height=30),
                        new_group_name,
                        ft.Container(height=15),
                        new_group_desc,
                        ft.Container(height=15),
                        new_group_icon,
                        ft.Container(height=15),
                        new_group_category,
                        ft.Container(height=20),
                        status_text,
                        ft.Container(height=10),
                        ft.ElevatedButton(
                            "Create Group",
                            expand=True,
                            bgcolor="#4CAF50",
                            color="white",
                            on_click=create_group_action
                        ),
                        ft.Container(height=10),
                        ft.Text(
                            "Note: Check Firebase console for error details",
                            size=11,
                            color="grey",
                            italic=True
                        )
                    ], horizontal_alignment="center", scroll="auto"),
                    padding=20,
                    expand=True
                )
            ], spacing=0),
            expand=True
        )
        
        page.add(create_group_view)
        page.update()
    
    def create_chat_id(user1_id, user2_id):
        ids = sorted([user1_id, user2_id])
        return f"{ids[0]}_{ids[1]}"
    
    def open_chat(user_data):
        nonlocal current_chat_id, current_chat_user
        current_chat_user = user_data
        # CRITICAL: Create unique chat ID for this specific conversation
        current_chat_id = create_chat_id(auth.user_id, user_data['id'])
        print(f"Opening chat with {user_data.get('username')} - Chat ID: {current_chat_id}")  # Debug
        show_chat_screen()
    
    def load_users():
        users_list.controls.clear()
        
        # Try to load from cache first
        try:
            if USER_LIST_CACHE_FILE.exists():
                with open(USER_LIST_CACHE_FILE, 'r') as f:
                    cached_data = json.load(f)
                    cache_time = cached_data.get('timestamp', 0)
                    
                    # Use cache if less than 5 minutes old
                    if time.time() - cache_time < 300:
                        all_users = cached_data.get('users', [])
                        display_users_from_cache(all_users)
                        
                        # Refresh in background
                        threading.Thread(target=refresh_users_background, daemon=True).start()
                        return
        except:
            pass
        
        # No cache or expired - show loading and fetch
        users_list.controls.append(
            ft.Container(
                content=ft.Row([
                    ft.ProgressRing(width=20, height=20),
                    ft.Text("Loading users...", size=14)
                ], spacing=10),
                padding=20
            )
        )
        page.update()
        
        # Fetch fresh data
        threading.Thread(target=fetch_and_display_users, daemon=True).start()

    def display_users_from_cache(all_users):
        """Display users from cached data immediately"""
        try:
            if not all_users:
                users_list.controls.append(ft.Container(content=ft.Text("No users available"), padding=20))
                page.update()
                return
            
            # Remove duplicates and filter current user
            seen_ids = set()
            other_users = []
            
            for user in all_users:
                user_id = user.get('id')
                if user_id and user_id != auth.user_id and user_id not in seen_ids:
                    seen_ids.add(user_id)
                    other_users.append(user)
            
            if not other_users:
                users_list.controls.append(ft.Container(content=ft.Text("No other users found"), padding=20))
                page.update()
                return
            
            # Sort alphabetically
            other_users.sort(key=lambda u: u.get('username', u.get('email', '')).lower())
            
            # Display all users
            for user in other_users:
                if not user.get('id'):
                    continue
                
                username = user.get('username', user.get('email', 'Unknown').split('@')[0])
                
                # Check for cached avatar
                if user.get('profile_image_url'):
                    cached_path = ImageCache.get_cached_image(user['profile_image_url'], "profile")
                    if cached_path:
                        avatar = ft.Image(src=cached_path, width=50, height=50, fit=ft.ImageFit.COVER, border_radius=25)
                    else:
                        avatar = ft.Container(
                            content=ft.Text(username[0].upper(), size=20, color="white"),
                            width=50, height=50, bgcolor="blue", border_radius=25,
                            alignment=ft.alignment.center
                        )
                        ImageCache.download_image(user['profile_image_url'], None, "profile")
                else:
                    avatar = ft.Container(
                        content=ft.Text(username[0].upper(), size=20, color="white"),
                        width=50, height=50, bgcolor="blue", border_radius=25,
                        alignment=ft.alignment.center
                    )
                
                # Check for pending request (skip for cached display to be faster)
                has_request = False
                
                user_row_content = [
                    avatar,
                    ft.Column([ft.Text(username, size=16, weight="bold")], spacing=2, expand=True)
                ]
                
                if has_request:
                    user_row_content.append(
                        ft.Container(
                            content=ft.Icon(ft.Icons.MAIL, color="white", size=16),
                            bgcolor="#FF5722", border_radius=12, padding=8,
                            tooltip="Message Request"
                        )
                    )
                
                user_btn = ft.Container(
                    content=ft.Row(user_row_content, spacing=15),
                    padding=15,
                    border=ft.border.only(bottom=ft.border.BorderSide(1, "#E0E0E0")),
                    on_click=lambda e, u=user: open_chat(u)
                )
                users_list.controls.append(user_btn)
            
            page.update()
        except Exception as e:
            print(f"Error displaying cached users: {e}")

    def fetch_and_display_users():
        """Fetch users from Firebase and update cache"""
        try:
            all_users = db.get_all_users()
            
            # Save to cache
            try:
                cache_data = {
                    'timestamp': time.time(),
                    'users': all_users
                }
                USER_LIST_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(USER_LIST_CACHE_FILE, 'w') as f:
                    json.dump(cache_data, f)
            except:
                pass
            
            # Clear and display
            users_list.controls.clear()
            display_users_from_cache(all_users)
            
        except Exception as e:
            print(f"Error fetching users: {e}")
            users_list.controls.clear()
            users_list.controls.append(
                ft.Container(
                    content=ft.Text("Error loading users. Please try again.", color="red"),
                    padding=20
                )
            )
            page.update()

    def refresh_users_background():
        """Silently refresh users in background"""
        try:
            all_users = db.get_all_users()
            
            # Update cache
            cache_data = {
                'timestamp': time.time(),
                'users': all_users
            }
            with open(USER_LIST_CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)
            
            # Update UI with fresh data (if still on chat list screen)
            if active_screen.get("current") == "chat_list":
                users_list.controls.clear()
                display_users_from_cache(all_users)
        except Exception as e:
            print(f"Background refresh error: {e}")
    
    # Users list component
    users_list = ft.Column(scroll="auto", expand=True, spacing=10)
    
    # Chat list view definition
    chat_list_view = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.IconButton("arrow_back", on_click=lambda e: handle_back_navigation(e)),
                    ft.Text("Private Chats", size=24, weight="bold", expand=True)
                ], alignment="spaceBetween"),
                padding=ft.padding.only(left=20, right=20, top=40, bottom=20),
                bgcolor="#E3F2FD"
            ),
            users_list
        ], spacing=0),
        expand=True
    )
    
    def show_chat_list():
        stop_auto_refresh()
        active_screen["current"] = "chat_list"  # Set active screen for refresh check
        navigation_stack.append(show_main_menu)
        
        page.clean()
        page.add(chat_list_view)
        page.update()
        
        # Load users (will use cache if available)
        load_users()
    
    
    # Private Chat Screen
    # messages_list and message_input are defined at the top of main()
    
    displayed_message_ids = set()
    current_chat_status = {"status": "pending"}
    
    def show_image_fullscreen(image_url, filename):
        """Show image in fullscreen dialog"""
        def close_dialog(e):
            dialog.open = False
            page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.IconButton(icon="close", on_click=close_dialog, tooltip="Close")
                    ], alignment=ft.MainAxisAlignment.END),
                    ft.Container(
                        content=ft.Image(
                            src=image_url, 
                            fit=ft.ImageFit.CONTAIN,
                        ),
                        expand=True,
                    ),
                ], horizontal_alignment="center", spacing=10),
                width=600,
                height=500,
            ),
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()
    
    def pick_file_private(e):
        print('[DEBUG] pick_file_private clicked')
        try:
            private_chat_file_picker.pick_files(allow_multiple=False)
        except Exception as ex:
            print(f'[ERROR] pick_file_private: {ex}')
            show_snackbar(f'File picker error: {ex}')

    
    def send_message(e=None):
        print('[DEBUG] send_message clicked')
        try:
            if not message_input.value or not message_input.value.strip():
                return
            
            # ADD OFFLINE CHECK:
            if not NetworkChecker.is_online():
                show_snackbar("❌ Cannot send - you're offline")
                return
        
            message_text = message_input.value.strip()
            message_input.value = ""
            page.update()
        
            # Immediately show the message optimistically
            timestamp = datetime.now()
            time_str = timestamp.strftime("%I:%M %p")
        
            message_content = [
                ft.Text(message_text, size=14),
                ft.Row([ft.Text(time_str, size=10)], spacing=2)
            ]
        
            if is_admin or user_is_group_admin:
                message_content.insert(0, ft.Text("👑 ADMIN", size=10, weight="bold", color="#FF6F00"))
        
            message_bubble = ft.Container(
                content=ft.Column(message_content, spacing=2),
                bgcolor="#FFD54F" if (is_admin or user_is_group_admin) else "#BBDEFB",
                border_radius=10,
                padding=10,
                margin=ft.margin.only(left=50, right=0)
            )
        
            messages_list.controls.append(
                ft.Row([message_bubble], alignment="end")
            )
            page.update()
        
            # Send to Firebase in background
            def send_in_background():
                # Check if this is the first message (chat request)
                messages = db.get_messages(current_chat_id)
                is_first_message = len(messages) == 0
            
                if is_first_message:
                    db.set_chat_requester(current_chat_id, auth.user_id)
                    db.update_chat_status(current_chat_id, "pending")
            
                success = db.send_message(
                    current_chat_id, 
                    auth.user_id, 
                    current_username, 
                    message_text,
                    is_admin=(is_admin or user_is_group_admin),
                    seen=False
                )
            
                if success:
                    # Send FCM notification to other user
                    threading.Thread(
                        target=db.send_fcm_notification,
                        args=(
                            current_chat_user['id'],
                            f"💬 {current_username}",
                            message_text[:100],
                            {
                                "chat_id": current_chat_id,
                                "sender_id": auth.user_id,
                                "type": "private_message"
                            }
                        ),
                        daemon=True
                    ).start()
                else:
                    show_snackbar("Failed to send message")
        
            threading.Thread(target=send_in_background, daemon=True).start()
    
        except Exception as ex:
            print(f'[ERROR] send_message: {ex}')
            show_snackbar(f'Message send error: {ex}')

    def on_file_selected_private(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            try:
                file = e.files[0]
                
                if file.size > MAX_FILE_SIZE:
                    show_snackbar(f"File too large! Max: {format_file_size(MAX_FILE_SIZE)}")
                    return
                
                # Generate upload ID
                upload_id = f"upload_{upload_counter['count']}"
                upload_counter['count'] += 1
                
                # Show uploading message immediately
                uploading_files[upload_id] = {
                    "name": file.name,
                    "size": file.size,
                    "status": "uploading"
                }
                
                # Add placeholder message
                add_upload_placeholder(upload_id, file.name, file.size)
                
                # Upload in background
                def upload_thread():
                    with open(file.path, 'rb') as f:
                        file_data = f.read()
                    
                    file_path = f"chat_files/{current_chat_id}/{int(time.time())}_{file.name}"
                    success, result = storage.upload_file(file_path, file.name, file_data)
                    
                    if success:
                        db.send_message(
                            current_chat_id,
                            auth.user_id,
                            current_username,
                            "",
                            is_admin=(is_admin or user_is_group_admin),
                            file_url=result,
                            file_name=file.name,
                            file_size=file.size,
                            seen=False
                        )
                        uploading_files[upload_id]["status"] = "done"
                        time.sleep(0.5)
                        load_messages()
                    else:
                        uploading_files[upload_id]["status"] = "failed"
                        show_snackbar(f"Upload failed: {result}")
                        load_messages()
                
                threading.Thread(target=upload_thread, daemon=True).start()
                
            except Exception as ex:
                show_snackbar(f"Error: {str(ex)}")
    
    private_chat_file_picker.on_result = on_file_selected_private
    
    def add_group_upload_placeholder(upload_id, file_name, file_size):
        """Add uploading placeholder in group chat"""
        is_image = any(file_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'])
        
        if is_image:
            placeholder = ft.Container(
                content=ft.Stack([
                    ft.Container(width=250, height=250, bgcolor="#E0E0E0", border_radius=10),
                    ft.Container(
                        content=ft.Column([
                            ft.ProgressRing(width=30, height=30),
                            ft.Text("Uploading...", size=12)
                        ], horizontal_alignment="center", spacing=5),
                        alignment=ft.alignment.center
                    )
                ]),
                bgcolor="#BBDEFB",
                border_radius=10,
                padding=10
            )
        else:
            placeholder = ft.Container(
                content=ft.Row([
                    ft.ProgressRing(width=20, height=20),
                    ft.Text(f"Uploading {file_name}...", size=12)
                ], spacing=10),
                bgcolor="#BBDEFB",
                border_radius=10,
                padding=10
            )

        group_messages_list.controls.append(
            ft.Row([placeholder], alignment="end")
        )
        page.update()
    
    def add_upload_placeholder(upload_id, file_name, file_size):
        """Add uploading placeholder to chat"""
        is_image = any(file_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'])
        
        if is_image:
            placeholder = ft.Container(
                content=ft.Stack([
                    ft.Container(width=250, height=250, bgcolor="#E0E0E0", border_radius=10),
                    ft.Container(
                        content=ft.Column([
                            ft.ProgressRing(width=30, height=30),
                            ft.Text("Uploading...", size=12)
                        ], horizontal_alignment="center", spacing=5),
                        alignment=ft.alignment.center
                    )
                ]),
                bgcolor="#BBDEFB",
                border_radius=10,
                padding=10
            )
        else:
            placeholder = ft.Container(
                content=ft.Row([
                    ft.ProgressRing(width=20, height=20),
                    ft.Text(f"Uploading {file_name}...", size=12)
                ], spacing=10),
                bgcolor="#BBDEFB",
                border_radius=10,
                padding=10
            )
        
        messages_list.controls.append(ft.Row([placeholder], alignment="end"))
        page.update()
    
    def load_messages():
        """Load messages with offline support"""
        if not current_chat_id:
            return
        
        # Step 1: Try to load from cache first
        cache_key = f"messages_{current_chat_id}"
        cached_messages = CacheManager.load_from_cache(cache_key)
        
        if cached_messages:
            # Show cached messages immediately
            display_messages_ui(cached_messages)
        
        # Step 2: Update from network
        try:
            if NetworkChecker.is_online():
                messages = db.get_messages(current_chat_id)
                
                # Save to cache
                CacheManager.save_to_cache(cache_key, messages)
                
                # Display fresh messages
                display_messages_ui(messages)
            elif not cached_messages:
                messages_list.controls.clear()
                messages_list.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.CLOUD_OFF, size=50, color="orange"),
                            ft.Text("You're offline", size=16, weight="bold"),
                            ft.Text("Connect to load messages", size=12, color="grey"),
                        ], horizontal_alignment="center", spacing=10),
                        padding=40
                    )
                )
                page.update()
        except Exception as e:
            print(f"Message load error: {e}")
            if not cached_messages:
                messages_list.controls.clear()
                messages_list.controls.append(
                    ft.Container(content=ft.Text("Error loading messages", color="red"), padding=20)
                )
                page.update()


    # Add this NEW function - extracts UI logic from load_messages
    def display_messages_ui(messages):
        """Display messages (separated from loading logic)"""
        try:
            # Get chat status
            chat_status = db.get_chat_status(current_chat_id)
            chat_requester = db.get_chat_requester(current_chat_id)
            current_chat_status["status"] = chat_status
            
            current_ids = {msg['id'] for msg in messages}
            
            if current_ids != displayed_message_ids:
                displayed_message_ids.clear()
                displayed_message_ids.update(current_ids)
                
                messages_list.controls.clear()
                
                # Show message request banner if pending
                if chat_status == "pending" and chat_requester and chat_requester != auth.user_id:
                    request_banner = ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.MAIL_OUTLINE, size=40, color="#2196F3"),
                            ], alignment=ft.MainAxisAlignment.CENTER),
                            ft.Text("Message Request", size=18, weight="bold", text_align="center"),
                            ft.Text(f"{current_chat_user.get('username', 'User')} wants to message you", 
                                   size=12, color="grey", text_align="center"),
                            ft.Container(height=10),
                            ft.Row([
                                ft.ElevatedButton(
                                    "Accept",
                                    icon=ft.Icons.CHECK_CIRCLE,
                                    bgcolor="green",
                                    color="white",
                                    on_click=lambda e: accept_chat_request()
                                ),
                                ft.ElevatedButton(
                                    "Delete",
                                    icon=ft.Icons.DELETE,
                                    bgcolor="red",
                                    color="white",
                                    on_click=lambda e: delete_chat_request()
                                )
                            ], alignment=ft.MainAxisAlignment.CENTER, spacing=10)
                        ], horizontal_alignment="center", spacing=5),
                        padding=20,
                        border_radius=10,
                        bgcolor="#E3F2FD",
                        margin=10
                    )
                    messages_list.controls.append(request_banner)
                
                if not messages:
                    if chat_status != "pending" or chat_requester == auth.user_id:
                        messages_list.controls.append(
                            ft.Container(content=ft.Text("No messages yet. Start the conversation!"), padding=20)
                        )
                else:
                    for msg in messages:
                        is_me = msg['sender_id'] == auth.user_id
                        is_msg_admin = msg.get('is_admin', False)
                        timestamp = datetime.fromtimestamp(msg['timestamp'] / 1000)
                        time_str = timestamp.strftime("%I:%M %p")
                        
                        if is_msg_admin:
                            bg_color = "#FFD54F" if is_me else "#FFF176"
                        else:
                            bg_color = "#BBDEFB" if is_me else "#E0E0E0"
                        
                        message_content = []
                        
                        if is_msg_admin:
                            message_content.append(ft.Text("👑 ADMIN", size=10, weight="bold", color="#FF6F00"))
                        
                        if msg.get('file_url'):
                            file_name = msg.get('file_name', 'File')
                            file_size = msg.get('file_size', 0)
                            file_url = msg['file_url']
                            
                            is_image = any(file_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'])
                            
                            if is_image:
                                image_preview = ft.Image(
                                    src=file_url,
                                    width=250,
                                    fit=ft.ImageFit.CONTAIN,
                                    border_radius=10
                                )
                                message_content.append(
                                    ft.Container(
                                        content=image_preview,
                                        on_click=lambda e, url=file_url, name=file_name: show_image_fullscreen(url, name)
                                    )
                                )
                            else:
                                file_button = ft.ElevatedButton(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.ATTACH_FILE, size=16),
                                        ft.Column([
                                            ft.Text(file_name, size=12, weight="bold"),
                                            ft.Text(format_file_size(file_size), size=10)
                                        ], spacing=0)
                                    ], spacing=5),
                                    on_click=lambda e, url=file_url: page.launch_url(url),
                                    style=ft.ButtonStyle(padding=10)
                                )
                                message_content.append(file_button)
                        
                        if msg['text']:
                            message_content.append(ft.Text(msg['text'], size=14))
                        
                        time_row_items = [ft.Text(time_str, size=10)]
                        
                        if is_me:
                            if msg.get('seen', False):
                                time_row_items.append(ft.Text(" • Seen", size=9, color="#4CAF50", weight="bold"))
                            else:
                                time_row_items.append(ft.Text(" • Sent", size=9, color="#757575"))
                        
                        message_content.append(ft.Row(time_row_items, spacing=2))
                        
                        message_bubble = ft.Container(
                            content=ft.Column(message_content, spacing=2),
                            bgcolor=bg_color,
                            border_radius=10,
                            padding=10,
                            margin=ft.margin.only(left=50 if is_me else 0, right=0 if is_me else 50)
                        )
                        
                        messages_list.controls.append(
                            ft.Row([message_bubble], alignment="end" if is_me else "start")
                        )
                
                page.update()
                
                # Mark as seen if accepted
                if chat_status == "accepted":
                    db.mark_messages_as_seen(current_chat_id, auth.user_id)
                    
        except Exception as ex:
            print(f"Error displaying messages: {ex}")
    
    def accept_chat_request():
        """Accept the chat request"""
        success = db.update_chat_status(current_chat_id, "accepted")
        if success:
            current_chat_status["status"] = "accepted"
            show_snackbar("Request accepted!")
            load_messages()
        else:
            show_snackbar("Failed to accept request")
    

    def delete_chat_request():
        """Delete (reject) the chat request"""
        try:
            ok = db.update_chat_status(current_chat_id, "rejected")
            if ok:
                show_snackbar("Request deleted")
            else:
                show_snackbar("Failed to delete request")
        except Exception as e:
            print(f"Error deleting chat request: {e}")
            show_snackbar("Failed to delete request")
        finally:
            back_to_chat_list(None)
    
    def process_private_message_queue():
        """Process queued message updates for private chat"""
        try:
            while not message_queue.empty():
                update = message_queue.get_nowait()
                
                if update['type'] == 'update_messages':
                    # Check if we're still on the same chat
                    if update['chat_id'] == current_chat_id and active_screen["current"] == "private_chat":
                        print(f"[QUEUE] Processing update for private chat {update['chat_id']}")
                        display_messages_ui(update['messages'])
                        page.update()
        except queue.Empty:
            pass
        except Exception as e:
            print(f"[QUEUE ERROR] {e}")
    
    def auto_refresh_messages():
        while refresh_control["active"]:
            try:
                # Process message queue instead of reloading
                process_private_message_queue()
                time.sleep(0.5)
            except:
                pass
    
    def back_to_chat_list(e):
        """Go back from private chat to chat list."""
        print('[DEBUG] back_to_chat_list clicked')
        try:
            stop_auto_refresh()
            stop_message_listener(current_chat_id)  # Stop listener for current chat
            show_chat_list()  # Go directly to chat list
        except Exception as ex:
            print(f'[ERROR] back_to_chat_list: {ex}')
            show_snackbar(f'Back error: {ex}')

    def show_chat_screen():
        nonlocal displayed_message_ids
        
        active_screen["current"] = "private_chat"  # ADD THIS LINE
        
        if current_chat_user:
            # Get user profile for avatar
            user_profile = db.get_user_profile(current_chat_user['id'])
            
            # Create avatar with caching
            if user_profile and user_profile.get('profile_image_url'):
                cached_path = ImageCache.get_cached_image(user_profile['profile_image_url'], "profile")
                
                if cached_path:
                    avatar = ft.Image(
                        src=cached_path, 
                        width=40, 
                        height=40, 
                        fit=ft.ImageFit.COVER, 
                        border_radius=20
                    )
                else:
                    avatar = ft.Container(
                        content=ft.Text(
                            current_chat_user.get('username', 'U')[0].upper(), 
                            size=18, 
                            color="white"
                        ),
                        width=40,
                        height=40,
                        bgcolor="blue",
                        border_radius=20,
                        alignment=ft.alignment.center
                    )
                    
                    # Download in background
                    ImageCache.download_image(user_profile['profile_image_url'], None, "profile")
            else:
                avatar = ft.Container(
                    content=ft.Text(
                        current_chat_user.get('username', 'U')[0].upper(), 
                        size=18, 
                        color="white"
                    ),
                    width=40,
                    height=40,
                    bgcolor="blue",
                    border_radius=20,
                    alignment=ft.alignment.center
                )
            
            # Update chat header with avatar and name
            chat_header.controls.clear()
            chat_header.controls.extend([
                ft.IconButton(ft.Icons.ARROW_BACK, on_click=back_to_chat_list),
                avatar,
                ft.Text(current_chat_user.get('username', current_chat_user['email']), size=18, weight="bold", expand=True),
            ])
        
        # CRITICAL: Clear displayed messages to force fresh load
        displayed_message_ids.clear()
        current_chat_status["status"] = "pending"  # Reset status
        messages_list.controls.clear()  # Clear UI
        
        page.clean()
        page.add(chat_screen)
        
        # Load messages for THIS specific chat
        print(f"Loading messages for chat_id: {current_chat_id}")  # Debug
        load_messages()
        
        # Start real-time listener for this chat
        start_message_listener(current_chat_id, db, page)
        print(f"[DEBUG] Started listener for private chat: {current_chat_id}")
        
        refresh_control["active"] = True
    
    def pick_file_group(e):
        group_chat_file_picker.pick_files(allow_multiple=False)

    
    def on_file_selected_group(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            try:
                if not current_group_id:
                    show_snackbar("No group selected")
                    return
                
                file = e.files[0]
                
                if file.size > MAX_FILE_SIZE:
                    show_snackbar(f"File too large! Max: {format_file_size(MAX_FILE_SIZE)}")
                    return

                upload_id = f"group_upload_{int(time.time())}"
                uploading_files[upload_id] = {
                    "name": file.name,
                    "size": file.size,
                    "status": "uploading"
                }

                add_group_upload_placeholder(upload_id, file.name, file.size)

                def upload_thread():
                    with open(file.path, 'rb') as f:
                        file_data = f.read()

                    file_path = f"group_files/{current_group_id}/{int(time.time())}_{file.name}"
                    success, result = storage.upload_file(file_path, file.name, file_data)

                    if success:
                        db.send_group_message_by_id(
                            current_group_id,
                            auth.user_id,
                            current_username,
                            "",
                            is_admin=(is_admin or user_is_group_admin),
                            file_url=result,
                            file_name=file.name,
                            file_size=file.size
                        )
                        uploading_files[upload_id]["status"] = "done"
                        time.sleep(1)  # Give time for message to be written to DB
                        page.update()  # Auto-refresh will pick it up
                    else:
                        uploading_files[upload_id]["status"] = "failed"
                        show_snackbar(f"Upload failed: {result}")
                        page.update()

                threading.Thread(target=upload_thread, daemon=True).start()

            except Exception as ex:
                show_snackbar(f"Error: {str(ex)}")
                
    group_chat_file_picker.on_result = on_file_selected_group            
    
    def send_group_message(e=None):
        print('[DEBUG] send_group_message clicked')
        try:
            if not group_message_input.value or not group_message_input.value.strip():
                return
            
            if not NetworkChecker.is_online():
                show_snackbar("❌ Cannot send - you're offline")
                return
        
            if not current_group_id:
                show_snackbar("No group selected")
                return
        
            message_text = group_message_input.value.strip()
            group_message_input.value = ""
            page.update()
        
            timestamp = datetime.now()
            time_str = timestamp.strftime("%I:%M %p")
        
            message_content = []
        
            if is_admin or user_is_group_admin:
                message_content.append(ft.Text("👑 ADMIN", size=10, weight="bold", color="#FF6F00"))
        
            message_content.extend([
                ft.Text(message_text, size=14),
                ft.Text(time_str, size=10)
            ])
        
            message_bubble = ft.Container(
                content=ft.Column(message_content, spacing=2),
                bgcolor="#FFD54F" if (is_admin or user_is_group_admin) else "#BBDEFB",
                border_radius=10,
                padding=10,
                margin=ft.margin.only(left=50, right=0)
            )
        
            group_messages_list.controls.append(
                ft.Row([message_bubble], alignment="end")
            )
            page.update()
        
            def send_in_background():
                success = db.send_group_message_by_id(
                    current_group_id,
                    auth.user_id, 
                    current_username, 
                    message_text,
                    is_admin=(is_admin or user_is_group_admin)
                )
            
                if not success:
                    show_snackbar("Failed to send message")
        
            threading.Thread(target=send_in_background, daemon=True).start()
    
        except Exception as ex:
            print(f'[ERROR] send_group_message: {ex}')
            show_snackbar(f'Group send error: {ex}')

    def back_to_main_menu(e):
        """Back from group chat to main menu using navigation stack."""
        print('[DEBUG] back_to_main_menu clicked')
        try:
            stop_auto_refresh()
            handle_back_navigation(e)
        except Exception as ex:
            print(f'[ERROR] back_to_main_menu: {ex}')
            show_snackbar(f'Back error: {ex}')

  
    group_chat_screen = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Column([
                    group_chat_header
                ], spacing=5),
                padding=ft.padding.only(left=10, right=10, top=30, bottom=10),
                bgcolor="#E3F2FD"
            ),
            ft.Container(content=group_messages_list, padding=20, expand=True),
            ft.Container(
                content=ft.Row([
                    ft.IconButton("attach_file", on_click=pick_file_group, tooltip="Attach file"),
                    group_message_input,
                    ft.ElevatedButton("Send", bgcolor="blue", color="white", on_click=send_group_message)
                ], spacing=10),
                padding=10
            )
        ], spacing=0),
        expand=True
    )
    
    # =============================
    # Message Queue Processor (replaces timer)
    # =============================
    def queue_checker():
        """Background thread to trigger UI updates when messages arrive"""
        while True:
            try:
                time.sleep(0.5)  # Check twice per second
                if not message_queue.empty():
                    # Process queue on next page update
                    try:
                        page.update()
                    except:
                        pass
            except Exception as e:
                print(f"[QUEUE CHECKER ERROR] {e}")
    
    # Start queue checker thread
    threading.Thread(target=queue_checker, daemon=True).start()
    print("[DEBUG] Message queue processor started")

    # Cleanup on page close
    def on_page_close(e):
        """Cleanup when page closes"""
        print("[CLEANUP] Stopping all listeners...")
        stop_all_listeners()
    
    page.on_close = on_page_close

    # Show startup screen (it already cleans page)
    show_startup_screen()
    page.update()

    # 🚫 IMPORTANT: DO NOT use a background thread here
    # Run auto-login on the main UI thread
    check_auto_login()

if __name__ == "__main__":
    ft.app(target=main)