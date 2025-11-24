# ============================================
# TOKEN USAGE TRACKER (CLOUD VERSION)
# Now with Google Sheets quota management
# ============================================

import json
import tiktoken
import tkinter as tk
from pathlib import Path
from datetime import datetime, date
from config_paths import app_paths
from token_manager import check_token_balance, deduct_tokens, get_token_manager

# ============================================
# PART 1: Token Calculation Functions
# ============================================

def count_tokens(text, model="gpt-4o-mini"):
    """Count tokens exactly like OpenAI API."""
    try:
        if model.startswith("gpt-4"):
            encoding = tiktoken.encoding_for_model("gpt-4")
        elif model.startswith("gpt-3.5"):
            encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        else:
            encoding = tiktoken.get_encoding("cl100k_base")
        
        tokens = encoding.encode(text)
        return len(tokens)
    except Exception as e:
        print(f"⚠ Token counting error: {e}")
        return len(text) // 4


def count_message_tokens(messages, model="gpt-4o-mini"):
    """Count tokens in messages array exactly like OpenAI API."""
    try:
        encoding = tiktoken.encoding_for_model("gpt-4")
        num_tokens = 0
        
        for message in messages:
            num_tokens += 4
            for key, value in message.items():
                num_tokens += len(encoding.encode(str(value)))
                if key == "name":
                    num_tokens += -1
        
        num_tokens += 2
        return num_tokens
    except Exception as e:
        print(f"⚠ Message token counting error: {e}")
        total_text = " ".join([msg.get("content", "") for msg in messages])
        return count_tokens(total_text, model)


# ============================================
# PART 2: Usage Tracking & Storage
# ============================================

_refresh_callback = None

def set_refresh_callback(callback_func):
    """Set a callback function to be called after token usage is saved."""
    global _refresh_callback
    _refresh_callback = callback_func
    print("✅ Token refresh callback registered")


def save_token_usage(prompt_tokens, completion_tokens, total_tokens, cost=0.0, 
                     session_name="", purpose=""):
    """Save token usage to local tracking file (for stats only)."""
    usage_file = Path(app_paths.appdata_dir) / "token_usage.json"
    
    try:
        if usage_file.exists():
            usage_data = json.loads(usage_file.read_text(encoding="utf-8"))
        else:
            usage_data = {
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "history": []
            }
        
        usage_data["total_prompt_tokens"] += prompt_tokens
        usage_data["total_completion_tokens"] += completion_tokens
        usage_data["total_tokens"] += total_tokens
        usage_data["total_cost"] += cost
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "session_name": session_name,
            "purpose": purpose,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost": cost
        }
        usage_data["history"].append(entry)
        
        if len(usage_data["history"]) > 1000:
            usage_data["history"] = usage_data["history"][-1000:]
        
        usage_file.write_text(json.dumps(usage_data, indent=2, ensure_ascii=False), 
                            encoding="utf-8")
        
        print(f"💰 Token usage saved: {total_tokens} tokens (${cost:.4f})")
        
        # Auto-refresh callback
        if _refresh_callback:
            try:
                _refresh_callback()
                print("✅ Token display auto-refreshed")
            except Exception as e:
                print(f"⚠ Auto-refresh callback error: {e}")
        
    except Exception as e:
        print(f"⚠ Error saving token usage: {e}")


def get_token_usage_stats():
    """Get local token usage statistics."""
    usage_file = Path(app_paths.appdata_dir) / "token_usage.json"
    
    if not usage_file.exists():
        return {
            "total_tokens": 0,
            "total_cost": 0.0,
            "today_tokens": 0,
            "today_cost": 0.0,
            "this_month_tokens": 0,
            "this_month_cost": 0.0
        }
    
    try:
        usage_data = json.loads(usage_file.read_text(encoding="utf-8"))
        today = date.today().isoformat()
        this_month = date.today().strftime("%Y-%m")
        
        today_tokens = 0
        today_cost = 0.0
        month_tokens = 0
        month_cost = 0.0
        
        for entry in usage_data.get("history", []):
            entry_date = entry.get("date", "")
            
            if entry_date == today:
                today_tokens += entry.get("total_tokens", 0)
                today_cost += entry.get("cost", 0.0)
            
            if entry_date.startswith(this_month):
                month_tokens += entry.get("total_tokens", 0)
                month_cost += entry.get("cost", 0.0)
        
        return {
            "total_tokens": usage_data.get("total_tokens", 0),
            "total_cost": usage_data.get("total_cost", 0.0),
            "today_tokens": today_tokens,
            "today_cost": today_cost,
            "this_month_tokens": month_tokens,
            "this_month_cost": month_cost
        }
        
    except Exception as e:
        print(f"⚠ Error getting token stats: {e}")
        return {
            "total_tokens": 0,
            "total_cost": 0.0,
            "today_tokens": 0,
            "today_cost": 0.0,
            "this_month_tokens": 0,
            "this_month_cost": 0.0
        }


def calculate_cost(prompt_tokens, completion_tokens, model="gpt-4o-mini"):
    """Calculate cost based on OpenAI pricing."""
    pricing = {
        "gpt-4o-mini": {
            "input": 0.150 / 1_000_000,
            "output": 0.600 / 1_000_000
        },
        "gpt-4o": {
            "input": 2.50 / 1_000_000,
            "output": 10.00 / 1_000_000
        },
        "gpt-4-turbo": {
            "input": 10.00 / 1_000_000,
            "output": 30.00 / 1_000_000
        },
        "gpt-3.5-turbo": {
            "input": 0.50 / 1_000_000,
            "output": 1.50 / 1_000_000
        }
    }
    
    model_pricing = pricing.get(model, pricing["gpt-4o-mini"])
    input_cost = prompt_tokens * model_pricing["input"]
    output_cost = completion_tokens * model_pricing["output"]
    
    return input_cost + output_cost


# ============================================
# PART 3: Modified OpenAI Call with Quota Check
# ============================================

def chat_complete_with_tracking(client, messages, model="gpt-4o-mini", temperature=0.7, 
                                session_name="", purpose=""):
    """
    Wrapper for OpenAI API call with cloud quota management.
    
    🔥 NEW: Checks cloud balance BEFORE calling API
    🔥 NEW: Deducts from cloud balance AFTER successful call
    """
    
    # Estimate tokens before call
    estimated_tokens = count_message_tokens(messages, model)
    estimated_tokens += 500  # Add buffer for response
    
    # 🔥 CHECK CLOUD BALANCE FIRST
    has_balance, balance_info = check_token_balance(estimated_tokens)
    
    if not has_balance:
        current_balance = balance_info.get("balance", 0)
        raise InsufficientTokensError(
            f"Insufficient tokens! You need {estimated_tokens:,} but have {current_balance:,}.\n"
            f"Please purchase more tokens to continue using AI features."
        )
    
    try:
        # Call OpenAI API
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature
        )
        
        # Get actual usage from response
        usage = response.usage
        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens
        
        # Calculate cost
        cost = calculate_cost(prompt_tokens, completion_tokens, model)
        
        # Save to local stats
        save_token_usage(prompt_tokens, completion_tokens, total_tokens, 
                        cost, session_name, purpose)
        
        # 🔥 DEDUCT FROM CLOUD BALANCE
        deduct_success = deduct_tokens(total_tokens)
        
        if not deduct_success:
            print("⚠ Warning: Failed to deduct tokens from cloud balance")
        
        # Return response content
        return response.choices[0].message.content.strip()
        
    except InsufficientTokensError:
        raise  # Re-raise quota errors
    except Exception as e:
        print(f"⚠ API call error: {e}")
        raise


class InsufficientTokensError(Exception):
    """Raised when user doesn't have enough tokens."""
    pass


# ============================================
# PART 4: UI Component - Enhanced Token Display
# ============================================

def create_token_usage_widget(parent_frame):
    """Create enhanced widget with cloud balance."""
    import tkinter as tk
    
    stats = get_token_usage_stats()
    
    # Get cloud balance
    tm = get_token_manager()
    balance_info = tm.get_balance()
    cloud_balance = balance_info.get("balance", 0)
    
    # Container frame
    token_frame = tk.Frame(parent_frame, bg="#34495e", relief="flat")
    
    # Title
    tk.Label(token_frame, 
             text="💰 Token Usage",
             font=("Segoe UI", 9, "bold"),
             bg="#34495e", fg="white").pack(side="left", padx=(8, 15))
    
    # Cloud balance (MOST IMPORTANT)
    balance_color = "#27ae60" if cloud_balance > 100000 else "#f39c12" if cloud_balance > 10000 else "#e74c3c"
    tk.Label(token_frame,
             text=f"Balance: {cloud_balance:,}",
             font=("Segoe UI", 9, "bold"),
             bg="#34495e", fg=balance_color).pack(side="left", padx=5)
    
    # Today's usage
    today_color = "#bdc3c7"
    tk.Label(token_frame,
             text=f"Today: {stats['today_tokens']:,}",
             font=("Segoe UI", 8),
             bg="#34495e", fg=today_color).pack(side="left", padx=5)
    
    # Month usage
    tk.Label(token_frame,
             text=f"Month: {stats['this_month_tokens']:,}",
             font=("Segoe UI", 8),
             bg="#34495e", fg="#95a5a6").pack(side="left", padx=(5, 8))
    
    return token_frame


def refresh_token_display(token_frame):
    """Refresh the token display widget with latest stats."""
    if not token_frame:
        return
    
    try:
        if not token_frame.winfo_exists():
            return
    except:
        return
    
    stats = get_token_usage_stats()
    
    # Get cloud balance
    tm = get_token_manager()
    balance_info = tm.get_balance()
    cloud_balance = balance_info.get("balance", 0)
    
    # Destroy all child widgets
    for widget in token_frame.winfo_children():
        try:
            widget.destroy()
        except:
            pass
    
    # Recreate with fresh data
    tk.Label(token_frame, 
             text="💰 Token Usage",
             font=("Segoe UI", 9, "bold"),
             bg="#34495e", fg="white").pack(side="left", padx=(8, 15))
    
    # Cloud balance with color coding
    if cloud_balance > 100000:
        balance_color = "#27ae60"  # Green
    elif cloud_balance > 10000:
        balance_color = "#f39c12"  # Yellow
    else:
        balance_color = "#e74c3c"  # Red
    
    tk.Label(token_frame,
             text=f"Balance: {cloud_balance:,}",
             font=("Segoe UI", 9, "bold"),
             bg="#34495e", fg=balance_color).pack(side="left", padx=5)
    
    # Today's usage
    tk.Label(token_frame,
             text=f"Today: {stats['today_tokens']:,}",
             font=("Segoe UI", 8),
             bg="#34495e", fg="#bdc3c7").pack(side="left", padx=5)
    
    # Month usage
    tk.Label(token_frame,
             text=f"Month: {stats['this_month_tokens']:,}",
             font=("Segoe UI", 8),
             bg="#34495e", fg="#95a5a6").pack(side="left", padx=(5, 8))
    
    # Force update
    token_frame.update_idletasks()
    
    print(f"✅ Token display refreshed - Balance: {cloud_balance:,} tokens")