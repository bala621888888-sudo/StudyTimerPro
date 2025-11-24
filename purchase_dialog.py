# ============================================
# TOKEN PURCHASE DIALOG - FIXED VERSION
# ============================================

import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import razorpay
from secrets_util import get_secret
from token_manager import TOKEN_PACKAGES, add_tokens, get_token_manager

class PurchaseDialog:
    def __init__(self, parent, current_balance):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("💰 Purchase Tokens")
        self.dialog.geometry("500x600")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.current_balance = current_balance
        self.selected_package = None
        self.poll_count = 0  # 🔥 ADD COUNTER
        self.max_polls = 40  # 🔥 2 minutes of polling (40 * 3 sec)
        
        # Initialize Razorpay
        try:
            self.razorpay_key_id = get_secret("RAZORPAY_KEY_ID")
            self.razorpay_key_secret = get_secret("RAZORPAY_KEY_SECRET")
            self.client = razorpay.Client(auth=(self.razorpay_key_id, self.razorpay_key_secret))
        except Exception as e:
            print(f"⚠ Razorpay init error: {e}")
            self.client = None
        
        self._create_ui()
        
        # Center dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (600 // 2)
        self.dialog.geometry(f"500x600+{x}+{y}")
    
    def _create_ui(self):
        """Create the purchase UI."""
        
        # Header
        header_frame = tk.Frame(self.dialog, bg="#4CAF50", height=80)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, 
                text="💰 Purchase AI Tokens",
                font=("Arial", 18, "bold"),
                bg="#4CAF50", fg="white").pack(pady=20)
        
        # Current balance
        balance_frame = tk.Frame(self.dialog, bg="#f5f5f5")
        balance_frame.pack(fill="x", pady=10)
        
        tk.Label(balance_frame,
                text=f"Current Balance: {self.current_balance:,} tokens",
                font=("Arial", 12),
                bg="#f5f5f5", fg="#333").pack(pady=10)
        
        # Packages section
        packages_frame = tk.Frame(self.dialog)
        packages_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        tk.Label(packages_frame,
                text="Choose a package:",
                font=("Arial", 12, "bold"),
                fg="#333").pack(anchor="w", pady=(0, 10))
        
        # Package cards
        self.package_vars = tk.StringVar(value="")
        
        for package_id, details in TOKEN_PACKAGES.items():
            self._create_package_card(packages_frame, package_id, details)
        
        # Payment button
        button_frame = tk.Frame(self.dialog)
        button_frame.pack(pady=20)
        
        self.pay_btn = tk.Button(button_frame,
                                text="Proceed to Payment",
                                command=self._process_payment,
                                font=("Arial", 12, "bold"),
                                bg="#4CAF50", fg="white",
                                width=20, height=2,
                                state="disabled")
        self.pay_btn.pack()
        
        # Info text
        info_frame = tk.Frame(self.dialog, bg="#fff3cd")
        info_frame.pack(fill="x", side="bottom")
        
        info_text = ("ℹ Automatic verification - tokens added instantly!\n"
                    "Secure payment powered by Razorpay.")
        tk.Label(info_frame,
                text=info_text,
                font=("Arial", 9),
                bg="#fff3cd", fg="#856404",
                justify="center").pack(pady=10)
    
    def _create_package_card(self, parent, package_id, details):
        """Create a package selection card."""
        
        card = tk.Frame(parent, relief="ridge", bd=2, bg="white")
        card.pack(fill="x", pady=8)
        
        rb_frame = tk.Frame(card, bg="white")
        rb_frame.pack(fill="x", padx=15, pady=15)
        
        rb = tk.Radiobutton(rb_frame,
                           text="",
                           variable=self.package_vars,
                           value=package_id,
                           command=self._on_package_select,
                           bg="white",
                           font=("Arial", 11))
        rb.pack(side="left")
        
        detail_frame = tk.Frame(rb_frame, bg="white")
        detail_frame.pack(side="left", fill="x", expand=True, padx=10)
        
        tk.Label(detail_frame,
                text=f"{details['tokens']:,} tokens",
                font=("Arial", 12, "bold"),
                bg="white", fg="#333").pack(anchor="w")
        
        tk.Label(detail_frame,
                text=f"₹{details['price']}",
                font=("Arial", 14, "bold"),
                bg="white", fg="#4CAF50").pack(anchor="w")
        
        if package_id == "premium":
            badge = tk.Label(card, text="🏆 Best Value",
                           font=("Arial", 9, "bold"),
                           bg="#FFD700", fg="#333",
                           padx=10, pady=2)
            badge.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)
    
    def _on_package_select(self):
        """Handle package selection."""
        self.selected_package = self.package_vars.get()
        self.pay_btn.config(state="normal")
    
    def _process_payment(self):
        """Create Razorpay order and show payment."""
        
        if not self.selected_package:
            messagebox.showwarning("No Package", "Please select a package first.")
            return
        
        if not self.client:
            messagebox.showerror("Payment Error", 
                               "Payment system not configured. Contact support.")
            return
        
        package = TOKEN_PACKAGES[self.selected_package]
        amount = package['price'] * 100  # Paise
        
        try:
            # 🔥 FIX 1: Create order without payment_capture (let Razorpay handle it)
            order_data = {
                'amount': amount,
                'currency': 'INR',
                'notes': {
                    'package_id': self.selected_package,
                    'tokens': package['tokens'],
                    'machine_fingerprint': get_token_manager().fingerprint
                }
            }
            
            order = self.client.order.create(data=order_data)
            order_id = order['id']
            
            print(f"✅ Created order: {order_id}")
            print(f"📊 Order details: {order}")
            
            # Show payment dialog
            self._show_payment_with_polling(order_id, package)
            
        except Exception as e:
            print(f"⚠ Payment error: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Payment Error",
                               f"Could not create payment.\n\n{str(e)}\n\n"
                               "Check:\n1. RAZORPAY_KEY_SECRET in Secret Manager\n"
                               "2. Internet connection\n3. Razorpay account active")
    
    def _show_payment_with_polling(self, order_id, package):
        """Show payment dialog with auto-polling."""
        
        pay_dialog = tk.Toplevel(self.dialog)
        pay_dialog.title("Complete Payment")
        pay_dialog.geometry("550x500")
        pay_dialog.resizable(False, False)
        pay_dialog.transient(self.dialog)
        pay_dialog.grab_set()
        
        # Store reference
        self.pay_dialog = pay_dialog
        
        # Header
        tk.Label(pay_dialog,
                text="🔐 Complete Your Payment",
                font=("Arial", 14, "bold"),
                bg="#4CAF50", fg="white",
                pady=15).pack(fill="x")
        
        # Content
        content = tk.Frame(pay_dialog, padx=20, pady=20)
        content.pack(fill="both", expand=True)
        
        tk.Label(content,
                text=f"Package: {package['tokens']:,} tokens",
                font=("Arial", 11, "bold")).pack(anchor="w", pady=5)
        
        tk.Label(content,
                text=f"Amount: ₹{package['price']}",
                font=("Arial", 12, "bold"),
                fg="#4CAF50").pack(anchor="w", pady=5)
        
        tk.Label(content,
                text="\n✅ Auto-verification enabled!",
                font=("Arial", 10, "bold"),
                fg="#27ae60").pack(anchor="w", pady=(10, 5))
        
        tk.Label(content,
                text="1. Click 'Pay Now' below\n"
                     "2. Complete payment in browser\n"
                     "3. Return here - tokens add automatically!",
                font=("Arial", 9),
                fg="#333",
                justify="left").pack(anchor="w", padx=10, pady=5)
        
        # 🔥 FIX 2: Add progress indicator
        progress_frame = tk.Frame(content, bg="#f0f0f0", relief="sunken", bd=1)
        progress_frame.pack(fill="x", pady=15)
        
        status_label = tk.Label(progress_frame,
                               text="⏳ Waiting for payment...",
                               font=("Arial", 10, "bold"),
                               fg="#FF9800",
                               bg="#f0f0f0")
        status_label.pack(pady=10)
        
        # 🔥 FIX 3: Add order ID display for debugging
        order_info = tk.Label(content,
                             text=f"Order ID: {order_id}",
                             font=("Arial", 8),
                             fg="#666")
        order_info.pack(pady=5)
        
        # 🔥 FIX 4: Create proper payment link
        try:
            payment_link = self.client.payment_link.create({
                "amount": package['price'] * 100,
                "currency": "INR",
                "description": f"{package['tokens']:,} AI Tokens",
                "reference_id": order_id,  # 🔥 Link to order
                "customer": {
                    "name": get_token_manager().username
                },
                "notify": {
                    "sms": False,
                    "email": False
                },
                "reminder_enable": False,
                "callback_url": "",
                "callback_method": "get"
            })
            payment_url = payment_link['short_url']
            payment_link_id = payment_link['id']
            print(f"✅ Payment link created: {payment_url}")
            print(f"📊 Payment link ID: {payment_link_id}")
        except Exception as e:
            print(f"⚠ Payment link creation failed: {e}")
            # Fallback to checkout
            payment_url = f"https://razorpay.com/payment-link/{order_id}"
            payment_link_id = None
        
        # Buttons
        btn_frame = tk.Frame(content)
        btn_frame.pack(pady=15, fill="x")
        
        def open_and_poll():
            webbrowser.open(payment_url)
            status_label.config(text="🌐 Payment opened in browser...", fg="#2196F3")
            pay_dialog.update()
            # 🔥 FIX 5: Start polling after 5 seconds (give time for payment page to load)
            self.poll_count = 0
            pay_dialog.after(5000, lambda: self._poll_payment_status(
                order_id, payment_link_id, package, pay_dialog, status_label))
        
        # Pay Now button
        pay_btn = tk.Button(btn_frame,
                            text="💳 Pay Now",
                            command=open_and_poll,
                            font=("Arial", 12, "bold"),
                            bg="#4CAF50", fg="white",
                            width=20, height=2,
                            relief="raised", bd=2,
                            cursor="hand2")
        pay_btn.pack(pady=5)
        
        # Check Status button
        check_btn = tk.Button(btn_frame,
                             text="🔍 Check Payment Status",
                             command=lambda: self._manual_check(
                                 order_id, payment_link_id, package, pay_dialog, status_label),
                             font=("Arial", 10),
                             bg="#2196F3", fg="white",
                             width=20,
                             relief="raised", bd=2,
                             cursor="hand2")
        check_btn.pack(pady=5)
        
        # Cancel button
        cancel_btn = tk.Button(btn_frame,
                              text="Cancel",
                              command=pay_dialog.destroy,
                              font=("Arial", 9),
                              bg="#e74c3c", fg="white",
                              width=15,
                              cursor="hand2")
        cancel_btn.pack(pady=5)
        
        # Center dialog
        pay_dialog.update_idletasks()
        x = (pay_dialog.winfo_screenwidth() // 2) - (275)
        y = (pay_dialog.winfo_screenheight() // 2) - (250)
        pay_dialog.geometry(f"550x500+{x}+{y}")
    
    def _poll_payment_status(self, order_id, payment_link_id, package, dialog, label):
        """Poll payment status with multiple methods."""
        
        # Check if dialog still exists
        if not dialog.winfo_exists():
            print("⚠ Dialog closed, stopping polling")
            return
        
        self.poll_count += 1
        
        print(f"📊 Poll #{self.poll_count} - Checking order {order_id}")
        
        try:
            # 🔥 METHOD 1: Check payment link status (if available)
            if payment_link_id:
                try:
                    link_status = self.client.payment_link.fetch(payment_link_id)
                    print(f"📊 Payment link status: {link_status.get('status')}")
                    
                    if link_status.get('status') == 'paid':
                        print("✅ Payment link shows PAID!")
                        self._process_successful_payment(order_id, package, dialog, label)
                        return
                except Exception as e:
                    print(f"⚠ Payment link check failed: {e}")
            
            # 🔥 METHOD 2: Check order status
            order = self.client.order.fetch(order_id)
            status = order.get('status', 'created')
            amount_paid = order.get('amount_paid', 0)
            
            print(f"📊 Order status: {status}, Amount paid: {amount_paid}/{order.get('amount')}")
            
            if status == 'paid' or amount_paid > 0:
                print("✅ Order shows PAID!")
                self._process_successful_payment(order_id, package, dialog, label)
                return
            
            # 🔥 METHOD 3: Check for payments on this order
            payments = self.client.payment.all({'order_id': order_id})
            payment_items = payments.get('items', [])
            
            print(f"📊 Found {len(payment_items)} payments for order")
            
            for payment in payment_items:
                payment_status = payment.get('status')
                print(f"   Payment {payment.get('id')}: {payment_status}")
                
                if payment_status in ['captured', 'authorized']:
                    print("✅ Found successful payment!")
                    self._process_successful_payment(order_id, package, dialog, label)
                    return
            
            # Continue polling if not successful yet
            if self.poll_count < self.max_polls:
                label.config(
                    text=f"⏳ Checking payment... ({self.poll_count}/{self.max_polls})", 
                    fg="#FF9800"
                )
                dialog.after(3000, lambda: self._poll_payment_status(
                    order_id, payment_link_id, package, dialog, label))
            else:
                label.config(
                    text="⏱️ Polling timeout - click 'Check Status' to verify", 
                    fg="#FF5722"
                )
                messagebox.showwarning(
                    "Verification Timeout",
                    f"Automatic verification timed out.\n\n"
                    f"If you completed payment:\n"
                    f"1. Click 'Check Payment Status'\n"
                    f"2. Or contact support with Order ID:\n{order_id}"
                )
            
        except Exception as e:
            print(f"⚠ Poll error: {e}")
            import traceback
            traceback.print_exc()
            
            label.config(text="⚠️ Check error - try manual check", fg="#e74c3c")
            
            # Continue polling on error (might be network issue)
            if self.poll_count < self.max_polls:
                dialog.after(5000, lambda: self._poll_payment_status(
                    order_id, payment_link_id, package, dialog, label))
    
    def _manual_check(self, order_id, payment_link_id, package, dialog, label):
        """Manual status check with all methods."""
        
        label.config(text="🔍 Checking payment...", fg="#2196F3")
        dialog.update()
        
        try:
            # Check payment link
            if payment_link_id:
                try:
                    link = self.client.payment_link.fetch(payment_link_id)
                    if link.get('status') == 'paid':
                        self._process_successful_payment(order_id, package, dialog, label)
                        return
                except:
                    pass
            
            # Check order
            order = self.client.order.fetch(order_id)
            status = order.get('status')
            amount_paid = order.get('amount_paid', 0)
            
            print(f"📊 Manual check - Status: {status}, Paid: {amount_paid}")
            
            if status == 'paid' or amount_paid > 0:
                self._process_successful_payment(order_id, package, dialog, label)
                return
            
            # Check payments
            payments = self.client.payment.all({'order_id': order_id})
            for payment in payments.get('items', []):
                if payment.get('status') in ['captured', 'authorized']:
                    self._process_successful_payment(order_id, package, dialog, label)
                    return
            
            # Not paid yet
            label.config(text=f"⏳ Status: {status} (not paid yet)", fg="#FF9800")
            messagebox.showinfo(
                "Payment Pending",
                f"Payment not completed yet.\n\n"
                f"Status: {status}\n"
                f"Amount paid: ₹{amount_paid/100}\n\n"
                f"Complete payment and check again."
            )
            
        except Exception as e:
            print(f"⚠ Manual check error: {e}")
            import traceback
            traceback.print_exc()
            label.config(text="❌ Check failed", fg="#e74c3c")
            messagebox.showerror("Error", f"Status check failed:\n{e}")
    
    def _process_successful_payment(self, order_id, package, dialog, label):
        """Process successful payment and add tokens."""
        
        label.config(text="✅ Payment successful! Adding tokens...", fg="#27ae60")
        dialog.update()
        
        try:
            # Add tokens with order_id for duplicate prevention
            success = add_tokens(
                tokens=package['tokens'], 
                amount_paid=package['price'],
                order_id=order_id,  # 🔥 CRITICAL: Prevents duplicate processing
                package_type=self.selected_package  # Track which package
            )
            
            if success:
                print(f"✅ Tokens added successfully!")
                messagebox.showinfo(
                    "Success! 🎉",
                    f"{package['tokens']:,} tokens added to your account!\n\n"
                    f"Order ID: {order_id}\n\n"
                    f"Thank you for your purchase!"
                )
                dialog.destroy()
                self.dialog.destroy()
            else:
                raise Exception("Token addition failed")
                
        except Exception as e:
            print(f"⚠ Token addition error: {e}")
            import traceback
            traceback.print_exc()
            
            messagebox.showerror(
                "Token Addition Failed",
                f"Payment successful but failed to add tokens.\n\n"
                f"Order ID: {order_id}\n\n"
                f"Please contact support with this Order ID.\n"
                f"Your tokens will be added manually."
            )
            label.config(text="❌ Token addition failed - contact support", fg="#e74c3c")


def show_purchase_dialog(parent):
    """Show the token purchase dialog."""
    from token_manager import get_token_manager
    
    tm = get_token_manager()
    balance_info = tm.get_balance()
    current_balance = balance_info.get("balance", 0)
    
    dialog = PurchaseDialog(parent, current_balance)
    parent.wait_window(dialog.dialog)