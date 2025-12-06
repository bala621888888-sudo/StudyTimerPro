# ai_chat_dialog_enhanced.py
# ✅ Complete with chat history, new topic, and better UI

import json
import threading
import base64
from pathlib import Path
from io import BytesIO
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkinter.scrolledtext import ScrolledText
from openai import OpenAI

from ai_integration import create_ai_prompt
from secrets_util import get_secret
from config_paths import app_paths

# ---------- Pillow for emoji and image handling ----------
from PIL import Image, ImageDraw, ImageFont, ImageTk
import os

APPDATA = Path(app_paths.appdata_dir)
PLANS_PATH = APPDATA / "plans.json"
PROFILE_PATH = APPDATA / "profile.json"
EXAM_DATE_PATH = APPDATA / "exam_date.json"
RAW_FALLBACK = APPDATA / "plans_raw_output.txt"
CHAT_HISTORY_PATH = APPDATA / "chat_history.json"


# ================= Emoji helpers =================
def _pick_emoji_font(size: int):
    font_paths = [
        r"C:\Windows\Fonts\seguiemj.ttf",
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return None

# PATCH: Fix emoji vertical alignment in render_emoji_photoimage

def render_emoji_photoimage(emoji_text: str, size: int = 16) -> ImageTk.PhotoImage:
    """Render emoji with proper baseline alignment"""
    # Increase height to prevent cutoff
    pad_x = int(size * 0.2)
    pad_y = int(size * 0.5)  # More bottom padding
    
    img = Image.new("RGBA", (size + pad_x, size + pad_y), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    font = _pick_emoji_font(int(size * 0.85)) or ImageFont.load_default()
    
    # Move emoji DOWN to align with text baseline
    draw.text((pad_x // 2, pad_y // 2), emoji_text, font=font, embedded_color=True)
    
    return ImageTk.PhotoImage(img)

def _iter_emoji_spans(text: str):
    try:
        import emoji
        try:
            pattern = emoji.regex().get_emoji_regexp()
        except Exception:
            pattern = emoji.get_emoji_regexp()
        for m in pattern.finditer(text):
            yield m.start(), m.end(), m.group(0)
    except Exception:
        for i, ch in enumerate(text):
            if ord(ch) >= 0x1F300:
                yield i, i + 1, ch

def insert_with_emojis(text_widget, text: str, image_cache: list, size_override=None):
    """Insert text with emoji + bold headings + automatic #→• conversion."""
    import re

    # --- Convert markdown headings (# Header) into bullet headers ---
    def convert_markdown_headings(t):
        lines = t.split("\n")
        new_lines = []
        for line in lines:
            if re.match(r"^\s*#{1,6}\s+.+", line):
                clean = re.sub(r"^\s*#{1,6}\s*", "", line).strip()
                new_lines.append(f"• {clean}")
            else:
                new_lines.append(line)
        return "\n".join(new_lines)

    # Apply heading conversion
    text = convert_markdown_headings(text)

    # --- Insert line-by-line using bold detection ---
    lines = text.split("\n")
    for line in lines:
        _insert_with_bold_and_emojis(text_widget, line, image_cache, size_override)
        text_widget.insert("end", "\n")
        
def _insert_with_bold_and_emojis(text_widget, line: str, image_cache: list, size_override):
    import re

    # Bold tag must exist
    text_widget.tag_configure("bold", font=("Segoe UI", 11, "bold"))

    stripped = line.strip()

    # ===== AUTO HEADLINE DETECTOR =====
    # (1) Emoji + text → headline
    if re.match(r"^[\W_]*[\U0001F300-\U0001F9FF].{3,}$", stripped):
        _insert_line_with_emojis(text_widget, line, image_cache, size_override, bold=True)
        return

    # (2) Lines ending with ":" (Common AI header)
    if stripped.endswith(":") and len(stripped) < 80:
        _insert_line_with_emojis(text_widget, line, image_cache, size_override, bold=True)
        return

    # (3) ALL CAPS headings
    if stripped.isupper() and len(stripped) > 3:
        _insert_line_with_emojis(text_widget, line, image_cache, size_override, bold=True)
        return

    # (4) **Markdown bold**
    if "**" in line or "__" in line:
        parts = re.split(r"(\*\*.+?\*\*|__.+?__)", line)
        for p in parts:
            if p.startswith("**") and p.endswith("**"):
                text_widget.insert("end", p[2:-2], "bold")
            elif p.startswith("__") and p.endswith("__"):
                text_widget.insert("end", p[2:-2], "bold")
            else:
                _insert_line_with_emojis(text_widget, p, image_cache, size_override)
        return

    # Normal line
    _insert_line_with_emojis(text_widget, line, image_cache, size_override)

def _insert_line_with_emojis(text_widget, line: str, image_cache: list, size_override, bold=False):
    idx = 0
    for start, end, emo in _iter_emoji_spans(line):
        # Insert text before emoji
        if start > idx:
            segment = line[idx:start]
            if bold:
                text_widget.insert("end", segment, "bold")
            else:
                text_widget.insert("end", segment)

        # Insert emoji image
        img = render_emoji_photoimage(emo, size=size_override or 20)
        image_cache.append(img)
        text_widget.image_create("end", image=img)

        idx = end

    # Insert remaining text
    if idx < len(line):
        segment = line[idx:]
        if bold:
            text_widget.insert("end", segment, "bold")
        else:
            text_widget.insert("end", segment)


# =================================================


class AIChatDialog(tk.Toplevel):
    def __init__(self, master=None, on_plans_updated=None):
        super().__init__(master)
        self.title("AI Study Coach")
        self.geometry("1000x750")
        self.transient(master)
        self.grab_set()

        # Configure colors
        self.accent_color = "#5856d6"
        self.bg_light = "#f8f9fa"
        self.card_bg = "#ffffff"

        self.api_key = None
        self.client = None
        
        # Separate chat histories for each tab
        self.plan_chat_history = []
        self.query_chat_history = []
        
        # Current topic
        self.current_topic_id = None
        self.current_topic_name = "New Chat"
        
        self.started = False
        self._emoji_images = []
        self._on_plans_updated = on_plans_updated
        
        # Plan creation specific
        self._waiting_for_hours = False
        self._study_hours = None
        self._study_time = None
        
        # Image handling
        self._uploaded_images = []
        self._current_image_data = None

        self._build_modern_ui()
        self._ensure_files_exist()
        
    def _show_plan_created_splash(self, plan_count, plan_names):
        """
        Show success splash inside the plan tab after plans are created.
        Offers: Return to Plans Tab OR Continue Creating
        """
        # ✅ Create overlay frame on top of plan tab
        self.splash_overlay = tk.Frame(self.plan_tab, bg="#f8f9fa")
        self.splash_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        # Center content frame
        center_frame = tk.Frame(self.splash_overlay, bg="#f8f9fa")
        center_frame.place(relx=0.5, rely=0.45, anchor="center")
        
        # ✅ Success checkmark
        success_icon = tk.Label(
            center_frame,
            text="✅",
            font=("Segoe UI Emoji", 64),
            bg="#f8f9fa"
        )
        success_icon.pack(pady=(0, 20))
        
        # ✅ Success title
        title_label = tk.Label(
            center_frame,
            text="Plans Created Successfully!",
            font=("Segoe UI", 22, "bold"),
            bg="#f8f9fa",
            fg="#2e7d32"
        )
        title_label.pack(pady=(0, 10))
        
        # ✅ Plan details
        plans_text = "\n".join([f"  📋 {name}" for name in plan_names[:5]])
        if len(plan_names) > 5:
            plans_text += f"\n  ... and {len(plan_names) - 5} more"
        
        details_label = tk.Label(
            center_frame,
            text=f"Created {plan_count} plan(s):\n{plans_text}",
            font=("Segoe UI", 11),
            bg="#f8f9fa",
            fg="#555",
            justify="left"
        )
        details_label.pack(pady=(0, 30))
        
        # ✅ Buttons container
        btn_frame = tk.Frame(center_frame, bg="#f8f9fa")
        btn_frame.pack(pady=(0, 20))
        
        def on_return_to_plans():
            """Close dialog and return to Plans Tab in main app"""
            self.splash_overlay.destroy()
            
            # Close the dialog
            self.destroy()
            
            # Switch to Plans tab in main app
            if hasattr(self, 'master') and self.master:
                try:
                    if hasattr(self.master, 'notebook'):
                        self.master.notebook.select(0)  # Today's Plan tab
                except Exception as e:
                    print(f"⚠ Could not switch tab: {e}")
        
        def on_continue():
            """Stay in dialog to create more plans"""
            self.splash_overlay.destroy()
            
            # Reset for new plan creation
            self.plan_chat_history = []
            self.started = False
            self._waiting_for_hours = False
            self._study_hours = None
            self._study_time = None
            
            # Clear chat box
            self.plan_chat_box.config(state=tk.NORMAL)
            self.plan_chat_box.delete("1.0", tk.END)
            self.plan_chat_box.config(state=tk.DISABLED)
            
            # Start fresh conversation
            self.after(100, self._auto_start_plan_chat)
        
        # ✅ "Return to Plans Tab" button
        return_btn = tk.Button(
            btn_frame,
            text="📋 Return to Plans Tab",
            font=("Segoe UI", 12, "bold"),
            bg="#4CAF50",
            fg="white",
            relief="flat",
            bd=0,
            padx=30,
            pady=14,
            cursor="hand2",
            command=on_return_to_plans
        )
        return_btn.pack(side="left", padx=(0, 15))
        
        def on_return_enter(e):
            return_btn.config(bg="#43A047")
        def on_return_leave(e):
            return_btn.config(bg="#4CAF50")
        return_btn.bind("<Enter>", on_return_enter)
        return_btn.bind("<Leave>", on_return_leave)
        
        # ✅ "Continue Creating" button
        continue_btn = tk.Button(
            btn_frame,
            text="➕ Continue Creating",
            font=("Segoe UI", 12),
            bg="#2196F3",
            fg="white",
            relief="flat",
            bd=0,
            padx=30,
            pady=14,
            cursor="hand2",
            command=on_continue
        )
        continue_btn.pack(side="left")
        
        def on_continue_enter(e):
            continue_btn.config(bg="#1976D2")
        def on_continue_leave(e):
            continue_btn.config(bg="#2196F3")
        continue_btn.bind("<Enter>", on_continue_enter)
        continue_btn.bind("<Leave>", on_continue_leave)
        
        # ✅ Tip text
        tip_label = tk.Label(
            center_frame,
            text="💡 Your plans are saved and ready to use in the Plans Tab!",
            font=("Segoe UI", 9),
            bg="#f8f9fa",
            fg="#888"
        )
        tip_label.pack(pady=(10, 0))

    def _ensure_files_exist(self):
        """Ensure all JSON files exist"""
        if not PLANS_PATH.exists():
            PLANS_PATH.parent.mkdir(parents=True, exist_ok=True)
            PLANS_PATH.write_text(json.dumps({}, indent=2), encoding="utf-8")
        
        if not CHAT_HISTORY_PATH.exists():
            CHAT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            CHAT_HISTORY_PATH.write_text(json.dumps({"topics": []}, indent=2), encoding="utf-8")

    def _build_modern_ui(self):
        """Build modern tabbed interface"""
        # Main container
        main_frame = tk.Frame(self, bg=self.bg_light)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header with gradient effect
        header = tk.Frame(main_frame, bg=self.accent_color, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        title_label = tk.Label(
            header, 
            text="🎓 AI Study Coach",
            font=("Segoe UI", 18, "bold"),
            bg=self.accent_color,
            fg="white"
        )
        title_label.pack(side=tk.LEFT, padx=20, pady=15)

        # Notebook with custom style
        notebook_frame = tk.Frame(main_frame, bg=self.bg_light)
        notebook_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.notebook = ttk.Notebook(notebook_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Create tabs - QUERY TAB FIRST!
        self.query_tab = self._create_query_tab()
        self.plan_tab = self._create_plan_tab()

        # Add query tab first so it opens by default
        self.notebook.add(self.query_tab, text="💡 Ask Questions & Problem Solving")
        self.notebook.add(self.plan_tab, text="📅 Study Plan Creation")

        # Bind tab change
        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)

    def _create_query_tab(self):
        """Create General Queries tab with better UI (bottom-fixed input)"""
        tab = tk.Frame(self.notebook, bg=self.card_bg)
        tab.pack_propagate(False)

        # Use grid layout - row 1 expands, row 2 doesn't take space when empty
        tab.rowconfigure(0, weight=0)  # toolbar - fixed
        tab.rowconfigure(1, weight=1)  # chat area - EXPANDS ✅
        tab.rowconfigure(2, weight=0)  # image preview - shrinks when empty ✅
        tab.rowconfigure(3, weight=0)  # input field - fixed ✅
        tab.columnconfigure(0, weight=1)

        # --- Toolbar (row 0) ---
        toolbar = tk.Frame(tab, bg=self.card_bg)
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        self.topic_label = tk.Label(
            toolbar,
            text=f"💬 {self.current_topic_name}",
            font=("Segoe UI", 10, "bold"),
            bg=self.card_bg,
            fg="#333"
        )
        self.topic_label.pack(side=tk.LEFT, padx=5)

        new_topic_btn = tk.Button(
            toolbar,
            text="➕ New",
            font=("Segoe UI", 9),
            bg="#34c759",
            fg="white",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._new_query_topic
        )
        new_topic_btn.pack(side=tk.RIGHT, padx=3)

        history_btn = tk.Button(
            toolbar,
            text="📜 History",
            font=("Segoe UI", 9),
            bg="#ff9500",
            fg="white",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._show_history
        )
        history_btn.pack(side=tk.RIGHT, padx=3)

        telegram_btn = tk.Button(
            toolbar,
            text="📱 Telegram",
            font=("Segoe UI", 9),
            bg="#0088cc",
            fg="white",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._export_to_telegram
        )
        telegram_btn.pack(side=tk.RIGHT, padx=3)

        # --- Chat area (row 1) - EXPANDS FULLY ---
        chat_container = tk.Frame(tab, bg="#e5e5ea")
        chat_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))

        self.query_chat_box = ScrolledText(
            chat_container,
            wrap=tk.WORD,
            font=("Segoe UI", 11),
            bg="white",
            relief=tk.FLAT,
            padx=20,
            pady=15,
            spacing3=5
        )
        self.query_chat_box.pack(fill=tk.BOTH, expand=True)
        self.query_chat_box.config(state=tk.DISABLED)

        # --- Image preview area (row 2) - ONLY VISIBLE WHEN IMAGE UPLOADED ---
        self.image_preview_frame = tk.Frame(tab, bg=self.card_bg)
        # ✅ DON'T grid it yet - only show when image is uploaded
        self.image_preview_label = None

        # --- Bottom input area (row 3) ---
        bottom_frame = tk.Frame(tab, bg=self.card_bg, height=40)
        bottom_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=10)
        bottom_frame.pack_propagate(False)

        input_frame = tk.Frame(bottom_frame, bg="white", relief=tk.SOLID, bd=1)
        input_frame.pack(fill=tk.BOTH, expand=True)

        self.query_image_btn = tk.Button(
            input_frame,
            text="📎",
            font=("Segoe UI", 14),
            bg="white",
            fg=self.accent_color,
            relief=tk.FLAT,
            width=3,
            cursor="hand2",
            command=self._upload_image
        )
        self.query_image_btn.pack(side=tk.LEFT, padx=2, pady=5)

        self.query_entry = tk.Entry(
            input_frame,
            font=("Segoe UI", 11),
            relief=tk.SOLID,
            bg="white",
            fg="#000",
            bd=1,
            insertbackground="#000"
        )
        self.query_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.query_entry.bind("<Return>", lambda e: self._send_query_message())

        self.query_send_btn = tk.Button(
            input_frame,
            text="➤",
            font=("Segoe UI", 14, "bold"),
            bg=self.accent_color,
            fg="white",
            relief=tk.FLAT,
            width=4,
            cursor="hand2",
            command=self._send_query_message
        )
        self.query_send_btn.pack(side=tk.LEFT, padx=2, pady=5)

        print("✅ Query tab input field fixed to bottom successfully!")
        return tab


    def _create_plan_tab(self):
        """Create Study Plan Creation tab"""
        tab = tk.Frame(self.notebook, bg=self.card_bg)
        
        # Info banner
        info_frame = tk.Frame(tab, bg="#e3f2fd", relief=tk.FLAT, bd=1)
        info_frame.pack(fill=tk.X, padx=10, pady=10)
        
        info_label = tk.Label(
            info_frame,
            text="💪 Let's create your personalized study plan! I'll guide you through the process.",
            font=("Segoe UI", 10),
            bg="#e3f2fd",
            fg="#1976d2",
            wraplength=900
        )
        info_label.pack(padx=15, pady=10)

        # Chat container
        chat_container = tk.Frame(tab, bg="#e5e5ea", relief=tk.FLAT, bd=1)
        chat_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.plan_chat_box = ScrolledText(
            chat_container, 
            wrap=tk.WORD,
            font=("Segoe UI", 11),
            bg="white",
            relief=tk.FLAT,
            padx=20,
            pady=15
        )
        self.plan_chat_box.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.plan_chat_box.config(state=tk.DISABLED)

        # Input area
        input_container = tk.Frame(tab, bg=self.card_bg)
        input_container.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        input_frame = tk.Frame(input_container, bg="white", relief=tk.SOLID, bd=1)
        input_frame.pack(fill=tk.X)

        self.plan_entry = tk.Entry(
            input_frame, 
            font=("Segoe UI", 11),
            relief=tk.FLAT,
            bg="white"
        )
        self.plan_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, ipady=10, padx=10)
        self.plan_entry.bind("<Return>", lambda e: self._send_plan_message())

        self.plan_send_btn = tk.Button(
            input_frame,
            text="➤",
            font=("Segoe UI", 14, "bold"),
            bg=self.accent_color,
            fg="white",
            relief=tk.FLAT,
            padx=15,
            cursor="hand2",
            command=self._send_plan_message
        )
        self.plan_send_btn.pack(side=tk.LEFT, padx=5)

        return tab

    def _on_tab_changed(self, event):
        """Handle tab change - auto-start conversations"""
        current_tab = self.notebook.index(self.notebook.select())
        
        if current_tab == 1 and not self.started:  # Plan tab (now second)
            self.after(100, self._auto_start_plan_chat)
        elif current_tab == 0 and len(self.query_chat_history) == 0:  # Query tab (now first)
            self.after(100, self._auto_start_query_chat)

    def _new_query_topic(self):
        """Start a new query topic"""
        # Save current topic if exists
        if self.current_topic_id and len(self.query_chat_history) > 0:
            self._save_current_topic()
        
        # Reset for new topic
        self.current_topic_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_topic_name = "New Chat"
        self.query_chat_history = []
        
        # Clear chat box
        self.query_chat_box.config(state=tk.NORMAL)
        self.query_chat_box.delete("1.0", tk.END)
        self.query_chat_box.config(state=tk.DISABLED)
        
        # Update label
        self.topic_label.config(text=f"💬 {self.current_topic_name}")
        
        # Restart chat
        self._auto_start_query_chat()

    def _save_current_topic(self):
        """Save current topic to history"""
        try:
            # Load existing history
            if CHAT_HISTORY_PATH.exists():
                data = json.loads(CHAT_HISTORY_PATH.read_text(encoding="utf-8"))
            else:
                data = {"topics": []}
            
            # Create topic entry
            topic_entry = {
                "id": self.current_topic_id,
                "name": self.current_topic_name,
                "timestamp": datetime.now().isoformat(),
                "messages": self.query_chat_history
            }
            
            # Update or append
            found = False
            for i, topic in enumerate(data["topics"]):
                if topic["id"] == self.current_topic_id:
                    data["topics"][i] = topic_entry
                    found = True
                    break
            
            if not found:
                data["topics"].insert(0, topic_entry)
            
            # Keep only last 50 topics
            data["topics"] = data["topics"][:50]
            
            # Save
            CHAT_HISTORY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"✅ Saved topic: {self.current_topic_name}")
            
        except Exception as e:
            print(f"⚠ Failed to save topic: {e}")

    def _export_to_telegram(self):
        """Export current chat to Telegram as HTML"""
        if not self.current_topic_id or len(self.query_chat_history) <= 1:
            messagebox.showinfo("No Chat", "No chat to export yet!")
            return
        
        try:
            # Get Telegram credentials
            bot_token = get_secret("TELEGRAM_BOT_TOKEN")
            if not bot_token:
                messagebox.showerror("Error", "TELEGRAM_BOT_TOKEN not found in secrets!")
                return
            
            # Get chat ID from profile
            profile = self._load_profile()
            chat_id = profile.get("telegram_chat_id", "")
            if not chat_id:
                messagebox.showerror("Error", "telegram_chat_id not found in profile.json!")
                return
            
            # Generate HTML instead of PDF
            html_path = self._generate_chat_html()
            
            if not html_path:
                return
            
            # Send to Telegram
            def send_worker():
                try:
                    import requests
                    
                    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
                    
                    with open(html_path, 'rb') as html_file:
                        files = {'document': html_file}
                        data = {
                            'chat_id': chat_id,
                            'caption': f"📚 Chat Export: {self.current_topic_name}"
                        }
                        
                        response = requests.post(url, files=files, data=data)
                        
                        if response.status_code == 200:
                            self.after(0, lambda: messagebox.showinfo("Success", "Chat sent to Telegram! ✅"))
                        else:
                            self.after(0, lambda: messagebox.showerror("Error", f"Failed to send: {response.text}"))
                    
                    # Clean up
                    if os.path.exists(html_path):
                        os.remove(html_path)
                        
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Error", f"Failed to send to Telegram: {e}"))
            
            self._with_thread(send_worker)
            
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")
    

    def _generate_chat_html(self):
        """Generate HTML from current chat - perfect for all languages!"""
        try:
            html_filename = f"chat_{self.current_topic_id}.html"
            html_path = APPDATA / html_filename
            
            # Build HTML content
            html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Chat: {self.current_topic_name}</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                max-width: 800px;
                margin: 40px auto;
                padding: 20px;
                background: #f8f9fa;
                color: #333;
            }}
            h1 {{
                color: #5856d6;
                border-bottom: 3px solid #5856d6;
                padding-bottom: 10px;
            }}
            .message {{
                background: white;
                padding: 15px 20px;
                margin: 15px 0;
                border-radius: 10px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            .user {{
                border-left: 4px solid #007aff;
            }}
            .assistant {{
                border-left: 4px solid #34c759;
            }}
            .role {{
                font-weight: bold;
                margin-bottom: 8px;
                font-size: 14px;
            }}
            .user .role {{
                color: #007aff;
            }}
            .assistant .role {{
                color: #34c759;
            }}
            .content {{
                line-height: 1.6;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            .timestamp {{
                color: #999;
                font-size: 12px;
                margin-top: 20px;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <h1>📚 Chat: {self.current_topic_name}</h1>
    """
            
            # Add messages
            message_count = 0
            for msg in self.query_chat_history:
                role = msg.get("role")
                content = msg.get("content", "")
                
                if role == "system" or not content or not isinstance(content, str):
                    continue
                
                # Escape HTML characters
                content_escaped = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                
                if role == "user":
                    html_content += f"""
        <div class="message user">
            <div class="role">👤 You</div>
            <div class="content">{content_escaped}</div>
        </div>
    """
                    message_count += 1
                elif role == "assistant":
                    html_content += f"""
        <div class="message assistant">
            <div class="role">🤖 AI Coach</div>
            <div class="content">{content_escaped}</div>
        </div>
    """
                    message_count += 1
            
            if message_count == 0:
                html_content += """
        <div class="message">
            <div class="content">No messages to export.</div>
        </div>
    """
            
            # Add footer
            html_content += f"""
        <div class="timestamp">
            Exported on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </body>
    </html>
    """
            
            # Write HTML file
            html_path.write_text(html_content, encoding='utf-8')
            
            print(f"✅ HTML created with {message_count} messages: {html_path}")
            return html_path
            
        except Exception as e:
            messagebox.showerror("Error", f"HTML generation failed: {e}")
            print(f"HTML error details: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _show_history(self):
        """Show chat history in a dialog"""
        try:
            if not CHAT_HISTORY_PATH.exists():
                messagebox.showinfo("No History", "No chat history found yet!")
                return
            
            data = json.loads(CHAT_HISTORY_PATH.read_text(encoding="utf-8"))
            topics = data.get("topics", [])
            
            if not topics:
                messagebox.showinfo("No History", "No chat history found yet!")
                return
            
            # ✅ Filter out topics with 0 messages (excluding system messages)
            topics_with_messages = []
            for topic in topics:
                msg_count = len([m for m in topic.get("messages", []) if m.get("role") not in ["system"]])
                if msg_count > 0:  # Only include topics with actual messages
                    topics_with_messages.append(topic)
            
            if not topics_with_messages:
                messagebox.showinfo("No History", "No chat history with messages found yet!")
                return
            
            # Create history dialog
            history_dlg = tk.Toplevel(self)
            history_dlg.title("Chat History")
            history_dlg.geometry("600x500")
            history_dlg.transient(self)
            
            # Header
            header = tk.Label(
                history_dlg,
                text="📜 Your Chat History",
                font=("Segoe UI", 14, "bold"),
                bg=self.accent_color,
                fg="white",
                pady=10
            )
            header.pack(fill=tk.X)
            
            # List frame with scrollbar
            list_frame = tk.Frame(history_dlg)
            list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            scrollbar = tk.Scrollbar(list_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            listbox = tk.Listbox(
                list_frame,
                font=("Segoe UI", 10),
                yscrollcommand=scrollbar.set,
                activestyle='none',
                selectbackground=self.accent_color
            )
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.config(command=listbox.yview)
            
            # ✅ Populate list with only non-empty topics
            for topic in topics_with_messages:
                timestamp = datetime.fromisoformat(topic["timestamp"]).strftime("%Y-%m-%d %H:%M")
                name = topic.get("name", "Untitled")
                msg_count = len([m for m in topic.get("messages", []) if m.get("role") not in ["system"]])
                listbox.insert(tk.END, f"{timestamp} - {name} ({msg_count} messages)")
            
            def load_selected():
                selection = listbox.curselection()
                if not selection:
                    return
                
                idx = selection[0]
                topic = topics_with_messages[idx]  # ✅ Use filtered list
                
                # Save current before loading
                if self.current_topic_id and len(self.query_chat_history) > 0:
                    self._save_current_topic()
                
                # Load selected topic
                self.current_topic_id = topic["id"]
                self.current_topic_name = topic.get("name", "Untitled")
                self.query_chat_history = topic.get("messages", [])
                
                # Clear and reload chat
                self.query_chat_box.config(state=tk.NORMAL)
                self.query_chat_box.delete("1.0", tk.END)
                self.query_chat_box.config(state=tk.DISABLED)
                
                # Display messages
                for msg in self.query_chat_history:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        if role == "user":
                            self._append_query_chat("user", content)
                        elif role == "assistant":
                            self._append_query_chat("assistant", content)
                
                self.topic_label.config(text=f"💬 {self.current_topic_name}")
                history_dlg.destroy()
                messagebox.showinfo("Loaded", f"Loaded: {self.current_topic_name}")
            
            # Buttons
            btn_frame = tk.Frame(history_dlg)
            btn_frame.pack(fill=tk.X, padx=10, pady=10)
            
            load_btn = tk.Button(
                btn_frame,
                text="Load Selected",
                font=("Segoe UI", 10, "bold"),
                bg=self.accent_color,
                fg="white",
                command=load_selected
            )
            load_btn.pack(side=tk.LEFT, padx=5)
            
            close_btn = tk.Button(
                btn_frame,
                text="Close",
                font=("Segoe UI", 10),
                command=history_dlg.destroy
            )
            close_btn.pack(side=tk.LEFT, padx=5)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load history: {e}")

    def _upload_image(self):
        """Handle image upload for query tab"""
        file_path = filedialog.askopenfilename(
            title="Select an image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("All files", "*.*")
            ]
        )
        
        if not file_path:
            return

        try:
            # Load and resize image
            img = Image.open(file_path)
            
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize for preview (max 150px height)
            max_height = 150
            ratio = max_height / img.height
            new_size = (int(img.width * ratio), max_height)
            preview_img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Save as PhotoImage for display
            photo = ImageTk.PhotoImage(preview_img)
            self._uploaded_images.append(photo)
            
            # Clear previous preview
            for widget in self.image_preview_frame.winfo_children():
                widget.destroy()
            
            # ✅ NOW grid the preview frame (only when image uploaded)
            self.image_preview_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=2)
            
            # Display preview
            preview_container = tk.Frame(self.image_preview_frame, bg="#e8f5e9", relief=tk.RAISED, bd=2)
            preview_container.pack(fill=tk.X, pady=5)
            
            self.image_preview_label = tk.Label(preview_container, image=photo, bg="#e8f5e9")
            self.image_preview_label.pack(side=tk.LEFT, padx=10, pady=5)
            
            remove_btn = tk.Button(
                preview_container,
                text="❌ Remove",
                font=("Segoe UI", 9),
                bg="#ff5252",
                fg="white",
                cursor="hand2",
                command=self._remove_image
            )
            remove_btn.pack(side=tk.LEFT, padx=5)
            
            # Convert image to base64 for API
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            self._current_image_data = f"data:image/jpeg;base64,{img_base64}"
            
            self._append_query_chat("system", "📸 Image uploaded! Now type your question below.")
            
            # Focus on entry field
            self.query_entry.focus_set()
            
        except Exception as e:
            messagebox.showerror("Image Upload Error", f"Failed to load image: {e}")

    def _remove_image(self):
        """Remove uploaded image"""
        for widget in self.image_preview_frame.winfo_children():
            widget.destroy()
        
        # ✅ Hide the preview frame
        self.image_preview_frame.grid_forget()
        
        self.image_preview_label = None
        self._current_image_data = None
        self._append_query_chat("system", "Image removed.")

    def _load_profile(self):
        if PROFILE_PATH.exists():
            try:
                return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"⚠ Failed to load profile.json: {e}")
        return {}

    def _load_exam_date(self):
        if EXAM_DATE_PATH.exists():
            try:
                data = json.loads(EXAM_DATE_PATH.read_text(encoding="utf-8"))
                return data.get("exam_date", "")
            except Exception as e:
                print(f"⚠ Failed to load exam_date.json: {e}")
        return ""

    def _get_language(self, profile):
        return profile.get("language", "English").strip().lower()

    def _get_exam_name(self, profile):
        return profile.get("exam_name", "Unknown Exam").strip()

    def _is_generic_exam_name(self, exam_name):
        """Check if exam name is too generic and needs specification."""
        generic_exams = {
            "ssc": ["SSC JE", "SSC CHSL", "SSC CGL", "SSC MTS", "SSC CPO", "SSC Stenographer"],
            "upsc": ["UPSC CSE", "UPSC IAS", "UPSC IPS", "UPSC CDS", "UPSC CAPF", "UPSC NDA"],
            "bank": ["IBPS PO", "IBPS Clerk", "SBI PO", "SBI Clerk", "RBI Grade B", "NABARD"],
            "railway": ["RRB NTPC", "RRB JE", "RRB ALP", "RRB Group D", "RRB SSE"],
            "state": ["TNPSC Group 1", "TNPSC Group 2", "MPSC", "KPSC", "UPPSC"],
        }
        
        exam_lower = exam_name.lower().strip()
        
        for category, specific_exams in generic_exams.items():
            if exam_lower == category or exam_lower == f"{category} exam":
                return True, category, specific_exams
        
        return False, None, None

    def _extract_duration_from_message(self, message):
        """Extract study duration from user's message if present."""
        import re
        
        message_lower = message.lower()
        
        # Pattern 1: "X hours" with timing
        pattern1 = r'(\d+)\s*(?:hours?|hrs?).*?(\d{1,2})\s*(?:am|pm).*?(?:to|-).*?(\d{1,2})\s*(?:am|pm)'
        match1 = re.search(pattern1, message_lower)
        if match1:
            return match1.group(1), "timing_found"
        
        # Pattern 2: Just hours
        pattern2 = r'(\d+)\s*(?:hours?|hrs?)'
        match2 = re.search(pattern2, message_lower)
        if match2:
            return match2.group(1), None
        
        # Pattern 3: Time range only
        pattern3 = r'(\d{1,2})\s*(?:am|pm).*?(?:to|-).*?(\d{1,2})\s*(?:am|pm)'
        match3 = re.search(pattern3, message_lower)
        if match3:
            return None, "timing_found"
        
        return None, None

    def _build_exam_syllabus(self, exam_name: str):
        """Return instruction to search for syllabus online"""
        return (
            f"INSTRUCTION: You must search online for the official '{exam_name}' syllabus.\n"
            f"Extract:\n"
            f"1. All major sections/subjects\n"
            f"2. Weightage/marks for each section\n"
            f"3. Important subtopics within each section\n"
            f"4. Previous year paper (PYP) frequently asked topics\n\n"
            f"Use this information to create plans."
        )

    def _get_language_reminder(self, profile):
        lang = self._get_language(profile)
        if lang == "tamil":
            return "Reminder: Always reply in Tanglish (Tamil + English mix) with friendly tone and emojis."
        if lang == "hindi":
            return "Reminder: Always reply in Hinglish (Hindi + English mix) with friendly tone and emojis."
        return f"Reminder: Always reply in {lang}+English mixed style with friendly tone and emojis."


    def _append_plan_chat(self, who, text):
        """Append message to plan chat box"""
        self.plan_chat_box.config(state=tk.NORMAL)
        
        if who == "user":
            self.plan_chat_box.insert("end", "\n")
            self.plan_chat_box.insert("end", "You", "user_tag")
            self.plan_chat_box.insert("end", "\n")
        elif who == "assistant":
            self.plan_chat_box.insert("end", "\n")
            self.plan_chat_box.insert("end", "AI Coach", "ai_tag")
            self.plan_chat_box.insert("end", "\n")
        
        # Configure tags
        self.plan_chat_box.tag_config("user_tag", foreground="#007aff", font=("Segoe UI", 10, "bold"))
        self.plan_chat_box.tag_config("ai_tag", foreground="#34c759", font=("Segoe UI", 10, "bold"))
        
        stripped = text.strip()
        emoji_only = stripped and all(ord(ch) >= 0x1F300 or ch.isspace() for ch in stripped)
        size = 36 if emoji_only else 20
        insert_with_emojis(self.plan_chat_box, text, self._emoji_images, size_override=size)
        self.plan_chat_box.insert("end", "\n")
        self.plan_chat_box.see("end")
        self.plan_chat_box.config(state=tk.DISABLED)

    def _append_query_chat(self, who, text):
        """Append message to query chat box with better styling"""
        self.query_chat_box.config(state=tk.NORMAL)
        
        if who == "user":
            self.query_chat_box.insert("end", "\n")
            self.query_chat_box.insert("end", "You", "user_tag")
            self.query_chat_box.insert("end", "\n")
        elif who == "assistant":
            self.query_chat_box.insert("end", "\n")
            self.query_chat_box.insert("end", "AI Coach", "ai_tag")
            self.query_chat_box.insert("end", "\n")
        elif who == "system":
            self.query_chat_box.insert("end", "\n")
        
        # Configure tags
        self.query_chat_box.tag_config("user_tag", foreground="#007aff", font=("Segoe UI", 11, "bold"))
        self.query_chat_box.tag_config("ai_tag", foreground="#34c759", font=("Segoe UI", 11, "bold"))
        
        stripped = text.strip()
        emoji_only = stripped and all(ord(ch) >= 0x1F300 or ch.isspace() for ch in stripped)
        size = 36 if emoji_only else 20
        insert_with_emojis(self.query_chat_box, text, self._emoji_images, size_override=size)
        self.query_chat_box.insert("end", "\n")
        self.query_chat_box.see("end")
        self.query_chat_box.config(state=tk.DISABLED)

    def _with_thread(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _init_client(self):
        if self.client:
            return
        self.api_key = get_secret("AI_API")
        if not self.api_key:
            raise RuntimeError("AI_API secret not found.")
        self.client = OpenAI(api_key=self.api_key)

    def _auto_start_plan_chat(self):
        """Auto-start plan creation chat"""
        if self.started:
            return
        self.started = True
        self._append_plan_chat("assistant", "Setting things up… ⚡")

        def worker():
            try:
                self._init_client()
                profile = self._load_profile()
                language = self._get_language(profile)
                exam_name = self._get_exam_name(profile)
                exam_date = self._load_exam_date()

                if language == "tamil":
                    sample = "Example: Hey bro 😎! Naan unaku study coach da 💪🔥"
                elif language == "hindi":
                    sample = "Example: Hey bhai 😄! Main tera study coach hoon 💪✨"
                else:
                    sample = "Example: Hey! Let's prep together 😎🔥"

                system_prompt = (
                    f"You are an AI study coach. Speak in {language}+English mix with emojis. "
                    f"{sample}"
                )

                exam_syllabus = self._build_exam_syllabus(exam_name)

                kickoff_user_msg = (
                    f"SYLLABUS:\n{exam_syllabus}\n\n"
                    f"PROFILE:\n{json.dumps(profile, ensure_ascii=False)}\n"
                    f"Exam Date: {exam_date}\n\n"
                    f"Speak in {language}+English with emojis. "
                    "DO NOT create plan yet. First chat with user, understand their needs, "
                    "then ask if they want to create a study plan."
                )

                self.plan_chat_history = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": kickoff_user_msg},
                ]
                
                reply = self._chat_complete(
                    self.plan_chat_history + [{"role":"system","content": self._get_language_reminder(profile)}],
                    session_name="plan_init",
                    purpose="initialization"
                )
                self.plan_chat_history.append({"role": "assistant", "content": reply})
                self._append_plan_chat("assistant", reply)
                self.plan_entry.focus_set()

            except Exception as e:
                self._append_plan_chat("assistant", f"Failed to start: {e}")

        self._with_thread(worker)

    def _auto_start_query_chat(self):
        """Auto-start general query chat"""
        # Initialize topic ID if not exists
        if not self.current_topic_id:
            self.current_topic_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        def worker():
            try:
                self._init_client()
                profile = self._load_profile()
                language = self._get_language(profile)
                exam_name = self._get_exam_name(profile)

                if language == "tamil":
                    greeting = "Vanakkam! 👋 Ena doubt iruku? Kelu bro! 😎🔥📚"
                elif language == "hindi":
                    greeting = "Namaste! 👋 Kya doubt hai? Pucho yaar! 😎🔥📚"
                else:
                    greeting = "Hello! 👋 What can I help you with today? 😎🔥📚"

                system_prompt = (
                    f"You are an AI study assistant. Help with exam tips, doubt clearing, and problem solving. "
                    f"User is preparing for {exam_name}. Speak in {language}+English mix with emojis. "
                    f"Be concise, helpful, and encouraging.\n\n"
                    f"IMPORTANT: Format all math in PLAIN TEXT using simple notation:\n"
                    f"- Use * for multiplication (5 * 3)\n"
                    f"- Use / for division (10 / 2)\n"
                    f"- Use ^ for powers (x^2)\n"
                    f"- Use sqrt() for square root (sqrt(25))\n"
                    f"- Show step-by-step calculations clearly\n"
                    f"- NEVER use LaTeX or special math symbols like \\text, \\frac, \\times\n"
                    f"- Write formulas in readable format: Speed = Distance / Time"
                )

                self.query_chat_history = [
                    {"role": "system", "content": system_prompt}
                ]
                
                self._append_query_chat("assistant", greeting)
                self.query_entry.focus_set()

            except Exception as e:
                self._append_query_chat("assistant", f"Failed to start: {e}")

        self._with_thread(worker)

    def _user_confirmed(self, text: str) -> bool:
        text = text.lower().strip()
        confirm_words = ["yes", "ok", "create", "start", "ஆம்", "சரி", "haan", "chalu", "begin", "ready", "plan", "schedule"]
        return any(word in text for word in confirm_words)

    def _ask_study_details(self):
        """Ask for study details only if not already provided."""
        duration_found = self._check_duration_in_history()
        if duration_found:
            profile = self._load_profile()
            lang = self._get_language(profile)
            
            msg = "✅ Perfect! Plan create panren... ⚡" if lang == "tamil" else "✅ Perfect! Creating your plan... ⚡"
            
            self._append_plan_chat("assistant", msg)
            self._auto_generate_plan()
            return
        
        profile = self._load_profile()
        lang = self._get_language(profile)
        
        if lang == "tamil":
            msg = "Seri bro! 💪 Evlo hours padika mudiyum and enna time la?\n\n📝 Example formats:\n  • 4 hours 6am to 10am\n  • 6am to 10am\n  • 3 hours\n\nType pannu! 📚⏰"
        elif lang == "hindi":
            msg = "Thik hai! 💪 Kitne hours aur kab?\n\n📝 Example formats:\n  • 4 hours 6am se 10am\n  • 6am se 10am\n  • 3 hours\n\nBatao! 📚⏰"
        else:
            msg = "Great! 💪 How many hours and when?\n\n📝 Example formats:\n  • 4 hours 6am to 10am\n  • 6am to 10am\n  • 3 hours\n\nTell me! 📚⏰"
        
        self._append_plan_chat("assistant", msg)
        self._waiting_for_hours = True
        
    def _ask_specific_exam_type(self, category, options):
        """Ask user to specify exact exam type."""
        profile = self._load_profile()
        lang = self._get_language(profile)
        
        options_text = "\n".join([f"  • {opt}" for opt in options])
        
        if lang == "tamil":
            msg = f"😎 '{category.upper()}' la evalo types iruku bro!\n\nExact ah enna exam ku prepare panringa?\n\n{options_text}\n\nType pannu! 👇"
        elif lang == "hindi":
            msg = f"😎 '{category.upper()}' mein bahut types hain bhai!\n\nExactly kaunsa exam ke liye prepare kar rahe ho?\n\n{options_text}\n\nBatao! 👇"
        else:
            msg = f"😎 I see you're preparing for {category.upper()}, but which specific exam?\n\nPlease choose:\n{options_text}\n\nType the exact exam name! 👇"
        
        self._append_plan_chat("assistant", msg)
        self._waiting_for_exam_type = True
        self._exam_category = category
        self._exam_options = options

    def _handle_exam_type_selection(self, user_msg):
        """Process user's exam type selection."""
        profile = self._load_profile()
        lang = self._get_language(profile)
        
        user_lower = user_msg.lower().strip()
        best_match = None
        
        for option in self._exam_options:
            if user_lower in option.lower() or option.lower() in user_lower:
                best_match = option
                break
        
        if not best_match:
            for option in self._exam_options:
                option_words = option.lower().split()
                if any(word in user_lower for word in option_words if len(word) > 2):
                    best_match = option
                    break
        
        if best_match:
            profile['exam_name'] = best_match
            PROFILE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding='utf-8')
            
            confirm_msg = f"✅ Super! {best_match} exam ku plan create panrom! 💪" if lang == "tamil" else f"✅ Perfect! Creating plan for {best_match}! 💪"
            
            self._append_plan_chat("assistant", confirm_msg)
            self._waiting_for_exam_type = False
            
            duration_found = self._check_duration_in_history()
            if duration_found:
                self._append_plan_chat("assistant", "Creating your plan now... ⚡")
                self._auto_generate_plan()
            else:
                self._ask_study_details()
        else:
            retry_msg = "🤔 Puriyala bro. List la irunthu select pannu please!" if lang == "tamil" else "🤔 I didn't catch that. Please choose from the list above!"
            self._append_plan_chat("assistant", retry_msg)

    def _check_duration_in_history(self):
        """Check if user already mentioned duration in chat history."""
        user_messages = [msg['content'] for msg in self.plan_chat_history if msg['role'] == 'user']
        
        for msg in user_messages[-3:]:
            hours, timing = self._extract_duration_from_message(msg)
            if hours or timing:
                self._parse_and_set_duration(msg)
                return True
        
        return False

    def _parse_and_set_duration(self, message):
        """Parse and set duration from message."""
        hours, timing = self._parse_study_info_with_ai(message)
        
        if hours and timing:
            self._study_hours = hours
            self._study_time = timing
        elif hours and not timing:
            profile = self._load_profile()
            lang = self._get_language(profile)
            
            time_msg = f"👍 {hours} hours... seri! Enna time la padikanum? (Example: 6am to 10am)" if lang == "tamil" else f"👍 Got the {hours} hours! When will you study? (e.g., 6am to 10am)"
            
            self._append_plan_chat("assistant", time_msg)
            self._waiting_for_hours = True
            self._study_hours = hours

    def _parse_study_info_with_ai(self, user_msg):
        """Enhanced parser with better handling of various formats."""
        parse_prompt = (
            f"Extract study hours and timing from: '{user_msg}'\n\n"
            "Return ONLY JSON: " + '{"hours": "4", "timing": "06:00-22:00"}\n\n'
            "Examples:\n"
            '- "4 hours 6am to 10am" → {"hours": "4", "timing": "06:00-22:00"}\n'
            '- "6am to 10am" → calculate hours → {"hours": "16", "timing": "06:00-22:00"}\n'
            '- "3 hours" → {"hours": "3", "timing": "not_specified"}\n\n'
            "Return ONLY JSON."
        )
        
        try:
            response = self._chat_complete([
                {"role": "system", "content": "Return only JSON."},
                {"role": "user", "content": parse_prompt}
            ], temperature=0.3, session_name="parse", purpose="time_parsing")
            
            response = response.strip()
            if "{" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                response = response[start:end]
            
            parsed = json.loads(response)
            hours = str(parsed.get("hours", ""))
            timing = parsed.get("timing", "")
            
            if timing == "not_specified" or not timing or "-" not in timing:
                if hours:
                    return hours, None
                return None, None
            
            if hours and timing and "-" in timing:
                return hours, timing
            
            return None, None
                
        except Exception as e:
            print(f"⚠ Parse failed: {e}")
            return None, None

    def _auto_generate_plan(self):
        profile = self._load_profile()
        lang = self._get_language(profile)
        
        if lang == "tamil":
            gen_msg = "Perfect bro! 📅 Syllabus search pandren, plans create aaguthu… ⚡✨"
        elif lang == "hindi":
            gen_msg = "Perfect! 📅 Syllabus search kar raha hoon, plans ban rahe hain… ⚡✨"
        else:
            gen_msg = "Perfect! 📅 Searching syllabus and creating plans… ⚡✨"
        
        self._append_plan_chat("assistant", gen_msg)

        exam_name = self._get_exam_name(profile)
        exam_date = self._load_exam_date()
        syllabus_instruction = self._build_exam_syllabus(exam_name)

        # Calculate available days
        try:
            from datetime import datetime
            exam_dt = datetime.fromisoformat(exam_date)
            days_left = (exam_dt - datetime.now()).days
        except:
            days_left = "unknown"

        instruction = f"""
🎯 PLAN CREATION TASK

EXAM: {exam_name}
EXAM DATE: {exam_date}
DAYS LEFT: {days_left}
STUDY TIME: {self._study_hours} hours per day ({self._study_time})

{syllabus_instruction}

═══════════════════════════════════════════════════════════════

📋 STEP-BY-STEP PROCESS:

STEP 1: SEARCH SYLLABUS
- Search online for "{exam_name}" official syllabus
- Extract ALL major sections/subjects
- Note weightage/marks for each section
- Identify high-weightage and PYP frequent topics

STEP 2: DETERMINE NUMBER OF PLANS
- Create ONE plan per major section
- Example: If exam has 5 sections → Create 5 plans
- Plan names = Section names (e.g., "General Intelligence", "Electrical Engineering")

STEP 3: DECIDE SESSION COUNT (IMPORTANT!)
- If study hours >= 10 hours/day:
  * Create detailed breakdown (15-25 sessions)
  * Include most subtopics
  
- If study hours 6-9 hours/day:
  * Create moderate breakdown (10-15 sessions)
  * Focus on high + medium weightage topics
  
- If study hours 3-5 hours/day:
  * Create minimal breakdown (5-10 sessions)
  * ONLY highest weightage + PYP repeated topics

STEP 4: TIME ALLOCATION RULES
- Allocate time based on weightage
  * 60% weightage topic → 60% of available time
  * 30% weightage topic → 30% of available time
  * 10% weightage topic → 10% of available time

- Session duration format: "HH:MM" (24-hour)
- Each session: ["Topic Name", "Start", "End", "Break"]

STEP 5: BREAK ALLOCATION
- 10 minutes break per 1 hour of study
- 30 minutes breakfast break (between 7:00-9:00 AM)
- 30 minutes lunch break (between 12:30-14:00)
- 30 minutes dinner break (between 19:00-21:00)
- Format: "HH:MM-HH:MM" or "No Break"

STEP 6: REVISION STRATEGY
- Include 1-2 revision sessions per plan
- Place revision at the end or between heavy topics
- Duration: 15-20% of total study time

STEP 7: SESSION NAMING
- Maximum 2 words per session name
- If topic split across breaks: Use "Topic 1", "Topic 2", etc.
- Examples: "Syllogism", "AC Circuits", "Reasoning 1", "Math 2"

═══════════════════════════════════════════════════════════════

📦 OUTPUT FORMAT (CRITICAL):

Return ONLY valid JSON. NO text before or after JSON.

{{
  "Plan_Name_1": [
    ["Session Name", "Start_Time", "End_Time", "Break_Time"],
    ["Topic 1", "07:00", "08:30", "08:30-08:40"],
    ["Topic 2", "08:40", "10:10", "10:10-10:40"],
    ["Revision", "10:40", "11:40", "No Break"]
  ],
  "Plan_Name_2": [
    ["Another Topic", "07:00", "09:00", "09:00-09:30"],
    ...
  ]
}}

═══════════════════════════════════════════════════════════════

⚠️ VALIDATION CHECKLIST:
✅ Number of plans = Number of major sections in syllabus
✅ Session count matches study hours (3-5h→fewer, 10+h→more)
✅ Time allocation matches weightage percentages
✅ Breaks follow rules (10min/hour + meal breaks)
✅ Session names ≤ 2 words
✅ All times in 24-hour format
✅ JSON is valid (no trailing commas, proper quotes)
✅ Timing fits within user's study window ({self._study_time})

═══════════════════════════════════════════════════════════════

NOW CREATE THE PLANS!
"""

        def worker():
            try:
                messages = self.plan_chat_history + [
                    {"role": "system", "content": instruction},
                ]
                
                # Use higher temperature for creative search, but structured output
                plan_reply = self._chat_complete(
                    messages,
                    temperature=0.7,
                    session_name="plan_generation",
                    purpose="create_plan",
                    model="gpt-4o-mini"  # Has web search capability
                )

                # Clean JSON
                plan_reply = plan_reply.strip()
                
                # Extract JSON from markdown code blocks if present
                if "```json" in plan_reply:
                    start = plan_reply.find("```json") + 7
                    end = plan_reply.find("```", start)
                    plan_reply = plan_reply[start:end].strip()
                elif "```" in plan_reply:
                    start = plan_reply.find("```") + 3
                    end = plan_reply.find("```", start)
                    plan_reply = plan_reply[start:end].strip()
                
                # Find JSON object
                if "{" in plan_reply:
                    start = plan_reply.find("{")
                    end = plan_reply.rfind("}") + 1
                    plan_reply = plan_reply[start:end]

                try:
                    parsed = json.loads(plan_reply)
                    if not isinstance(parsed, dict):
                        raise ValueError("Not a dict")
                    
                    # --- Load existing full structure from plans.json ---
                    try:
                        if PLANS_PATH.exists():
                            full = json.loads(PLANS_PATH.read_text(encoding="utf-8"))
                            if not isinstance(full, dict):
                                full = {}
                        else:
                            full = {}
                    except Exception:
                        full = {}

                    # --- Determine exam key (same idea as in StudyTimer.py) ---
                    exam_key = (exam_name or "").strip() or "__GLOBAL__"

                    # If file is in LEGACY flat format, wrap into current exam
                    if full:
                        sample_val = next(iter(full.values()))
                        if not isinstance(sample_val, dict):
                            # legacy: {plan_name: [...]}
                            full = {exam_key: full}

                    # --- Get or create dict for this exam ---
                    exam_plans = full.get(exam_key, {})
                    if not isinstance(exam_plans, dict):
                        exam_plans = {}

                    # Merge new plans for this exam
                    exam_plans.update(parsed)
                    full[exam_key] = exam_plans

                    # --- Save back to disk ---
                    PLANS_PATH.write_text(
                        json.dumps(full, indent=2, ensure_ascii=False),
                        encoding="utf-8"
                    )

                    # ✅ Register all sessions in all newly created plans
                    self._register_sessions_from_ai_plans(parsed)
                    
                    # Create explanation message
                    if lang == "tamil":
                        explanation_prompt = (
                            f"Plans create aayiduchu! 📝 Ippo explain pannu:\n"
                            f"1. Yen indha plans create panninga\n"
                            f"2. Time epdi allocate panninga\n"
                            f"3. Edha priority kudutha and why\n"
                            f"Short and friendly ah explain pannu with emojis!"
                        )
                    elif lang == "hindi":
                        explanation_prompt = (
                            f"Plans ban gaye! 📝 Ab explain karo:\n"
                            f"1. Ye plans kyun banaye\n"
                            f"2. Time kaise allocate kiya\n"
                            f"3. Kisko priority diya aur kyun\n"
                            f"Short aur friendly explain karo with emojis!"
                        )
                    else:
                        explanation_prompt = (
                            f"Plans created! 📝 Now explain:\n"
                            f"1. Why you created these plans\n"
                            f"2. How you allocated time\n"
                            f"3. Which topics got priority and why\n"
                            f"Keep it short and friendly with emojis!"
                        )
                    
                    # Get explanation
                    explain_messages = self.plan_chat_history + [
                        {"role": "assistant", "content": f"Created {len(parsed)} plans successfully."},
                        {"role": "user", "content": explanation_prompt}
                    ]
                    
                    explanation = self._chat_complete(
                        explain_messages,
                        temperature=0.7,
                        session_name="plan_explanation",
                        purpose="explanation"
                    )
                    
                    # ✅ Show explanation in chat
                    self._append_plan_chat("assistant", f"✅ {len(parsed)} plans created!\n\n{explanation}")
                    
                    # ✅ Refresh main app data
                    def refresh():
                        try:
                            if callable(self._on_plans_updated):
                                self._on_plans_updated()
                            if hasattr(self.master, 'refresh_token_usage_display'):
                                self.master.refresh_token_usage_display()
                        except Exception as e:
                            print(f"⚠ Refresh error: {e}")
                    
                    if hasattr(self, 'master') and self.master:
                        self.master.after(200, refresh)
                    else:
                        self.after(200, refresh)
                    
                    # ✅ Show success splash with options (after short delay)
                    plan_names = list(parsed.keys())
                    self.after(800, lambda: self._show_plan_created_splash(len(parsed), plan_names))

                except Exception as e:
                    RAW_FALLBACK.write_text(plan_reply, encoding="utf-8")
                    self._append_plan_chat("assistant", f"⚠ JSON parsing error: {e}\n\nRaw output saved to plans_raw_output.txt")
                    print(f"Raw AI response:\n{plan_reply}")

            except Exception as e:
                self._append_plan_chat("assistant", f"⚠ Generation failed: {e}")
                import traceback
                traceback.print_exc()

        self._with_thread(worker)
        
    def _register_sessions_from_ai_plans(self, plans_dict):
        """Register all sessions from AI-generated plans."""
        try:
            # Get current global day
            from config_paths import app_paths
            from datetime import date
            
            global_progress_file = Path(app_paths.appdata_dir) / "global_study_progress.json"
            
            # Get or create global day for each plan
            if global_progress_file.exists():
                global_data = json.loads(global_progress_file.read_text(encoding="utf-8"))
            else:
                global_data = {}
            
            session_registry_file = Path(app_paths.appdata_dir) / "session_registry.json"
            
            if session_registry_file.exists():
                registry_data = json.loads(session_registry_file.read_text(encoding="utf-8"))
            else:
                registry_data = {}
            
            # Process each plan
            for plan_name, sessions in plans_dict.items():
                # Get or create global day for this plan
                if plan_name not in global_data:
                    global_data[plan_name] = {
                        "global_day": 1,
                        "last_access_date": date.today().isoformat()
                    }
                
                current_global_day = global_data[plan_name]["global_day"]
                
                # Register each session in this plan
                for session in sessions:
                    if isinstance(session, list) and len(session) > 0:
                        session_name = session[0]  # First element is session name
                        
                        key = f"{plan_name}_{session_name}"
                        
                        # Only register if not already registered
                        if key not in registry_data:
                            registry_data[key] = {
                                "created_on_global_day": current_global_day,
                                "created_date": date.today().isoformat()
                            }
                            print(f"📝 AI: Registered {session_name} in {plan_name} on Global Day {current_global_day}")
            
            # Save both files
            global_progress_file.write_text(json.dumps(global_data, indent=2, ensure_ascii=False), encoding="utf-8")
            session_registry_file.write_text(json.dumps(registry_data, indent=2, ensure_ascii=False), encoding="utf-8")
            
            print(f"✅ Registered {len(registry_data)} total sessions across {len(plans_dict)} plans")
        
        except Exception as e:
            print(f"⚠ Error registering AI-generated sessions: {e}")
            import traceback
            traceback.print_exc()

    def _send_plan_message(self):
        """Handle plan tab messages with exam specificity and smart duration"""
        msg = self.plan_entry.get().strip()
        if not msg or not self.client:
            return
        self.plan_entry.delete(0, tk.END)
        self._append_plan_chat("user", msg)

        # Handle exam type selection
        if hasattr(self, '_waiting_for_exam_type') and self._waiting_for_exam_type:
            self._handle_exam_type_selection(msg)
            return

        # Handle study hours/timing
        if self._waiting_for_hours:
            profile = self._load_profile()
            lang = self._get_language(profile)
            
            parse_msg = "Wait pannu... ⚡" if lang == "tamil" else "Processing... ⚡"
            self._append_plan_chat("assistant", parse_msg)
            
            def parse_worker():
                hours, timing = self._parse_study_info_with_ai(msg)
                
                if hours and timing:
                    self._waiting_for_hours = False
                    self._study_hours = hours
                    self._study_time = timing
                    self._append_plan_chat("assistant", f"✅ {hours}h, {timing}! Creating...")
                    self._auto_generate_plan()
                else:
                    self._append_plan_chat("assistant", "Please clarify: like 4 hours 6am to 10am 😊")
            
            self._with_thread(parse_worker)
            return

        def worker():
            try:
                self.plan_chat_history.append({"role": "user", "content": msg})
                profile = self._load_profile()
                reply = self._chat_complete_stream(
                    self.plan_chat_history + [{"role":"system","content": self._get_language_reminder(profile)}],
                    self.plan_chat_box,
                    session_name="plan_chat",
                    purpose="conversation"
                )
                self.plan_chat_history.append({"role": "assistant", "content": reply})

                # ✅ NEW: Check exam specificity when user confirms
                if self._user_confirmed(msg) and not self._waiting_for_hours:
                    exam_name = self._get_exam_name(profile)
                    is_generic, category, options = self._is_generic_exam_name(exam_name)
                    
                    if is_generic:
                        self._ask_specific_exam_type(category, options)
                    else:
                        duration_found = self._check_duration_in_history()
                        if duration_found:
                            self._append_plan_chat("assistant", "Got it! Creating your plan now... ⚡")
                            self._auto_generate_plan()
                        else:
                            self._ask_study_details()

            except Exception as e:
                self._append_plan_chat("assistant", f"Error: {e}")
        self._with_thread(worker)

    def _send_query_message(self):
        """Handle query tab messages with optional image"""
        msg = self.query_entry.get().strip()
        
        # Remove placeholder text
        if msg == "Type your question here...":
            msg = ""
        
        if not msg and not self._current_image_data:
            return
        
        if not self.client:
            self._append_query_chat("assistant", "Please wait, initializing...")
            return
        
        # Auto-generate topic name from first message
        if self.current_topic_name == "New Chat" and msg:
            self.current_topic_name = msg[:30] + "..." if len(msg) > 30 else msg
            self.topic_label.config(text=f"💬 {self.current_topic_name}")
            
        self.query_entry.delete(0, tk.END)
        
        if msg:
            self._append_query_chat("user", msg)

        def worker():
            try:
                # Build message content
                if self._current_image_data:
                    # Vision API format
                    content = []
                    if msg:
                        content.append({"type": "text", "text": msg})
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": self._current_image_data}
                    })
                    user_message = {"role": "user", "content": content}
                else:
                    user_message = {"role": "user", "content": msg}

                self.query_chat_history.append(user_message)
                
                # Use vision model if image present
                model = "gpt-4o-mini"
                
                reply = self._chat_complete_stream(
                    self.query_chat_history,
                    self.query_chat_box,
                    session_name="query_chat",
                    purpose="query_resolution",
                    model=model
                )
                
                self.query_chat_history.append({"role": "assistant", "content": reply})
                
                # Auto-save after each exchange
                self._save_current_topic()
                
                # Clear image after sending
                if self._current_image_data:
                    self._remove_image()

            except Exception as e:
                self._append_query_chat("assistant", f"Error: {e}")
                print(f"Query error: {e}")
                
        self._with_thread(worker)
        
    def _chat_complete_stream(self, messages, chat_box, temperature=0.7, session_name="", purpose="chat", model="gpt-4o-mini"):
        """Stream chat completion with letter-by-letter display + formatting"""
        try:
            # Start streaming response
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=True
            )
            
            full_response = ""
            buffer = ""
            
            # Add "AI Coach" header first
            self.after(0, lambda: self._start_streaming_message(chat_box))
            
            import time
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_response += token
                    buffer += token
                    
                    # Process buffer when we have enough characters or newlines
                    if len(buffer) >= 3 or '\n' in buffer:  # Changed from 5 to 3
                        self.after(0, lambda b=buffer: self._append_streaming_text(chat_box, b))
                        buffer = ""
                        time.sleep(0.015)
            
            # Flush remaining buffer
            if buffer:
                self.after(0, lambda b=buffer: self._append_streaming_text(chat_box, b))
            
            # Finalize the message
            self.after(0, lambda: self._finalize_streaming_message(chat_box))
            
            # Track tokens (approximate for streaming)
            from token_tracker import track_completion
            track_completion(
                model=model,
                prompt_tokens=sum(len(str(m.get('content', '')).split()) for m in messages),
                completion_tokens=len(full_response.split()),
                session_name=session_name,
                purpose=purpose
            )
            
            return full_response
            
        except Exception as e:
            print(f"Streaming error: {e}")
            # Fallback to non-streaming
            return self._chat_complete(messages, temperature, session_name, purpose, model)

    def _start_streaming_message(self, chat_box):
        """Start a new streaming message with AI header"""
        chat_box.config(state=tk.NORMAL)
        chat_box.insert("end", "\n")
        chat_box.insert("end", "AI Coach", "ai_tag")
        chat_box.insert("end", "\n")
        
        # Create streaming buffer attribute
        if not hasattr(self, '_stream_buffer'):
            self._stream_buffer = {
                'text': '',
                'in_bold': False,
                'bold_buffer': ''
            }
        
        chat_box.config(state=tk.DISABLED)

    def _append_streaming_text(self, chat_box, text):
        """Append text chunk with emoji/bold detection during streaming"""
        chat_box.config(state=tk.NORMAL)
        
        # Process text character by character for formatting
        i = 0
        while i < len(text):
            char = text[i]
            
            # Check for emoji
            if ord(char) >= 0x1F300:
                img = render_emoji_photoimage(char, size=16)
                self._emoji_images.append(img)
                chat_box.image_create("end", image=img)
                i += 1
                continue
            
            # Check for bold markers (**)
            if text[i:i+2] == '**':
                self._stream_buffer['in_bold'] = not self._stream_buffer['in_bold']
                i += 2
                continue
            
            # Insert character
            if self._stream_buffer['in_bold']:
                chat_box.insert("end", char, "bold")
            else:
                chat_box.insert("end", char)
            
            i += 1
        
        chat_box.see("end")
        chat_box.config(state=tk.DISABLED)
        chat_box.update_idletasks()

    def _finalize_streaming_message(self, chat_box):
        """Finalize streaming message"""
        chat_box.config(state=tk.NORMAL)
        chat_box.insert("end", "\n")
        chat_box.config(state=tk.DISABLED)
        
        # Reset buffer
        if hasattr(self, '_stream_buffer'):
            self._stream_buffer = {
                'text': '',
                'in_bold': False,
                'bold_buffer': ''
            }

    def _chat_complete(self, messages, temperature=0.7, session_name="", purpose="chat", model="gpt-4o-mini"):
        """Wrapper for chat completion with tracking"""
        from token_tracker import chat_complete_with_tracking
        
        return chat_complete_with_tracking(
            self.client,
            messages,
            model=model,
            temperature=temperature,
            session_name=session_name,
            purpose=purpose
        )

    def destroy(self):
        """Save before closing - DON'T trigger plan refresh"""
        if self.current_topic_id and len(self.query_chat_history) > 0:
            self._save_current_topic()
        
        # Disable callback to prevent plan switching
        self._on_plans_updated = None
        
        super().destroy()


def open_ai_chat_dialog(master, on_plans_updated=None):
    """Open the enhanced AI chat dialog"""
    dlg = AIChatDialog(master, on_plans_updated=on_plans_updated)
    master.wait_window(dlg)
    
    # Force reload after close
    print("🔄 Dialog closed, reloading...")
    if on_plans_updated and callable(on_plans_updated):
        try:
            on_plans_updated()
        except Exception as e:
            print(f"⚠ Reload error: {e}")