import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageDraw, ImageTk, ImageFont
import firebase_admin
from firebase_admin import credentials, db, storage
import random
import string
import hashlib
from datetime import datetime, timedelta
import json
import threading
import time
import os
import platform
import uuid
from secrets_util import get_secret
from cryptography.fernet import Fernet
import webbrowser
from config_paths import app_paths
from io import BytesIO  # ✅ CRITICAL FIX: Added missing import
import requests  # ✅ For Telegram API
import schedule  # ✅ For scheduled notifications

import requests
import schedule
import threading
import time
from datetime import datetime
from secrets_util import get_secret




# ============================================================================
# STEP 1: ADD THIS CLASS BEFORE ModernGroupsTab CLASS
# ============================================================================

class LightweightNotificationSystem:
    """
    Optimized notification system that:
    - ✅ NO heavy Firebase queries (queries only individual members)
    - ✅ Minimal data transfer (< 100 KB per group selection)
    - ✅ Proper job scheduling with closures (actually sends notifications!)
    - ✅ Lightweight scheduler (checks time only, no Firebase polling)
    """
    
    def __init__(self, db_ref, profile_data, user_id):
        """Initialize notification system for manual notifications only"""
        self.db_ref = db_ref
        self.profile_data = profile_data
        self.user_id = user_id
        self.telegram_bot_token = None
        
        print("🔔 Initializing notification system (manual only)...")
        self._init_telegram()
    
    def _init_telegram(self):
        """Load Telegram bot token from secrets"""
        try:
            self.telegram_bot_token = get_secret("TELEGRAM_BOT_TOKEN")
            if self.telegram_bot_token:
                print("✅ Telegram bot token loaded successfully")
            else:
                print("⚠️ TELEGRAM_BOT_TOKEN not found in secrets manager")
        except Exception as e:
            print(f"⚠️ Failed to load Telegram token: {e}")
    
    
    
    def stop(self):
        """Stop the notification system"""
        print("✅ Notification system stopped")
    
    def send_telegram_message(self, chat_id, message):
        """
        Send message via Telegram Bot API
        Returns: True if successful, False otherwise
        """
        if not self.telegram_bot_token:
            print("⚠️ Cannot send: Telegram token not configured")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": str(chat_id),
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                print(f"⚠️ Telegram API error {response.status_code}: {response.text[:100]}")
                return False
                
        except requests.exceptions.Timeout:
            print("⚠️ Telegram API timeout")
            return False
        except Exception as e:
            print(f"⚠️ Failed to send Telegram message: {e}")
            return False
    
    def get_member_telegram_id(self, group_id, user_id):
        """
        Get Telegram chat ID for a member
        LIGHTWEIGHT: Only queries THIS specific member (not whole group!)
        Data usage: < 1 KB per call
        """
        try:
            # Query ONLY this member (lightweight!)
            member_ref = self.db_ref.child(f'studyGroups/{group_id}/members/{user_id}')
            member_data = member_ref.get()
            
            if member_data:
                telegram_id = member_data.get('telegram_chat_id')
                if telegram_id:
                    return telegram_id
            
            # Fallback to profile data for current user
            if user_id == self.user_id:
                telegram_id = self.profile_data.get('telegram_chat_id')
                if telegram_id:
                    return telegram_id
            
            return None
            
        except Exception as e:
            print(f"⚠️ Error getting Telegram ID for user {user_id}: {e}")
            return None
    
    
    
# ============================================================================
# LIGHTWEIGHT NOTIFICATION HELPER - Fixes 7MB data usage issue
# ============================================================================
class SimpleNotificationHelper:
    """Simple notification system that doesn't query entire group"""
    
    def __init__(self, db_ref, profile_data, user_id):
        self.db_ref = db_ref
        self.profile_data = profile_data
        self.user_id = user_id
        self.has_telegram = False
        
        # Try to get Telegram token (optional)
        try:
            from secrets_util import get_secret
            token = get_secret("TELEGRAM_BOT_TOKEN")
            if token:
                self.bot_token = token
                self.has_telegram = True
                print("ℹ️ Telegram bot configured")
        except:
            self.has_telegram = False
            print("ℹ️ Telegram not configured (notifications disabled)")
    
    def is_available(self):
        """Check if notifications are available"""
        return self.has_telegram
    
    def send_message(self, chat_id, text):
        """Send Telegram message"""
        if not self.has_telegram:
            return False
        
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            r = requests.post(url, json={
                "chat_id": str(chat_id),
                "text": text,
                "parse_mode": "HTML"
            }, timeout=5)
            return r.status_code == 200
        except:
            return False
    
    def get_member_telegram_id(self, group_id, user_id):
        """Get telegram ID for a member - LIGHTWEIGHT query"""
        try:
            # Only query THIS member (not whole group!)
            ref = self.db_ref.child(f'studyGroups/{group_id}/members/{user_id}')
            data = ref.get()
            
            if data and 'telegram_chat_id' in data:
                return data['telegram_chat_id']
            
            # Fallback to profile for current user
            if user_id == self.user_id:
                return self.profile_data.get('telegram_chat_id')
        except:
            pass
        return None
    
    def notify_members(self, group_id, group_name, member_ids, message, admin_name):
        """Send notification to members - queries one at a time"""
        if not self.has_telegram:
            return 0, len(member_ids)
        
        import time
        sent = 0
        failed = 0
        
        msg_text = (
            f"📢 <b>Group Notification</b>\n\n"
            f"<b>From:</b> {group_name}\n"
            f"<b>Admin:</b> {admin_name}\n\n"
            f"<b>Message:</b>\n{message}"
        )
        
        for member_id in member_ids:
            # Query ONLY this member
            telegram_id = self.get_member_telegram_id(group_id, member_id)
            
            if telegram_id:
                if self.send_message(telegram_id, msg_text):
                    sent += 1
                else:
                    failed += 1
            else:
                failed += 1
            
            time.sleep(0.1)  # Rate limiting
        
        return sent, failed



class ModernGroupsTab:
    def __init__(self, notebook, user_id, import_plan_callback, profile_data=None):
        """Initialize Modern Groups Tab with Firebase"""
        import os
        from tkinter import ttk

        self.notebook = notebook
        self.parent = notebook.master

        # --- Stable device fingerprint for identity recovery ---
        self.machine_fingerprint = (profile_data or {}).get("machine_fingerprint") or self._generate_machine_fingerprint()
        if profile_data is not None and "machine_fingerprint" not in profile_data and self.machine_fingerprint:
            profile_data["machine_fingerprint"] = self.machine_fingerprint

        # --- Get user_id safely ---
        self.user_id = None
        if profile_data and profile_data.get("user_id"):
            self.user_id = profile_data.get("user_id")
        else:
            self.user_id = user_id

        # --- Ensure valid fallback if somehow None or invalid ---
        if not self.user_id or str(self.user_id).lower() == "none":
            print("⚠ user_id missing or invalid, using fallback.")
            try:
                self.user_id = (profile_data.get("user_id") if profile_data else None) or self.machine_fingerprint or user_id
            except Exception:
                self.user_id = self.machine_fingerprint or user_id

        # If we still don't have a user_id, rely on the machine fingerprint to keep membership intact
        if not self.user_id and self.machine_fingerprint:
            self.user_id = self.machine_fingerprint

        # ✅ Clean user_id globally
        if isinstance(self.user_id, str):
            self.user_id = self.user_id.strip().replace(" ", "")
        else:
            self.user_id = str(self.user_id or "").strip()

        self.import_plan_callback = import_plan_callback
        self.profile_data = profile_data or {}  # ✅ store safely

        self.loaded_message_keys = set()
        
        # --- Firebase initialization ---
        self.init_firebase()

        # --- Groups UI setup ---
        self.groups_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.groups_frame, text="👥 Groups")

        # --- State variables ---
        self.current_group = None
        self.current_plan = None
        self.groups = {}
        self.listeners = []
        self.online_check_thread = None
        self.typing_timers = {}
        self.message_listener = None

        # --- UI setup ---
        self.setup_styles()
        self.setup_ui()

        # --- Start Firebase listeners ---
        self.start_firebase_listeners()

        # --- Start online status updater ---
        self.start_online_presence()

        # --- Initial load ---
        self.load_all_groups()

        # --- Misc assets ---
        self._avatar_cache = {}
        self.send_icon_path = os.path.join(os.getcwd(), "assets", "send.png")
        self.selected_plan_for_members = None 
        
        # ✅ Initialize LIGHTWEIGHT notification system (fixes both issues)
        try:
            self.notification_system = LightweightNotificationSystem(
                self.db_ref,
                self.profile_data,
                self.user_id
            )
            print("✅ Lightweight notification system initialized")
        except Exception as e:
            print(f"⚠️ Notification system disabled: {e}")
            self.notification_system = None


    def _generate_machine_fingerprint(self):
        """Generate a stable machine fingerprint for group identity"""
        try:
            system_info = f"{platform.system()}-{platform.machine()}-{platform.processor()}"
            hostname = platform.node()
            fingerprint_data = f"{system_info}-{hostname}"
            return hashlib.md5(fingerprint_data.encode()).hexdigest()[:16]
        except Exception as e:
            print(f"⚠️ Failed to generate machine fingerprint: {e}")
            return str(uuid.uuid4())[:16]


    def clear_plan_selection(self):
        """Clear plan selection to show all members again"""
        self.selected_plan_for_members = None
        self.show_group_content()
        print("✅ Cleared plan selection - showing all enrolled members")
        
    def select_plan_for_members(self, plan_id):
        """Select a plan to view its enrolled members"""
        self.selected_plan_for_members = plan_id
        self.current_plan = plan_id  # Also set as current for materials
        
        # Refresh the plans section to show selection
        self.show_group_content()
        
        print(f"✅ Selected plan {plan_id} for viewing enrolled members")
        
    def is_creator(self, group_id):
        """Check if the current user is the group creator."""
        try:
            group_data = self.groups.get(group_id, {})
            metadata = group_data.get("metadata", {})
            return str(metadata.get("created_by", "")).strip() == str(self.user_id).strip()
        except:
            return False

    def remove_plan(self, plan_id):
        """Delete a plan and refresh UI instantly."""
        from tkinter import messagebox
        if not self.current_group:
            return
        if messagebox.askyesno("Confirm Delete", "Delete this plan and all its materials?"):
            try:
                path = f"studyGroups/{self.current_group}/plans/{plan_id}"
                self.db_ref.child(path).delete()
                print(f"✅ Deleted plan: {path}")

                # --- Instant UI refresh ---
                self.groups.get(self.current_group, {}).get("plans", {}).pop(plan_id, None)
                self.show_group_content()  # ✅ no argument now
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete plan: {e}")
                print("⚠ remove_plan error:", e)

    def remove_material(self, plan_id, mat_id):
        """Delete a study material and refresh instantly (auto-detect correct path)."""
        from tkinter import messagebox
        if not self.current_group:
            return
        if messagebox.askyesno("Confirm Delete", "Delete this material?"):
            try:
                # --- Try nested path first ---
                path_nested = f"studyGroups/{self.current_group}/plans/{plan_id}/materials/{mat_id}"
                path_root = f"studyGroups/{self.current_group}/materials/{mat_id}"
                
                deleted = False
                # Check which exists
                nested_ref = self.db_ref.child(path_nested)
                if nested_ref.get():
                    nested_ref.delete()
                    deleted = True
                    print(f"✅ Deleted from nested path: {path_nested}")
                
                elif self.db_ref.child(path_root).get():
                    self.db_ref.child(path_root).delete()
                    deleted = True
                    print(f"✅ Deleted from root path: {path_root}")

                if not deleted:
                    print("⚠ No matching material found in Firebase!")

                # --- Instant local refresh ---
                plan = self.groups.get(self.current_group, {}).get("plans", {}).get(plan_id, {})
                if "materials" in plan and mat_id in plan["materials"]:
                    plan["materials"].pop(mat_id)
                self.show_group_content()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete material: {e}")
                print("⚠ remove_material error:", e)
        
    def get_user_study_hours(self):
        """✅ Get current user's study hours from Firebase LEADERBOARD (not groups)"""
        try:
            if not self.db_ref:
                return None
            
            # ✅ CRITICAL: Fetch from 'leaderboard' node, NOT 'studyGroups'
            leaderboard_ref = self.db_ref.child(f'leaderboard/{self.user_id}')
            user_data = leaderboard_ref.get()
            
            if user_data:
                today_hours = user_data.get('todayHours', 0)
                week_hours = user_data.get('weekHours', 0)
                
                # Format with 1 decimal place
                return {
                    'today': f"{today_hours:.1f}h",
                    'week': f"{week_hours:.1f}h"
                }
        except Exception as e:
            print(f"Study hours fetch error: {e}")
        
        return None
    
    def get_online_members_count(self, group_id):
        """Get count of currently online members in a group"""
        try:
            if not group_id or group_id not in self.groups:
                return 0
            
            members = self.groups[group_id].get('members', {})
            online_count = sum(1 for member in members.values() if member.get('online', False))
            return online_count
        except Exception as e:
            print(f"Error getting online count: {e}")
            return 0
    
    def get_member_study_hours(self, user_id):
        """Get study hours for any user from leaderboard"""
        try:
            if not self.db_ref:
                return 0
            
            leaderboard_ref = self.db_ref.child(f'leaderboard/{user_id}')
            user_data = leaderboard_ref.get()
            
            if user_data:
                # Return total week hours for sorting
                return user_data.get('weekHours', 0)
        except Exception as e:
            print(f"Error fetching study hours for {user_id}: {e}")
        
        return 0
    
    def _init_notification_system(self):
        """Initialize Telegram notification system"""
        try:
            # Get Telegram bot token from secrets manager
            self.telegram_bot_token = get_secret("TELEGRAM_BOT_TOKEN")
            if not self.telegram_bot_token:
                print("⚠️ TELEGRAM_BOT_TOKEN not found in secrets manager")
                return
            
            print("✅ Telegram notification system initialized")
            
            # Start the scheduler thread for automatic plan notifications
            self._start_notification_scheduler()
            
        except Exception as e:
            print(f"⚠️ Failed to initialize notification system: {e}")
    
    def _start_notification_scheduler(self):
        """Start background scheduler for plan notifications"""
        if self.notification_scheduler_running:
            return
        
        self.notification_scheduler_running = True
        
        def scheduler_loop():
            while self.notification_scheduler_running:
                try:
                    schedule.run_pending()
                    time.sleep(30)  # Check every 30 seconds
                except Exception as e:
                    print(f"Scheduler error: {e}")
        
        self.scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        print("✅ Notification scheduler started")
    
    def _stop_notification_scheduler(self):
        """Stop the notification scheduler"""
        self.notification_scheduler_running = False
        schedule.clear()
    
    def send_telegram_message(self, chat_id, message):
        """Send message via Telegram bot"""
        if not self.telegram_bot_token:
            print("⚠️ Telegram bot token not available")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                print(f"✅ Telegram message sent to {chat_id}")
                return True
            else:
                print(f"⚠️ Telegram API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"⚠️ Failed to send Telegram message: {e}")
            return False
    
    def get_member_telegram_id(self, user_id):
        """Get Telegram chat ID for a member from Firebase"""
        try:
            if not self.db_ref or not self.current_group:
                return None
            
            member_ref = self.db_ref.child(f'studyGroups/{self.current_group}/members/{user_id}')
            member_data = member_ref.get()
            
            if member_data:
                # Try to get telegram_chat_id from member data
                telegram_id = member_data.get('telegram_chat_id')
                if telegram_id:
                    return telegram_id
            
            # If not in member data, check if this is current user and get from profile
            if user_id == self.user_id:
                return self.profile_data.get('telegram_chat_id')
            
            return None
            
        except Exception as e:
            print(f"Error getting Telegram ID for {user_id}: {e}")
            return None
    
    def notify_all_members(self):
        """Send notification to all members - LIGHTWEIGHT VERSION"""
        import tkinter as tk
        from tkinter import messagebox
        import threading
        
        if not self.current_group:
            messagebox.showwarning("⚠️", "No group selected!")
            return
        
        if not self.is_admin(self.current_group):
            messagebox.showwarning("⚠️", "Only admins can send notifications!")
            return
        
        # Check if notification system is available
        if not hasattr(self, 'notification_system') or not self.notification_system:
            messagebox.showinfo("ℹ️ Info", 
                "Notifications not configured.\n\n"
                "To enable notifications:\n"
                "1. Create a Telegram bot with @BotFather\n"
                "2. Add TELEGRAM_BOT_TOKEN to secrets manager\n"
                "3. Restart the app")
            return
        
        # ✅ FIX: Check if telegram_bot_token exists instead of calling is_available()
        if not self.notification_system.telegram_bot_token:
            messagebox.showinfo("ℹ️ Info",
                "Telegram bot not configured.\n"
                "Add TELEGRAM_BOT_TOKEN to secrets manager to use notifications.")
            return
        
        # Create dialog
        dialog = tk.Toplevel(self.parent)
        dialog.title("📢 Notify All Members")
        dialog.geometry("500x450")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        # Header
        header = tk.Frame(dialog, bg='#9B59B6', height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="📢 Send Notification", 
                font=('Segoe UI', 14, 'bold'),
                bg='#9B59B6', fg='white').pack(pady=15)
        
        # Content
        content = tk.Frame(dialog, bg='white')
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Group info
        group_data = self.groups.get(self.current_group, {})
        group_name = group_data.get('metadata', {}).get('name', 'Unknown Group')
        members = list(group_data.get('members', {}).keys())
        
        tk.Label(content, text=f"Group: {group_name}", 
                font=('Segoe UI', 10, 'bold'),
                bg='white').pack(anchor='w', pady=(0, 5))
        
        tk.Label(content, text=f"Members: {len(members)}", 
                font=('Segoe UI', 9),
                bg='white', fg='#666').pack(anchor='w', pady=(0, 15))
        
        # Message input
        tk.Label(content, text="Your Message:", 
                font=('Segoe UI', 10),
                bg='white').pack(anchor='w', pady=(0, 5))
        
        msg_text = tk.Text(content, width=50, height=10, 
                          font=('Segoe UI', 10),
                          relief='solid', borderwidth=1)
        msg_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Status label
        status_label = tk.Label(content, text="", 
                               font=('Segoe UI', 9),
                               bg='white', fg='#27AE60')
        status_label.pack()
        
        def send_notification():
            message = msg_text.get('1.0', tk.END).strip()
            
            if not message:
                messagebox.showerror("Error", "Please enter a message!")
                return
            
            # Disable button
            send_btn.config(state='disabled', text="Sending...")
            status_label.config(text="Sending notifications...", fg='#F39C12')
            dialog.update()
            
            def send_in_background():
                # Send notifications using the notification system
                sent = 0
                failed = 0
                
                # Format message
                msg_text_formatted = (
                    f"📢 <b>Group Notification</b>\n\n"
                    f"<b>From:</b> {group_name}\n"
                    f"<b>Admin:</b> {self.get_user_name()}\n\n"
                    f"<b>Message:</b>\n{message}"
                )
                
                for member_id in members:
                    # Get member's telegram ID
                    telegram_id = self.notification_system.get_member_telegram_id(
                        self.current_group, 
                        member_id
                    )
                    
                    if telegram_id:
                        if self.notification_system.send_telegram_message(telegram_id, msg_text_formatted):
                            sent += 1
                        else:
                            failed += 1
                    else:
                        failed += 1
                    
                    import time
                    time.sleep(0.1)  # Rate limiting
                
                # Update UI on main thread
                def show_result():
                    send_btn.config(state='normal', text="📤 Send")
                    status_label.config(
                        text=f"✅ Sent: {sent} | ⚠️ Failed: {failed}",
                        fg='#27AE60'
                    )
                    
                    if sent > 0:
                        messagebox.showinfo("✅ Success", 
                            f"Notification sent to {sent} member(s)!\n"
                            f"{failed} member(s) don't have Telegram configured.")
                    else:
                        messagebox.showwarning("⚠️ Warning",
                            "No notifications sent.\n"
                            "Members need to register their Telegram IDs.")
                
                self.parent.after(0, show_result)
            
            threading.Thread(target=send_in_background, daemon=True).start()
        
        # Buttons
        btn_frame = tk.Frame(content, bg='white')
        btn_frame.pack(pady=(15, 0))
        
        send_btn = tk.Button(btn_frame, text="📤 Send", 
                            bg='#9B59B6', fg='white',
                            font=('Segoe UI', 10, 'bold'),
                            relief='flat', padx=25, pady=8,
                            cursor='hand2',
                            command=send_notification)
        send_btn.pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Cancel", 
                 bg='#95A5A6', fg='white',
                 font=('Segoe UI', 10),
                 relief='flat', padx=25, pady=8,
                 cursor='hand2',
                 command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    
    
    def _send_plan_start_notification(self, plan_id, plan_data, enrolled_members):
        """Send notification to enrolled members when their plan starts"""
        if not self.telegram_bot_token:
            return
        
        try:
            group_data = self.groups.get(self.current_group, {})
            group_name = group_data.get('metadata', {}).get('name', 'Study Group')
            plan_name = plan_data.get('name', 'Study Plan')
            
            message = (
                f"⏰ <b>Study Session Starting!</b>\n\n"
                f"<b>Group:</b> {group_name}\n"
                f"<b>Plan:</b> {plan_name}\n\n"
                f"Your enrolled study plan is starting now! 📚\n"
                f"Please join the session. Good luck! 💪"
            )
            
            sent_count = 0
            for member_id in enrolled_members:
                telegram_id = self.get_member_telegram_id(member_id)
                
                if telegram_id:
                    if self.send_telegram_message(telegram_id, message):
                        sent_count += 1
                        time.sleep(0.1)
            
            print(f"✅ Plan notification sent to {sent_count} members")
            
        except Exception as e:
            print(f"⚠️ Failed to send plan notification: {e}")
        
    def sync_profile_to_firebase(self):
        """Force sync current profile to all joined groups - uses avatar NAME only (no upload!)"""
        if not self.db_ref:
            return
        name = self.get_user_name()
        
        # ✅ GET AVATAR NAME ONLY (NO UPLOAD!)
        avatar_id = self.profile_data.get("avatar_id", 1)
        avatar_name = f"avatar {avatar_id}.png"
        
        update_data = {
            'name': name,
            'avatar_name': avatar_name,
            'last_seen': datetime.now().isoformat(),
            'telegram_chat_id': self.profile_data.get('telegram_chat_id', '')  # ✅ ADD THIS
        }
        
        try:
            for group_id, group_data in self.groups.items():
                if self.user_id in group_data.get('members', {}):
                    member_ref = self.db_ref.child(f'studyGroups/{group_id}/members/{self.user_id}')
                    member_ref.update(update_data)
                    # Update local cache
                    if 'members' in self.groups[group_id] and self.user_id in self.groups[group_id]['members']:
                        self.groups[group_id]['members'][self.user_id].update(update_data)
            
            print(f"✅ Profile synced across all groups: {update_data}")
            
            # ✅ Refresh UI immediately
            self.update_groups_lists()
            
            if self.current_group:
                self.show_group_content()
                
                # ✅ Clear and reload messages
                if hasattr(self, 'loaded_message_keys'):
                    self.loaded_message_keys.clear()
                
                # Force reload from Firebase
                messages_ref = self.db_ref.child(f'studyGroups/{self.current_group}/messages')
                messages_data = messages_ref.get()
                if messages_data:
                    self.display_messages(messages_data, force_refresh=True)
                
        except Exception as e:
            print(f"Profile sync error: {e}")

    def _reload_chat_messages(self):
        """Force reload chat messages from Firebase"""
        if not self.current_group or not self.db_ref:
            return
        try:
            messages_ref = self.db_ref.child(f'studyGroups/{self.current_group}/messages')
            messages_data = messages_ref.get()
            if messages_data:
                self.display_messages(messages_data, force_refresh=True)
        except Exception as e:
            print(f"Error reloading messages: {e}")

    
    def get_decrypted_service_account(self):
        """Get decrypted service account from secrets"""
        try:
            encryption_key = get_secret('ENCRYPTION_KEY')
            encrypted_sa = get_secret('ENCRYPTED_SERVICE_ACCOUNT')
            
            if not encryption_key or not encrypted_sa:
                return None
            
            cipher = Fernet(encryption_key.encode())
            service_account_json = cipher.decrypt(encrypted_sa.encode()).decode()
            return json.loads(service_account_json)
        except Exception as e:
            print(f"Decryption failed: {e}")
            return None
        
    def init_firebase(self):
        """Initialize Firebase connection"""
        try:
            database_url = get_secret("FIREBASE_DATABASE_URL") or \
                          "https://leaderboard-98e8c-default-rtdb.asia-southeast1.firebasedatabase.app"
            
            service_account = self.get_decrypted_service_account()
            if not service_account:
                self.db_ref = None
                self.storage_bucket = None
                return
            
            if not firebase_admin._apps:
                cred = credentials.Certificate(service_account)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': database_url,
                    'storageBucket': 'leaderboard-98e8c.firebasestorage.app'
                })
            
            self.db_ref = db.reference()
            
            try:
                self.storage_bucket = storage.bucket('leaderboard-98e8c.firebasestorage.app')
            except:
                self.storage_bucket = None
            
        except Exception as e:
            print(f"Firebase error: {e}")
            self.db_ref = None
            self.storage_bucket = None
    
    def setup_styles(self):
        """Setup modern UI styles"""
        self.colors = {
            'primary': '#4A90E2',
            'secondary': '#50C878',
            'accent': '#FF6B6B',
            'dark': '#2C3E50',
            'light': '#FFFFFF',
            'gray': '#95A5A6',
            'bg': '#F8F9FA',
            'online': '#2ECC71',
            'offline': '#BDC3C7',
            'hover': '#E8F4F8',
            'shadow': '#00000010'
        }

    def _create_soft_button(self, parent, text, fg, command, bg=None, hover_bg=None,
                             font=None, padding=(10, 4)):
        """Create a slim, pill-like label button with hover effect."""
        base_bg = bg or '#F4F6FB'
        hover_bg = hover_bg or '#E8ECF4'
        btn = tk.Label(
            parent,
            text=text,
            font=font or ('Segoe UI', 9),
            bg=base_bg,
            fg=fg,
            padx=padding[0],
            pady=padding[1],
            cursor='hand2',
            bd=0,
            relief='flat'
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=base_bg))
        if command:
            btn.bind('<Button-1>', lambda e: command())
        return btn
        
    def setup_ui(self):
        """Setup modern 3-column layout"""
        main_container = tk.Frame(self.groups_frame, bg=self.colors['bg'])
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # LEFT: Groups column - FIXED WIDTH
        groups_wrapper = tk.Frame(main_container, bg=self.colors['bg'], width=220)
        groups_wrapper.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 5), pady=10)
        groups_wrapper.pack_propagate(False)
        
        chat_wrapper = tk.Frame(main_container, bg=self.colors['bg'], width=280)
        chat_wrapper.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 10), pady=10)
        chat_wrapper.pack_propagate(False)


        # 🔧 Allow inner widgets to expand vertically but keep width fixed
        chat_wrapper.configure(height=500)  # any approximate height of your app area
        chat_wrapper.pack_propagate(False)
        
        
        # CENTER: Content area - EXPANDABLE
        center_wrapper = tk.Frame(main_container, bg=self.colors['bg'])
        center_wrapper.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=10)
        
        # Setup columns
        self.setup_groups_column(groups_wrapper)
        # delay chat build slightly so Tkinter has valid geometry
        self.parent.after(100, lambda: self.safe_build_chat(chat_wrapper))
        self.setup_center_column(center_wrapper)
        
    # ========================================
    # FIX 1: Modern Slim Scrollbar for Chat
    # ========================================
    # Replace the safe_build_chat method with this version:

    def safe_build_chat(self, chat_wrapper):
        """Builds chat layout with sleek modern scrollbar."""
        import tkinter as tk
        from tkinter import ttk
        from PIL import Image, ImageTk
        import os

        print("🧩 Building chat layout...")

        # === MAIN COLUMN STRUCTURE ===
        chat_wrapper.pack_propagate(False)
        chat_wrapper.update_idletasks()

        chat_frame = tk.Frame(chat_wrapper, bg='white')
        chat_frame.pack(fill=tk.BOTH, expand=True)

        # 1️⃣ Top: Chat header
        header = tk.Frame(chat_frame, bg='#1B5E20', height=35)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)
        tk.Label(header, text="💬 CHAT", bg='#1B5E20', fg='white',
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=10)

        # 2️⃣ Middle: Scrollable message area with CUSTOM MODERN SCROLLBAR
        scroll_container = tk.Frame(chat_frame, bg='white')
        scroll_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 2))

        canvas = tk.Canvas(scroll_container, bg='white', highlightthickness=0)
        
        # ✅ MODERN CUSTOM SCROLLBAR using Canvas (no ttk style conflicts)
        scrollbar_frame = tk.Frame(scroll_container, bg='#F5F5F5', width=8)
        scrollbar_frame.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_frame.pack_propagate(False)
        
        scrollbar_canvas = tk.Canvas(scrollbar_frame, bg='#F5F5F5', 
                                      highlightthickness=0, width=6)
        scrollbar_canvas.pack(fill=tk.BOTH, expand=True, padx=1)
        
        # Create scrollbar thumb
        thumb = scrollbar_canvas.create_rectangle(0, 0, 6, 50, 
                                                  fill='#C0C0C0', 
                                                  outline='',
                                                  tags='thumb')

        # ✅ Inner frame inside the canvas (where messages will appear)
        inner_frame = tk.Frame(canvas, bg='white')
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        # Bind scroll region
        def update_scroll_region(e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            update_scrollbar()
        
        inner_frame.bind("<Configure>", update_scroll_region)

        # Custom scrollbar logic
        def update_scrollbar():
            """Update custom scrollbar position and size"""
            try:
                view = canvas.yview()
                canvas_height = scrollbar_canvas.winfo_height()
                
                # Calculate thumb size and position
                thumb_height = max(20, canvas_height * (view[1] - view[0]))
                thumb_y = (canvas_height - thumb_height) * view[0]
                
                scrollbar_canvas.coords('thumb', 0, thumb_y, 6, thumb_y + thumb_height)
            except:
                pass
        
        def on_canvas_scroll(*args):
            canvas.yview(*args)
            update_scrollbar()
        
        canvas.configure(yscrollcommand=lambda *args: (canvas.yview_moveto(args[0]), update_scrollbar())[1])
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            update_scrollbar()
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Scrollbar drag functionality
        def on_thumb_press(event):
            scrollbar_canvas.scan_mark(event.x, event.y)
            scrollbar_canvas['cursor'] = 'hand2'
        
        def on_thumb_drag(event):
            canvas_height = scrollbar_canvas.winfo_height()
            thumb_coords = scrollbar_canvas.coords('thumb')
            thumb_height = thumb_coords[3] - thumb_coords[1]
            
            new_y = max(0, min(event.y, canvas_height - thumb_height))
            scroll_fraction = new_y / (canvas_height - thumb_height) if canvas_height > thumb_height else 0
            
            canvas.yview_moveto(scroll_fraction)
            update_scrollbar()
        
        def on_thumb_release(event):
            scrollbar_canvas['cursor'] = ''
        
        # Hover effect
        def on_thumb_enter(event):
            scrollbar_canvas.itemconfig('thumb', fill='#A0A0A0')
        
        def on_thumb_leave(event):
            scrollbar_canvas.itemconfig('thumb', fill='#C0C0C0')
        
        scrollbar_canvas.tag_bind('thumb', '<Button-1>', on_thumb_press)
        scrollbar_canvas.tag_bind('thumb', '<B1-Motion>', on_thumb_drag)
        scrollbar_canvas.tag_bind('thumb', '<ButtonRelease-1>', on_thumb_release)
        scrollbar_canvas.tag_bind('thumb', '<Enter>', on_thumb_enter)
        scrollbar_canvas.tag_bind('thumb', '<Leave>', on_thumb_leave)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ✅ Store references for display_messages()
        self.messages_canvas = canvas
        self.messages_list_frame = inner_frame
        self._scrollbar_canvas = scrollbar_canvas
        self._update_scrollbar = update_scrollbar

        # 3️⃣ Bottom: Input + send button row
        input_row = tk.Frame(chat_frame, bg='white', height=40)
        input_row.pack(fill=tk.X, side=tk.BOTTOM)
        input_row.pack_propagate(False)

        self.chat_entry = tk.Entry(input_row, font=('Segoe UI', 10))
        self.chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 4), pady=8)
        self.chat_entry.bind("<Return>", self.send_message_on_click)

        # ✅ Send button with icon or fallback
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "send_icon.png")
            if os.path.exists(icon_path):
                img = Image.open(icon_path).resize((22, 22), Image.Resampling.LANCZOS)
                send_icon = ImageTk.PhotoImage(img)
                send_btn = tk.Button(
                    input_row, image=send_icon, bg=self.colors['secondary'],
                    relief='flat', bd=0, cursor='hand2',
                    command=self.send_message_on_click
                )
                send_btn.image = send_icon  # keep reference
            else:
                raise FileNotFoundError("No send_icon.png found")

        except Exception as e:
            print("⚠ Send icon load error:", e)
            send_btn = tk.Button(
                input_row, text="▶", font=('Segoe UI', 14, 'bold'),
                bg=self.colors['secondary'], fg='white',
                relief='flat', bd=0, cursor='hand2',
                command=self.send_message_on_click
            )

        send_btn.pack(side=tk.RIGHT, padx=6, pady=(2, 2))

        print(f"✅ Chat layout ready with visible scrollbar")

        
    def setup_groups_column(self, parent):
        """Setup left groups column with modern design"""
        groups_container = tk.Frame(parent, bg=self.colors['light'])
        groups_container.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header = tk.Frame(groups_container, bg=self.colors['primary'], height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(header, text="GROUPS", font=('Segoe UI', 14, 'bold'),
                bg=self.colors['primary'], fg='white').pack(pady=15)
        
        # Scrollable content
        canvas = tk.Canvas(groups_container, bg=self.colors['light'], 
                          highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(groups_container, orient="vertical", command=canvas.yview)
        self.groups_content = tk.Frame(canvas, bg=self.colors['light'])
        
        self.groups_content.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas.create_window((0, 0), window=self.groups_content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Create sections
        self.create_groups_sections()
        
    def create_groups_sections(self):
        """Create Your Groups, Joined Groups, Search sections"""
        for widget in self.groups_content.winfo_children():
            widget.destroy()
        
        # YOUR GROUPS section
        self.create_your_groups_section()
        
        # Separator
        tk.Frame(self.groups_content, height=1, bg=self.colors['bg']).pack(fill=tk.X, pady=15)
        
        # JOINED GROUPS section
        self.create_joined_groups_section()
        
        # Separator
        tk.Frame(self.groups_content, height=1, bg=self.colors['bg']).pack(fill=tk.X, pady=15)
        
        # SEARCH GROUP section
        self.create_search_section()
        
    def create_your_groups_section(self):
        """Create Your Groups section"""
        section = tk.Frame(self.groups_content, bg=self.colors['light'])
        section.pack(fill=tk.X, padx=10, pady=5)
        
        # Header
        header = tk.Frame(section, bg=self.colors['light'])
        header.pack(fill=tk.X)
        
        tk.Label(header, text="YOUR GROUPS", font=('Segoe UI', 10, 'bold'),
                bg=self.colors['light'], fg=self.colors['dark']).pack(side=tk.LEFT)
        
        # Create button
        create_btn = tk.Label(header, text="➕", font=('Segoe UI', 12),
                            bg=self.colors['light'], fg=self.colors['primary'],
                            cursor='hand2')
        create_btn.pack(side=tk.RIGHT)
        create_btn.bind('<Button-1>', lambda e: self.create_group_dialog())
        
        # List container
        self.your_groups_list = tk.Frame(section, bg=self.colors['light'])
        self.your_groups_list.pack(fill=tk.X, pady=(10, 0))
        
    def create_joined_groups_section(self):
        """Create Joined Groups section"""
        section = tk.Frame(self.groups_content, bg=self.colors['light'])
        section.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(section, text="JOINED GROUPS", font=('Segoe UI', 10, 'bold'),
                bg=self.colors['light'], fg=self.colors['dark']).pack(anchor=tk.W)
        
        self.joined_groups_list = tk.Frame(section, bg=self.colors['light'])
        self.joined_groups_list.pack(fill=tk.X, pady=(10, 0))
        
    def send_join_request(self, group_id, group_name):
        """Send join request to group admins"""
        if not self.db_ref:
            return
        
        try:
            request_data = {
                'user_id': self.user_id,
                'user_name': self.get_user_name(),
                'avatar_name': f"avatar {self.profile_data.get('avatar_id', 1)}.png",  # ✅ Include .png
                'requested_at': datetime.now().isoformat()
            }
            
            request_ref = self.db_ref.child(f'studyGroups/{group_id}/pending_requests/{self.user_id}')
            request_ref.set(request_data)
            
            messagebox.showinfo("Request Sent", 
                              f"Your join request has been sent to '{group_name}' admins.\n\nYou will be notified when accepted.")
            
            # Refresh search results
            self.search_groups()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send request: {e}")

    def show_join_requests(self):
        """Show pending join requests dialog for admins"""
        if not self.current_group or not self.is_admin(self.current_group):
            return
        
        pending_requests = self.groups[self.current_group].get('pending_requests', {})
        
        if not pending_requests:
            messagebox.showinfo("No Requests", "No pending join requests")
            return
        
        dialog = tk.Toplevel(self.parent)
        dialog.title("Join Requests")
        dialog.geometry("400x500")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        tk.Label(dialog, text="Pending Join Requests", font=('Segoe UI', 14, 'bold')).pack(pady=20)
        
        # Scrollable list
        list_frame = tk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20)
        
        for user_id, request_data in pending_requests.items():
            self.create_request_item(list_frame, user_id, request_data)

    def create_request_item(self, parent, user_id, request_data):
        """Create join request item"""
        name = request_data.get('user_name', 'Unknown')
        
        item = tk.Frame(parent, bg='white', relief='solid', borderwidth=1)
        item.pack(fill=tk.X, pady=5)
        
        content = tk.Frame(item, bg='white')
        content.pack(fill=tk.X, padx=15, pady=10)
        
        tk.Label(content, text=name, font=('Segoe UI', 11, 'bold'),
                bg='white').pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Accept button
        accept_btn = tk.Label(content, text="✓ Accept", font=('Segoe UI', 9),
                             bg=self.colors['secondary'], fg='white',
                             cursor='hand2', padx=10, pady=5)
        accept_btn.pack(side=tk.RIGHT, padx=2)
        accept_btn.bind('<Button-1>', lambda e: self.accept_join_request(user_id, request_data))
        
        # Reject button
        reject_btn = tk.Label(content, text="✗ Reject", font=('Segoe UI', 9),
                             bg=self.colors['accent'], fg='white',
                             cursor='hand2', padx=10, pady=5)
        reject_btn.pack(side=tk.RIGHT, padx=2)
        reject_btn.bind('<Button-1>', lambda e: self.reject_join_request(user_id))

    def accept_join_request(self, user_id, request_data):
        """Accept join request"""
        try:
            # Add member
            member_data = {
                'name': request_data.get('user_name'),
                'avatar': request_data.get('avatar'),
                'role': 'member',
                'joined_at': datetime.now().isoformat(),
                'online': True,
                'last_seen': datetime.now().isoformat(),
                'typing': False
            }
            
            self.db_ref.child(f'studyGroups/{self.current_group}/members/{user_id}').set(member_data)
            
            # Remove request
            self.db_ref.child(f'studyGroups/{self.current_group}/pending_requests/{user_id}').delete()
            
            messagebox.showinfo("Success", f"{request_data.get('user_name')} has been added to the group!")
            self.refresh_group_data()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed: {e}")

    def reject_join_request(self, user_id):
        """Reject join request"""
        try:
            self.db_ref.child(f'studyGroups/{self.current_group}/pending_requests/{user_id}').delete()
            messagebox.showinfo("Success", "Request rejected")
            self.refresh_group_data()
        except Exception as e:
            messagebox.showerror("Error", f"Failed: {e}")
        
    def create_search_section(self):
        """Create Search Group section with join request"""
        section = tk.Frame(self.groups_content, bg=self.colors['light'])
        section.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(section, text="SEARCH GROUP", font=('Segoe UI', 10, 'bold'),
                bg=self.colors['light'], fg=self.colors['dark']).pack(anchor=tk.W, pady=(0, 10))
        
        # Search by name with search button
        search_frame = tk.Frame(section, bg=self.colors['bg'], relief='flat')
        search_frame.pack(fill=tk.X, pady=5)
        
        search_inner = tk.Frame(search_frame, bg='white')
        search_inner.pack(fill=tk.X, padx=1, pady=1)
        
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(search_inner, textvariable=self.search_var,
                               font=('Segoe UI', 10), bg='white', relief='flat',
                               bd=0)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=6)
        search_entry.bind('<Return>', lambda e: self.search_groups())
        
        # ✅ Search button
        search_btn = tk.Label(search_inner, text="🔍", font=('Segoe UI', 12),
                             bg=self.colors['primary'], fg='white',
                             cursor='hand2', padx=10, pady=4)
        search_btn.pack(side=tk.RIGHT, padx=2)
        search_btn.bind('<Button-1>', lambda e: self.search_groups())
        
        # Search results container
        self.search_results_frame = tk.Frame(section, bg=self.colors['light'])
        self.search_results_frame.pack(fill=tk.X, pady=(5, 0))
        
        # Join by code button
        join_btn_container = tk.Frame(section, bg=self.colors['secondary'], cursor='hand2')
        join_btn_container.pack(fill=tk.X, pady=5)
        
        join_label = tk.Label(join_btn_container, text="Join by Invite Code", font=('Segoe UI', 10),
                bg=self.colors['secondary'], fg='white', cursor='hand2')
        join_label.pack(pady=8, fill=tk.X)
        
        join_btn_container.bind('<Button-1>', lambda e: self.join_group_dialog())
        join_label.bind('<Button-1>', lambda e: self.join_group_dialog())

    def search_groups(self):
        """Search groups by name and show results with join request option"""
        # Clear previous results
        for widget in self.search_results_frame.winfo_children():
            widget.destroy()
        
        search_term = self.search_var.get().strip().lower()
        
        if not search_term:
            return
        
        if not self.db_ref:
            tk.Label(self.search_results_frame, text="❌ Search unavailable",
                    font=('Segoe UI', 9), bg=self.colors['light'],
                    fg=self.colors['accent']).pack(pady=10)
            return
        
        try:
            groups_data = self.db_ref.child('studyGroups').get()
            
            if not groups_data:
                tk.Label(self.search_results_frame, text="No groups found",
                        font=('Segoe UI', 9), bg=self.colors['light'],
                        fg=self.colors['gray']).pack(pady=10)
                return
            
            results = []
            for group_id, group_data in groups_data.items():
                group_name = group_data.get('metadata', {}).get('name', '').lower()
                if search_term in group_name:
                    results.append((group_id, group_data))
            
            if not results:
                tk.Label(self.search_results_frame, text=f"No groups matching '{search_term}'",
                        font=('Segoe UI', 9), bg=self.colors['light'],
                        fg=self.colors['gray']).pack(pady=10)
                return
            
            # Show results
            for group_id, group_data in results[:5]:  # Show max 5 results
                self.create_search_result_item(group_id, group_data)
                
        except Exception as e:
            print(f"Search error: {e}")
            tk.Label(self.search_results_frame, text="Search failed",
                    font=('Segoe UI', 9), bg=self.colors['light'],
                    fg=self.colors['accent']).pack(pady=10)

    def create_search_result_item(self, group_id, group_data):
        """Create search result item with join request button"""
        metadata = group_data.get('metadata', {})
        group_name = metadata.get('name', 'Unnamed')
        member_count = len(group_data.get('members', {}))
        
        # Check if already a member
        is_member = self.user_id in group_data.get('members', {})
        
        # Check if already requested
        pending_requests = group_data.get('pending_requests', {})
        has_requested = self.user_id in pending_requests
        
        item = tk.Frame(self.search_results_frame, bg='white', relief='solid', borderwidth=1)
        item.pack(fill=tk.X, pady=2)
        
        content = tk.Frame(item, bg='white')
        content.pack(fill=tk.X, padx=10, pady=8)
        
        # Group info
        info = tk.Frame(content, bg='white')
        info.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(info, text=group_name, font=('Segoe UI', 10, 'bold'),
                bg='white', fg=self.colors['dark']).pack(anchor=tk.W)
        
        tk.Label(info, text=f"{member_count} members", font=('Segoe UI', 8),
                bg='white', fg=self.colors['gray']).pack(anchor=tk.W)
        
        # Action button
        if is_member:
            btn_text = "✓ Joined"
            btn_color = self.colors['gray']
            btn_cmd = lambda: self.select_group(group_id)
        elif has_requested:
            btn_text = "⏳ Pending"
            btn_color = self.colors['gray']
            btn_cmd = None
        else:
            btn_text = "📩 Request Join"
            btn_color = self.colors['secondary']
            btn_cmd = lambda: self.send_join_request(group_id, group_name)
        
        if btn_cmd:
            btn = tk.Label(content, text=btn_text, font=('Segoe UI', 9),
                          bg=btn_color, fg='white',
                          cursor='hand2', padx=12, pady=5)
            btn.pack(side=tk.RIGHT)
            btn.bind('<Button-1>', lambda e: btn_cmd())
        else:
            btn = tk.Label(content, text=btn_text, font=('Segoe UI', 9),
                          bg=btn_color, fg='white', padx=12, pady=5)
            btn.pack(side=tk.RIGHT)
        
    def setup_center_column(self, parent):
        """Setup center content area"""
        self.center_container = tk.Frame(parent, bg=self.colors['light'])
        self.center_container.pack(fill=tk.BOTH, expand=True)
        
        self.show_empty_state()
        
    
    

    def send_message_on_enter(self, event):
        """Send message when Enter is pressed"""
        message_text = self.message_entry.get('1.0', tk.END).strip()
        
        if not message_text or not self.current_group:
            return 'break'
        
        self.send_message_logic(message_text)
        return 'break'

    def send_message_on_click(self, event=None):
        """Send chat message - stores avatar NAME only (no upload!)"""
        import tkinter as tk
        from datetime import datetime

        try:
            msg = self.chat_entry.get().strip()
            if not msg:
                return

            if not self.current_group:
                print("⚠ No group selected, cannot send message")
                return

            # Get avatar name
            avatar_id = self.profile_data.get("avatar_id", 1)
            avatar_name = f"avatar {avatar_id}.png"  # ✅ Include .png

            print(f"🔍 Using local avatar: {avatar_name}")

            # === Prepare message ===
            msg_data = {
                "message": msg,
                "sender_id": self.user_id,
                "sender_name": self.get_user_name() or self.profile_data.get("name", "Unknown"),
                "sender_avatar": avatar_name,  # ✅ JUST THE NAME!
                "timestamp": datetime.now().isoformat(),
                "type": "text",
            }

            # --- Clear chat box ---
            self.chat_entry.delete(0, tk.END)

            # --- Push to Firebase ---
            self.db_ref.child(f"studyGroups/{self.current_group}/messages").push(msg_data)

            print(f"📤 Sent message: {msg} with avatar: {avatar_name}")

        except Exception as e:
            print("⚠ Send message error:", e)

            # === Prepare message ===
            msg_data = {
                "message": msg,
                "sender_id": self.user_id,
                "sender_name": self.get_user_name() or self.profile_data.get("name", "Unknown"),
                "sender_avatar": avatar_name,  # ✅ JUST THE NAME!
                "timestamp": datetime.now().isoformat(),
                "type": "text",
            }

            # --- Clear chat box ---
            self.chat_entry.delete(0, tk.END)

            # --- Push to Firebase ---
            self.db_ref.child(f"studyGroups/{self.current_group}/messages").push(msg_data)

            print(f"📤 Sent message: {msg} with avatar: {avatar_url}")

        except Exception as e:
            print("⚠ Send message error:", e)
    
    # ======================================================
    # ✅ COMPLETE CHAT SECTION (FINAL VERSION)
    # ======================================================

    def setup_chat_column(self, parent):
        """Setup right chat column with working scrollbar, avatars, and send button"""
        import tkinter as tk
        from PIL import Image, ImageTk
        import os

        # --- Outer container ---
        chat_container = tk.Frame(parent, bg=self.colors['light'])
        chat_container.pack(fill=tk.Y, expand=True)



        # ===== Header =====
        header = tk.Frame(chat_container, bg=self.colors['secondary'], height=45)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header,
            text="💬 CHAT",
            font=('Segoe UI', 12, 'bold'),
            bg=self.colors['secondary'],
            fg='white'
        ).pack(side=tk.LEFT, padx=12)

        chat_refresh = self._create_soft_button(
            header,
            "🔄 Refresh",
            'white',
            self._reload_chat_messages,
            bg='#6BD18B',
            hover_bg='#5BC47D',
            font=('Segoe UI', 9, 'bold'),
            padding=(10, 4)
        )
        chat_refresh.pack(side=tk.RIGHT, padx=12, pady=8)

        # ===== Messages Area =====
        messages_area = tk.Frame(chat_container, bg='white')
        messages_area.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 4))

        # --- Canvas + Scrollbar ---
        self.messages_canvas = tk.Canvas(messages_area, bg='white', highlightthickness=0, bd=0)
        msg_scroll = tk.Scrollbar(messages_area, orient="vertical", command=self.messages_canvas.yview)
        
        # ✅ Add padding frame to prevent avatar hiding behind scrollbar
        messages_container = tk.Frame(self.messages_canvas, bg='white')
        self.messages_list_frame = tk.Frame(messages_container, bg='white')
        self.messages_list_frame.pack(fill=tk.BOTH, expand=True, padx=(5, 20))  # ✅ Right padding for scrollbar

        # Bind scroll updates with auto-scroll to bottom
        def update_scroll_region(event=None):
            self.messages_canvas.configure(scrollregion=self.messages_canvas.bbox("all"))
            # ✅ Auto-scroll to bottom when new messages arrive
            self.messages_canvas.after(10, lambda: self.messages_canvas.yview_moveto(1.0))
        
        messages_container.bind("<Configure>", update_scroll_region)

        # Add frame inside canvas
        self.canvas_window = self.messages_canvas.create_window(
            (0, 0),
            window=messages_container,
            anchor="nw"
        )

        # Keep width synced
        def _resize_messages(event):
            canvas_width = event.width - 5  # ✅ Account for padding
            self.messages_canvas.itemconfig(self.canvas_window, width=canvas_width)
        self.messages_canvas.bind("<Configure>", _resize_messages)

        self.messages_canvas.configure(yscrollcommand=msg_scroll.set)
        self.messages_canvas.pack(side="left", fill="both", expand=True)
        msg_scroll.pack(side="right", fill="y")
        
        # ✅ Enable mouse wheel scrolling
        def _on_mousewheel(event):
            self.messages_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.messages_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ===== Typing Indicator =====
        self.typing_label = tk.Label(
            chat_container,
            text="",
            font=('Segoe UI', 8, 'italic'),
            bg=self.colors['light'],
            fg=self.colors['gray']
        )
        self.typing_label.pack(fill=tk.X, padx=8, pady=(0, 2))

        # ===== Input Area =====
        input_outer = tk.Frame(chat_container, bg=self.colors['light'])
        input_outer.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=8)

        # ✅ Let its children expand (so send button isn’t clipped)
        input_row = tk.Frame(input_outer, bg='white', relief='solid', borderwidth=1)
        input_row.pack(fill=tk.X, expand=True)
        input_row.pack_propagate(True)

        # --- Text Entry ---
        self.message_entry = tk.Text(
            input_row,
            height=2,
            wrap=tk.WORD,
            font=('Segoe UI', 10),
            bg='white',
            relief='flat',
            bd=0
        )
        self.message_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=8)
        self.message_entry.bind('<Return>', self.send_message_on_enter)
        self.message_entry.bind('<KeyPress>', self.on_typing)

        # --- Send Button with Icon (or Fallback Text) ---
        send_btn_icon = None
        try:
            # Use the pre-defined icon path (set in __init__)
            if hasattr(self, "send_icon_path") and os.path.exists(self.send_icon_path):
                img = Image.open(self.send_icon_path).resize((16, 16), Image.Resampling.LANCZOS)
                send_btn_icon = ImageTk.PhotoImage(img)
            else:
                print(f"⚠ Send icon missing at {getattr(self, 'send_icon_path', 'unknown')}")

        except Exception as e:
            print(f"⚠ Send icon load error: {e}")

        send_btn = tk.Button(
            input_row,
            image=send_btn_icon if send_btn_icon else None,
            text="" if send_btn_icon else "▶",
            font=('Segoe UI', 14, 'bold'),
            bg=self.colors['secondary'],
            fg='white',
            relief='flat',
            bd=0,
            cursor='hand2',
            command=self.send_message_on_click
        )

        if send_btn_icon:
            send_btn.image = send_btn_icon  # ✅ keep icon in memory

        send_btn.pack(side=tk.RIGHT, padx=8, pady=5)

        # --- Final Debug ---
        print("🧩 Chat ready: canvas:", len(self.messages_list_frame.winfo_children()), "scroll:", msg_scroll.winfo_ismapped())
        chat_container.update()



    def start_message_listener(self, group_id):
        """Debug-friendly listener that logs each polling cycle — cleans Firebase avatar URLs before sending to UI."""
        import re, time, threading

        if not self.db_ref:
            print("⚠ No database reference found.")
            return

        self.current_group = group_id
        self.last_message_snapshot = None
        
        # ✅ CRITICAL FIX: Clear loaded message keys when switching groups
        if hasattr(self, "loaded_message_keys"):
            self.loaded_message_keys.clear()
            print(f"🧹 Cleared message cache for new group: {group_id}")

        def poll_messages():
            print(f"🔄 Starting message listener for group {group_id}")
            first_load = True
            while self.current_group == group_id:
                try:
                    ref = self.db_ref.child(f"studyGroups/{group_id}/messages")
                    data = ref.get()

                    if data is None:
                        print("📭 No messages found in Firebase.")
                        data = {}

                    # --- 🧽 Clean avatar URLs before rendering ---
                    try:
                        for key, msg in data.items():
                            if isinstance(msg, dict) and msg.get("sender_avatar"):
                                a = str(msg["sender_avatar"])
                                # remove zero-width, RTL, NBSP, and all whitespace
                                a = re.sub(r'[\u00a0\u2000-\u200f\u202a-\u202e\u2060-\u206f\s]+', '', a)
                                a = a.strip().replace(" /", "/").replace("  ", "").replace(" ", "%20")
                                msg["sender_avatar"] = a
                    except Exception as e:
                        print("⚠ Avatar cleanup failed:", e)

                    # --- Force UI update only when data changes ---
                    if self.last_message_snapshot is None or data != self.last_message_snapshot:
                        print(f"✅ Messages changed: {len(data)} items")
                        self.last_message_snapshot = data
                        # ✅ Force refresh on first load
                        self.parent.after(0, lambda d=data, first=first_load: self.display_messages(d, force_refresh=first))
                        first_load = False
                    else:
                        print("⏸ No new messages")

                except Exception as e:
                    print(f"⚠ Listener error: {e}")

                time.sleep(3)

            print(f"🛑 Listener stopped for {group_id}")

        threading.Thread(target=poll_messages, daemon=True).start()

    def send_message_logic(self, message_text):
        """Send chat message with metadata"""
        if not self.db_ref or not self.current_group:
            return

        try:
            message_data = {
                'sender_id': self.user_id,
                'sender_name': self.get_user_name() or "Unknown",
                'message': message_text.strip(),
                'timestamp': datetime.now().isoformat(),
                'type': 'text'
            }
            self.db_ref.child(f'studyGroups/{self.current_group}/messages').push(message_data)
            self.message_entry.delete('1.0', tk.END)
            self.stop_typing()
        except Exception as e:
            print(f"Send error: {e}")


    def display_messages(self, messages_data, force_refresh=False):
        """Safe and efficient message display – prevents Tkinter crashes and ensures avatar URLs are clean."""
        import tkinter as tk
        import re
        from datetime import datetime

        # ✅ AGGRESSIVE URL CLEANING FUNCTION
        def ultra_clean_url(url):
            if not url:
                return None
            url = str(url)
            # Remove ALL Unicode whitespace and control characters
            url = re.sub(r'[\s\u00a0\u1680\u180e\u2000-\u200f\u2028-\u202f\u205f\u3000\ufeff]+', '', url)
            url = url.strip().replace(" /", "/").replace("/ ", "/")
            url = url.replace(" ", "%20")
            return url

        try:
            # ✅ CRITICAL: Check if all required widgets exist
            if not hasattr(self, "messages_list_frame"):
                print("⚠ messages_list_frame not initialized yet")
                return
            
            if not hasattr(self, "messages_canvas"):
                print("⚠ messages_canvas not initialized yet")
                return
            
            # --- Stop if tab switched or chat frame invalid ---
            try:
                if not self.messages_list_frame.winfo_exists():
                    print("⚠ Message frame destroyed or tab inactive – skipping Firebase UI refresh")
                    return
            except tk.TclError:
                print("⚠ Message frame no longer exists")
                return

            if not hasattr(self, "loaded_message_keys"):
                self.loaded_message_keys = set()
            
            
            # ✅ FORCE REFRESH: Clear loaded keys AND UI if requested
            if force_refresh:
                self.loaded_message_keys.clear()
                # ✅ Clear all existing message widgets to prevent duplicates
                try:
                    for widget in list(self.messages_list_frame.winfo_children()):
                        widget.destroy()
                except:
                    pass
                print("🔄 Force refresh: Cleared message cache and UI")

            # --- Handle empty chat safely ---
            if not messages_data:
                try:
                    if not (self.messages_list_frame and self.messages_list_frame.winfo_exists()):
                        print("⚠ Frame destroyed, skipping empty chat UI update.")
                        return

                    for w in list(self.messages_list_frame.winfo_children()):
                        try:
                            if w and str(w) and w.winfo_exists():
                                w.destroy()
                        except tk.TclError:
                            continue

                    self.loaded_message_keys.clear()

                    if self.messages_list_frame.winfo_exists():
                        placeholder = tk.Label(
                            self.messages_list_frame,
                            text="No messages yet. Start the conversation!",
                            font=("Segoe UI", 9, "italic"),
                            bg="white", fg="#888"
                        )
                        placeholder.pack(pady=20)

                    if self.messages_canvas and self.messages_canvas.winfo_exists():
                        try:
                            self.messages_canvas.update_idletasks()
                            region = self.messages_canvas.bbox("all")
                            if region:
                                self.messages_canvas.configure(scrollregion=region)
                        except tk.TclError:
                            print("⚠ Canvas refresh skipped (window closed)")
                    return

                except tk.TclError:
                    print("⚠ Safe ignore: UI cleared mid-refresh (frame destroyed)")
                    return

            # --- Only render new messages ---
            all_keys = list(messages_data.keys())
            new_keys = [k for k in all_keys if k not in self.loaded_message_keys]

            if not new_keys:
                print("⏸ No new messages")
                return

            # --- Sort by timestamp ---
            sorted_new = sorted(
                [(k, messages_data[k]) for k in new_keys],
                key=lambda x: x[1].get("timestamp", "")
            )

            # --- Render messages safely ---
            for key, msg_data in sorted_new:
                try:
                    msg_data.setdefault("sender_id", "unknown")
                    msg_data.setdefault("sender_name", "Unknown")
                    msg_data.setdefault("message", "")
                    msg_data.setdefault("timestamp", datetime.now().isoformat())

                    if key in self.loaded_message_keys:
                        continue

                    # ✅ CRITICAL: Clean avatar URL BEFORE rendering
                    if msg_data.get("sender_avatar"):
                        msg_data["sender_avatar"] = ultra_clean_url(msg_data["sender_avatar"])

                    self.loaded_message_keys.add(key)
                    self.create_message_widget(msg_data)

                except tk.TclError:
                    print(f"⚠ Widget destroyed mid-render for key={key}")
                except Exception as e:
                    print("⚠ Msg render error:", e)

            # --- Scroll region ---
            try:
                if hasattr(self, 'messages_canvas') and self.messages_canvas and self.messages_canvas.winfo_exists():
                    self.messages_canvas.update_idletasks()
                    region = self.messages_canvas.bbox("all")
                    if region:
                        self.messages_canvas.configure(scrollregion=region)

                        # ✅ Smooth delayed auto-scroll to bottom
                        def _scroll_to_bottom():
                            try:
                                if hasattr(self, 'messages_canvas') and self.messages_canvas and self.messages_canvas.winfo_exists():
                                    self.messages_canvas.yview_moveto(1.0)
                            except Exception:
                                pass

                        # Scroll twice: immediately and after a short delay
                        self.messages_canvas.yview_moveto(1.0)
                        self.messages_canvas.after(150, _scroll_to_bottom)

            except tk.TclError:
                print("⚠ Canvas update skipped (window closed)")
            except Exception as e:
                print(f"⚠ Scroll region update error: {e}")

            # --- Mousewheel scroll binding ---
            def _on_mousewheel(event):
                self.messages_canvas.yview_scroll(-1 * int(event.delta / 120), "units")

            if self.messages_canvas and self.messages_canvas.winfo_exists():
                self.messages_canvas.bind(
                    "<Enter>",
                    lambda e: self.messages_canvas.bind_all("<MouseWheel>", _on_mousewheel)
                )
                self.messages_canvas.bind(
                    "<Leave>",
                    lambda e: self.messages_canvas.unbind_all("<MouseWheel>")
                )
        
        except Exception as e:
            print(f"⚠ Display messages error: {e}")


    def create_message_widget(self, msg_data):
        """Chat bubble with LOCAL avatar loading only"""
        import os, tkinter as tk
        from PIL import Image, ImageTk, ImageDraw
        from datetime import datetime
        from config_paths import app_paths

        sender_id = msg_data.get("sender_id")
        message = msg_data.get("message", "")
        timestamp = msg_data.get("timestamp", "")
        avatar_name = msg_data.get("sender_avatar", "avatar 1.png")  # ✅ GET NAME ONLY

        # Get sender name
        sender_name = msg_data.get("sender_name", "Unknown")
        is_admin = False
        
        try:
            if self.current_group:
                members = self.groups.get(self.current_group, {}).get("members", {})
                member_data = members.get(sender_id, {})
                
                if member_data.get("name"):
                    sender_name = member_data["name"]
                if member_data.get("avatar_name"):
                    avatar_name = member_data["avatar_name"]
                is_admin = member_data.get("role") == "admin"
        except Exception as e:
            print("⚠ Member fetch error:", e)

        is_own = sender_id == self.user_id

        # ✅ CRITICAL: Check if avatar_name is an old HTTP URL
        if avatar_name and avatar_name.startswith("http"):
            print(f"⚠ Old message with HTTP URL detected, using member's current avatar instead")
            # Get current avatar from member data
            avatar_id = 1
            try:
                if self.current_group:
                    members = self.groups.get(self.current_group, {}).get("members", {})
                    member_data = members.get(sender_id, {})
                    if 'avatar_id' in member_data:
                        avatar_id = member_data['avatar_id']
                    elif 'avatar_name' in member_data:
                        avatar_name = member_data['avatar_name']
            except:
                pass
            
            # If still HTTP, use default
            if avatar_name.startswith("http"):
                avatar_name = f"avatar {avatar_id}.png"
        
        # ✅ BUILD LOCAL PATH FROM AVATAR NAME
        if not avatar_name.endswith('.png'):
            avatar_path = os.path.join(app_paths.avatars_dir, f"{avatar_name}.png")
        else:
            avatar_path = os.path.join(app_paths.avatars_dir, avatar_name)

        print(f"🎯 Rendering msg from {sender_name} | avatar={avatar_name} | path={avatar_path} | exists={os.path.exists(avatar_path)}")

        # === MESSAGE FRAME ===
        msg_frame = tk.Frame(self.messages_list_frame, bg="white")
        msg_frame.pack(fill=tk.X, padx=6, pady=2)

        # === OWN MESSAGE (right side) ===
        if is_own:
            # ✅ Create wrapper with max width constraint
            wrapper = tk.Frame(msg_frame, bg="white")
            wrapper.pack(side=tk.RIGHT, anchor="e")
            
            right_container = tk.Frame(wrapper, bg="white")
            right_container.pack(anchor="e", padx=(0, 10))
            right_container.configure(width=300)  # ✅ Max width for message + avatar
            
            # Avatar
            avatar_size = 28
            avatar_frame = tk.Frame(right_container, bg="white")
            avatar_frame.pack(side=tk.RIGHT, anchor="ne", padx=(5, 0))
            
            avatar_loaded = False
            try:
                if os.path.exists(avatar_path):
                    avatar_img = Image.open(avatar_path).convert("RGBA")
                    avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                    mask = Image.new("L", (avatar_size, avatar_size), 0)
                    ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
                    output = Image.new("RGBA", (avatar_size, avatar_size), (255, 255, 255, 255))
                    output.paste(avatar_img, (0, 0), mask)
                    avatar_photo = ImageTk.PhotoImage(output)
                    lbl = tk.Label(avatar_frame, image=avatar_photo, bg="white")
                    lbl.image = avatar_photo
                    lbl.pack()
                    if not hasattr(self, "_message_avatar_cache"):
                        self._message_avatar_cache = []
                    self._message_avatar_cache.append(avatar_photo)
                    avatar_loaded = True
                    print(f"✅ Own avatar loaded from: {avatar_path}")
            except Exception as e:
                print(f"⚠ Own avatar load failed: {e}")
            
            if not avatar_loaded:
                canvas = tk.Canvas(avatar_frame, width=avatar_size, height=avatar_size, bg="white", highlightthickness=0)
                canvas.pack()
                initials = "".join([w[0].upper() for w in sender_name.split()[:2]]) or "?"
                canvas.create_oval(1, 1, avatar_size - 1, avatar_size - 1, fill=self.colors["primary"], outline="")
                canvas.create_text(avatar_size // 2, avatar_size // 2, text=initials, fill="white", font=("Segoe UI", 9, "bold"))
            
            # Message content
            right = tk.Frame(right_container, bg="white")
            right.pack(side=tk.RIGHT, anchor="e")
            
            name_frame = tk.Frame(right, bg="white")
            name_frame.pack(anchor="e", pady=(0, 1))
            
            if is_admin:
                tk.Label(name_frame, text="👑", font=("Segoe UI", 8), bg="white").pack(side=tk.RIGHT, padx=(2, 0))
            
            tk.Label(name_frame, text=sender_name, font=("Segoe UI", 8, "bold" if is_admin else "normal"),
                     bg="white", fg="#FF6B6B" if is_admin else "#2C3E50").pack(side=tk.RIGHT)
            
            bubble_bg = "#FFE5E5" if is_admin else self.colors["primary"]
            text_color = "#C41E3A" if is_admin else "white"
            bubble = tk.Frame(right, bg=bubble_bg, padx=8, pady=4,
                             highlightbackground="#FF6B6B" if is_admin else bubble_bg,
                             highlightthickness=2 if is_admin else 0)
            bubble.pack(anchor="e")
            tk.Label(bubble, text=message, font=("Segoe UI", 9),
                     bg=bubble_bg, fg=text_color, wraplength=200, justify=tk.LEFT).pack(anchor="w")
            try:
                time_str = datetime.fromisoformat(timestamp).strftime("%I:%M %p")
            except Exception:
                time_str = ""
            tk.Label(bubble, text=time_str, font=("Segoe UI", 7),
                     bg=bubble_bg, fg="#999999" if is_admin else "#E0E0E0").pack(anchor="e", pady=(1, 0))
            return

        # === OTHER USERS (left side) ===
        # ✅ Create wrapper with max width constraint
        wrapper = tk.Frame(msg_frame, bg="white")
        wrapper.pack(side=tk.LEFT, anchor="w")

        left_container = tk.Frame(wrapper, bg="white")
        left_container.pack(anchor="w")
        left_container.configure(width=300)  # ✅ Max width for message + avatar

        avatar_size = 28
        avatar_frame = tk.Frame(left_container, bg="white")
        avatar_frame.pack(side=tk.LEFT, anchor="nw", padx=(0, 5))

        # Load avatar
        avatar_loaded = False
        try:
            if os.path.exists(avatar_path):
                avatar_img = Image.open(avatar_path).convert("RGBA")
                avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                mask = Image.new("L", (avatar_size, avatar_size), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
                output = Image.new("RGBA", (avatar_size, avatar_size), (255, 255, 255, 255))
                output.paste(avatar_img, (0, 0), mask)
                avatar_photo = ImageTk.PhotoImage(output)
                lbl = tk.Label(avatar_frame, image=avatar_photo, bg="white")
                lbl.image = avatar_photo
                lbl.pack()
                if not hasattr(self, "_message_avatar_cache"):
                    self._message_avatar_cache = []
                self._message_avatar_cache.append(avatar_photo)
                avatar_loaded = True
                print(f"✅ Avatar loaded from: {avatar_path}")
        except Exception as e:
            print(f"⚠ Avatar load failed: {e}")
        
        if not avatar_loaded:
            canvas = tk.Canvas(avatar_frame, width=avatar_size, height=avatar_size, bg="white", highlightthickness=0)
            canvas.pack()
            initials = "".join([w[0].upper() for w in sender_name.split()[:2]]) or "?"
            canvas.create_oval(1, 1, avatar_size - 1, avatar_size - 1, fill="#95A5A6", outline="")
            canvas.create_text(avatar_size // 2, avatar_size // 2, text=initials, fill="white", font=("Segoe UI", 9, "bold"))

        # Message bubble
        content_frame = tk.Frame(left_container, bg="white")
        content_frame.pack(side=tk.LEFT, fill=tk.X)

        name_frame = tk.Frame(content_frame, bg="white")
        name_frame.pack(anchor="w", pady=(0, 1))
        
        if is_admin:
            tk.Label(name_frame, text="👑 ADMIN", font=("Segoe UI", 7, "bold"),
                     bg="white", fg="#FF6B6B").pack(side=tk.LEFT, padx=(0, 4))
        
        name_color = "#FF6B6B" if is_admin else "#2C3E50"
        tk.Label(name_frame, text=sender_name, font=("Segoe UI", 8, "bold" if is_admin else "normal"),
                 bg="white", fg=name_color).pack(side=tk.LEFT)

        if is_admin:
            bubble_bg = "#FFF3E0"
            border_color = "#FF9800"
            text_color = "#E65100"
            highlight_thickness = 2
        else:
            bubble_bg = "#F0F0F0"
            border_color = "#F0F0F0"
            text_color = "black"
            highlight_thickness = 0
            
        bubble = tk.Frame(content_frame, bg=bubble_bg,
                          highlightbackground=border_color,
                          highlightthickness=highlight_thickness,
                          padx=8, pady=4)
        bubble.pack(anchor="w")

        tk.Label(bubble, text=message, font=("Segoe UI", 9, "bold" if is_admin else "normal"),
                 bg=bubble_bg, fg=text_color, wraplength=200, justify=tk.LEFT).pack(anchor="w")

        try:
            time_str = datetime.fromisoformat(timestamp).strftime("%I:%M %p")
        except Exception:
            time_str = ""
        tk.Label(bubble, text=time_str, font=("Segoe UI", 7),
                 bg=bubble_bg, fg="#666666").pack(anchor="e", pady=(1, 0))

        
    def show_empty_state(self):
        """Show empty state"""
        for widget in self.center_container.winfo_children():
            widget.destroy()
        
        empty = tk.Frame(self.center_container, bg=self.colors['light'])
        empty.pack(expand=True)
        
        tk.Label(empty, text="👥", font=('Segoe UI', 60), bg=self.colors['light']).pack(pady=20)
        tk.Label(empty, text="Select a group to get started",
                font=('Segoe UI', 16), bg=self.colors['light'],
                fg=self.colors['gray']).pack()
        
    def show_group_content(self):
        """Show group content with FIXED header and scrollable body"""
        if not self.current_group or self.current_group not in self.groups:
            return

        for widget in self.center_container.winfo_children():
            widget.destroy()

        container = tk.Frame(self.center_container, bg=self.colors['light'])
        container.pack(fill=tk.BOTH, expand=True)

        # ✅ FIXED HEADER (non-scrollable)
        header_container = tk.Frame(container, bg=self.colors['light'])
        header_container.pack(fill=tk.X, side=tk.TOP)
        
        self.create_group_header(header_container)

        # ✅ SCROLLABLE BODY (plans + members only)
        scrollable_frame = tk.Frame(container, bg=self.colors['light'])
        scrollable_frame.pack(fill=tk.BOTH, expand=True, side=tk.BOTTOM)

        canvas = tk.Canvas(scrollable_frame, bg=self.colors['light'], highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(scrollable_frame, orient="vertical", command=canvas.yview)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        content = tk.Frame(canvas, bg=self.colors['light'])
        canvas_window = canvas.create_window((0, 0), window=content, anchor="nw")

        def resize_canvas(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", resize_canvas)

        def update_scroll(event=None):
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        content.bind("<Configure>", update_scroll)
        canvas.configure(yscrollcommand=scrollbar.set)

        # ✅ TWO COLUMN LAYOUT (Plans + Members)
        two_col_frame = tk.Frame(content, bg=self.colors['light'])
        two_col_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        plans_col = tk.Frame(two_col_frame, bg=self.colors['light'])
        plans_col.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        plans_col.configure(width=330)

        members_col = tk.Frame(two_col_frame, bg=self.colors['light'])
        members_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        self.create_plans_section(plans_col)
        self.create_admins_section(members_col)
        self.create_enrolled_members_section(members_col)
        self.create_all_members_section(members_col)

        def finalize_scroll():
            try:
                if canvas.winfo_exists():
                    canvas.update_idletasks()
                    bbox = canvas.bbox("all")
                    if bbox:
                        canvas.configure(scrollregion=(bbox[0], bbox[1], bbox[2], bbox[3] + 50))
                    canvas.yview_moveto(0)
            except Exception:
                pass
        
        self.center_container.after(100, finalize_scroll)
        self.center_container.after(300, finalize_scroll)

        def _on_mousewheel(event):
            try:
                if canvas.winfo_exists():
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def refresh_scroll_region(self):
        """Force update of canvas scroll region"""
        try:
            for widget in self.center_container.winfo_children():
                if isinstance(widget, tk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Canvas):
                            child.update_idletasks()
                            child.configure(scrollregion=child.bbox("all"))
        except Exception as e:
            print("Scroll refresh error:", e)
            
    def exit_group(self):
        """Exit/leave the current group"""
        if not self.current_group:
            return
        
        group_name = self.groups[self.current_group].get('metadata', {}).get('name', 'this group')
        
        if not messagebox.askyesno("Exit Group", 
            f"Are you sure you want to exit '{group_name}'?\n\nYou will need an invite code to rejoin."):
            return
        
        if not self.db_ref:
            return
        
        try:
            # Remove user from group members
            member_ref = self.db_ref.child(f'studyGroups/{self.current_group}/members/{self.user_id}')
            member_ref.delete()
            
            # Unenroll from all plans in this group
            plans_ref = self.db_ref.child(f'studyGroups/{self.current_group}/plans')
            plans_data = plans_ref.get()
            
            if plans_data:
                for plan_id, plan_data in plans_data.items():
                    enrolled = plan_data.get('enrolled_members', [])
                    if self.user_id in enrolled:
                        enrolled.remove(self.user_id)
                        plans_ref.child(f'{plan_id}/enrolled_members').set(enrolled)
            
            messagebox.showinfo("Success", f"You have left '{group_name}'")
            
            # Clear current group and refresh
            self.current_group = None
            self.show_empty_state()
            self.load_all_groups()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to exit group: {e}")
        
    def create_group_header(self, parent):
        """✅ Group header with colored background and exit option"""
        group_data = self.groups.get(self.current_group, {})
        metadata = group_data.get('metadata', {})
        group_name = metadata.get('name', 'Unnamed')
        group_desc = metadata.get('description', 'No description')
        icon_url = metadata.get('icon_url', None)
        header_bg_color = metadata.get('header_bg_color', self.colors['light'])  # ✅ Get color
        created_by = metadata.get('created_by')

        # ✅ MAIN HEADER CONTAINER with background color
        header = tk.Frame(parent, bg=header_bg_color)  # ✅ Use background color
        header.pack(fill=tk.X, padx=20, pady=20)

        # === Icon + Info Row ===
        top_row = tk.Frame(header, bg=header_bg_color)
        top_row.pack(fill=tk.X, padx=15, pady=15)

        # === SMOOTH CIRCULAR ICON ===
        size = 80
        icon_canvas = tk.Canvas(top_row, width=size, height=size,
                                bg=header_bg_color, highlightthickness=0)
        icon_canvas.pack(side=tk.LEFT, padx=(0, 20))

        def draw_group_icon(url=None):
            """Load from URL or draw default"""
            try:
                if url:
                    from urllib.request import urlopen
                    img_data = urlopen(url, timeout=10).read()
                    img = Image.open(BytesIO(img_data)).convert("RGBA")
                    img = img.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
                else:
                    raise ValueError("No URL")
            except Exception as e:
                print(f"Icon load error: {e}")
                img = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                draw.ellipse([20, 20, size*2-20, size*2-20], fill="#95A5A6")
                
                try:
                    font = ImageFont.truetype("seguiemj.ttf", 64)
                    draw.text((size - 32, size - 40), "👥", fill="white", font=font)
                except:
                    try:
                        font = ImageFont.truetype("arial.ttf", 48)
                        draw.text((size - 20, size - 32), "GP", fill="white", font=font)
                    except:
                        pass

            from PIL import ImageFilter
            mask = Image.new("L", (size * 2, size * 2), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((2, 2, size*2-2, size*2-2), fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(2))
            
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            img.putalpha(mask)
            img = img.resize((size, size), Image.Resampling.LANCZOS)

            photo = ImageTk.PhotoImage(img)
            icon_canvas.delete("all")
            icon_canvas.create_oval(2, 2, size-2, size-2, fill="#E0E0E0", outline="")
            icon_canvas.create_image(size//2, size//2, image=photo)
            icon_canvas.image = photo
            icon_canvas.create_oval(1, 1, size-1, size-1, outline="#D0D0D0", width=1)

        draw_group_icon(icon_url)

        if self.is_admin(self.current_group):
            def on_icon_click(e):
                self.change_group_icon(lambda new_url: draw_group_icon(new_url))
            icon_canvas.bind("<Button-1>", on_icon_click)
            icon_canvas.config(cursor='hand2')

        # === RIGHT: Name + Buttons ===
        info_frame = tk.Frame(top_row, bg=header_bg_color)
        info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        name_row = tk.Frame(info_frame, bg=header_bg_color)
        name_row.pack(fill=tk.X)

        tk.Label(name_row, text=group_name, font=('Segoe UI', 18, 'bold'),
                 bg=header_bg_color, fg=self.colors['dark']).pack(side=tk.LEFT)

        # Always show online status as right-aligned free text
        online_count = self.get_online_members_count(self.current_group)
        online_label = tk.Label(
            name_row,
            text=f"🟢 Online ({online_count})",
            font=('Segoe UI', 9),
            bg=header_bg_color,
            fg='#00CC66'
        )
        online_label.pack(side=tk.RIGHT)

        # Manual refresh for the entire groups tab
        refresh_btn = self._create_soft_button(
            name_row,
            "🔄 Refresh",
            self.colors['secondary'],
            self.refresh_groups_tab,
            bg='#E8F5E9',
            hover_bg='#D5EFE0',
            font=('Segoe UI', 9, 'bold'),
            padding=(8, 3)
        )
        refresh_btn.pack(side=tk.RIGHT, padx=(0, 8))

        # ✅ EXIT BUTTON (non-creators only)
        if self.user_id != created_by:
            exit_btn = tk.Label(name_row, text="🚪 Exit", font=('Segoe UI', 9),
                               bg=header_bg_color, fg=self.colors['accent'], cursor='hand2')
            exit_btn.pack(side=tk.RIGHT)
            exit_btn.bind('<Button-1>', lambda e: self.exit_group())

        # Description
        desc_frame = tk.Frame(info_frame, bg=self.colors['bg'])
        desc_frame.pack(fill=tk.X, pady=(10, 0))
        tk.Label(desc_frame, text=group_desc, font=('Segoe UI', 10),
                 bg=self.colors['bg'], fg=self.colors['dark'],
                 wraplength=600, justify=tk.LEFT).pack(padx=15, pady=15)

        # ✅ ADMIN OPTIONS
        if self.is_admin(self.current_group):
            edit_btn = self._create_soft_button(
                name_row,
                "✏ Edit",
                self.colors['primary'],
                self.edit_group_info,
                padding=(8, 3)
            )
            edit_btn.pack(side=tk.LEFT, padx=(10, 0))

            share_btn = self._create_soft_button(
                name_row,
                "🔗 Share",
                self.colors['secondary'],
                self.share_invite_link,
                padding=(8, 3)
            )
            share_btn.pack(side=tk.LEFT, padx=(10, 0))

            # ✅ NOTIFY ALL BUTTON (Admin only)
            notify_btn = self._create_soft_button(
                name_row,
                "📢 Notify All",
                '#9B59B6',
                self.notify_all_members,
                font=('Segoe UI', 9, 'bold'),
                padding=(8, 3)
            )
            notify_btn.pack(side=tk.LEFT, padx=(10, 0))
            
            # ✅ JOIN REQUESTS BUTTON
            pending_count = len(group_data.get('pending_requests', {}))
            if pending_count > 0:
                requests_btn = tk.Label(name_row, text=f"📩 Requests ({pending_count})",
                                       font=('Segoe UI', 9),
                                       bg=header_bg_color, fg=self.colors['accent'], cursor='hand2')
                requests_btn.pack(side=tk.LEFT, padx=(10, 0))
                requests_btn.bind('<Button-1>', lambda e: self.show_join_requests())

        # ✅ LIBRARY BUTTON (visible to all members)
        library_btn = self._create_soft_button(
            name_row,
            "📚 Library",
            self.colors['dark'],
            self.open_library_window,
            padding=(8, 3),
            font=('Segoe UI', 9, 'bold')
        )
        library_btn.pack(side=tk.LEFT, padx=(10, 0))

    def is_admin_or_creator(self):
        """Check if current user is admin or creator for the active group."""
        if not self.current_group:
            return False
        return self.is_creator(self.current_group) or self.is_admin(self.current_group)

    def open_library_window(self):
        """Open the shared group library for all members."""
        if not self.current_group:
            return

        try:
            if hasattr(self, 'library_window') and self.library_window.winfo_exists():
                self.library_window.lift()
                self.render_library_lists()
                return
        except Exception:
            pass

        window = tk.Toplevel(self.parent)
        window.title("Group Library")
        window.geometry("780x620")
        window.transient(self.parent)
        window.configure(bg=self.colors['light'])
        self.library_window = window
        self.library_image_cache = {}

        def on_close():
            try:
                if hasattr(self, 'library_window'):
                    delattr(self, 'library_window')
                if hasattr(self, 'library_body_frame'):
                    delattr(self, 'library_body_frame')
                if hasattr(self, 'library_approved_frame'):
                    delattr(self, 'library_approved_frame')
                if hasattr(self, 'library_pending_frame'):
                    delattr(self, 'library_pending_frame')
            except Exception:
                pass
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", on_close)

        header = tk.Frame(window, bg=self.colors['primary'])
        header.pack(fill=tk.X)

        tk.Label(header, text="📚 Group Library", font=('Segoe UI', 14, 'bold'),
                 bg=self.colors['primary'], fg='white').pack(side=tk.LEFT, padx=15, pady=12)

        add_btn = tk.Button(header, text="➕ Add Material", font=('Segoe UI', 10, 'bold'),
                            bg=self.colors['secondary'], fg='white', relief='flat', padx=15, pady=6,
                            cursor='hand2', command=self.show_add_library_dialog)
        add_btn.pack(side=tk.RIGHT, padx=15, pady=10)

        # Scrollable body
        body_container = tk.Frame(window, bg=self.colors['light'])
        body_container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(body_container, bg=self.colors['light'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(body_container, orient="vertical", command=canvas.yview)
        self.library_body_frame = tk.Frame(canvas, bg=self.colors['light'])

        frame_window = canvas.create_window((0, 0), window=self.library_body_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        self.library_body_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(frame_window, width=e.width))

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Approved and pending sections
        self.library_approved_frame = tk.Frame(self.library_body_frame, bg=self.colors['light'])
        self.library_approved_frame.pack(fill=tk.X, padx=15, pady=(10, 5))

        self.library_pending_frame = tk.Frame(self.library_body_frame, bg=self.colors['light'])
        self.library_pending_frame.pack(fill=tk.X, padx=15, pady=(5, 15))

        self.render_library_lists()

    def render_library_lists(self):
        """Render approved materials and pending approvals."""
        if not self.current_group or not getattr(self, 'library_body_frame', None):
            return

        for frame in [self.library_approved_frame, self.library_pending_frame]:
            for widget in frame.winfo_children():
                widget.destroy()

        tk.Label(self.library_approved_frame, text="✅ Approved Materials", font=('Segoe UI', 12, 'bold'),
                 bg=self.colors['light'], fg=self.colors['dark']).pack(anchor='w', pady=(0, 8))

        library_data = {}
        if self.db_ref:
            try:
                library_data = self.db_ref.child(f'studyGroups/{self.current_group}/library').get() or {}
            except Exception as e:
                tk.Label(self.library_approved_frame, text=f"Error loading library: {e}",
                         font=('Segoe UI', 9), bg=self.colors['light'], fg=self.colors['accent']).pack(anchor='w', pady=5)
                return

        approved_items = []
        pending_items = []
        for item_id, item in library_data.items():
            if item.get('status', 'approved') == 'pending':
                pending_items.append((item_id, item))
            else:
                approved_items.append((item_id, item))

        def _sort_items(items):
            def parse_time(ts):
                try:
                    return datetime.fromisoformat(ts)
                except Exception:
                    return datetime.min

            return sorted(
                items,
                key=lambda pair: (
                    0 if pair[1].get('pinned') else 1,
                    -parse_time(pair[1].get('uploaded_at', '')).timestamp()
                )
            )

        if approved_items:
            for item_id, item in _sort_items(approved_items):
                self.create_library_item(self.library_approved_frame, item_id, item, approved=True)
        else:
            tk.Label(self.library_approved_frame, text="No approved materials yet.",
                     font=('Segoe UI', 9), bg=self.colors['light'], fg=self.colors['gray']).pack(anchor='w', pady=5)

        # Pending section
        tk.Label(self.library_pending_frame, text="⏳ Pending Approval", font=('Segoe UI', 12, 'bold'),
                 bg=self.colors['light'], fg=self.colors['dark']).pack(anchor='w', pady=(10, 8))

        if pending_items:
            for item_id, item in pending_items:
                self.create_library_item(self.library_pending_frame, item_id, item, approved=False)
        else:
            tk.Label(self.library_pending_frame, text="No pending submissions.",
                     font=('Segoe UI', 9), bg=self.colors['light'], fg=self.colors['gray']).pack(anchor='w', pady=5)

    def create_library_item(self, parent, item_id, item_data, approved=True):
        """Render a single library entry."""
        card = tk.Frame(parent, bg='white', relief='solid', borderwidth=1)
        card.pack(fill=tk.X, pady=4)

        inner = tk.Frame(card, bg='white')
        inner.pack(fill=tk.X, padx=10, pady=8)

        icon_map = {'pdf': '📕', 'link': '🔗', 'image': '🖼️', 'file': '📎'}
        preview_container = tk.Frame(inner, bg='white')
        preview_container.pack(side=tk.LEFT, padx=(0, 8))

        preview_rendered = False
        if item_data.get('type') == 'image' and item_data.get('url'):
            try:
                if not hasattr(self, 'library_image_cache'):
                    self.library_image_cache = {}
                cached = self.library_image_cache.get(item_data['url'])
                if not cached:
                    response = requests.get(item_data['url'], timeout=8)
                    response.raise_for_status()
                    image = Image.open(BytesIO(response.content))
                    image.thumbnail((72, 72))
                    cached = ImageTk.PhotoImage(image)
                    self.library_image_cache[item_data['url']] = cached
                img_label = tk.Label(preview_container, image=cached, bg='white')
                img_label.image = cached
                img_label.pack()
                preview_rendered = True
            except Exception as e:
                print(f"⚠️ Failed to render image preview: {e}")

        if not preview_rendered:
            icon = icon_map.get(item_data.get('type', 'file'), '📎')
            tk.Label(preview_container, text=icon, font=('Segoe UI', 14), bg='white').pack()

        text_frame = tk.Frame(inner, bg='white')
        text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        name = item_data.get('name', 'Untitled')
        uploader = item_data.get('uploader_name', 'Unknown')
        status = item_data.get('status', 'approved')
        uploaded_at = item_data.get('uploaded_at', '')

        tk.Label(text_frame, text=name, font=('Segoe UI', 10, 'bold'), bg='white', anchor='w').pack(fill=tk.X)
        detail_text = f"By {uploader}"
        if uploaded_at:
            detail_text += f" • {uploaded_at.split('T')[0]}"
        if not approved:
            detail_text += " • Pending"
        tk.Label(text_frame, text=detail_text, font=('Segoe UI', 9), bg='white', fg=self.colors['gray']).pack(anchor='w')

        meta_frame = tk.Frame(text_frame, bg='white')
        meta_frame.pack(anchor='w', pady=(4, 0))

        tk.Label(meta_frame, text=f"Type: {item_data.get('type', 'file').capitalize()}",
                 font=('Segoe UI', 8, 'bold'), bg=self.colors['light'],
                 fg=self.colors['dark'], padx=6, pady=2).pack(side=tk.LEFT, padx=(0, 6))

        if item_data.get('pinned'):
            tk.Label(meta_frame, text="📌 Pinned", font=('Segoe UI', 8, 'bold'),
                     bg=self.colors['secondary'], fg='white', padx=6, pady=2).pack(side=tk.LEFT, padx=(0, 6))

        views = item_data.get('views', 0)
        tk.Label(meta_frame, text=f"👁️ {views}", font=('Segoe UI', 8), bg=self.colors['light'],
                 fg=self.colors['dark'], padx=6, pady=2).pack(side=tk.LEFT)

        # Actions
        actions = tk.Frame(inner, bg='white')
        actions.pack(side=tk.RIGHT, anchor='e')

        button_row = tk.Frame(actions, bg='white')
        button_row.pack(anchor='e')

        open_btn = tk.Label(button_row, text="Open", font=('Segoe UI', 9, 'bold'),
                            bg=self.colors['primary'], fg='white', cursor='hand2', padx=10, pady=4)
        open_btn.pack(side=tk.LEFT, padx=4, pady=2)
        open_btn.bind('<Button-1>', lambda e, data=item_data, iid=item_id: self.open_material(data, iid))

        download_btn = tk.Label(button_row, text="Download", font=('Segoe UI', 9),
                                bg=self.colors['secondary'], fg='white', cursor='hand2', padx=10, pady=4)
        download_btn.pack(side=tk.LEFT, padx=4, pady=2)
        download_btn.bind('<Button-1>', lambda e, data=item_data: self.download_material(data))

        if self.is_admin_or_creator():
            if approved:
                pin_text = "Unpin" if item_data.get('pinned') else "Pin"
                pin_btn = tk.Label(button_row, text=pin_text, font=('Segoe UI', 9),
                                   bg=self.colors['secondary'], fg='white', cursor='hand2', padx=10, pady=4)
                pin_btn.pack(side=tk.LEFT, padx=4, pady=2)
                pin_btn.bind('<Button-1>', lambda e, iid=item_id, current=item_data.get('pinned', False):
                             self.toggle_library_pin(iid, not current))

                remove_btn = tk.Label(button_row, text="Remove", font=('Segoe UI', 9),
                                      bg=self.colors['accent'], fg='white', cursor='hand2', padx=10, pady=4)
                remove_btn.pack(side=tk.LEFT, padx=4, pady=2)
                remove_btn.bind('<Button-1>', lambda e, iid=item_id: self.remove_library_item(iid))
            else:
                approve_btn = tk.Label(button_row, text="Approve", font=('Segoe UI', 9, 'bold'),
                                       bg=self.colors['secondary'], fg='white', cursor='hand2', padx=10, pady=4)
                approve_btn.pack(side=tk.LEFT, padx=4, pady=2)
                approve_btn.bind('<Button-1>', lambda e, iid=item_id: self.update_library_status(iid, 'approved'))

                reject_btn = tk.Label(button_row, text="Reject", font=('Segoe UI', 9),
                                      bg=self.colors['accent'], fg='white', cursor='hand2', padx=10, pady=4)
                reject_btn.pack(side=tk.LEFT, padx=4, pady=2)
                reject_btn.bind('<Button-1>', lambda e, iid=item_id: self.remove_library_item(iid))
        else:
            if not approved:
                tk.Label(button_row, text="Awaiting approval", font=('Segoe UI', 8),
                         bg='white', fg=self.colors['gray'], padx=6).pack(side=tk.LEFT, padx=4, pady=2)

    def show_add_library_dialog(self):
        """Dialog for adding new library material."""
        if not self.current_group:
            return

        dialog = tk.Toplevel(self.library_window if hasattr(self, 'library_window') else self.parent)
        dialog.title("Add Library Material")
        dialog.geometry("420x360")
        dialog.transient(self.parent)
        dialog.grab_set()

        tk.Label(dialog, text="Material Name", font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=20, pady=(20, 5))
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(padx=20, fill=tk.X)

        tk.Label(dialog, text="Type", font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=20, pady=(15, 5))
        type_var = tk.StringVar(value='file')
        type_combo = ttk.Combobox(dialog, textvariable=type_var, values=['file', 'pdf', 'image', 'link'], state='readonly')
        type_combo.pack(padx=20, fill=tk.X)

        link_frame = tk.Frame(dialog)
        link_frame.pack(fill=tk.X, padx=20, pady=(15, 5))
        tk.Label(link_frame, text="URL (for links)", font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        url_entry = ttk.Entry(link_frame, width=40)
        url_entry.pack(fill=tk.X, pady=(5, 0))

        file_frame = tk.Frame(dialog)
        file_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
        file_path_var = tk.StringVar()

        tk.Label(file_frame, text="File (any type)", font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        file_row = tk.Frame(file_frame)
        file_row.pack(fill=tk.X, pady=(5, 0))
        file_entry = ttk.Entry(file_row, textvariable=file_path_var, width=30)
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def browse_file():
            filetypes = [("All files", "*.*")]
            path = filedialog.askopenfilename(title="Select file", filetypes=filetypes)
            if path:
                file_path_var.set(path)

        ttk.Button(file_row, text="Browse", command=browse_file).pack(side=tk.LEFT, padx=5)

        def save_material():
            name = name_entry.get().strip()
            selected_type = type_var.get()
            url = url_entry.get().strip()
            status = 'approved' if self.is_admin_or_creator() else 'pending'

            if not name:
                messagebox.showerror("Error", "Please provide a name for the material.")
                return

            material_url = None

            if selected_type == 'link':
                if not url:
                    messagebox.showerror("Error", "Please provide a URL for the link.")
                    return
                material_url = url
            else:
                if not self.storage_bucket:
                    messagebox.showerror("Error", "Storage not available for file uploads.")
                    return
                path = file_path_var.get()
                if not path or not os.path.exists(path):
                    messagebox.showerror("Error", "Please choose a file to upload.")
                    return
                try:
                    file_size_mb = os.path.getsize(path) / (1024 * 1024)
                    if file_size_mb > 5:
                        messagebox.showerror("Error", "File must be 5 MB or smaller.")
                        return
                except Exception:
                    messagebox.showerror("Error", "Unable to read file size.")
                    return

                filename = os.path.basename(path)
                progress_dialog = self._show_progress_dialog(dialog, f"Uploading {filename}...")

                def perform_upload():
                    upload_error = None
                    upload_url = None
                    try:
                        blob_path = f'groups/{self.current_group}/library/{int(time.time())}_{filename}'
                        blob = self.storage_bucket.blob(blob_path)
                        blob.upload_from_filename(path)
                        blob.make_public()
                        upload_url = blob.public_url
                    except Exception as e:
                        upload_error = e

                    def finalize():
                        if progress_dialog and progress_dialog.winfo_exists():
                            progress_dialog.destroy()
                        if upload_error:
                            messagebox.showerror("Error", f"Failed to upload file: {upload_error}")
                            return
                        self._save_library_entry(name, selected_type, upload_url, status, dialog)

                    dialog.after(0, finalize)

                threading.Thread(target=perform_upload, daemon=True).start()
                return

            self._save_library_entry(name, selected_type, material_url, status, dialog)

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="Save", bg=self.colors['secondary'], fg='white', relief='flat',
                 padx=20, command=save_material).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="Cancel", bg=self.colors['gray'], fg='white', relief='flat',
                 padx=20, command=dialog.destroy).pack(side=tk.LEFT, padx=8)

    def _save_library_entry(self, name, selected_type, material_url, status, dialog):
        """Persist a new library entry and refresh UI."""
        try:
            entry = {
                'name': name,
                'type': selected_type,
                'url': material_url,
                'uploaded_by': self.user_id,
                'uploader_name': self.get_user_name(),
                'uploaded_at': datetime.now().isoformat(),
                'status': status,
                'pinned': False,
                'views': 0
            }
            ref = self.db_ref.child(f'studyGroups/{self.current_group}/library').push()
            ref.set(entry)
            if dialog and dialog.winfo_exists():
                dialog.destroy()
            self.refresh_group_data()
            self.render_library_lists()
            if status == 'pending':
                messagebox.showinfo("Submitted", "Your material is pending approval by an admin or creator.")
            else:
                messagebox.showinfo("Added", "Material added to the library.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save material: {e}")

    def _show_progress_dialog(self, parent, message):
        """Show an indeterminate progress dialog while a task runs."""
        dialog = tk.Toplevel(parent)
        dialog.title("Please wait")
        dialog.geometry("320x140")
        dialog.transient(parent)
        dialog.grab_set()

        tk.Label(dialog, text=message, font=('Segoe UI', 10, 'bold')).pack(pady=(20, 10))
        bar = ttk.Progressbar(dialog, mode='indeterminate', length=240)
        bar.pack(pady=(0, 10))
        bar.start(10)

        tk.Label(dialog, text="This may take a few seconds...", font=('Segoe UI', 9), fg=self.colors['gray']).pack()
        return dialog

    def update_library_status(self, item_id, status):
        """Approve or update status for a library item."""
        if not self.current_group or not self.db_ref:
            return
        try:
            self.db_ref.child(f'studyGroups/{self.current_group}/library/{item_id}/status').set(status)
            self.refresh_group_data()
            self.render_library_lists()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update status: {e}")

    def toggle_library_pin(self, item_id, should_pin):
        """Toggle the pinned state for a library item (admin only)."""
        if not self.current_group or not self.db_ref:
            return

        if not self.is_admin_or_creator():
            messagebox.showwarning("Permission denied", "Only admins or the creator can pin items.")
            return

        try:
            self.db_ref.child(f'studyGroups/{self.current_group}/library/{item_id}/pinned').set(bool(should_pin))
            self.refresh_group_data()
            self.render_library_lists()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update pin: {e}")

    def remove_library_item(self, item_id):
        """Remove a library item (admin/creator only)."""
        if not self.current_group or not self.db_ref:
            return
        if not self.is_admin_or_creator():
            messagebox.showwarning("Permission denied", "Only admins or the creator can remove items.")
            return
        if not messagebox.askyesno("Remove", "Remove this library item?"):
            return
        try:
            self.db_ref.child(f'studyGroups/{self.current_group}/library/{item_id}').delete()
            self.refresh_group_data()
            self.render_library_lists()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove item: {e}")
        
    def set_background_image(self):
        """✅ Upload and set background image for group header"""
        if not self.storage_bucket:
            messagebox.showerror("Error", "Storage not available!")
            return

        filepath = filedialog.askopenfilename(
            title="Select Background Image (Wide format recommended)",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg"), ("All files", "*.*")]
        )
        if not filepath:
            return

        try:
            # Compress and resize image
            img = Image.open(filepath).convert("RGB")
            
            # Resize to wide format (1200x300 max)
            img.thumbnail((1200, 300), Image.Resampling.LANCZOS)
            
            # Save temporarily
            temp_path = os.path.join(os.path.dirname(filepath), "temp_bg_upload.jpg")
            img.save(temp_path, "JPEG", quality=85, optimize=True)

            # Upload to Firebase Storage
            blob_path = f'groups/{self.current_group}/background/{int(time.time())}.jpg'
            blob = self.storage_bucket.blob(blob_path)
            blob.upload_from_filename(temp_path)
            blob.make_public()
            
            # Cleanup
            try:
                os.remove(temp_path)
            except:
                pass

            bg_url = blob.public_url

            # Update Firebase metadata
            meta_ref = self.db_ref.child(f'studyGroups/{self.current_group}/metadata')
            meta_ref.update({'bg_image_url': bg_url})

            # Update local cache
            if self.current_group in self.groups:
                self.groups[self.current_group]['metadata']['bg_image_url'] = bg_url
            
            # Refresh UI
            self.show_group_content()
            self.update_groups_lists()

            messagebox.showinfo("Success", "Background image updated!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update background: {e}")
            print(f"Full error: {e}")
        

    def change_group_icon(self, callback=None):
        """✅ FIXED: Upload and display new group icon immediately"""
        if not self.storage_bucket:
            messagebox.showerror("Error", "Storage not available!")
            return

        filepath = filedialog.askopenfilename(
            title="Select Group Icon",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg"), ("All files", "*.*")]
        )
        if not filepath:
            return

        try:
            # Compress image
            img = Image.open(filepath).convert("RGB")
            img.thumbnail((256, 256), Image.Resampling.LANCZOS)
            
            # Save temporarily
            temp_path = os.path.join(os.path.dirname(filepath), "temp_icon_upload.jpg")
            img.save(temp_path, "JPEG", quality=85, optimize=True)

            # Upload to Firebase Storage
            blob_path = f'groups/{self.current_group}/icon/{int(time.time())}.jpg'
            blob = self.storage_bucket.blob(blob_path)
            blob.upload_from_filename(temp_path)
            blob.make_public()
            
            # Cleanup temp file
            try:
                os.remove(temp_path)
            except:
                pass

            icon_url = blob.public_url

            # Update Firebase metadata
            meta_ref = self.db_ref.child(f'studyGroups/{self.current_group}/metadata')
            meta_ref.update({'icon_url': icon_url})

            # ✅ FIX: Update local data immediately
            if self.current_group in self.groups:
                self.groups[self.current_group]['metadata']['icon_url'] = icon_url
            
            # ✅ FIX: Refresh UI immediately
            if callback:
                callback(icon_url)
            else:
                self.show_group_content()
            
            # ✅ FIX: Also refresh group list
            self.update_groups_lists()

            messagebox.showinfo("Success", "Group icon updated!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update icon: {e}")
            print(f"Full error: {e}")

    def share_invite_link(self):
        """Admin can share invite link/code"""
        if not self.current_group:
            return

        metadata = self.groups[self.current_group].get('metadata', {})
        invite_code = metadata.get('invite_code')

        if not invite_code:
            messagebox.showerror("Error", "Invite code not found!")
            return

        invite_link = f"Join using code: {invite_code}"

        self.parent.clipboard_clear()
        self.parent.clipboard_append(invite_code)
        self.parent.update()

        messagebox.showinfo("Invite Copied", f"Copied to clipboard:\n\n{invite_link}")
        
    def create_plans_section(self, parent):
        """Create plans section with highlighted header"""
        group_data = self.groups[self.current_group]
        plans = group_data.get('plans', {})

        # --- Header row: "📅 PLANS" label + "Add Plan" button side-by-side ---
        header_frame = tk.Frame(parent, bg='#E8F4FF', relief='flat', bd=0)
        header_frame.pack(fill=tk.X, pady=(5, 10), padx=5, ipady=6)

        plans_label = tk.Label(
            header_frame,
            text="📅 PLANS",
            font=('Segoe UI', 13, 'bold'),
            bg='#E8F4FF',
            fg=self.colors['dark']
        )
        plans_label.pack(side=tk.LEFT, anchor=tk.W, padx=(10, 0))

        # ✅ Only show "Add Plan" button for admins/creators
        if self.is_admin(self.current_group):
            add_btn = tk.Label(
                header_frame,
                text="➕ Add Plan",
                font=('Segoe UI', 9, 'bold'),
                bg=self.colors['primary'],
                fg='white',
                cursor='hand2',
                padx=12,
                pady=5
            )
            add_btn.pack(side=tk.RIGHT, anchor=tk.E, padx=(0, 10))
            add_btn.bind('<Button-1>', lambda e: self.upload_plan())

        # --- Plans list container ---
        plans_list = tk.Frame(parent, bg=self.colors['light'])
        plans_list.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        if plans:
            for plan_id, plan_data in plans.items():
                self.create_plan_item(plans_list, plan_id, plan_data)
        else:
            tk.Label(
                plans_list,
                text="No plans yet",
                font=('Segoe UI', 10),
                bg=self.colors['light'],
                fg=self.colors['gray']
            ).pack(pady=20)
        
    def create_plan_item(self, parent, plan_id, plan_data):
        """Create a plan item with selection for viewing enrolled members"""
        is_enrolled = self.user_id in plan_data.get('enrolled_members', [])
        is_selected = plan_id == self.selected_plan_for_members  # Changed from self.current_plan
        time_str = self.extract_plan_time(plan_data)

        bg = self.colors['hover'] if is_selected else 'white'
        # ✅ Add thin black outline for selected plan
        border_width = 2 if is_selected else 1
        border_color = '#000000' if is_selected else self.colors['bg']
        
        item = tk.Frame(parent, bg=bg, cursor='hand2', relief='flat',
                        highlightthickness=border_width, highlightbackground=border_color)
        item.pack(fill=tk.X, pady=4)

        # Main clickable area to select plan
        def select_plan(e=None):
            self.select_plan_for_members(plan_id)
            
        item.bind('<Button-1>', select_plan)

        main_content = tk.Frame(item, bg=bg)
        main_content.pack(fill=tk.X, padx=15, pady=10)
        main_content.bind('<Button-1>', select_plan)

        left = tk.Frame(main_content, bg=bg)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        left.bind('<Button-1>', select_plan)

        icon_label = tk.Label(left, text="📅", font=('Segoe UI', 18), bg=bg)
        icon_label.pack(side=tk.LEFT, padx=(0, 10))
        icon_label.bind('<Button-1>', select_plan)

        info = tk.Frame(left, bg=bg)
        info.pack(side=tk.LEFT, fill=tk.X, expand=True)
        info.bind('<Button-1>', select_plan)

        name_label = tk.Label(info, text=plan_data.get('name', 'Unnamed Plan'),
                 font=('Segoe UI', 11, 'bold'), bg=bg, anchor='w')
        name_label.pack(fill=tk.X)
        name_label.bind('<Button-1>', select_plan)

        enrolled_count = len(plan_data.get('enrolled_members', []))
        detail_text = f"{enrolled_count} enrolled"
        if time_str:
            detail_text += f" • {time_str}"

        detail_label = tk.Label(info, text=detail_text, font=('Segoe UI', 8),
                 bg=bg, fg=self.colors['gray'], anchor='w')
        detail_label.pack(fill=tk.X)
        detail_label.bind('<Button-1>', select_plan)

        # --- Enroll / Unenroll button (prevent event propagation) ---
        if is_enrolled:
            btn = tk.Label(main_content, text="Unenroll", font=('Segoe UI', 9),
                           bg=self.colors['accent'], fg='white',
                           cursor='hand2', padx=12, pady=5)
            btn.pack(side=tk.RIGHT)
            btn.bind('<Button-1>', lambda e: self.unenroll_from_plan(plan_id, plan_data))
        else:
            btn = tk.Label(main_content, text="Enroll", font=('Segoe UI', 9),
                           bg=self.colors['secondary'], fg='white',
                           cursor='hand2', padx=12, pady=5)
            btn.pack(side=tk.RIGHT)
            btn.bind('<Button-1>', lambda e: self.enroll_in_plan(plan_id, plan_data))

        # === Study Materials Header Row ===
        materials_toggle = tk.Frame(item, bg=bg)
        materials_toggle.pack(fill=tk.X, padx=15, pady=(0, 5))

        arrow_label = tk.Label(materials_toggle, text="▶", font=('Segoe UI', 10),
                               bg=bg, fg=self.colors['primary'])
        arrow_label.pack(side=tk.LEFT, padx=(0, 5))

        materials_label = tk.Label(materials_toggle, text="📚 Study Materials", 
                                   font=('Segoe UI', 9, 'bold'),
                                   bg=bg, fg=self.colors['dark'])
        materials_label.pack(side=tk.LEFT)

        # --- Remove Plan button for creator (properly right-aligned & visible) ---
        try:
            group_ref = self.db_ref.child(f"studyGroups/{self.current_group}/metadata")
            meta_data = group_ref.get() or {}
            creator_id = meta_data.get("created_by")

            if str(self.user_id).strip() == str(creator_id).strip():
                # ✅ use place() instead of pack() to anchor precisely on right side
                remove_btn = tk.Button(
                    materials_toggle,
                    text="Remove Plan",
                    bg="#FFEBEE",          # soft red background
                    fg="#C62828",          # deep red text
                    relief="flat",
                    bd=0,
                    font=('Segoe UI', 9, 'bold'),
                    activebackground="#E57373",
                    activeforeground="white",
                    cursor="hand2",
                    padx=10,
                    pady=4,
                    command=lambda pid=plan_id: self.remove_plan(pid)
                )

                # --- position precisely (relative to materials_toggle width)
                remove_btn.place(relx=1.05, rely=0.19, anchor="ne")  # 👈 shifts button to top-right corner
        except Exception as e:
            print("⚠ Could not check creator:", e)

        # --- Container for materials (expand/collapse) ---
        materials_container = tk.Frame(item, bg=self.colors['bg'])
        materials_shown = [False]

        def toggle_materials(e):
            if materials_shown[0]:
                materials_container.pack_forget()
                arrow_label.config(text="▶")
                materials_shown[0] = False
            else:
                materials_container.pack(fill=tk.X, padx=15, pady=(0, 10))
                arrow_label.config(text="▼")
                materials_shown[0] = True
                self.load_plan_materials(materials_container, plan_id, plan_data)

            self.center_container.after(150, self.refresh_scroll_region)
            self.center_container.after(400, self.refresh_scroll_region)

        materials_toggle.bind('<Button-1>', toggle_materials)
        arrow_label.bind('<Button-1>', toggle_materials)
        materials_label.bind('<Button-1>', toggle_materials)
        
        # Auto-expand newly created plans
        if hasattr(self, "expanded_plans") and plan_id in self.expanded_plans:
            materials_container.pack(fill=tk.X, padx=15, pady=(0, 10))
            arrow_label.config(text="▼")
            materials_shown[0] = True
            self.load_plan_materials(materials_container, plan_id, plan_data)
            self.center_container.after(150, self.refresh_scroll_region)
            self.center_container.after(400, self.refresh_scroll_region)
    
    def extract_plan_time(self, plan_data):
        """Extract start and end time"""
        try:
            plan_json = json.loads(plan_data.get('file_data', '{}'))
            sessions = plan_json.get('sessions', [])
            
            if not sessions:
                return None
            
            start_time = sessions[0][1]
            end_time = sessions[-1][2]
            
            def format_time(time_str):
                h, m = map(int, time_str.split(':'))
                period = 'AM' if h < 12 else 'PM'
                h = h if h <= 12 else h - 12
                h = 12 if h == 0 else h
                return f"{h}:{m:02d} {period}"
            
            return f"{format_time(start_time)} - {format_time(end_time)}"
        except:
            return None
    
    def load_plan_materials(self, container, plan_id, plan_data):
        """Load materials"""
        for widget in container.winfo_children():
            widget.destroy()
        
        inner = tk.Frame(container, bg=self.colors['bg'])
        inner.pack(fill=tk.X, padx=10, pady=5)
        
        if self.is_admin(self.current_group):
            btn_frame = tk.Frame(inner, bg=self.colors['bg'])
            btn_frame.pack(fill=tk.X, pady=(0, 5))
            
            for text, cmd in [("📄 PDF", 'pdf'), ("🔗 Link", 'link'), ("📎 File", 'file')]:
                btn = tk.Label(btn_frame, text=text, font=('Segoe UI', 8),
                             bg=self.colors['primary'], fg='white',
                             cursor='hand2', padx=8, pady=4)
                btn.pack(side=tk.LEFT, padx=2)
                btn.bind('<Button-1>', lambda e, t=cmd, pid=plan_id: self.add_material_to_plan(t, pid))
        
        try:
            materials = plan_data.get('materials', {})
            
            if materials:
                for mat_id, mat_data in materials.items():
                    self.create_material_item_compact(inner, mat_id, mat_data)
            else:
                tk.Label(inner, text="No materials yet", font=('Segoe UI', 8),
                        bg=self.colors['bg'], fg=self.colors['gray']).pack(pady=5)
        except:
            tk.Label(inner, text="No materials yet", font=('Segoe UI', 8),
                    bg=self.colors['bg'], fg=self.colors['gray']).pack(pady=5)
    
    def create_material_item_compact(self, parent, mat_id, mat_data):
        """Create compact material item"""
        item = tk.Frame(parent, bg='white', cursor='hand2', relief='flat')
        item.pack(fill=tk.X, pady=1)
        
        content = tk.Frame(item, bg='white')
        content.pack(fill=tk.X, padx=8, pady=5)
        
        icons = {'pdf': '📄', 'link': '🔗', 'file': '📎'}
        icon = icons.get(mat_data.get('type', 'file'), '📎')
        
        tk.Label(content, text=icon, font=('Segoe UI', 12), bg='white').pack(side=tk.LEFT, padx=(0, 8))
        
        tk.Label(content, text=mat_data.get('name', 'Unnamed'),
                font=('Segoe UI', 9), bg='white', anchor='w').pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ✅ Show "Remove" button only if creator (pack this FIRST)
        if self.is_creator(self.current_group):
            remove_btn = tk.Button(
                content,
                text="Remove",
                bg="#E74C3C", fg="white",
                relief="flat", bd=0,
                font=('Segoe UI', 8, 'bold'),
                padx=8, pady=3,
                activebackground="#C0392B", activeforeground="white",
                command=lambda pid=self.current_plan, mid=mat_id: self.remove_material(pid, mid)
            )
            remove_btn.pack(side=tk.RIGHT, padx=(0, 5))  # rightmost

        # Then pack OPEN (so it stays to the left of Remove)
        open_btn = tk.Label(content, text="Open", font=('Segoe UI', 8, 'bold'),
                            bg=self.colors['primary'], fg='white',
                            cursor='hand2', padx=8, pady=3)
        open_btn.pack(side=tk.RIGHT, padx=(0, 8))
        open_btn.bind('<Button-1>', lambda e: self.open_material(mat_data))


    
    def add_material_to_plan(self, material_type, plan_id):
        """Add material to plan"""
        self.current_plan = plan_id
        self.add_material(material_type)
        
    def create_materials_section(self, parent):
        pass
        
    def create_material_item(self, parent, mat_id, mat_data):
        """Create material item"""
        item = tk.Frame(parent, bg='white', cursor='hand2')
        item.pack(fill=tk.X, pady=2)
        
        content = tk.Frame(item, bg='white')
        content.pack(fill=tk.X, padx=15, pady=10)
        
        icons = {'pdf': '📄', 'link': '🔗', 'file': '📎'}
        icon = icons.get(mat_data.get('type', 'file'), '📎')
        
        tk.Label(content, text=icon, font=('Segoe UI', 16), bg='white').pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Label(content, text=mat_data.get('name', 'Unnamed'),
                font=('Segoe UI', 10), bg='white', anchor='w').pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # ✅ Show "Remove" button only if creator (pack this FIRST)
        if self.is_creator(self.current_group):
            remove_btn = tk.Button(
                content,
                text="Remove",
                bg="#E74C3C", fg="white",
                relief="flat", bd=0,
                font=('Segoe UI', 9, 'bold'),
                padx=10, pady=4,
                activebackground="#C0392B", activeforeground="white",
                command=lambda pid=self.current_plan, mid=mat_id: self.remove_material(pid, mid)
            )
            remove_btn.pack(side=tk.RIGHT, padx=(0, 5))  # rightmost

        # Then pack OPEN (so it stays to the left of Remove)
        open_btn = tk.Label(content, text="Open", font=('Segoe UI', 9, 'bold'),
                            bg=self.colors['primary'], fg='white',
                            cursor='hand2', padx=10, pady=4)
        open_btn.pack(side=tk.RIGHT, padx=(0, 8))
        open_btn.bind('<Button-1>', lambda e: self.open_material(mat_data))


        
    def create_admins_section(self, parent):
        """Create admins section with dynamic grid"""
        group_data = self.groups[self.current_group]
        members = group_data.get('members', {})
        admins = [(mid, mdata) for mid, mdata in members.items() if mdata.get('role') == 'admin']
        
        tk.Label(parent, text="👑 ADMINS", font=('Segoe UI', 14, 'bold'),
                bg=self.colors['light'], fg=self.colors['dark']).pack(anchor=tk.W, pady=(0, 10))
        
        # ✅ Dynamic grid container
        grid_container = tk.Frame(parent, bg=self.colors['light'])
        grid_container.pack(fill=tk.X, pady=(0, 20))
        
        if admins:
            for idx, (member_id, member_data) in enumerate(admins):
                self.create_member_widget_dynamic(grid_container, member_id, member_data, idx)

    def create_enrolled_members_section(self, parent):
        """Create enrolled members section - shows selected plan's members or all if none selected"""
        group_data = self.groups[self.current_group]
        
        # If a specific plan is selected, show only its members
        if self.selected_plan_for_members:
            plans = group_data.get('plans', {})
            selected_plan = plans.get(self.selected_plan_for_members)
            
            if not selected_plan:
                return
            
            plan_name = selected_plan.get('name', 'Unknown Plan')
            enrolled_ids = selected_plan.get('enrolled_members', [])
            
            if not enrolled_ids:
                return
            
            # Header with plan name
            header_frame = tk.Frame(parent, bg=self.colors['light'])
            header_frame.pack(fill=tk.X, pady=(20, 10))
            
            tk.Label(header_frame, 
                    text=f"👥 ENROLLED IN: {plan_name}", 
                    font=('Segoe UI', 14, 'bold'),
                    bg=self.colors['light'], 
                    fg=self.colors['primary']).pack(side=tk.LEFT)
            
            # Clear selection button
            clear_btn = tk.Label(header_frame, 
                                text="✕ Show All", 
                                font=('Segoe UI', 9),
                                bg=self.colors['gray'], 
                                fg='white',
                                cursor='hand2', 
                                padx=10, 
                                pady=5)
            clear_btn.pack(side=tk.RIGHT)
            clear_btn.bind('<Button-1>', lambda e: self.clear_plan_selection())
            
            # Grid container
            grid_container = tk.Frame(parent, bg=self.colors['light'])
            grid_container.pack(fill=tk.X, pady=(0, 20))
            
            members = group_data.get('members', {})
            
            # ✅ Sort enrolled members by study hours (highest first)
            member_list = []
            for member_id in enrolled_ids:
                if member_id in members:
                    member_data = members[member_id]
                    study_hours = self.get_member_study_hours(member_id)
                    member_list.append((member_id, member_data, study_hours))
            
            # Sort by study hours descending
            member_list.sort(key=lambda x: x[2], reverse=True)
            
            # Display members with ranking
            for idx, (member_id, member_data, study_hours) in enumerate(member_list):
                rank = idx + 1  # 1-indexed rank
                self.create_member_widget_dynamic(grid_container, member_id, member_data, idx, rank, study_hours)
        
        else:
            # Original behavior: show all enrolled members from all plans
            all_enrolled = set()
            plans = group_data.get('plans', {})
            for plan_id, plan_data in plans.items():
                enrolled_ids = plan_data.get('enrolled_members', [])
                all_enrolled.update(enrolled_ids)
            
            if not all_enrolled:
                return
            
            tk.Label(parent, text="👥 ENROLLED MEMBERS", font=('Segoe UI', 14, 'bold'),
                    bg=self.colors['light'], fg=self.colors['dark']).pack(anchor=tk.W, pady=(20, 10))
            
            grid_container = tk.Frame(parent, bg=self.colors['light'])
            grid_container.pack(fill=tk.X, pady=(0, 20))
            
            members = group_data.get('members', {})
            
            # ✅ Sort all enrolled members by study hours
            member_list = []
            for member_id in all_enrolled:
                if member_id in members and members[member_id].get('role') != 'admin':
                    member_data = members[member_id]
                    study_hours = self.get_member_study_hours(member_id)
                    member_list.append((member_id, member_data, study_hours))
            
            # Sort by study hours descending
            member_list.sort(key=lambda x: x[2], reverse=True)
            
            # Display members with ranking
            for idx, (member_id, member_data, study_hours) in enumerate(member_list):
                rank = idx + 1
                self.create_member_widget_dynamic(grid_container, member_id, member_data, idx, rank, study_hours)

    def create_all_members_section(self, parent):
        """Create all members section with dynamic grid sorted by study hours"""
        group_data = self.groups[self.current_group]
        members = group_data.get('members', {})
        
        # ✅ Get regular members and their study hours
        member_list = []
        for mid, mdata in members.items():
            if mdata.get('role') != 'admin':
                study_hours = self.get_member_study_hours(mid)
                member_list.append((mid, mdata, study_hours))
        
        # Sort by study hours descending (highest first)
        member_list.sort(key=lambda x: x[2], reverse=True)
        
        tk.Label(parent, text="👥 ALL GROUP MEMBERS", font=('Segoe UI', 14, 'bold'),
                bg=self.colors['light'], fg=self.colors['dark']).pack(anchor=tk.W, pady=(0, 10))
        
        # ✅ Dynamic grid container
        grid_container = tk.Frame(parent, bg=self.colors['light'])
        grid_container.pack(fill=tk.X)
        
        if member_list:
            for idx, (member_id, member_data, study_hours) in enumerate(member_list):
                rank = idx + 1  # 1-indexed rank
                self.create_member_widget_dynamic(grid_container, member_id, member_data, idx, rank, study_hours)

    def create_member_widget_dynamic(self, parent, member_id, member_data, index, rank=None, study_hours=None):
        """✅ Create member widget that flows dynamically with ranking and highlighting for top 3"""
        name = member_data.get('name', 'Unknown')
        
        # ✅ Load avatar from LOCAL path using avatar_name
        avatar_name = member_data.get('avatar_name', 'avatar 1.png')
        
        # Handle old HTTP URLs
        if avatar_name and avatar_name.startswith('http'):
            avatar_id = member_data.get('avatar_id', 1)
            avatar_name = f"avatar {avatar_id}.png"
        
        # Build local path
        from config_paths import app_paths
        if not avatar_name.endswith('.png'):
            avatar_path = os.path.join(app_paths.avatars_dir, f"{avatar_name}.png")
        else:
            avatar_path = os.path.join(app_paths.avatars_dir, avatar_name)
        
        size = 50
        
        # ✅ Determine if this is a top 3 member
        is_top_3 = rank is not None and rank <= 3
        
        # ✅ Color scheme for top 3
        if is_top_3:
            if rank == 1:
                bg_color = '#FFD700'  # Gold
                border_color = '#FFA500'
                rank_emoji = '🥇'
            elif rank == 2:
                bg_color = '#C0C0C0'  # Silver
                border_color = '#A9A9A9'
                rank_emoji = '🥈'
            else:  # rank == 3
                bg_color = '#CD7F32'  # Bronze
                border_color = '#8B4513'
                rank_emoji = '🥉'
        else:
            bg_color = self.colors['light']
            border_color = None
            rank_emoji = None

        frame = tk.Frame(parent, bg=bg_color, cursor='hand2', relief='raised' if is_top_3 else 'flat', bd=2 if is_top_3 else 0)
        frame.pack(side=tk.LEFT, padx=8, pady=8)

        try:
            # ✅ Load from local path only
            if os.path.exists(avatar_path):
                avatar_img = Image.open(avatar_path).convert("RGBA")
            else:
                raise ValueError("no avatar")
            
            avatar_img = avatar_img.resize((size, size), Image.Resampling.LANCZOS)
            background = Image.new("RGBA", (size, size), (255, 255, 255, 255))
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
            final_img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
            final_img.paste(avatar_img, (0, 0), mask)
            
        except Exception:
            final_img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
            draw = ImageDraw.Draw(final_img)
            draw.ellipse((0, 0, size, size), fill="#BDC3C7")

            initials = ''.join([part[0].upper() for part in name.split()[:2]]) or '?'
            try:
                font = ImageFont.truetype("arial.ttf", 18)
            except:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), initials, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            position = ((size - text_width) // 2, (size - text_height) // 2)
            draw.text(position, initials, fill='white', font=font)

        avatar_canvas = tk.Canvas(frame, width=size+4, height=size+4, 
                                  bg=bg_color, highlightthickness=0, bd=0)
        avatar_canvas.pack()

        # ✅ Top 3 members get special border
        if is_top_3:
            avatar_canvas.create_oval(0, 0, size+4, size+4, outline=border_color, width=3)
        else:
            avatar_canvas.create_oval(1, 1, size+3, size+3, outline='#E0E0E0', width=1)

        photo = ImageTk.PhotoImage(final_img)
        avatar_canvas.create_image((size+4)//2, (size+4)//2, image=photo)
        avatar_canvas.image = photo

        # Online indicator
        is_online = member_data.get('online', False)
        status_color = self.colors['online'] if is_online else self.colors['offline']
        indicator_size = 10
        x_pos = size - 10
        y_pos = size - 10

        avatar_canvas.create_oval(x_pos-1, y_pos-1, x_pos+indicator_size+1, y_pos+indicator_size+1,
                                 fill='white', outline='')
        avatar_canvas.create_oval(x_pos, y_pos, x_pos+indicator_size, y_pos+indicator_size,
                                 fill=status_color, outline='white', width=2)

        # ✅ Member name with study hours
        if study_hours is not None and study_hours > 0:
            name_text = f"{name[:8]} {study_hours:.1f}h"
        else:
            name_text = name[:12]
        
        # ✅ Add rank emoji for top 3
        if is_top_3 and rank_emoji:
            name_text = f"{rank_emoji} {name_text}"
        
        name_label = tk.Label(frame, text=name_text, font=('Segoe UI', 9, 'bold' if is_top_3 else 'normal'),
                             bg=bg_color, fg='#1a1a1a')
        name_label.pack()

        # ========================================================================
        # ✅ FIX: BIND BOTH LEFT-CLICK AND RIGHT-CLICK FOR ALL USERS
        # ========================================================================
        
        # Left-click (Button-1) shows menu for everyone
        frame.bind('<Button-1>', lambda e: self.show_member_menu(e, member_id, member_data))
        avatar_canvas.bind('<Button-1>', lambda e: self.show_member_menu(e, member_id, member_data))
        name_label.bind('<Button-1>', lambda e: self.show_member_menu(e, member_id, member_data))
        
        # Right-click (Button-3) also works
        frame.bind('<Button-3>', lambda e: self.show_member_menu(e, member_id, member_data))
        avatar_canvas.bind('<Button-3>', lambda e: self.show_member_menu(e, member_id, member_data))
        name_label.bind('<Button-3>', lambda e: self.show_member_menu(e, member_id, member_data))
        
        # ✅ Add hover effect to show it's clickable
        def on_enter(e):
            if not is_top_3:
                frame.configure(bg='#E8F4F8')
                name_label.configure(bg='#E8F4F8')
                avatar_canvas.configure(bg='#E8F4F8')
        
        def on_leave(e):
            frame.configure(bg=bg_color)
            name_label.configure(bg=bg_color)
            avatar_canvas.configure(bg=bg_color)
        
        frame.bind('<Enter>', on_enter)
        frame.bind('<Leave>', on_leave)
    
    def show_member_menu(self, event, member_id, member_data):
        """Show member context menu - different options for admins vs members"""
        menu = tk.Menu(self.parent, tearoff=0)
        
        member_name = member_data.get('name', 'Unknown')
        member_role = member_data.get('role', 'member')
        is_admin = self.is_admin(self.current_group)
        is_self = (member_id == self.user_id)
        
        # ========================================================================
        # HEADER - Show member name
        # ========================================================================
        menu.add_command(
            label=f"👤 {member_name}",
            state='disabled',
            font=('Segoe UI', 10, 'bold')
        )
        menu.add_separator()
        
        # ========================================================================
        # FOR ADMINS ONLY - Show admin actions
        # ========================================================================
        if is_admin and not is_self:
            # Toggle admin role
            if member_role == 'admin':
                menu.add_command(
                    label="⬇️ Remove Admin Role",
                    command=lambda: self.toggle_admin_role(member_id, False)
                )
            else:
                menu.add_command(
                    label="⬆️ Make Admin",
                    command=lambda: self.toggle_admin_role(member_id, True)
                )
            
            menu.add_separator()
            
            # Remove from group
            menu.add_command(
                label="🚫 Remove from Group",
                command=lambda: self.remove_member(member_id)
            )
            
            menu.add_separator()
        
        # ========================================================================
        # FOR YOURSELF - Show leave option
        # ========================================================================
        if is_self:
            menu.add_command(
                label="🚪 Leave Group",
                command=self.exit_group
            )
            menu.add_separator()
        
        # ========================================================================
        # FOR EVERYONE - Show view profile
        # ========================================================================
        menu.add_command(
            label="ℹ️ View Profile",
            command=lambda: self.view_member_profile(member_id, member_data)
        )
        
        # Show the menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
            
    def view_member_profile(self, member_id, member_data):
        """Show member profile dialog"""
        member_name = member_data.get('name', 'Unknown')
        
        # Create dialog
        dialog = tk.Toplevel(self.parent)
        dialog.title(f"Profile: {member_name}")
        dialog.geometry("400x350")
        dialog.configure(bg=self.colors['primary'])
        dialog.transient(self.parent)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (200)
        y = (dialog.winfo_screenheight() // 2) - (175)
        dialog.geometry(f"400x350+{x}+{y}")
        
        # Header with avatar
        header = tk.Frame(dialog, bg=self.colors['secondary'], height=100)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        # Avatar
        avatar_name = member_data.get('avatar_name', 'avatar 1.png')
        from config_paths import app_paths
        avatar_path = os.path.join(app_paths.avatars_dir, avatar_name)
        
        if os.path.exists(avatar_path):
            try:
                img = Image.open(avatar_path)
                img = img.resize((70, 70), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                avatar_label = tk.Label(header, image=photo, bg=self.colors['secondary'])
                avatar_label.image = photo
                avatar_label.pack(pady=15)
            except:
                pass
        
        # Name
        tk.Label(
            dialog,
            text=member_name,
            font=('Segoe UI', 18, 'bold'),
            bg=self.colors['primary'],
            fg='white'
        ).pack(pady=15)
        
        # Role
        role = member_data.get('role', 'member')
        role_emoji = '👑' if role == 'admin' else '👤'
        tk.Label(
            dialog,
            text=f"{role_emoji} {role.capitalize()}",
            font=('Segoe UI', 12),
            bg=self.colors['primary'],
            fg='white'
        ).pack()
        
        # Details frame
        details = tk.Frame(dialog, bg='white')
        details.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Online status
        is_online = member_data.get('online', False)
        status_text = "🟢 Online" if is_online else "⚫ Offline"
        tk.Label(
            details,
            text=f"Status: {status_text}",
            font=('Segoe UI', 10),
            bg='white'
        ).pack(anchor='w', pady=5)
        
        # Joined date
        joined = member_data.get('joined_at', 'Unknown')
        if joined != 'Unknown':
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(joined)
                joined = dt.strftime('%B %d, %Y')
            except:
                pass
        
        tk.Label(
            details,
            text=f"Joined: {joined}",
            font=('Segoe UI', 10),
            bg='white'
        ).pack(anchor='w', pady=5)
        
        # Study hours if available
        study_hours = self.get_member_study_hours(member_id)
        if study_hours > 0:
            tk.Label(
                details,
                text=f"Study Hours: {study_hours:.1f}h",
                font=('Segoe UI', 10),
                bg='white'
            ).pack(anchor='w', pady=5)
        
        # Close button
        tk.Button(
            dialog,
            text="Close",
            command=dialog.destroy,
            bg=self.colors['secondary'],
            fg='white',
            relief='flat',
            padx=20,
            pady=8
        ).pack(pady=15)
    
    def toggle_admin_role(self, member_id, make_admin):
        """Toggle admin role with immediate UI update"""
        if not self.db_ref:
            return
        
        try:
            role = 'admin' if make_admin else 'member'
            
            # Update Firebase
            member_ref = self.db_ref.child(f'studyGroups/{self.current_group}/members/{member_id}')
            member_ref.update({'role': role})
            
            # ✅ FIX 1: Update local cache immediately
            if self.current_group in self.groups:
                if 'members' in self.groups[self.current_group]:
                    if member_id in self.groups[self.current_group]['members']:
                        self.groups[self.current_group]['members'][member_id]['role'] = role
            
            action = "promoted to admin" if make_admin else "removed from admin"
            messagebox.showinfo("Success", f"Member {action}!")
            
            # ✅ FIX 2: Refresh the entire UI
            self.show_group_content()
            
            # ✅ FIX 3: Force scroll region update
            self.parent.after(100, self.refresh_scroll_region)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed: {e}")
            import traceback
            traceback.print_exc()

    def remove_member(self, member_id):
        """Remove member from group with immediate UI update"""
        if not messagebox.askyesno("Confirm", "Remove this member from the group?"):
            return
        
        if not self.db_ref:
            return
        
        try:
            # Remove from Firebase
            self.db_ref.child(f'studyGroups/{self.current_group}/members/{member_id}').delete()
            
            # ✅ FIX 1: Update local cache immediately
            if self.current_group in self.groups:
                if 'members' in self.groups[self.current_group]:
                    self.groups[self.current_group]['members'].pop(member_id, None)
            
            messagebox.showinfo("Success", "Member removed from group!")
            
            # ✅ FIX 2: Refresh the entire UI
            self.show_group_content()
            
            # ✅ FIX 3: Force scroll region update
            self.parent.after(100, self.refresh_scroll_region)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove member: {e}")
            import traceback
            traceback.print_exc()
    
    def enroll_in_plan(self, plan_id, plan_data):
        """Enroll in plan"""
        if not self.db_ref:
            return
        
        try:
            enrolled_ref = self.db_ref.child(
                f'studyGroups/{self.current_group}/plans/{plan_id}/enrolled_members'
            )
            current_enrolled = enrolled_ref.get() or []
            
            if self.user_id not in current_enrolled:
                current_enrolled.append(self.user_id)
                enrolled_ref.set(current_enrolled)
                
                try:
                    plan_json = json.loads(plan_data['file_data'])
                    if self.import_plan_callback:
                        self.import_plan_callback(plan_json)
                except Exception as e:
                    print(f"Import error: {e}")
                
                plan_name = plan_data.get('name', 'Plan')
                
                # ✅ SEND ENROLLMENT MESSAGE TO CHAT
                try:
                    plan_json = json.loads(plan_data.get('file_data', '{}'))
                    sessions = plan_json.get('sessions', [])
                    session_count = len(sessions)
                    
                    # Get session times
                    session_times = []
                    for session in sessions[:3]:
                        if isinstance(session, list) and len(session) >= 2:
                            session_times.append(f"{session[0]} at {session[1]}")
                    
                    times_text = "\n".join(session_times)
                    if len(sessions) > 3:
                        times_text += f"\n... and {len(sessions) - 3} more session(s)"
                    
                    enrollment_msg = (
                        f"📋 {self.get_user_name()} enrolled in plan: {plan_name}\n\n"
                        f"📅 {session_count} session(s) scheduled:\n{times_text}\n\n"
                        "🔔 Every session start will be notified.\n"
                    )
                    
                    # Get avatar name
                    avatar_id = self.profile_data.get("avatar_id", 1)
                    avatar_name = f"avatar {avatar_id}.png"
                    
                    # Send to chat
                    msg_ref = self.db_ref.child(f'studyGroups/{self.current_group}/messages').push()
                    msg_data = {
                        "message": enrollment_msg,
                        "sender_id": "system",
                        "sender_name": "System",
                        "sender_avatar": avatar_name,
                        "timestamp": datetime.now().isoformat(),
                        "type": "plan_enrollment"
                    }
                    msg_ref.set(msg_data)
                    print(f"✅ Plan enrollment message sent to chat")
                    
                except Exception as e:
                    print(f"⚠ Failed to send enrollment message: {e}")
                
                messagebox.showinfo("Success", 
                    f"Successfully enrolled in {plan_name}! Check your Plan tab.")
                
                self.refresh_group_data()
        except Exception as e:
            messagebox.showerror("Error", f"Failed: {e}")
    
    def unenroll_from_plan(self, plan_id, plan_data):
        """Unenroll from plan"""
        if not messagebox.askyesno("Confirm", "Unenroll from this plan?"):
            return
        
        if not self.db_ref:
            return
        
        try:
            enrolled_ref = self.db_ref.child(
                f'studyGroups/{self.current_group}/plans/{plan_id}/enrolled_members'
            )
            current_enrolled = enrolled_ref.get() or []
            
            if self.user_id in current_enrolled:
                current_enrolled.remove(self.user_id)
                enrolled_ref.set(current_enrolled)
                
                messagebox.showinfo("Success", "Unenrolled successfully!")
                self.refresh_group_data()
        except Exception as e:
            messagebox.showerror("Error", f"Failed: {e}")
    
    def upload_plan(self):
        """Upload plan"""
        filepath = filedialog.askopenfilename(
            title="Select Plan File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                plan_data = json.load(f)
            
            if 'plan_name' not in plan_data or 'sessions' not in plan_data:
                messagebox.showerror("Invalid Plan", "Not a valid plan file!")
                return
            
            plan_id = self.db_ref.child(f'studyGroups/{self.current_group}/plans').push().key
            plan_entry = {
                'name': plan_data['plan_name'],
                'uploaded_by': self.user_id,
                'uploaded_at': datetime.now().isoformat(),
                'file_data': json.dumps(plan_data),
                'enrolled_members': [],
                'materials': {}
            }
            
            self.db_ref.child(f'studyGroups/{self.current_group}/plans/{plan_id}').set(plan_entry)
            # ✅ Auto-expand the new plan so creator sees Study Materials section immediately
            if not hasattr(self, "expanded_plans"):
                self.expanded_plans = set()
            self.expanded_plans.add(plan_id)
            self.current_plan = plan_id
            print(f"✅ Auto-expanded new plan {plan_id} for adding materials")
            
            messagebox.showinfo("Success", f"Plan '{plan_data['plan_name']}' uploaded!")
            self.refresh_group_data()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed: {e}")
    
    def add_material(self, material_type):
        """Add material"""
        if not self.current_plan:
            messagebox.showwarning("No Plan", "Select a plan first!")
            return
        
        if material_type == 'link':
            self.add_material_link()
        else:
            self.add_material_file(material_type)
    
    def add_material_link(self):
        """Add link"""
        dialog = tk.Toplevel(self.parent)
        dialog.title("Add Link")
        dialog.geometry("400x200")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        tk.Label(dialog, text="Link Title:", font=('Segoe UI', 10)).pack(pady=(20, 5))
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(pady=5)
        
        tk.Label(dialog, text="URL:", font=('Segoe UI', 10)).pack(pady=5)
        url_entry = ttk.Entry(dialog, width=40)
        url_entry.pack(pady=5)
        
        def save_link():
            name = name_entry.get().strip()
            url = url_entry.get().strip()
            
            if not name or not url:
                messagebox.showerror("Error", "Provide both!")
                return
            
            try:
                material_data = {
                    'name': name,
                    'type': 'link',
                    'url': url,
                    'uploaded_by': self.user_id,
                    'uploaded_at': datetime.now().isoformat()
                }
                
                mat_ref = self.db_ref.child(
                    f'studyGroups/{self.current_group}/plans/{self.current_plan}/materials'
                )
                mat_ref.push(material_data)
                
                dialog.destroy()
                messagebox.showinfo("Success", "Link added!")
                self.refresh_group_data()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed: {e}")
        
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="Save", bg=self.colors['primary'], fg='white',
                 relief='flat', padx=20, command=save_link).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", bg=self.colors['gray'], fg='white',
                 relief='flat', padx=20, command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def add_material_file(self, file_type):
        """Upload file"""
        if not self.storage_bucket:
            messagebox.showerror("Error", "Storage not available!")
            return
        
        filetypes = [("All files", "*.*")]
        if file_type == 'pdf':
            filetypes = [("PDF files", "*.pdf"), ("All files", "*.*")]
        
        filepath = filedialog.askopenfilename(title="Select File", filetypes=filetypes)
        
        if not filepath:
            return
        
        try:
            filename = os.path.basename(filepath)
            
            blob_path = f'groups/{self.current_group}/plans/{self.current_plan}/{filename}'
            blob = self.storage_bucket.blob(blob_path)
            blob.upload_from_filename(filepath)
            blob.make_public()
            
            material_data = {
                'name': filename,
                'type': file_type,
                'url': blob.public_url,
                'uploaded_by': self.user_id,
                'uploaded_at': datetime.now().isoformat()
            }
            
            mat_ref = self.db_ref.child(
                f'studyGroups/{self.current_group}/plans/{self.current_plan}/materials'
            )
            mat_ref.push(material_data)
            
            messagebox.showinfo("Success", f"File Added!")
            self.refresh_group_data()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed: {e}")
    
    def open_material(self, mat_data, library_item_id=None):
        """Open material and optionally track library views."""
        webbrowser.open(mat_data['url'])

        if library_item_id and self.current_group and self.db_ref:
            try:
                views_ref = self.db_ref.child(
                    f'studyGroups/{self.current_group}/library/{library_item_id}/views'
                )

                def _increment(current):
                    try:
                        return int(current or 0) + 1
                    except Exception:
                        return 1

                views_ref.transaction(_increment)

                if hasattr(self, 'library_window') and self.library_window.winfo_exists():
                    self.render_library_lists()
            except Exception as e:
                print(f"⚠️ Failed to update view count: {e}")

    def download_material(self, mat_data):
        """Allow members to download a library item to their device."""
        url = mat_data.get('url')
        if not url:
            messagebox.showerror("Error", "Download link not available.")
            return

        default_name = mat_data.get('name', 'download')
        save_path = filedialog.asksaveasfilename(title="Save File As", initialfile=default_name)
        if not save_path:
            return

        progress_dialog = self._show_progress_dialog(self.parent, f"Downloading {default_name}...")

        def perform_download():
            error = None
            try:
                with requests.get(url, stream=True, timeout=20) as response:
                    response.raise_for_status()
                    with open(save_path, 'wb') as outfile:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                outfile.write(chunk)
            except Exception as e:
                error = e

            def finalize():
                if progress_dialog and progress_dialog.winfo_exists():
                    progress_dialog.destroy()
                if error:
                    messagebox.showerror("Error", f"Download failed: {error}")
                else:
                    messagebox.showinfo("Downloaded", f"File saved to:\n{save_path}")

            self.parent.after(0, finalize)

        threading.Thread(target=perform_download, daemon=True).start()
    
    def edit_group_info(self):
        """Modern edit group dialog matching create dialog design"""
        dialog = tk.Toplevel(self.parent)
        dialog.title("✏️ Edit Group")
        dialog.geometry("550x800")
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.configure(bg='#F5F7FA')
        
        metadata = self.groups[self.current_group].get('metadata', {})
        
        # Main container with scrollbar
        main_canvas = tk.Canvas(dialog, bg='#F5F7FA', highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=main_canvas.yview)
        scrollable_frame = tk.Frame(main_canvas, bg='#F5F7FA')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        # ===== HEADER =====
        header = tk.Frame(scrollable_frame, bg='#E67E22', height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(header, text="✏️ Edit Your Study Group", 
                font=('Segoe UI', 16, 'bold'),
                bg='#E67E22', fg='white').pack(pady=20)
        
        # ===== CONTENT AREA =====
        content = tk.Frame(scrollable_frame, bg='#F5F7FA')
        content.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)
        
        # Group Name
        name_frame = tk.Frame(content, bg='#F5F7FA')
        name_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(name_frame, text="📝 Group Name *", font=('Segoe UI', 11, 'bold'),
                bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(0, 5))
        name_entry = ttk.Entry(name_frame, width=50, font=('Segoe UI', 10))
        name_entry.insert(0, metadata.get('name', ''))
        name_entry.pack(fill=tk.X)
        
        # Description
        desc_frame = tk.Frame(content, bg='#F5F7FA')
        desc_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(desc_frame, text="📄 Description", font=('Segoe UI', 11, 'bold'),
                bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(0, 5))
        desc_text = tk.Text(desc_frame, width=50, height=4, font=('Segoe UI', 10),
                           relief='solid', borderwidth=1)
        desc_text.insert('1.0', metadata.get('description', ''))
        desc_text.pack(fill=tk.X)
        
        # Header Background Color
        tk.Label(content, text="🎨 Header Background Color",
                 font=('Segoe UI', 11, 'bold'),
                 bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(15, 5))

        # Unified area so preview and palette align nicely
        color_area = tk.Frame(content, bg='#F5F7FA')
        color_area.pack(fill=tk.X, pady=(0, 10))

        current_bg_color = metadata.get('header_bg_color', self.colors['light'])
        selected_color = tk.StringVar(value=current_bg_color)

        # Make 4 equal-width columns
        for col in range(4):
            color_area.grid_columnconfigure(col, weight=1, uniform="colors")

        # Preview row (row 0)
        tk.Label(
            color_area,
            text="Preview:",
            font=('Segoe UI', 9),
            bg='#F5F7FA',
            fg='#2C3E50'
        ).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 8))

        color_preview = tk.Canvas(
            color_area,
            height=40,
            bg=current_bg_color,
            highlightthickness=2,
            highlightbackground='#CCCCCC'
        )
        # Span remaining columns so its width matches the palette area
        color_preview.grid(row=0, column=1, columnspan=3, sticky="nsew", pady=(0, 8))

        # Color palette buttons
        preset_colors = [
            ('#FFFFFF', 'White'),
            ('#F8F9FA', 'Light Gray'),
            ('#E3F2FD', 'Sky Blue'),
            ('#E8F5E9', 'Mint'),
            ('#FFF3E0', 'Peach'),
            ('#F3E5F5', 'Lavender'),
            ('#FFE0B2', 'Orange'),
            ('#FFEBEE', 'Pink'),
            ('#E0F7FA', 'Cyan'),
            ('#FFF9C4', 'Yellow'),
            ('#D7CCC8', 'Beige'),
            ('#CFD8DC', 'Blue Gray'),
            ('#C8E6C9', 'Green'),
            ('#FFCCBC', 'Coral'),
            ('#B3E5FC', 'Light Blue'),
            ('#F0F4C3', 'Lime')
        ]

        def set_color(color):
            selected_color.set(color)
            color_preview.config(bg=color)

        max_cols = 4
        for i, (color, name) in enumerate(preset_colors):
            row = 1 + i // max_cols   # start from row 1 (row 0 is preview)
            col = i % max_cols

            # This frame is the button and stretches to fill its grid cell
            color_btn = tk.Frame(
                color_area,
                bg=color,
                relief='raised',
                borderwidth=2,
                cursor='hand2'
            )
            color_btn.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            label = tk.Label(
                color_btn,
                text=name,
                font=('Segoe UI', 8),
                bg=color,
                cursor='hand2'
            )
            label.pack(expand=True, fill="both", padx=2, pady=2)

            # Click handling
            color_btn.bind('<Button-1>', lambda e, c=color: set_color(c))
            label.bind('<Button-1>', lambda e, c=color: set_color(c))

        # Security Settings
        tk.Label(content, text="🔒 Security Settings",
                font=('Segoe UI', 11, 'bold'),
                bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(15, 5))

        security_frame = tk.Frame(content, bg='white', relief='solid', borderwidth=1)
        security_frame.pack(fill=tk.X, pady=(0, 15))

        password_enabled = metadata.get('password') is not None
        password_var = tk.BooleanVar(value=password_enabled)

        def toggle_password_fields():
            state = 'normal' if password_var.get() else 'disabled'
            password_entry.config(state=state)

        password_check = tk.Checkbutton(security_frame, text="🔐 Password Protected Group",
                                       variable=password_var,
                                       font=('Segoe UI', 10),
                                       bg='white', activebackground='white',
                                       command=toggle_password_fields)
        password_check.pack(anchor='w', padx=10, pady=10)

        password_entry_frame = tk.Frame(security_frame, bg='white')
        password_entry_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        tk.Label(password_entry_frame, text="Password:", font=('Segoe UI', 9),
                bg='white').pack(anchor='w')
        password_entry = ttk.Entry(password_entry_frame, width=40, show="●", font=('Segoe UI', 10))
        password_entry.pack(fill=tk.X, pady=(2, 0))
        toggle_password_fields()
        
        # Remove background button
        remove_bg_btn = tk.Button(content, text="🔄 Reset to Default Color", 
                                 bg='#7F8C8D', fg='white',
                                 font=('Segoe UI', 9),
                                 relief='flat', padx=15, pady=5,
                                 cursor='hand2',
                                 command=lambda: set_color(self.colors['light']))
        remove_bg_btn.pack(pady=(0, 15))
        
        # Group Icon
        tk.Label(content, text="🖼️ Group Icon", 
                font=('Segoe UI', 11, 'bold'),
                bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(15, 5))
        
        def upload_new_icon():
            self.change_group_icon()
            dialog.destroy()
        
        tk.Button(content, text="📁 Change Group Icon", 
                 bg='#3498DB', fg='white',
                 font=('Segoe UI', 10),
                 relief='flat', padx=20, pady=8,
                 cursor='hand2',
                 command=upload_new_icon).pack(anchor='w', pady=(0, 15))
        
        def save_changes():
            name = name_entry.get().strip()
            desc = desc_text.get('1.0', tk.END).strip()

            if not name:
                messagebox.showerror("❌ Error", "Group name is required!")
                return

            current_password_hash = metadata.get('password')
            if password_var.get():
                if password_entry.get():
                    new_password_hash = hashlib.sha256(password_entry.get().encode()).hexdigest()
                else:
                    new_password_hash = current_password_hash
            else:
                new_password_hash = None

            try:
                updates = {
                    'name': name,
                    'description': desc,
                    'header_bg_color': selected_color.get(),
                    'password': new_password_hash
                }
                meta_ref = self.db_ref.child(f'studyGroups/{self.current_group}/metadata')
                meta_ref.update(updates)
                
                dialog.destroy()
                messagebox.showinfo("✅ Success", "Group updated successfully!")
                self.refresh_group_data()
                
            except Exception as e:
                messagebox.showerror("❌ Error", f"Failed to update: {e}")
        
        # Action Buttons
        btn_frame = tk.Frame(content, bg='#F5F7FA')
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="💾 Save Changes", bg='#27AE60', fg='white',
                 font=('Segoe UI', 11, 'bold'),
                 relief='flat', padx=30, pady=10,
                 cursor='hand2',
                 command=save_changes).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="❌ Cancel", bg='#95A5A6', fg='white',
                 font=('Segoe UI', 11),
                 relief='flat', padx=30, pady=10,
                 cursor='hand2',
                 command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # Danger Zone
        danger_frame = tk.Frame(content, bg='#FFEBEE', relief='solid', borderwidth=2)
        danger_frame.pack(fill=tk.X, pady=(30, 0))
        
        tk.Label(danger_frame, text="⚠️ DANGER ZONE", 
                font=('Segoe UI', 11, 'bold'),
                bg='#FFEBEE', fg='#C0392B').pack(pady=(15, 5))
        
        tk.Label(danger_frame, text="Deleting this group is permanent and cannot be undone!", 
                font=('Segoe UI', 9),
                bg='#FFEBEE', fg='#555').pack(pady=(0, 10))
        
        def delete_group():
            if not messagebox.askyesno("⚠️ Confirm Delete", 
                "Are you absolutely sure you want to delete this group?\n\n" +
                "⚠️ This action is PERMANENT and will:\n" +
                "• Delete all messages\n" +
                "• Delete all study plans\n" +
                "• Remove all members\n\n" +
                "This CANNOT be undone!"):
                return
            
            try:
                self.db_ref.child(f'studyGroups/{self.current_group}').delete()
                
                dialog.destroy()
                messagebox.showinfo("✅ Success", "Group deleted successfully!")
                
                self.current_group = None
                self.show_empty_state()
                self.load_all_groups()
                
            except Exception as e:
                messagebox.showerror("❌ Error", f"Failed to delete: {e}")
        
        tk.Button(danger_frame, text="🗑️ Delete Group Forever", 
                 bg='#E74C3C', fg='white',
                 font=('Segoe UI', 10, 'bold'),
                 relief='flat', padx=20, pady=8,
                 cursor='hand2',
                 command=delete_group).pack(pady=(0, 15))
        
        # Pack canvas and scrollbar
        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        main_canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    
    
    def on_typing(self, event):
        """Handle typing"""
        if self.current_group and event.char and event.char.isprintable():
            try:
                member_ref = self.db_ref.child(
                    f'studyGroups/{self.current_group}/members/{self.user_id}'
                )
                member_ref.update({'typing': True})
                
                if self.user_id in self.typing_timers:
                    self.parent.after_cancel(self.typing_timers[self.user_id])
                
                self.typing_timers[self.user_id] = self.parent.after(2000, self.stop_typing)
                
            except:
                pass
    
    def stop_typing(self):
        """Stop typing"""
        if self.current_group:
            try:
                member_ref = self.db_ref.child(
                    f'studyGroups/{self.current_group}/members/{self.user_id}'
                )
                member_ref.update({'typing': False})
            except:
                pass


    def refresh_groups_tab(self):
        """Manually refresh all group data and current view."""
        self.load_all_groups()
        if self.current_group:
            self.show_group_content()
            self._reload_chat_messages()


    def load_all_groups(self):
        """Load all groups"""
        if not self.db_ref:
            return
        
        try:
            groups_data = self.db_ref.child('studyGroups').get()
            if groups_data:
                self.groups = groups_data
                self.update_groups_lists()
            else:
                # ✅ FIX: Handle empty groups
                self.groups = {}
                self.update_groups_lists()
        except Exception as e:
            print(f"Load error: {e}")

    def update_groups_lists(self):
        """Update all group lists with detailed debugging"""
        # Clear existing lists
        for widget in self.your_groups_list.winfo_children():
            widget.destroy()
        for widget in self.joined_groups_list.winfo_children():
            widget.destroy()
        
        your_groups = []
        joined_groups = []
        
        print("\n" + "="*80)
        print(f"🔍 DEBUGGING GROUP LISTS")
        print("="*80)
        print(f"👤 Current User ID: {self.user_id}")
        print(f"📊 Total groups in self.groups: {len(self.groups)}")
        print()
        
        for group_id, group_data in self.groups.items():
            print(f"📂 Checking Group ID: {group_id}")
            
            # Get members
            members = group_data.get('members', {})
            print(f"   👥 Total members in group: {len(members)}")
            print(f"   👥 Member IDs: {list(members.keys())}")
            
            # Get metadata
            metadata = group_data.get('metadata', {})
            created_by = metadata.get('created_by', '')
            group_name = metadata.get('name', 'Unnamed')
            
            print(f"   📝 Group Name: {group_name}")
            print(f"   👑 Created By: {created_by}")
            
            # Check if user is in members
            is_member = self.user_id in members
            print(f"   ❓ Is user in members? {is_member}")
            
            if is_member:
                # Check who created it
                is_creator = (created_by == self.user_id)
                print(f"   ❓ Is user the creator? {is_creator}")

                if is_creator:
                    your_groups.append((group_id, group_data))
                    print(f"   ✅ Added to YOUR GROUPS")
                else:
                    joined_groups.append((group_id, group_data))
                    print(f"   ✅ Added to JOINED GROUPS")
            else:
                # If the user created the group but isn't listed as a member (e.g., after reinstall), re-add them
                if created_by == self.user_id:
                    print("   ⚠️ User is creator but missing from members - restoring membership")

                    # Attempt to re-add the creator as admin to preserve access
                    try:
                        if self.db_ref:
                            member_data = {
                                'name': self.get_user_name(),
                                'avatar_name': f"avatar {self.profile_data.get('avatar_id', 1)}.png",
                                'role': 'admin',
                                'joined_at': datetime.now().isoformat(),
                                'online': True,
                                'last_seen': datetime.now().isoformat(),
                                'typing': False,
                                'telegram_chat_id': self.profile_data.get('telegram_chat_id', '')
                            }
                            self.db_ref.child(f'studyGroups/{group_id}/members/{self.user_id}').set(member_data)
                            print("   ✅ Creator membership restored as admin")
                    except Exception as e:
                        print(f"   ⚠️ Failed to restore membership: {e}")

                    your_groups.append((group_id, group_data))
                    print(f"   ✅ Added creator-owned group to YOUR GROUPS")
                else:
                    print(f"   ❌ User NOT in members - Skipping")
            
            print()
        
        print("="*80)
        print(f"📊 FINAL RESULTS:")
        print(f"   Your Groups: {len(your_groups)}")
        print(f"   Joined Groups: {len(joined_groups)}")
        print("="*80 + "\n")
        
        # Display your groups
        if your_groups:
            for group_id, group_data in your_groups:
                self.create_group_list_item(self.your_groups_list, group_id, group_data)
        else:
            tk.Label(self.your_groups_list, text="No groups created",
                    font=('Segoe UI', 8), bg=self.colors['light'],
                    fg=self.colors['gray']).pack(pady=10)
        
        # Display joined groups
        if joined_groups:
            for group_id, group_data in joined_groups:
                self.create_group_list_item(self.joined_groups_list, group_id, group_data)
        else:
            tk.Label(self.joined_groups_list, text="No joined groups",
                    font=('Segoe UI', 8), bg=self.colors['light'],
                    fg=self.colors['gray']).pack(pady=10)
    
    def create_group_list_item(self, parent, group_id, group_data):
        """✅ FIXED: Create compact group item with smooth circular icon"""
        is_selected = group_id == self.current_group
        bg = self.colors['hover'] if is_selected else self.colors['light']

        item = tk.Frame(parent, bg=bg, cursor='hand2')
        item.pack(fill=tk.X, pady=1)

        def select(e=None):
            self.select_group(group_id)

        item.bind('<Button-1>', select)

        content = tk.Frame(item, bg=bg)
        content.pack(fill=tk.X, padx=6, pady=4)
        content.bind('<Button-1>', select)

        # === SMOOTH CIRCULAR GROUP ICON ===
        icon_url = group_data.get('metadata', {}).get('icon_url')
        size = 28
        
        try:
            if icon_url:
                from urllib.request import urlopen
                img_data = urlopen(icon_url, timeout=5).read()
                img = Image.open(BytesIO(img_data)).convert("RGBA")
                # Upscale for quality
                img = img.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
            else:
                raise ValueError("No icon")

        except Exception as e:
            # Default icon at 2x for smoothness
            img = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([4, 4, size*2-4, size*2-4], fill="#95A5A6")
            
            # Try to add group emoji
            try:
                font = ImageFont.truetype("seguiemj.ttf", 28)
                draw.text((size - 14, size - 18), "👥", fill="white", font=font)
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", 20)
                    draw.text((size - 10, size - 14), "GP", fill="white", font=font)
                except:
                    pass

        # Smooth anti-aliased mask at 2x
        mask = Image.new("L", (size * 2, size * 2), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((1, 1, size*2-1, size*2-1), fill=255)
        
        # Soft blur for smooth edges
        from PIL import ImageFilter
        mask = mask.filter(ImageFilter.GaussianBlur(1))
        
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        img.putalpha(mask)
        
        # Downscale to final size (smooth anti-aliasing)
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        
        photo = ImageTk.PhotoImage(img)

        icon_label = tk.Label(content, image=photo, bg=bg)
        icon_label.image = photo
        icon_label.pack(side=tk.LEFT, padx=(0, 4))
        icon_label.bind('<Button-1>', select)

        # === GROUP NAME & MEMBER COUNT ===
        info = tk.Frame(content, bg=bg)
        info.pack(side=tk.LEFT, fill=tk.X, expand=True)
        info.bind('<Button-1>', select)

        name = group_data.get('metadata', {}).get('name', 'Unnamed')
        name_label = tk.Label(
            info, text=name[:18], font=('Segoe UI', 9, 'bold'),
            bg=bg, fg=self.colors['dark'], anchor='w'
        )
        name_label.pack(fill=tk.X)
        name_label.bind('<Button-1>', select)

        member_count = len(group_data.get('members', {}))
        count_label = tk.Label(
            info, text=f"{member_count} members", font=('Segoe UI', 8),
            bg=bg, fg=self.colors['gray'], anchor='w'
        )
        count_label.pack(fill=tk.X)
        count_label.bind('<Button-1>', select)
        
    def upload_user_avatar_to_firebase(self):
        """Uploads local avatar image to Firebase Storage and returns cleaned public URL."""
        import os, time

        try:
            # --- Ensure user_id is valid and clean ---
            if not self.user_id:
                raise ValueError("⚠ user_id missing during avatar upload")
            self.user_id = str(self.user_id).strip().replace(" ", "")

            avatar_path = self.get_user_avatar() or self.profile_data.get("avatar_url")

            # --- Skip if missing or already a URL ---
            if not avatar_path:
                print("⚠ No avatar found to upload (skipping).")
                return None

            if str(avatar_path).startswith("http"):
                # Already uploaded URL — clean it once more just to be sure
                clean_url = str(avatar_path).strip()
                clean_url = "".join(clean_url.split())
                clean_url = clean_url.replace(" ", "%20")
                return clean_url

            if not os.path.exists(str(avatar_path)):
                print("⚠ Local avatar file missing, skipping upload.")
                return None

            if not self.storage_bucket:
                print("⚠ No Firebase bucket available.")
                return None

            # --- Clean filename and build upload path ---
            filename = os.path.basename(avatar_path).strip().replace(" ", "_")
            user_id_clean = str(self.user_id).strip().replace(" ", "")
            blob_path = f"avatars/{user_id_clean}/{int(time.time())}_{filename}"

            # --- Upload to Firebase Storage ---
            blob = self.storage_bucket.blob(blob_path)
            blob.upload_from_filename(avatar_path)
            blob.make_public()

            # --- Clean and normalize the final public URL ---
            avatar_url = str(blob.public_url).strip()
            avatar_url = "".join(avatar_url.split())       # remove hidden newlines
            avatar_url = avatar_url.replace(" ", "%20")    # URL-safe

            # --- Save locally & optionally sync to member data ---
            self.profile_data["avatar_url"] = avatar_url

            # (optional) also update in Firebase member node if exists
            try:
                if self.db_ref and self.current_group:
                    member_ref = self.db_ref.child(f"studyGroups/{self.current_group}/members/{self.user_id}")
                    # Clean and update avatar automatically
                    clean_avatar = "".join(avatar_url.split()).replace(" /", "/").replace(" ", "%20")
                    member_ref.update({"avatar": clean_avatar})
                    print(f"✅ Synced cleaned avatar URL to member data for {self.user_id}")

            except Exception as e:
                print("⚠ Member avatar sync skipped:", e)

            print(f"✅ Avatar uploaded: {avatar_url}")
            return avatar_url

        except Exception as e:
            print(f"⚠ Avatar upload skipped: {e}")
            return None


    def select_group(self, group_id):
        """Select a group — OPTIMIZED to fix 7MB load + enable notifications."""
        import threading, time, tkinter as tk

        self.current_group = group_id
        self._all_messages_cache = []
        self.current_plan = None
        
        # ✅ Clear message avatar cache
        if hasattr(self, "_message_avatar_cache"):
            self._message_avatar_cache.clear()
        
        # Clear loaded messages
        self.loaded_message_keys.clear()

        # --- clear old messages instantly ---
        for widget in self.messages_list_frame.winfo_children():
            widget.destroy()

        # 🌀 create loading label
        loading_label = tk.Label(
            self.messages_list_frame,
            text="Loading messages",
            font=('Segoe UI', 9, 'italic'),
            bg='white', fg='#888'
        )
        loading_label.pack(pady=20)

        self.messages_canvas.update_idletasks()
        self.messages_canvas.configure(scrollregion=self.messages_canvas.bbox("all"))

        # --- simple animated spinner ---
        def animate_loading(dot_count=0):
            if not (loading_label and loading_label.winfo_exists()):
                return
            dots = "." * (dot_count % 4)
            loading_label.config(text=f"Loading messages{dots}")
            self.parent.after(150, lambda: animate_loading(dot_count + 1))

        self._loading_active = True
        animate_loading()

        # --- clear caches for fresh group ---
        self.loaded_message_keys.clear()
        if hasattr(self, "_avatar_cache"):
            self._avatar_cache.clear()

        # --- show UI instantly ---
        self.update_groups_lists()
        self.show_group_content()
        self.parent.update_idletasks()

        # --- async profile sync ---
        def background_sync():
            try:
                name = self.get_user_name()
                avatar_id = self.profile_data.get("avatar_id", 1)
                avatar_name = f"avatar {avatar_id}.png"
                telegram_chat_id = self.profile_data.get('telegram_chat_id', '')
                
                update_data = {
                    'name': name,
                    'avatar_name': avatar_name,
                    'telegram_chat_id': telegram_chat_id  # ✅ ADD THIS
                }
                
                member_ref = self.db_ref.child(
                    f'studyGroups/{self.current_group}/members/{self.user_id}'
                )
                member_ref.update(update_data)
                print(f"✅ Profile synced: {update_data}")
            except Exception as e:
                print(f"⚠ Profile sync error: {e}")
        threading.Thread(target=background_sync, daemon=True).start()
       
        # --- async messages load (OPTIMIZED: only loads 30 recent messages initially) ---
        def load_messages_async():
            import time
            try:
                time.sleep(0.3)
                if self.db_ref and self.current_group:
                    # ✅ OPTIMIZED: Limit to 30 messages (NOT ALL!)
                    messages_ref = self.db_ref.child(f'studyGroups/{self.current_group}/messages')
                    messages_data = messages_ref.order_by_key().limit_to_last(30).get() or {}

                    sorted_messages = sorted(messages_data.items(), key=lambda x: x[1].get('timestamp', ''))
                    total_messages = len(sorted_messages)
                    print(f"✅ Loaded {total_messages} recent messages (optimized)")

                    self._all_messages_cache = sorted_messages
                    self.parent.after(0, lambda: self.display_messages(dict(sorted_messages)))

                    if hasattr(self, "_loading_active"):
                        self._loading_active = False
                    loading_label.destroy()

                    # Bind lazy scroll
                    def on_scroll(event):
                        if not hasattr(self, "_lazy_loading") or not self._lazy_loading:
                            if self.messages_canvas.yview()[0] <= 0.05:
                                self._lazy_loading = True
                                self.lazy_load_older_messages()
                                self.parent.after(1000, lambda: setattr(self, "_lazy_loading", False))
                    self.messages_canvas.bind("<MouseWheel>", on_scroll)

            except Exception as e:
                print(f"⚠ Message load error: {e}")
                self._loading_active = False
                self.parent.after(0, lambda: loading_label.config(text="⚠ Failed to load"))

        threading.Thread(target=load_messages_async, daemon=True).start()

        # --- reconnect realtime listener ---
        self.start_message_listener(group_id)


    def lazy_load_older_messages(self, batch_size=25):
        """Loads older messages when user scrolls to top, with loading indicator."""
        import tkinter as tk
        import time

        try:
            if not hasattr(self, "_all_messages_cache") or not self._all_messages_cache:
                print("⚠ No message cache found.")
                return

            loaded_count = len(self.loaded_message_keys)
            total = len(self._all_messages_cache)

            if loaded_count >= total:
                return  # already all messages loaded

            # --- Add temporary loading label at top ---
            loading_label = tk.Label(
                self.messages_list_frame,
                text="Loading older messages...",
                font=('Segoe UI', 8, 'italic'),
                bg='white', fg='#888'
            )
            loading_label.pack(anchor='n', pady=(5, 0))

            # --- Update UI instantly ---
            self.messages_canvas.update_idletasks()

            # --- Compute new batch indices ---
            start_index = max(total - loaded_count - batch_size, 0)
            end_index = total - loaded_count
            new_batch = self._all_messages_cache[start_index:end_index]
            print(f"📜 Lazy loading {len(new_batch)} older messages...")

            # --- Temporarily store scroll position ---
            y_before = self.messages_canvas.yview()[0]

            # --- Render older messages (prepend order) ---
            for key, msg_data in new_batch:
                self.display_messages({key: msg_data})

            # --- Restore scroll position ---
            self.messages_canvas.update_idletasks()
            self.messages_canvas.yview_moveto(y_before)

            # --- Remove loading label after short delay ---
            def remove_label():
                try:
                    loading_label.destroy()
                except Exception:
                    pass

            self.parent.after(600, remove_label)

        except Exception as e:
            print("⚠ Lazy load error:", e)
    
    def load_messages(self):
        """Load messages"""
        if not self.current_group or not self.db_ref:
            return
        
        try:
            messages_ref = self.db_ref.child(f'studyGroups/{self.current_group}/messages')
            messages_data = messages_ref.get()
            
            self.display_messages(messages_data if messages_data else {})
        except Exception as e:
            print(f"Load messages error: {e}")
    
    def refresh_group_data(self):
        """Refresh group data"""
        if not self.current_group or not self.db_ref:
            return
        
        try:
            group_ref = self.db_ref.child(f'studyGroups/{self.current_group}')
            group_data = group_ref.get()
            
            if group_data:
                self.groups[self.current_group] = group_data
                self.show_group_content()
        except Exception as e:
            print(f"Refresh error: {e}")
    
    def create_group_dialog(self):
        """Modern create group dialog with all customization options"""
        dialog = tk.Toplevel(self.parent)
        dialog.title("✨ Create New Group")
        dialog.geometry("550x750")
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.configure(bg='#F5F7FA')
        
        # Main container with scrollbar
        main_canvas = tk.Canvas(dialog, bg='#F5F7FA', highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=main_canvas.yview)
        scrollable_frame = tk.Frame(main_canvas, bg='#F5F7FA')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        # ===== HEADER =====
        header = tk.Frame(scrollable_frame, bg='#4A90E2', height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(header, text="🎯 Create Your Study Group", 
                font=('Segoe UI', 16, 'bold'),
                bg='#4A90E2', fg='white').pack(pady=20)
        
        # ===== CONTENT AREA =====
        content = tk.Frame(scrollable_frame, bg='#F5F7FA')
        content.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)
        
        # Group Name
        name_frame = tk.Frame(content, bg='#F5F7FA')
        name_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(name_frame, text="📝 Group Name *", font=('Segoe UI', 11, 'bold'),
                bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(0, 5))
        name_entry = ttk.Entry(name_frame, width=50, font=('Segoe UI', 10))
        name_entry.pack(fill=tk.X)
        
        # Description
        desc_frame = tk.Frame(content, bg='#F5F7FA')
        desc_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(desc_frame, text="📄 Description", font=('Segoe UI', 11, 'bold'),
                bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(0, 5))
        desc_text = tk.Text(desc_frame, width=50, height=4, font=('Segoe UI', 10),
                           relief='solid', borderwidth=1)
        desc_text.pack(fill=tk.X)
        
        # Header Background Color
        tk.Label(content, text="🎨 Header Background Color", 
                font=('Segoe UI', 11, 'bold'),
                bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(15, 5))
        
        color_frame = tk.Frame(content, bg='#F5F7FA')
        color_frame.pack(fill=tk.X, pady=(0, 10))
        
        current_bg_color = self.colors['light']
        selected_color = tk.StringVar(value=current_bg_color)
        
        # Color preview
        preview_frame = tk.Frame(color_frame, bg='#F5F7FA')
        preview_frame.pack(anchor='w', pady=(0, 10))
        
        tk.Label(preview_frame, text="Preview:", font=('Segoe UI', 9),
                bg='#F5F7FA').pack(side=tk.LEFT, padx=(0, 10))
        
        color_preview = tk.Canvas(preview_frame, width=120, height=40, 
                                  bg=current_bg_color, highlightthickness=2, 
                                  highlightbackground='#CCCCCC')
        color_preview.pack(side=tk.LEFT)
        
        # Color palette
        colors_grid = tk.Frame(content, bg='#F5F7FA')
        colors_grid.pack(fill=tk.X, pady=(0, 10))
        
        preset_colors = [
            ('#FFFFFF', 'White'),
            ('#F8F9FA', 'Light Gray'),
            ('#E3F2FD', 'Sky Blue'),
            ('#E8F5E9', 'Mint'),
            ('#FFF3E0', 'Peach'),
            ('#F3E5F5', 'Lavender'),
            ('#FFE0B2', 'Orange'),
            ('#FFEBEE', 'Pink'),
            ('#E0F7FA', 'Cyan'),
            ('#FFF9C4', 'Yellow'),
            ('#D7CCC8', 'Beige'),
            ('#CFD8DC', 'Blue Gray'),
            ('#C8E6C9', 'Green'),
            ('#FFCCBC', 'Coral'),
            ('#B3E5FC', 'Light Blue'),
            ('#F0F4C3', 'Lime')
        ]
        
        def set_color(color):
            selected_color.set(color)
            color_preview.config(bg=color)
        
        for i, (color, name) in enumerate(preset_colors):
            row = i // 4
            col = i % 4
            
            color_container = tk.Frame(colors_grid, bg='#F5F7FA')
            color_container.grid(row=row, column=col, padx=5, pady=5)
            
            color_btn = tk.Frame(color_container, bg=color, width=90, height=35,
                                relief='raised', borderwidth=2, cursor='hand2')
            color_btn.pack()
            color_btn.pack_propagate(False)
            
            color_label = tk.Label(color_btn, text=name, font=('Segoe UI', 8),
                                  bg=color, cursor='hand2')
            color_label.pack(expand=True)
            
            color_btn.bind('<Button-1>', lambda e, c=color: set_color(c))
            color_label.bind('<Button-1>', lambda e, c=color: set_color(c))
        
        # Group Icon
        tk.Label(content, text="🖼️ Group Icon", 
                font=('Segoe UI', 11, 'bold'),
                bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(15, 5))
        
        icon_note = tk.Label(content, text="(You can change the icon after creating the group)", 
                           font=('Segoe UI', 9, 'italic'),
                           bg='#F5F7FA', fg='#7F8C8D')
        icon_note.pack(anchor='w', pady=(0, 15))
        
        # Security Settings
        tk.Label(content, text="🔒 Security Settings", 
                font=('Segoe UI', 11, 'bold'),
                bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(15, 5))
        
        security_frame = tk.Frame(content, bg='white', relief='solid', borderwidth=1)
        security_frame.pack(fill=tk.X, pady=(0, 15))
        
        password_var = tk.BooleanVar()
        password_check = tk.Checkbutton(security_frame, text="🔐 Password Protected Group", 
                                       variable=password_var,
                                       font=('Segoe UI', 10),
                                       bg='white', activebackground='white')
        password_check.pack(anchor='w', padx=10, pady=10)
        
        password_entry_frame = tk.Frame(security_frame, bg='white')
        password_entry_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Label(password_entry_frame, text="Password:", font=('Segoe UI', 9),
                bg='white').pack(anchor='w')
        password_entry = ttk.Entry(password_entry_frame, width=40, show="●", font=('Segoe UI', 10))
        password_entry.pack(fill=tk.X, pady=(2, 0))
        
        # Max Members
        members_frame = tk.Frame(content, bg='#F5F7FA')
        members_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(members_frame, text="👥 Maximum Members", font=('Segoe UI', 11, 'bold'),
                bg='#F5F7FA', fg='#2C3E50').pack(anchor='w', pady=(0, 5))
        
        max_members_frame = tk.Frame(members_frame, bg='white', relief='solid', borderwidth=1)
        max_members_frame.pack(fill=tk.X, pady=(0, 5))
        
        max_members = ttk.Spinbox(max_members_frame, from_=2, to=200, width=15, font=('Segoe UI', 10))
        max_members.set(50)
        max_members.pack(padx=10, pady=10)
        
        # Action Buttons
        btn_frame = tk.Frame(content, bg='#F5F7FA')
        btn_frame.pack(pady=30)
        
        def create():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("❌ Error", "Group name is required!")
                return
            
            if not self.db_ref:
                return
            
            try:
                group_id = self.db_ref.child('studyGroups').push().key
                
                group_data = {
                    'metadata': {
                        'name': name,
                        'description': desc_text.get('1.0', tk.END).strip(),
                        'created_by': self.user_id,
                        'created_at': datetime.now().isoformat(),
                        'password': hashlib.sha256(password_entry.get().encode()).hexdigest() 
                                   if password_var.get() and password_entry.get() else None,
                        'max_members': int(max_members.get()),
                        'invite_code': self.generate_invite_code(),
                        'header_bg_color': selected_color.get()
                    },
                    'members': {
                        self.user_id: {
                            'name': self.get_user_name(),
                            'avatar_name': f"avatar {self.profile_data.get('avatar_id', 1)}.png",  # ✅ Include .png
                            'role': 'admin',
                            'joined_at': datetime.now().isoformat(),
                            'online': True,
                            'last_seen': datetime.now().isoformat(),
                            'typing': False
                        }
                    },
                    'messages': {},
                    'plans': {}
                }
                
                self.db_ref.child(f'studyGroups/{group_id}').set(group_data)
                
                dialog.destroy()
                messagebox.showinfo("✅ Success", f"Group '{name}' created successfully!")
                
                self.load_all_groups()
                self.select_group(group_id)
                
            except Exception as e:
                messagebox.showerror("❌ Error", f"Failed to create group: {e}")
        
        tk.Button(btn_frame, text="✨ Create Group", bg='#4A90E2', fg='white',
                 font=('Segoe UI', 11, 'bold'),
                 relief='flat', padx=30, pady=10, 
                 cursor='hand2',
                 command=create).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="❌ Cancel", bg='#95A5A6', fg='white',
                 font=('Segoe UI', 11),
                 relief='flat', padx=30, pady=10,
                 cursor='hand2',
                 command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # Pack canvas and scrollbar
        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        main_canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def join_group_dialog(self):
        """Join group dialog"""
        dialog = tk.Toplevel(self.parent)
        dialog.title("Join Group")
        dialog.geometry("400x250")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        tk.Label(dialog, text="Enter Invite Code:", font=('Segoe UI', 10)).pack(pady=(20, 5))
        invite_entry = ttk.Entry(dialog, width=30, font=('Segoe UI', 11))
        invite_entry.pack(pady=5)
        
        tk.Label(dialog, text="Password (if required):", font=('Segoe UI', 10)).pack(pady=(10, 5))
        password_entry = ttk.Entry(dialog, width=30, show="*", font=('Segoe UI', 11))
        password_entry.pack(pady=5)
        
        def join():
            invite_code = invite_entry.get().strip()
            password = password_entry.get()
            
            if not invite_code:
                messagebox.showerror("Error", "Enter code!")
                return
            
            if not self.db_ref:
                return
            
            try:
                groups_data = self.db_ref.child('studyGroups').get()
                group_found = None
                group_id_found = None
                
                if groups_data:
                    for group_id, group_data in groups_data.items():
                        if group_data.get('metadata', {}).get('invite_code') == invite_code:
                            group_found = group_data
                            group_id_found = group_id
                            break
                
                if not group_found:
                    messagebox.showerror("Error", "Invalid code!")
                    return
                
                if self.user_id in group_found.get('members', {}):
                    messagebox.showinfo("Info", "Already a member!")
                    dialog.destroy()
                    self.select_group(group_id_found)
                    return
                
                stored_password = group_found.get('metadata', {}).get('password')
                if stored_password:
                    if hashlib.sha256(password.encode()).hexdigest() != stored_password:
                        messagebox.showerror("Error", "Incorrect password!")
                        return
                
                current_members = len(group_found.get('members', {}))
                max_members = group_found.get('metadata', {}).get('max_members', 50)
                if current_members >= max_members:
                    messagebox.showerror("Error", "Group full!")
                    return
                
                member_data = {
                    'name': self.get_user_name(),
                    'avatar_name': f"avatar {self.profile_data.get('avatar_id', 1)}.png",
                    'role': 'member',
                    'joined_at': datetime.now().isoformat(),
                    'online': True,
                    'last_seen': datetime.now().isoformat(),
                    'typing': False,
                    'telegram_chat_id': self.profile_data.get('telegram_chat_id', '')  # ✅ ADD THIS
                }

                self.db_ref.child(f'studyGroups/{group_id_found}/members/{self.user_id}').set(member_data)
                
                dialog.destroy()
                messagebox.showinfo("Success", "Joined successfully!")
                
                self.load_all_groups()
                self.select_group(group_id_found)
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed: {e}")
        
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="Join", bg=self.colors['secondary'], fg='white',
                 relief='flat', padx=20, command=join).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", bg=self.colors['gray'], fg='white',
                 relief='flat', padx=20, command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def start_firebase_listeners(self):
        """Start Firebase listeners"""
        if not self.db_ref:
            return
        
        try:
            groups_ref = self.db_ref.child('studyGroups')
            groups_ref.listen(self.on_groups_change)
        except Exception as e:
            print(f"Listener error: {e}")
    
    
    def on_groups_change(self, event):
        """Handle groups change"""
        if event.data:
            self.groups = event.data
            # ✅ Sync profile name immediately to all groups
            self._sync_member_name_across_groups()
            self.update_groups_lists()
            
            if self.current_group:
                self.refresh_current_group()

    def _sync_member_name_across_groups(self):
        """Sync current profile name and avatar to all group memberships"""
        try:
            current_name = self.get_user_name()
            avatar_id = self.profile_data.get("avatar_id", 1)
            avatar_name = f"avatar {avatar_id}.png"
            
            update_data = {
                'name': current_name,
                'avatar_name': avatar_name
            }
            
            for group_id in self.groups:
                if self.user_id in self.groups[group_id].get('members', {}):
                    member_ref = self.db_ref.child(f'studyGroups/{group_id}/members/{self.user_id}')
                    member_ref.update(update_data)
                    # Update local cache
                    if 'members' in self.groups[group_id] and self.user_id in self.groups[group_id]['members']:
                        self.groups[group_id]['members'][self.user_id].update(update_data)
        except Exception as e:
            print(f"Error syncing member data: {e}")

    
    def refresh_current_group(self):
        """Refresh current group"""
        if self.current_group and self.current_group in self.groups:
            self.show_group_content()
    
    def is_admin(self, group_id):
        """Check if admin"""
        if group_id in self.groups:
            members = self.groups[group_id].get('members', {})
            if self.user_id in members:
                return members[self.user_id].get('role') == 'admin'
        return False
    
    def get_user_name(self):
        """Return user_name from profile data"""
        name = self.profile_data.get("user_name")
        if name:
            return name
        return f"User_{self.user_id[-4:]}"
        
    def get_user_avatar(self):
        """Return LOCAL avatar path only (no Firebase upload!)"""
        # Get avatar_id from profile
        avatar_id = self.profile_data.get("avatar_id", 1)
        
        # Build LOCAL path (avatars stored locally: "avatar 1.png", "avatar 2.png", etc.)
        from config_paths import app_paths
        actual_path = os.path.join(app_paths.avatars_dir, f"avatar {avatar_id}.png")
        
        if os.path.exists(actual_path):
            return actual_path
        
        # Fallback to avatar 1 if not found
        fallback = os.path.join(app_paths.avatars_dir, "avatar 1.png")
        if os.path.exists(fallback):
            return fallback
        
        return None
    
    def generate_invite_code(self):
        """Generate invite code"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    def start_online_presence(self):
        """Use Firebase's onDisconnect for automatic, low-cost presence tracking"""
        try:
            if not self.db_ref or not self.current_group:
                return

            member_path = f'studyGroups/{self.current_group}/members/{self.user_id}'
            member_ref = self.db_ref.child(member_path)

            # Mark as online immediately
            member_ref.update({
                'online': True,
                'last_seen': datetime.now().isoformat()
            })

            # Automatically mark offline when app closes or network drops
            on_disconnect_ref = member_ref.on_disconnect()
            on_disconnect_ref.update({
                'online': False,
                'last_seen': datetime.now().isoformat()
            })

        except Exception as e:
            print(f"Presence setup error: {e}")
    
    def cleanup(self):
        """Cleanup when closing app"""
        try:
            if self.current_group and self.db_ref:
                member_ref = self.db_ref.child(
                    f'studyGroups/{self.current_group}/members/{self.user_id}'
                )
                member_ref.update({
                    'online': False,
                    'last_seen': datetime.now().isoformat()
                })
        except:
            pass

        # Close message listener
        if self.message_listener:
            try:
                self.message_listener.close()
            except:
                pass
        
        # ✅ Stop notification system
        if hasattr(self, 'notification_system') and self.notification_system:
            try:
                self.notification_system.stop()
            except:
                pass


def add_firebase_groups_tab(notebook, user_id, import_plan_callback, profile_data=None):
    """Add Firebase-powered Groups tab to notebook"""
    return ModernGroupsTab(notebook, user_id, import_plan_callback, profile_data)