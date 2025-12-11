import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import threading
import json
import os
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
import socket
import smtplib
import random
import string
import re
import hashlib
import uuid
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import gspread
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from secrets_util import get_encrypted_gspread_client
# --- Top of Authenticator.py ---

import google.auth
from google.cloud import secretmanager

from secrets_util import get_secret, ONLINE


# Try loading from specific path
import pathlib
env_file_path = pathlib.Path('.env')
print(f"[DEBUG] .env file exists at {env_file_path.absolute()}: {env_file_path.exists()}")
if env_file_path.exists():
    load_dotenv(env_file_path)
   

if ONLINE:
    # Google OAuth
    GOOGLE_CLIENT_ID = get_secret("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = get_secret("GOOGLE_CLIENT_SECRET")
else:
    GOOGLE_CLIENT_ID = GOOGLE_CLIENT_SECRET = None
    print("[OFFLINE] Skipping Google OAuth secrets")

# OAuth URLs (no network needed)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USER_INFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"

if ONLINE:
    # Email / SMTP
    SMTP_SERVER = get_secret("SMTP_SERVER") or "smtp.gmail.com"
    SMTP_PORT = int(get_secret("SMTP_PORT") or "587")
    EMAIL_USER = get_secret("EMAIL_USER")
    EMAIL_PASSWORD = get_secret("EMAIL_PASSWORD")
else:
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    EMAIL_USER = EMAIL_PASSWORD = None
    print("[OFFLINE] Skipping SMTP secrets")

if ONLINE:
    # Google Sheets
    SHEET_ID = get_secret("LB_SHEET_ID")
    if not SHEET_ID:
        # ⚠ Do NOT crash – just log and run without online sheet
        print("⚠ [AUTH] LB_SHEET_ID secret missing or fetch failed. "
              "Running without online user sheet for now.")
    WORKSHEET_NAME = get_secret("USER_WORKSHEET") or "UserAccounts"
else:
    SHEET_ID = None
    WORKSHEET_NAME = "UserAccounts"
    print("[OFFLINE] Skipping Google Sheets secrets")

# Simple flag to know if sheet features are enabled
SHEETS_ENABLED = bool(SHEET_ID)

def get_free_port():
    """Get a free port on localhost"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback from Google"""
    def do_GET(self):
        try:
            query = urlparse(self.path).query
            params = parse_qs(query)
            
            print(f"[CALLBACK] Received: {self.path}")
            
            if 'error' in params:
                # Handle OAuth errors
                error = params['error'][0]
                error_description = params.get('error_description', ['Unknown error'])[0]
                print(f"[CALLBACK] OAuth error: {error} - {error_description}")
                
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                error_html = f"""
                    <html>
                    <body style="font-family: Arial; text-align: center; padding: 50px;">
                        <h2 style="color: red;">Authentication Error</h2>
                        <p>Error: {error}</p>
                        <p>{error_description}</p>
                        <p>Please close this window and try again.</p>
                    </body>
                    </html>
                """
                self.wfile.write(error_html.encode())
                return
            
            if 'code' in params:
                self.server.auth_code = params['code'][0]
                print(f"[CALLBACK] Authorization code received: {self.server.auth_code[:10]}...")
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                success_html = """
                    <html>
                    <head>
                        <style>
                            body {
                                font-family: Arial, sans-serif;
                                display: flex;
                                justify-content: center;
                                align-items: center;
                                height: 100vh;
                                margin: 0;
                                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            }
                            .container {
                                background: white;
                                padding: 40px;
                                border-radius: 10px;
                                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                                text-align: center;
                            }
                            .checkmark {
                                font-size: 60px;
                                color: #4CAF50;
                                animation: scale 0.5s ease-in-out;
                            }
                            @keyframes scale {
                                0% { transform: scale(0); }
                                50% { transform: scale(1.2); }
                                100% { transform: scale(1); }
                            }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="checkmark">✓</div>
                            <h2>Authentication Successful!</h2>
                            <p>You can close this window and return to the application.</p>
                        </div>
                        <script>setTimeout(function() { window.close(); }, 3000);</script>
                    </body>
                    </html>
                """
                self.wfile.write(success_html.encode())
            else:
                print("[CALLBACK] No authorization code received")
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"No authorization code received")
                
        except Exception as e:
            print(f"[CALLBACK] Error handling callback: {e}")
            self.send_response(500)
            self.end_headers()
            
    def log_message(self, format, *args):
        # Only log errors
        if "error" in format.lower():
            print(f"[CALLBACK] {format % args}")

class UnifiedAuthSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("Welcome - Sign In")
        self.root.geometry("500x700")
        self.root.resizable(False, False)
        
        # Storage paths
        self.appdata_path = os.path.join(os.getenv('APPDATA'), 'StudyTimer')
        self.user_config_file = os.path.join(self.appdata_path, 'user_config.json')
        os.makedirs(self.appdata_path, exist_ok=True)
        
        # User data
        self.user_data = None
        self.temp_registration = {}
        self.current_otp = None
        self.current_email = None
        
        # Google Sheets client
        self.gspread_client = None
        self.sheet_id = SHEET_ID
        self.worksheet_name = WORKSHEET_NAME
        
        # Debug info
        print(f"[AUTH] Using Sheet ID: {self.sheet_id}")
        print(f"[AUTH] Using Worksheet: {self.worksheet_name}")
        
        # Setup styles
        self.setup_styles()
        
        # Test Google Sheets connection
        self.test_sheets_connection()
        
        # Check existing login
        if self.check_existing_login():
            self.show_main_app()
        else:
            self.show_unified_auth_page()
        self.gspread_client = None
        
    def save_profile_data(self, profile_dict, app_paths_instance=None):
        """Save profile data AND all app data files to UserAccounts sheet"""
        try:
            client = self.get_gspread_client()
            if not client:
                print("[AUTH] No Google Sheets client available.")
                return

            # 🔁 If we don't have sheet_id yet, try to (re)fetch it once here
            if not getattr(self, "sheet_id", None):
                try:
                    from secrets_util import get_secret, ONLINE
                    if ONLINE:
                        new_id = get_secret("LB_SHEET_ID")
                        if new_id:
                            self.sheet_id = new_id
                            print(f"[AUTH] LB_SHEET_ID fetched on demand: {self.sheet_id}")
                        else:
                            print("[AUTH] LB_SHEET_ID still missing; "
                                  "skipping this cloud sheet operation.")
                            return
                    else:
                        print("[AUTH] Offline; skipping this cloud sheet operation.")
                        return
                except Exception as e:
                    print(f"[AUTH] Error while re-fetching LB_SHEET_ID: {e}")
                    return

            # ✅ Only reach here if we have a valid sheet_id
            sheet = client.open_by_key(self.sheet_id)
            worksheet = sheet.worksheet(self.worksheet_name)
            
            # Define all columns we need
            all_columns = [
                'profile_json',
                'wastage_log_csv', 
                'total_studied_time_json',
                'wastage_by_day_json',
                'studied_today_time_json',
                'exam_date_json',
                'opened_days_txt',
                'goal_config_json',
                'plans_json'  # ADD THIS LINE
            ]
            
            # Check and add missing columns
            headers = worksheet.row_values(1)
            for col_name in all_columns:
                if col_name not in headers:
                    new_col_index = len(headers) + 1
                    worksheet.update_cell(1, new_col_index, col_name)
                    headers.append(col_name)
                    print(f"Added column: {col_name}")
            
            # Prepare all data to save
            data_to_save = {}
            
            # 1. Profile JSON
            data_to_save['profile_json'] = json.dumps(profile_dict, indent=2)
            
            # 2. Read all other app data files if app_paths is provided
            if app_paths_instance:
                print("Reading app data files...")
                
                # Wastage log CSV
                try:
                    if os.path.exists(app_paths_instance.wastage_file):
                        with open(app_paths_instance.wastage_file, 'r', encoding='utf-8') as f:
                            data_to_save['wastage_log_csv'] = f.read()
                        print(f"Read wastage log: {len(data_to_save['wastage_log_csv'])} characters")
                    else:
                        data_to_save['wastage_log_csv'] = ''
                        print("No wastage log file found")
                except Exception as e:
                    print(f"Error reading wastage log: {e}")
                    data_to_save['wastage_log_csv'] = ''
                
                # Total studied time JSON
                try:
                    if os.path.exists(app_paths_instance.study_total_file):
                        with open(app_paths_instance.study_total_file, 'r', encoding='utf-8') as f:
                            data_to_save['total_studied_time_json'] = f.read()
                        print(f"Read total study time: {len(data_to_save['total_studied_time_json'])} characters")
                    else:
                        data_to_save['total_studied_time_json'] = '{}'
                        print("No total study time file found")
                except Exception as e:
                    print(f"Error reading total study time: {e}")
                    data_to_save['total_studied_time_json'] = '{}'
                
                # Wastage by day JSON
                try:
                    if os.path.exists(app_paths_instance.wastage_day_file):
                        with open(app_paths_instance.wastage_day_file, 'r', encoding='utf-8') as f:
                            data_to_save['wastage_by_day_json'] = f.read()
                        print(f"Read wastage by day: {len(data_to_save['wastage_by_day_json'])} characters")
                    else:
                        data_to_save['wastage_by_day_json'] = '{}'
                        print("No wastage by day file found")
                except Exception as e:
                    print(f"Error reading wastage by day: {e}")
                    data_to_save['wastage_by_day_json'] = '{}'
                
                # Studied today JSON
                try:
                    if os.path.exists(app_paths_instance.study_today_file):
                        with open(app_paths_instance.study_today_file, 'r', encoding='utf-8') as f:
                            data_to_save['studied_today_time_json'] = f.read()
                        print(f"Read studied today: {len(data_to_save['studied_today_time_json'])} characters")
                    else:
                        data_to_save['studied_today_time_json'] = '{}'
                        print("No studied today file found")
                except Exception as e:
                    print(f"Error reading studied today: {e}")
                    data_to_save['studied_today_time_json'] = '{}'
                
                # Exam date JSON
                try:
                    if os.path.exists(app_paths_instance.exam_date_file):
                        with open(app_paths_instance.exam_date_file, 'r', encoding='utf-8') as f:
                            data_to_save['exam_date_json'] = f.read()
                        print(f"Read exam date: {len(data_to_save['exam_date_json'])} characters")
                    else:
                        data_to_save['exam_date_json'] = '{}'
                        print("No exam date file found")
                except Exception as e:
                    print(f"Error reading exam date: {e}")
                    data_to_save['exam_date_json'] = '{}'
                
                # Opened days TXT
                try:
                    if os.path.exists(app_paths_instance.opened_days_file):
                        with open(app_paths_instance.opened_days_file, 'r', encoding='utf-8') as f:
                            data_to_save['opened_days_txt'] = f.read()
                        print(f"Read opened days: {len(data_to_save['opened_days_txt'])} characters")
                    else:
                        data_to_save['opened_days_txt'] = ''
                        print("No opened days file found")
                except Exception as e:
                    print(f"Error reading opened days: {e}")
                    data_to_save['opened_days_txt'] = ''
                
                # Goal config JSON
                try:
                    if os.path.exists(app_paths_instance.goal_config_file):
                        with open(app_paths_instance.goal_config_file, 'r', encoding='utf-8') as f:
                            data_to_save['goal_config_json'] = f.read()
                        print(f"Read goal config: {len(data_to_save['goal_config_json'])} characters")
                    else:
                        data_to_save['goal_config_json'] = '{}'
                        print("No goal config file found")
                except Exception as e:
                    print(f"Error reading goal config: {e}")
                    data_to_save['goal_config_json'] = '{}'
                    
                try:
                    if os.path.exists(app_paths_instance.plans_file):  # Make sure you have this property in AppPaths
                        with open(app_paths_instance.plans_file, 'r', encoding='utf-8') as f:
                            data_to_save['plans_json'] = f.read()
                        print(f"Read plans: {len(data_to_save['plans_json'])} characters")
                    else:
                        data_to_save['plans_json'] = '{}'
                        print("No plans file found")
                except Exception as e:
                    print(f"Error reading plans: {e}")
                    data_to_save['plans_json'] = '{}'
            else:
                print("No app_paths provided - only saving profile")
                # Set empty values for all other columns
                data_to_save['wastage_log_csv'] = ''
                data_to_save['total_studied_time_json'] = '{}'
                data_to_save['wastage_by_day_json'] = '{}'
                data_to_save['studied_today_time_json'] = '{}'
                data_to_save['exam_date_json'] = '{}'
                data_to_save['opened_days_txt'] = ''
                data_to_save['goal_config_json'] = '{}'
            
            # Find user's row
            records = worksheet.get_all_records()
            user_uid = self.user_data.get('uid')
            user_row = None
            
            for i, record in enumerate(records, start=2):
                if record.get('uid') == user_uid:
                    user_row = i
                    break
            
            if user_row:
                # Update all data columns for this user
                headers = worksheet.row_values(1)
                
                for col_name, data_content in data_to_save.items():
                    if col_name in headers:
                        col_index = headers.index(col_name) + 1
                        try:
                            worksheet.update_cell(user_row, col_index, data_content)
                            print(f"Updated {col_name}: {len(str(data_content))} characters")
                        except Exception as e:
                            print(f"Error updating {col_name}: {e}")
                
                print(f"Saved profile + all app data for user in row {user_row}")
            else:
                print("User not found in UserAccounts sheet")
            
            print("Profile and all app data saved to UserAccounts sheet!")
            
        except Exception as e:
            print(f"Error saving profile and app data: {e}")
            import traceback
            traceback.print_exc()

    def load_profile_from_sheet(self, app_paths_instance=None):
        """Load profile with REAL security - auto-generate machine fingerprint"""
        try:
            client = self.get_gspread_client()
            if not client:
                print("[AUTH] No Google Sheets client available.")
                return

            # 🔁 If we don't have sheet_id yet, try to (re)fetch it once here
            if not getattr(self, "sheet_id", None):
                try:
                    from secrets_util import get_secret, ONLINE
                    if ONLINE:
                        new_id = get_secret("LB_SHEET_ID")
                        if new_id:
                            self.sheet_id = new_id
                            print(f"[AUTH] LB_SHEET_ID fetched on demand: {self.sheet_id}")
                        else:
                            print("[AUTH] LB_SHEET_ID still missing; "
                                  "skipping this cloud sheet operation.")
                            return
                    else:
                        print("[AUTH] Offline; skipping this cloud sheet operation.")
                        return
                except Exception as e:
                    print(f"[AUTH] Error while re-fetching LB_SHEET_ID: {e}")
                    return

            # ✅ Only reach here if we have a valid sheet_id
            sheet = client.open_by_key(self.sheet_id)
            worksheet = sheet.worksheet(self.worksheet_name)
            
            # Get current user info
            current_email = self.user_data.get('email')
            
            # SECURITY FIX: Generate fingerprint from ACTUAL system, not user data
            current_machine_fp = self.generate_machine_fingerprint()
            
            print(f"=== REAL SECURITY CHECK ===")
            print(f"Current email: {current_email}")
            print(f"Machine fingerprint (auto-generated): {current_machine_fp}")
            
            # Check email and machine fingerprint match
            records = worksheet.get_all_records()
            user_record = None
            access_granted = False
            
            for record in records:
                sheet_email = record.get('email', '')
                sheet_machine_fp = record.get('machine_fingerprint', '')
                
                if sheet_email == current_email:
                    print(f"Found user record with email: {sheet_email}")
                    print(f"Stored machine FP: {sheet_machine_fp}")
                    print(f"Current machine FP: {current_machine_fp}")
                    
                    # REAL security check
                    if sheet_machine_fp == current_machine_fp:
                        print("✓ Email and machine fingerprint match - ACCESS GRANTED")
                        user_record = record
                        access_granted = True
                        break
                    else:
                        print("⚠ Machine fingerprint MISMATCH - ACCESS DENIED")
                        print("This device is not authorized for this account")
                        return None
            
            if not access_granted:
                print("⚠ No authorized device record found - ACCESS DENIED")
                return None
            
            # Security passed - proceed with file operations
            profile_data = None
            files_to_restore = []
            
            if app_paths_instance:
                file_mappings = {
                    'profile_json': app_paths_instance.profile_file,
                    'wastage_log_csv': app_paths_instance.wastage_file,
                    'total_studied_time_json': app_paths_instance.study_total_file,
                    'wastage_by_day_json': app_paths_instance.wastage_day_file,
                    'studied_today_time_json': app_paths_instance.study_today_file,
                    'exam_date_json': app_paths_instance.exam_date_file,
                    'opened_days_txt': app_paths_instance.opened_days_file,
                    'goal_config_json': app_paths_instance.goal_config_file,
                    'plans_json': app_paths_instance.plans_file
                }
                
                missing_files = []
                for column_name, file_path in file_mappings.items():
                    if not os.path.exists(file_path):
                        missing_files.append(os.path.basename(file_path))
                        files_to_restore.append((column_name, file_path))
                
                if missing_files:
                    print(f"Missing files to restore: {', '.join(missing_files)}")
                else:
                    print("All files exist locally")
            
            # Handle profile
            if os.path.exists(app_paths_instance.profile_file):
                try:
                    with open(app_paths_instance.profile_file, 'r', encoding='utf-8') as f:
                        profile_data = json.load(f)
                        print("Using existing local profile")
                except Exception as e:
                    print(f"Error reading local profile: {e}")
            else:
                if user_record.get('profile_json'):
                    try:
                        profile_data = json.loads(user_record['profile_json'])
                        print("Loaded profile from cloud")
                    except json.JSONDecodeError as e:
                        print(f"Error parsing cloud profile: {e}")
                        profile_data = {}
            
            # Restore missing files
            if files_to_restore:
                print(f"Restoring {len(files_to_restore)} missing files...")
                files_restored = 0
                
                for column_name, file_path in files_to_restore:
                    if user_record.get(column_name):
                        try:
                            os.makedirs(os.path.dirname(file_path), exist_ok=True)
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write(user_record[column_name])
                            files_restored += 1
                            print(f"✓ Restored {os.path.basename(file_path)}")
                        except Exception as e:
                            print(f"✗ Error restoring {column_name}: {e}")
                    else:
                        print(f"⚠ No cloud data for {os.path.basename(file_path)}")
                
                print(f"Successfully restored {files_restored} files")
            
            return profile_data
            
        except Exception as e:
            print(f"Error in security check: {e}")
            return None
    
    def test_sheets_connection(self):
        """Test Google Sheets connection at startup"""
        print("[AUTH] Testing Google Sheets connection...")
        client = self.get_gspread_client()
        if client:
            try:
                sheet = client.open_by_key(self.sheet_id)
                print(f"✓ [AUTH] Successfully connected to sheet: {sheet.title}")
                
                # List existing worksheets
                worksheets = sheet.worksheets()
                worksheet_names = [ws.title for ws in worksheets]
                print(f"[AUTH] Existing worksheets: {worksheet_names}")
                
                if self.worksheet_name not in worksheet_names:
                    print(f"[AUTH] Worksheet '{self.worksheet_name}' does not exist - will create on first user save")
                else:
                    print(f"✓ [AUTH] Worksheet '{self.worksheet_name}' already exists")
                    
            except Exception as e:
                print(f"⚠ [AUTH] Failed to test connection: {e}")
        else:
            print("⚠ [AUTH] Failed to establish connection")
    
    def setup_styles(self):
        """Configure styles for professional look"""
        style = ttk.Style()
        style.theme_use('clam')
        
        self.bg_color = "#f5f5f5"
        self.primary_color = "#4285f4"
        self.email_color = "#00BCD4"
        self.text_color = "#333333"
        self.white = "#ffffff"
        
        self.root.configure(bg=self.bg_color)
    
    def get_gspread_client(self):
        # 🛡 Check if attribute exists or is None
        if not hasattr(self, "gspread_client") or not self.gspread_client:
            from secrets_util import get_encrypted_gspread_client, ONLINE

            # 📴 If offline, don't try to create it
            if not ONLINE:
                print("[GSPREAD] Offline mode - skipping client creation")
                self.gspread_client = None
                return None

            # 🌐 Online: initialize gspread client
            self.gspread_client = get_encrypted_gspread_client()

        return self.gspread_client
    
    def generate_machine_fingerprint(self):
        """Generate unique machine fingerprint"""
        import platform
        try:
            system_info = f"{platform.system()}-{platform.machine()}-{platform.processor()}"
            hostname = platform.node()
            fingerprint_data = f"{system_info}-{hostname}"
            fingerprint = hashlib.md5(fingerprint_data.encode()).hexdigest()[:16]
            return fingerprint
        except:
            return str(uuid.uuid4())[:16]
    
    def check_existing_login(self):
        """Check for existing login locally and in Google Sheets"""
        # First check local file
        if os.path.exists(self.user_config_file):
            try:
                with open(self.user_config_file, 'r') as f:
                    self.user_data = json.load(f)
                    
                    # Verify with Google Sheets if possible
                    if self.verify_with_sheet():
                        return True
                    else:
                        # Local data exists but not in sheet, still allow
                        return True
            except:
                pass
        
        # If no local data, try to recover from Google Sheets using machine fingerprint
        machine_fp = self.generate_machine_fingerprint()
        user_from_sheet = self.get_user_from_sheet(machine_fingerprint=machine_fp)
        
        if user_from_sheet:
            self.user_data = user_from_sheet
            self.save_user_data_locally()
            return True
        
        return False
    
    def verify_with_sheet(self):
        """Verify user data with Google Sheet"""
        try:
            client = self.get_gspread_client()
            if not client:
                print("[AUTH] No Google Sheets client available.")
                return

            # 🔁 If we don't have sheet_id yet, try to (re)fetch it once here
            if not getattr(self, "sheet_id", None):
                try:
                    from secrets_util import get_secret, ONLINE
                    if ONLINE:
                        new_id = get_secret("LB_SHEET_ID")
                        if new_id:
                            self.sheet_id = new_id
                            print(f"[AUTH] LB_SHEET_ID fetched on demand: {self.sheet_id}")
                        else:
                            print("[AUTH] LB_SHEET_ID still missing; "
                                  "skipping this cloud sheet operation.")
                            return
                    else:
                        print("[AUTH] Offline; skipping this cloud sheet operation.")
                        return
                except Exception as e:
                    print(f"[AUTH] Error while re-fetching LB_SHEET_ID: {e}")
                    return

            # ✅ Only reach here if we have a valid sheet_id
            sheet = client.open_by_key(self.sheet_id)
            worksheet = sheet.worksheet(self.worksheet_name)
            
            # Get all records and check if user exists
            records = worksheet.get_all_records()
            
            for record in records:
                if (record.get('email') == self.user_data.get('email') or 
                    record.get('uid') == self.user_data.get('uid')):
                    # Update local data with sheet data
                    self.user_data.update(record)
                    return True
            
            return False
            
        except:
            return True  # On error, trust local data
    
    def get_user_from_sheet(self, email=None, machine_fingerprint=None):
        """Get user data from Google Sheet"""
        try:
            client = self.get_gspread_client()
            if not client:
                return None
            
            sheet = client.open_by_key(self.sheet_id)
            
            # Create worksheet if doesn't exist
            try:
                worksheet = sheet.worksheet(self.worksheet_name)
            except:
                worksheet = sheet.add_worksheet(title=self.worksheet_name, rows="1000", cols="20")
                headers = ["uid", "email", "name", "auth_method", "machine_fingerprint", 
                          "created_at", "last_login", "google_id", "picture", "status"]
                worksheet.append_row(headers)
                return None
            
            records = worksheet.get_all_records()
            
            for record in records:
                if email and record.get('email') == email:
                    return record
                if machine_fingerprint and record.get('machine_fingerprint') == machine_fingerprint:
                    return record
            
            return None
            
        except Exception as e:
            print(f"Error getting user from sheet: {e}")
            return None
    
    def save_user_to_sheet(self, update_only: bool = False):
        """Save user with auto-generated machine fingerprint.

        Args:
            update_only: When True, update an existing row but do not append a new one.
        """
        try:
            client = self.get_gspread_client()
            if not client:
                return True
            
            sheet = client.open_by_key(self.sheet_id)
            
            try:
                worksheet = sheet.worksheet(self.worksheet_name)
            except:
                worksheet = sheet.add_worksheet(title=self.worksheet_name, rows=1000, cols=15)
                headers = ["uid", "email", "name", "auth_method", "machine_fingerprint", 
                          "created_at", "last_login", "google_id", "picture", "status", "profile_json"]
                worksheet.append_row(headers)
            
            # Check if user exists
            records = worksheet.get_all_records()
            user_row = None

            for i, record in enumerate(records, start=2):
                if record.get('email') == self.user_data.get('email'):
                    user_row = i
                    break
            
            # SECURITY FIX: Generate REAL machine fingerprint
            real_machine_fp = self.generate_machine_fingerprint()
            
            # Prepare row data with REAL fingerprint
            row_data = [
                self.user_data.get('uid', ''),
                self.user_data.get('email', ''),
                self.user_data.get('name', ''),
                self.user_data.get('auth_method', ''),
                real_machine_fp,  # Use REAL fingerprint, not user data
                self.user_data.get('created_at', datetime.now().isoformat()),
                datetime.now().isoformat(),
                self.user_data.get('google_id', ''),
                self.user_data.get('picture', ''),
                'active',
                '{}'  # Empty profile initially
            ]
            
            if user_row:
                # Update existing row
                for i, value in enumerate(row_data[:-1], start=1):
                    worksheet.update_cell(user_row, i, value)
                print(f"✓ Updated user with real machine fingerprint: {real_machine_fp}")
            elif update_only:
                # Respect login-only creation rule
                print("[AUTH] Skipping user creation (update-only mode)")
                return True
            else:
                # Add new row
                worksheet.append_row(row_data)
                print(f"✓ Added user with real machine fingerprint: {real_machine_fp}")
            
            # Update user_data with real fingerprint
            self.user_data['machine_fingerprint'] = real_machine_fp
            
            return True
            
        except Exception as e:
            print(f"Error saving user: {e}")
            return True
    
    def save_user_data_locally(self):
        """Save user data locally"""
        try:
            with open(self.user_config_file, 'w') as f:
                json.dump(self.user_data, f, indent=2)
            print("✓ [AUTH] User data saved locally")
            return True
        except Exception as e:
            print(f"⚠ [AUTH] Error saving locally: {e}")
            return False
    
    def show_unified_auth_page(self):
        """Show unified authentication page with all options"""
        # Clear window
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Main container
        main_frame = tk.Frame(self.root, bg=self.white)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)
        
        # Logo/App Name
        logo_frame = tk.Frame(main_frame, bg=self.white)
        logo_frame.pack(pady=(20, 30))
        
        app_name = tk.Label(logo_frame, text="Your App Name",
                           font=('Arial', 28, 'bold'),
                           bg=self.white, fg=self.text_color)
        app_name.pack()
        
        tagline = tk.Label(logo_frame, text="Welcome back",
                          font=('Arial', 12),
                          bg=self.white, fg="#666666")
        tagline.pack(pady=(5, 0))
        
        # Separator
        tk.Frame(main_frame, height=1, bg="#e0e0e0").pack(fill=tk.X, pady=20)
        
        # Google Sign-up Button
        google_btn = tk.Button(main_frame,
                              text="  🔷  Continue with Google",
                              font=('Arial', 12, 'bold'),
                              bg=self.primary_color,
                              fg=self.white,
                              activebackground="#357ae8",
                              activeforeground=self.white,
                              bd=0,
                              padx=30,
                              pady=12,
                              cursor="hand2",
                              command=self.initiate_google_signin)
        google_btn.pack(fill=tk.X, pady=10)
        
        # OR separator
        or_frame = tk.Frame(main_frame, bg=self.white)
        or_frame.pack(pady=20, fill=tk.X)
        
        tk.Frame(or_frame, height=1, bg="#e0e0e0").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        tk.Label(or_frame, text="OR", bg=self.white, fg="#999999", font=('Arial', 10)).pack(side=tk.LEFT)
        tk.Frame(or_frame, height=1, bg="#e0e0e0").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        
        # Email section
        email_frame = tk.Frame(main_frame, bg=self.white)
        email_frame.pack(fill=tk.X, pady=10)
        
        tk.Label(email_frame, text="Email address:",
                font=('Arial', 11), bg=self.white).pack(anchor='w', pady=(0, 5))
        
        self.email_var = tk.StringVar()
        self.email_entry = tk.Entry(email_frame, textvariable=self.email_var,
                                   font=('Arial', 12), bd=1, relief="solid")
        self.email_entry.pack(fill=tk.X, pady=(0, 10))
        
        # Sign in / Sign up buttons
        button_frame = tk.Frame(email_frame, bg=self.white)
        button_frame.pack(fill=tk.X)
        
        signin_btn = tk.Button(button_frame,
                              text="Sign In",
                              font=('Arial', 11, 'bold'),
                              bg=self.email_color,
                              fg=self.white,
                              bd=0,
                              padx=20,
                              pady=10,
                              cursor="hand2",
                              command=self.handle_email_signin)
        signin_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        signup_btn = tk.Button(button_frame,
                              text="Sign Up",
                              font=('Arial', 11, 'bold'),
                              bg="#4CAF50",
                              fg=self.white,
                              bd=0,
                              padx=20,
                              pady=10,
                              cursor="hand2",
                              command=self.show_signup_form)
        signup_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # Terms and Privacy
        terms_frame = tk.Frame(main_frame, bg=self.white)
        terms_frame.pack(pady=(30, 10))
        
        terms_text = tk.Label(terms_frame,
                            text="By continuing, you agree to our Terms of Service\nand Privacy Policy",
                            font=('Arial', 9),
                            bg=self.white,
                            fg="#999999",
                            justify=tk.CENTER)
        terms_text.pack()
        
        # Loading indicator (hidden)
        self.loading_label = tk.Label(main_frame, text="",
                                    font=('Arial', 10),
                                    bg=self.white, fg=self.primary_color)
    
    def initiate_google_signin(self):
        """Start Google OAuth flow — credentials managed by Firebase backend."""

        # ✅ Client ID is now managed securely by Firebase
        GOOGLE_CLIENT_ID = None  # Managed by Firebase

        # ✅ No need to validate client ID format anymore
        # We only build the redirect URL for the local callback server
        redirect_port = get_free_port()
        redirect_uri = f"http://localhost:{redirect_port}/callback"

        # Build OAuth URL — backend handles real auth
        auth_params = {
            'client_id': GOOGLE_CLIENT_ID,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile',
            'access_type': 'offline',
            'prompt': 'select_account'
        }

        auth_url = GOOGLE_AUTH_URL + '?' + urlencode(auth_params)

        print(f"[OAUTH] Firebase-managed Google OAuth")
        print(f"[OAUTH] Redirect URI: {redirect_uri}")
        print(f"[OAUTH] Auth URL: {auth_url}")

        # Start local callback server to receive code
        threading.Thread(
            target=self.start_google_callback_server,
            args=(redirect_port,),
            daemon=True
        ).start()

        # Open browser to Firebase/Google Sign-in page
        try:
            webbrowser.open(auth_url)
            print("[OAUTH] Browser opened")
        except Exception as e:
            print(f"[OAUTH] Error opening browser: {e}")
            messagebox.showerror("Error", f"Could not open browser: {e}")
            return

        # Show loading indicator
        self.loading_label.config(text="Waiting for Google authentication...")
        self.loading_label.pack(pady=10)

    
    def start_google_callback_server(self, port):
        """Start server for Google OAuth callback"""
        server = HTTPServer(('localhost', port), OAuthCallbackHandler)
        server.auth_code = None
        server.timeout = 120
        
        while server.auth_code is None:
            server.handle_request()
        
        if server.auth_code:
            self.root.after(0, self.exchange_google_code, server.auth_code, 
                          f"http://localhost:{port}/callback")
    
    def exchange_google_code(self, auth_code, redirect_uri):
        """Exchange Google authorization code via Firebase backend."""
        from api_client import api  # ✅ ensure imported at top of file

        print(f"[OAUTH] Exchanging code via backend: {auth_code[:10]}...")

        # ✅ Client secrets are managed by Firebase backend
        GOOGLE_CLIENT_ID = None
        GOOGLE_CLIENT_SECRET = None

        try:
            # ✅ Ask backend to handle token exchange securely
            result = api.exchange_google_code(auth_code, redirect_uri)

            if result.get('success'):
                user_info = result.get('user')
                if user_info:
                    print("[OAUTH] Access token verified and user info received")
                    self.get_google_user_info(user_info)  # or directly call self._on_auth_success
                else:
                    print("[OAUTH] No user info in backend response")
                    self.loading_label.pack_forget()
                    messagebox.showerror("Error", "Failed to retrieve user information.")
            else:
                error_msg = result.get('error', 'Unknown error')
                print(f"[OAUTH] Token verification failed: {error_msg}")
                self.loading_label.pack_forget()
                messagebox.showerror("Authentication Error", f"Google authentication failed.\n{error_msg}")

        except Exception as e:
            print(f"[OAUTH] Exception during token exchange: {e}")
            self.loading_label.pack_forget()
            messagebox.showerror("Error", f"Connection error: {str(e)}")

    
    def get_google_user_info(self, access_token):
        """Get user info from Google"""
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get(GOOGLE_USER_INFO_URL, headers=headers)
            user_info = response.json()
            
            # Create user data
            self.user_data = {
                'uid': str(uuid.uuid4()),
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'picture': user_info.get('picture'),
                'google_id': user_info.get('id'),
                'auth_method': 'google',
                'created_at': datetime.now().isoformat(),
                'machine_fingerprint': self.generate_machine_fingerprint()
            }
            
            # Save to sheet and locally
            self.save_user_to_sheet()
            self.save_user_data_locally()
            
            self.loading_label.pack_forget()
            messagebox.showinfo("Success", f"Welcome, {self.user_data['name']}!")
            self.show_main_app()
            
        except Exception as e:
            self.loading_label.pack_forget()
            messagebox.showerror("Error", f"Failed to get user info: {str(e)}")
    
    def is_valid_email(self, email):
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def generate_otp(self):
        """Generate 6-digit OTP"""
        return ''.join(random.choices(string.digits, k=6))
    
    def send_otp_email(self, email, otp, purpose="Sign In"):
        """Send OTP via email"""
        try:
            subject = f"StudyTimer - {purpose} OTP"
            body = f"""Hi there!

Your OTP for StudyTimer {purpose} is: {otp}

This OTP is valid for 5 minutes only.
If you didn't request this, please ignore this email.

Best regards,
StudyTimer Team"""
            
            msg = MIMEMultipart()
            msg['From'] = EMAIL_USER
            msg['To'] = email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
            server.quit()
            
            return True
            
        except Exception as e:
            print(f"Email error: {e}")
            return False
    
    def handle_email_signin(self):
        """Handle email sign in"""
        email = self.email_var.get().strip()
        
        if not self.is_valid_email(email):
            messagebox.showerror("Error", "Please enter a valid email address")
            return
        
        # Check if user exists in sheet
        user_from_sheet = self.get_user_from_sheet(email=email)
        
        if not user_from_sheet:
            response = messagebox.askyesno("Account Not Found",
                                          "No account found with this email.\nWould you like to sign up?")
            if response:
                self.show_signup_form()
            return
        
        # Send OTP
        otp = self.generate_otp()
        if self.send_otp_email(email, otp, "Sign In"):
            self.show_otp_verification(email, otp, user_from_sheet, is_signin=True)
        else:
            messagebox.showerror("Error", "Failed to send OTP. Please try again.")
    
    def show_signup_form(self):
        """Show email signup form"""
        signup_window = tk.Toplevel(self.root)
        signup_window.title("Sign Up")
        signup_window.geometry("400x350")
        signup_window.resizable(False, False)
        signup_window.grab_set()
        
        # Center window
        signup_window.transient(self.root)
        x = self.root.winfo_rootx() + 50
        y = self.root.winfo_rooty() + 50
        signup_window.geometry(f"400x350+{x}+{y}")
        
        tk.Label(signup_window, text="Create Account",
                font=('Arial', 16, 'bold')).pack(pady=20)
        
        # Name input
        tk.Label(signup_window, text="Full Name:",
                font=('Arial', 11)).pack(anchor='w', padx=40, pady=(10, 5))
        
        name_var = tk.StringVar()
        name_entry = tk.Entry(signup_window, textvariable=name_var,
                             font=('Arial', 12), width=25)
        name_entry.pack(pady=(0, 15))
        name_entry.focus()
        
        # Email input
        tk.Label(signup_window, text="Email Address:",
                font=('Arial', 11)).pack(anchor='w', padx=40, pady=(5, 5))
        
        email_var = tk.StringVar(value=self.email_var.get())
        email_entry = tk.Entry(signup_window, textvariable=email_var,
                              font=('Arial', 12), width=25)
        email_entry.pack(pady=(0, 20))
        
        def handle_signup():
            name = name_var.get().strip()
            email = email_var.get().strip()
            
            if not name:
                messagebox.showerror("Error", "Please enter your name")
                return
            
            if not self.is_valid_email(email):
                messagebox.showerror("Error", "Please enter a valid email")
                return
            
            # Check if already exists
            if self.get_user_from_sheet(email=email):
                messagebox.showwarning("Account Exists", "An account with this email already exists")
                return
            
            # Create temp user data
            temp_data = {
                'uid': str(uuid.uuid4()),
                'name': name,
                'email': email,
                'auth_method': 'email',
                'created_at': datetime.now().isoformat(),
                'machine_fingerprint': self.generate_machine_fingerprint()
            }
            
            # Send OTP
            otp = self.generate_otp()
            if self.send_otp_email(email, otp, "Sign Up"):
                signup_window.destroy()
                self.show_otp_verification(email, otp, temp_data, is_signup=True)
            else:
                messagebox.showerror("Error", "Failed to send OTP")
        
        tk.Button(signup_window, text="Create Account",
                 font=('Arial', 12, 'bold'), bg="#4CAF50", fg="white",
                 command=handle_signup, width=20, height=2).pack(pady=20)
    
    def show_otp_verification(self, email, otp, user_data, is_signup=False, is_signin=False):
        """Show OTP verification window"""
        otp_window = tk.Toplevel(self.root)
        otp_window.title("OTP Verification")
        otp_window.geometry("400x350")
        otp_window.resizable(False, False)
        otp_window.grab_set()
        
        # Center window
        otp_window.transient(self.root)
        x = self.root.winfo_rootx() + 50
        y = self.root.winfo_rooty() + 50
        otp_window.geometry(f"400x350+{x}+{y}")
        
        tk.Label(otp_window, text="Enter OTP",
                font=('Arial', 16, 'bold')).pack(pady=20)
        
        tk.Label(otp_window, text=f"OTP sent to: {email}",
                font=('Arial', 10)).pack(pady=5)
        
        # OTP input
        otp_var = tk.StringVar()
        otp_entry = tk.Entry(otp_window, textvariable=otp_var,
                            font=('Arial', 18), width=10, justify='center')
        otp_entry.pack(pady=20)
        otp_entry.focus()
        
        # Timer
        timer_label = tk.Label(otp_window, text="Valid for: 5:00",
                              font=('Arial', 10), fg="#666")
        timer_label.pack()
        
        start_time = datetime.now()
        
        def update_timer():
            from datetime import datetime
            elapsed = datetime.now() - start_time
            remaining = 300 - elapsed.total_seconds()
            
            if remaining <= 0:
                timer_label.config(text="OTP Expired", fg="red")
                return
            
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            timer_label.config(text=f"Valid for: {minutes}:{seconds:02d}")
            otp_window.after(1000, update_timer)
        
        update_timer()
        
        def verify_otp():
            entered_otp = otp_var.get().strip()
            
            if entered_otp != otp:
                messagebox.showerror("Invalid OTP", "Please enter the correct OTP")
                return
            
            # Success
            self.user_data = user_data
            
            # Save to sheet and locally
            self.save_user_to_sheet()
            self.save_user_data_locally()
            
            otp_window.destroy()
            
            if is_signup:
                messagebox.showinfo("Success", "Account created successfully!")
            else:
                messagebox.showinfo("Success", "Signed in successfully!")
            
            self.show_main_app()
        
        def resend_otp():
            nonlocal otp, start_time
            otp = self.generate_otp()
            purpose = "Sign Up" if is_signup else "Sign In"
            
            if self.send_otp_email(email, otp, purpose):
                messagebox.showinfo("OTP Sent", "New OTP sent to your email")
                start_time = datetime.now()
                update_timer()
            else:
                messagebox.showerror("Error", "Failed to resend OTP")
        
        # Buttons
        button_frame = tk.Frame(otp_window)
        button_frame.pack(pady=30)
        
        tk.Button(button_frame, text="Verify",
                 font=('Arial', 11, 'bold'), bg=self.primary_color, fg=self.white,
                 width=12, command=verify_otp).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Resend OTP",
                 font=('Arial', 11), bg="#FF9800", fg=self.white,
                 width=12, command=resend_otp).pack(side=tk.LEFT, padx=5)
        
        # Bind Enter key
        otp_window.bind('<Return>', lambda e: verify_otp())
    
    def show_main_app(self):
        """Modified to work with integration"""
        # Clear auth window
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # If we have a main app reference, just signal completion
        if hasattr(self, 'main_app'):
            # The main app will handle closing this window
            if hasattr(self, 'launch_main_app'):
                self.launch_main_app()
            return
        
        # Otherwise show the welcome screen as before
        self.root.title("Welcome to Study Timer")
        self.root.geometry("600x500")
        self.root.resizable(False, False)
        
        # Main frame
        main_frame = tk.Frame(self.root, bg=self.white)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)
        
        # Welcome header
        welcome_label = tk.Label(main_frame,
                               text="Welcome to Study Timer!",
                               font=('Arial', 24, 'bold'),
                               bg=self.white, fg=self.text_color)
        welcome_label.pack(pady=(20, 10))
        
        # Success message
        success_label = tk.Label(main_frame,
                               text="Account setup completed successfully",
                               font=('Arial', 14),
                               bg=self.white, fg="#4CAF50")
        success_label.pack(pady=5)
        
        # User info box
        info_frame = tk.Frame(main_frame, bg="#f8f9fa", relief=tk.RAISED, bd=1)
        info_frame.pack(pady=20, padx=20, fill=tk.X)
        
        if self.user_data:
            tk.Label(info_frame, text="Account Information",
                    font=('Arial', 16, 'bold'),
                    bg="#f8f9fa", fg=self.text_color).pack(pady=(15, 10))
            
            user_details = f"Name: {self.user_data.get('name', 'N/A')}\nEmail: {self.user_data.get('email', 'N/A')}\nLogin Method: {self.user_data.get('auth_method', 'email').title()}"
            
            tk.Label(info_frame, text=user_details,
                    font=('Arial', 12),
                    bg="#f8f9fa", fg=self.text_color,
                    justify=tk.LEFT).pack(pady=10)
        
        # BUTTONS FRAME - Make sure this is properly indented
        button_frame = tk.Frame(main_frame, bg=self.white)
        button_frame.pack(pady=30)
        
        # Continue button
        continue_btn = tk.Button(button_frame,
                               text="Continue to Study Timer",
                               font=('Arial', 14, 'bold'),
                               bg=self.primary_color,
                               fg=self.white,
                               bd=0,
                               padx=40,
                               pady=15,
                               cursor="hand2",
                               command=self.launch_main_app)
        continue_btn.pack(side=tk.LEFT, padx=10)
        
        # Logout button
        logout_btn = tk.Button(button_frame,
                              text="Logout",
                              font=('Arial', 12),
                              bg="#dc3545",
                              fg=self.white,
                              bd=0,
                              padx=20,
                              pady=10,
                              cursor="hand2",
                              command=self.handle_logout)
        logout_btn.pack(side=tk.LEFT, padx=10)
        
        print("Buttons created successfully")

    def launch_main_app(self):
        """Launch the actual Study Timer application"""
        try:
            # Close auth window
            self.root.quit()
            self.root.destroy()
            
            # Launch main app using stored launcher
            if hasattr(self, 'main_app_launcher'):
                self.main_app_launcher()
            else:
                print("No main app launcher found")
                
        except Exception as e:
            import tkinter.messagebox as mbox
            mbox.showerror("Launch Error", f"Could not launch main app: {e}")
    
    def handle_logout(self):
        """Handle logout and return to auth screen"""
        response = messagebox.askyesno("Logout", "Are you sure you want to logout?")
        if response:
            # Clear user data but keep local profile
            self.user_data = None
            
            # Return to auth screen
            self.show_unified_auth_page()

# Helper class to integrate with existing code
class AuthenticationManager:
    """Manager class to integrate authentication with your existing app"""
    
    def __init__(self, root, sheet_credentials=None):
        self.root = root
        self.auth_system = UnifiedAuthSystem(root)
        
        # If you have existing sheet credentials, set them here
        if sheet_credentials:
            self.auth_system.gspread_client = sheet_credentials
    
    def get_current_user(self):
        """Get current authenticated user"""
        return self.auth_system.user_data
    
    def is_authenticated(self):
        """Check if user is authenticated"""
        return self.auth_system.user_data is not None
    
    def require_authentication(self):
        """Ensure user is authenticated"""
        if not self.is_authenticated():
            return False
        return True
    
    def get_user_email(self):
        """Get user email"""
        if self.auth_system.user_data:
            return self.auth_system.user_data.get('email')
        return None
    
    def get_user_name(self):
        """Get user name"""
        if self.auth_system.user_data:
            return self.auth_system.user_data.get('name')
        return None

if __name__ == "__main__":
    root = tk.Tk()
    
    # Initialize the unified authentication system
    app = UnifiedAuthSystem(root)
    
    # Or use with the authentication manager
    # auth_manager = AuthenticationManager(root)
    
    root.mainloop()