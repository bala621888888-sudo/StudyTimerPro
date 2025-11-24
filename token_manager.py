# ============================================
# CLOUD TOKEN MANAGER - FIXED VERSION
# Manages token quotas via Google Sheets
# WITH DUPLICATE ORDER PREVENTION
# ============================================

import json
import platform
import uuid
import hashlib
import os
from datetime import datetime
from secrets_util import get_secret, get_encrypted_gspread_client

# Constants
TRIAL_QUOTA = 1_000_000  # 1M tokens free
TOKEN_SHEET_NAME = "api_data_track"
TRANSACTION_SHEET_NAME = "token_transactions"  # 🔥 NEW: Transaction history sheet

# Token packages (price in rupees)
TOKEN_PACKAGES = {
    "basic": {"tokens": 1_000_000, "price": 1, "label": "1M tokens - ₹50"},
    "standard": {"tokens": 4_000_000, "price": 150, "label": "4M tokens - ₹150"},
    "premium": {"tokens": 20_000_000, "price": 500, "label": "20M tokens - ₹500"}
}

class TokenManager:
    def __init__(self):
        self.fingerprint = self._get_machine_fingerprint()
        self.username = self._get_username()
        self.gc = get_encrypted_gspread_client()
        self.sheet_id = get_secret("GOOGLE_SHEET_ID")
        self.worksheet = None
        self.transaction_worksheet = None  # 🔥 NEW: For transaction history
        self._init_worksheet()
        self._init_transaction_worksheet()  # 🔥 NEW
    
    def _get_machine_fingerprint(self):
        """Generate unique machine fingerprint."""
        try:
            identifiers = [
                platform.system(),
                platform.machine(),
                str(uuid.getnode())
            ]
            combined = '|'.join(str(i) for i in identifiers if i)
            return hashlib.sha256(combined.encode()).hexdigest()[:16]
        except:
            return "unknown_machine"
    
    def _get_username(self):
        """Get computer username."""
        try:
            return os.getlogin()
        except:
            return os.environ.get('USERNAME') or os.environ.get('USER') or "Unknown"
    
    def _init_worksheet(self):
        """Initialize or create the api_data_track worksheet."""
        if not self.gc or not self.sheet_id:
            print("⚠ Cannot init token worksheet - no credentials")
            return False
        
        try:
            sheet = self.gc.open_by_key(self.sheet_id)
            
            # Try to get existing worksheet
            try:
                self.worksheet = sheet.worksheet(TOKEN_SHEET_NAME)
                print(f"✅ Found existing worksheet: {TOKEN_SHEET_NAME}")
            except:
                # Create new worksheet with headers
                self.worksheet = sheet.add_worksheet(
                    title=TOKEN_SHEET_NAME, 
                    rows=1000, 
                    cols=8
                )
                
                # Set headers
                headers = [
                    "Machine Fingerprint",
                    "Name", 
                    "Trial Quota",
                    "Purchased Tokens",
                    "Amount Paid (₹)",
                    "Date of Payment",
                    "Balance Tokens",
                    "Total Used Tokens"
                ]
                self.worksheet.update('A1:H1', [headers])
                print(f"✅ Created new worksheet: {TOKEN_SHEET_NAME}")
            
            return True
            
        except Exception as e:
            print(f"⚠ Worksheet init error: {e}")
            return False
    
    # 🔥 NEW METHOD: Initialize transaction history worksheet
    def _init_transaction_worksheet(self):
        """Initialize or create the token_transactions worksheet for tracking all purchases."""
        if not self.gc or not self.sheet_id:
            print("⚠ Cannot init transaction worksheet - no credentials")
            return False
        
        try:
            sheet = self.gc.open_by_key(self.sheet_id)
            
            # Try to get existing worksheet
            try:
                self.transaction_worksheet = sheet.worksheet(TRANSACTION_SHEET_NAME)
                print(f"✅ Found existing transaction worksheet: {TRANSACTION_SHEET_NAME}")
            except:
                # Create new worksheet with headers
                self.transaction_worksheet = sheet.add_worksheet(
                    title=TRANSACTION_SHEET_NAME, 
                    rows=10000, 
                    cols=8
                )
                
                # Set headers
                headers = [
                    "Timestamp",
                    "Machine Fingerprint",
                    "Username",
                    "Order ID",  # 🔥 CRITICAL: Razorpay order ID
                    "Tokens Added",
                    "Amount Paid (₹)",
                    "Package Type",
                    "Status"
                ]
                self.transaction_worksheet.update('A1:H1', [headers])
                print(f"✅ Created new transaction worksheet: {TRANSACTION_SHEET_NAME}")
            
            return True
            
        except Exception as e:
            print(f"⚠ Transaction worksheet init error: {e}")
            return False
    
    # 🔥 NEW METHOD: Check if order already processed
    def _is_order_processed(self, order_id):
        """Check if this order_id has already been processed."""
        if not self.transaction_worksheet or not order_id:
            return False
        
        try:
            # Get all order IDs from column D (Order ID column)
            all_order_ids = self.transaction_worksheet.col_values(4)  # Column D
            
            # Check if this order_id exists (skip header)
            if order_id in all_order_ids[1:]:
                print(f"⚠️ DUPLICATE DETECTED: Order {order_id} already processed!")
                return True
            
            return False
            
        except Exception as e:
            print(f"⚠ Error checking order: {e}")
            # On error, assume not processed (safer to add tokens than fail)
            return False
    
    # 🔥 NEW METHOD: Record transaction
    def _record_transaction(self, order_id, tokens, amount_paid, package_type="manual"):
        """Record a transaction in the transaction history sheet."""
        if not self.transaction_worksheet:
            print("⚠ No transaction worksheet - cannot record")
            return False
        
        try:
            transaction_row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.fingerprint,
                self.username,
                order_id or "N/A",
                tokens,
                amount_paid,
                package_type,
                "completed"
            ]
            
            self.transaction_worksheet.append_row(transaction_row)
            print(f"✅ Transaction recorded: Order {order_id}, {tokens:,} tokens")
            return True
            
        except Exception as e:
            print(f"⚠ Error recording transaction: {e}")
            return False
    
    def _find_user_row(self):
        """Find the row number for current machine, or return None."""
        if not self.worksheet:
            return None
        
        try:
            all_fingerprints = self.worksheet.col_values(1)  # Column A
            
            for idx, fp in enumerate(all_fingerprints[1:], start=2):  # Skip header
                if fp == self.fingerprint:
                    return idx
            
            return None
            
        except Exception as e:
            print(f"⚠ Error finding user row: {e}")
            return None
    
    def _create_user_row(self):
        """Create a new row for this user with trial quota."""
        if not self.worksheet:
            return False
        
        try:
            new_row = [
                self.fingerprint,
                self.username,
                TRIAL_QUOTA,      # Trial quota
                0,                # Purchased tokens
                0,                # Amount paid
                "",               # Date of payment
                TRIAL_QUOTA,      # Balance tokens (starts with trial)
                0                 # Total used tokens
            ]
            
            self.worksheet.append_row(new_row)
            print(f"✅ Created new user with {TRIAL_QUOTA:,} trial tokens")
            return True
            
        except Exception as e:
            print(f"⚠ Error creating user row: {e}")
            return False
    
    def get_balance(self):
        """
        Get current token balance for this machine.
        Returns dict with: balance, trial_quota, purchased, used
        """
        if not self.worksheet:
            print("⚠ No worksheet - returning offline fallback")
            return {
                "balance": 0,
                "trial_quota": 0,
                "purchased": 0,
                "used": 0,
                "error": "No connection to token database"
            }
        
        try:
            row_num = self._find_user_row()
            
            # New user - create with trial quota
            if row_num is None:
                self._create_user_row()
                return {
                    "balance": TRIAL_QUOTA,
                    "trial_quota": TRIAL_QUOTA,
                    "purchased": 0,
                    "used": 0
                }
            
            # Existing user - fetch data
            row_data = self.worksheet.row_values(row_num)
            
            return {
                "balance": int(row_data[6]) if len(row_data) > 6 and row_data[6] else 0,
                "trial_quota": int(row_data[2]) if len(row_data) > 2 and row_data[2] else 0,
                "purchased": int(row_data[3]) if len(row_data) > 3 and row_data[3] else 0,
                "used": int(row_data[7]) if len(row_data) > 7 and row_data[7] else 0
            }
            
        except Exception as e:
            print(f"⚠ Error getting balance: {e}")
            return {
                "balance": 0,
                "trial_quota": 0,
                "purchased": 0,
                "used": 0,
                "error": str(e)
            }
    
    def deduct_tokens(self, tokens_used):
        """
        Deduct tokens from balance after API call.
        Returns True if successful, False if insufficient balance.
        """
        if not self.worksheet:
            print("⚠ No worksheet - cannot deduct tokens")
            return False
        
        try:
            row_num = self._find_user_row()
            
            if row_num is None:
                print("⚠ User not found in sheet")
                return False
            
            row_data = self.worksheet.row_values(row_num)
            
            current_balance = int(row_data[6]) if len(row_data) > 6 and row_data[6] else 0
            current_used = int(row_data[7]) if len(row_data) > 7 and row_data[7] else 0
            
            # Check if enough balance
            if current_balance < tokens_used:
                print(f"⚠ Insufficient balance: {current_balance} < {tokens_used}")
                return False
            
            # Update balance and used tokens
            new_balance = current_balance - tokens_used
            new_used = current_used + tokens_used
            
            self.worksheet.update_cell(row_num, 7, new_balance)      # Column G: Balance
            self.worksheet.update_cell(row_num, 8, new_used)         # Column H: Used
            
            print(f"✅ Deducted {tokens_used:,} tokens. New balance: {new_balance:,}")
            return True
            
        except Exception as e:
            print(f"⚠ Error deducting tokens: {e}")
            return False
    
    # 🔥 FIXED METHOD: Add duplicate prevention
    def add_purchased_tokens(self, tokens, amount_paid, order_id=None, package_type="manual"):
        """
        Add purchased tokens to user's balance.
        Called after successful payment.
        
        Args:
            tokens: Number of tokens to add
            amount_paid: Amount paid in rupees
            order_id: Razorpay order ID (CRITICAL for duplicate prevention)
            package_type: Type of package purchased
        
        Returns:
            True if successful, False if failed or duplicate
        """
        if not self.worksheet:
            print("⚠ No worksheet - cannot add tokens")
            return False
        
        # 🔥 STEP 1: Check for duplicate order
        if order_id and self._is_order_processed(order_id):
            print(f"⚠️ DUPLICATE ORDER REJECTED: {order_id}")
            return False
        
        try:
            row_num = self._find_user_row()
            
            if row_num is None:
                print("⚠ User not found in sheet")
                return False
            
            row_data = self.worksheet.row_values(row_num)
            
            current_purchased = int(row_data[3]) if len(row_data) > 3 and row_data[3] else 0
            current_amount = float(row_data[4]) if len(row_data) > 4 and row_data[4] else 0.0
            current_balance = int(row_data[6]) if len(row_data) > 6 and row_data[6] else 0
            
            # Calculate new values
            new_purchased = current_purchased + tokens
            new_amount = current_amount + amount_paid
            new_balance = current_balance + tokens
            payment_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 🔥 STEP 2: Record transaction FIRST (before updating balance)
            transaction_recorded = self._record_transaction(
                order_id=order_id,
                tokens=tokens,
                amount_paid=amount_paid,
                package_type=package_type
            )
            
            if not transaction_recorded:
                print("⚠️ Failed to record transaction - aborting token addition")
                return False
            
            # 🔥 STEP 3: Update user balance (only after transaction recorded)
            self.worksheet.update_cell(row_num, 4, new_purchased)    # Column D: Purchased
            self.worksheet.update_cell(row_num, 5, new_amount)       # Column E: Amount Paid
            self.worksheet.update_cell(row_num, 6, payment_date)     # Column F: Date
            self.worksheet.update_cell(row_num, 7, new_balance)      # Column G: Balance
            
            print(f"✅ Added {tokens:,} tokens. New balance: {new_balance:,}")
            print(f"📊 Order ID: {order_id}")
            return True
            
        except Exception as e:
            print(f"⚠ Error adding tokens: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def has_sufficient_balance(self, tokens_needed):
        """Check if user has enough tokens."""
        balance_info = self.get_balance()
        return balance_info.get("balance", 0) >= tokens_needed
    
    def get_balance_percentage(self):
        """Get balance as percentage of total (trial + purchased)."""
        balance_info = self.get_balance()
        balance = balance_info.get("balance", 0)
        total = balance_info.get("trial_quota", 0) + balance_info.get("purchased", 0)
        
        if total == 0:
            return 0
        
        return (balance / total) * 100
    
    # 🔥 NEW METHOD: Get transaction history for this user
    def get_transaction_history(self, limit=50):
        """Get recent transaction history for this user."""
        if not self.transaction_worksheet:
            print("⚠ No transaction worksheet")
            return []
        
        try:
            # Get all rows
            all_rows = self.transaction_worksheet.get_all_values()
            
            if len(all_rows) <= 1:  # Only header
                return []
            
            # Filter for this user's fingerprint
            user_transactions = []
            for row in all_rows[1:]:  # Skip header
                if len(row) >= 8 and row[1] == self.fingerprint:
                    user_transactions.append({
                        "timestamp": row[0],
                        "fingerprint": row[1],
                        "username": row[2],
                        "order_id": row[3],
                        "tokens": int(row[4]) if row[4] else 0,
                        "amount_paid": float(row[5]) if row[5] else 0.0,
                        "package_type": row[6],
                        "status": row[7]
                    })
            
            # Return most recent first, limited
            return user_transactions[-limit:][::-1]
            
        except Exception as e:
            print(f"⚠ Error getting transaction history: {e}")
            return []


# ============================================
# GLOBAL INSTANCE
# ============================================

_token_manager = None

def get_token_manager():
    """Get singleton instance of TokenManager."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def check_token_balance(tokens_needed):
    """Check if user has enough tokens. Returns (has_balance, balance_info)."""
    tm = get_token_manager()
    balance_info = tm.get_balance()
    has_balance = balance_info.get("balance", 0) >= tokens_needed
    return has_balance, balance_info

def deduct_tokens(tokens_used):
    """Deduct tokens after API call."""
    tm = get_token_manager()
    return tm.deduct_tokens(tokens_used)

# 🔥 FIXED FUNCTION: Now accepts order_id
def add_tokens(tokens, amount_paid, order_id=None, package_type="manual"):
    """
    Add purchased tokens with duplicate prevention.
    
    Args:
        tokens: Number of tokens to add
        amount_paid: Amount paid in rupees
        order_id: Razorpay order ID (REQUIRED for duplicate prevention)
        package_type: Package type identifier
    
    Returns:
        True if successful, False if duplicate or failed
    """
    tm = get_token_manager()
    return tm.add_purchased_tokens(tokens, amount_paid, order_id, package_type)


# 🔥 NEW FUNCTION: Get transaction history
def get_transaction_history(limit=50):
    """Get transaction history for current user."""
    tm = get_token_manager()
    return tm.get_transaction_history(limit)