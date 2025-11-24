"""
API Client for Study Timer Backend
Connects to your Firebase Cloud Functions
"""
import requests
import json


class StudyTimerAPI:
    def __init__(self):
        # Your backend URL
        self.base_url = "https://asia-southeast1-leaderboard-98e8c.cloudfunctions.net"
        self.id_token = None
    
    def set_auth_token(self, id_token):
        """Call this after user logs in with Google"""
        self.id_token = id_token
        print(f"[API] ✅ Token set: {id_token[:30] if id_token else 'None'}...")
    
    def _headers(self):
        """Get headers with authorization"""
        headers = {'Content-Type': 'application/json'}
        if self.id_token:
            headers['Authorization'] = f'Bearer {self.id_token}'
            print(f"[API] Headers include Authorization: Bearer {self.id_token[:30]}...")
        else:
            print("[API] ⚠️ WARNING: No token set in headers!")
        return headers
        
    def anonymous_login(self):
        """Call backend to perform Firebase anonymous login securely."""
        try:
            print("[API] Calling anonymous_login endpoint...")
            response = requests.post(
                f"{self.base_url}/anonymous_login",
                timeout=10
            )

            print(f"[API] Backend status: {response.status_code}")
            print(f"[API] Backend raw response: {response.text[:200]}")

            if response.status_code == 200:
                data = response.json()
                print(f"[API] Login success: {data.get('success')}")
                if data.get('success') and data.get('idToken'):
                    print(f"[API] ✅ Received token: {data['idToken'][:30]}...")
                return data
            else:
                print(f"[API] ❌ Login failed with status {response.status_code}")
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            print(f"[API] ❌ Anonymous login exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def create_payment(self, amount, currency='INR'):
        """Create Razorpay payment order"""
        try:
            print("=" * 60)
            print("[API] create_payment called")
            print(f"[API] Amount: {amount}, Currency: {currency}")
            print(f"[API] Token exists: {bool(self.id_token)}")
            if self.id_token:
                print(f"[API] Token preview: {self.id_token[:30]}...")
            
            headers = self._headers()
            print(f"[API] Request headers: {headers}")
            
            body = {'amount': amount, 'currency': currency}
            print(f"[API] Request body: {body}")
            print("=" * 60)

            response = requests.post(
                f'{self.base_url}/create_payment_order',
                headers=headers,
                json=body,
                timeout=10
            )
            
            print(f"[API] Response status: {response.status_code}")
            print(f"[API] Response text: {response.text[:500]}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"[API] ✅ Payment order created: {result.get('order_id')}")
                return result
            else:
                print(f"[API] ❌ Payment failed: {response.text}")
                return {'success': False, 'error': response.text}
                
        except Exception as e:
            print(f"[API] ❌ Payment creation exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}
    
    def verify_payment(self, order_id, payment_id, signature):
        """Verify Razorpay payment after user completes payment"""
        try:
            response = requests.post(
                f'{self.base_url}/verify_payment',
                headers=self._headers(),
                json={
                    'order_id': order_id,
                    'payment_id': payment_id,
                    'signature': signature
                },
                timeout=10
            )
            return response.json()
        except Exception as e:
            print(f"[API] Payment verification failed: {e}")
            return {'error': str(e)}
    
    def send_telegram(self, msg, chat_id=None):
        response = requests.post(
            f"{self.base_url}/send_telegram_notification",
            headers=self._headers(),
            json={"chat_id": chat_id, "message": msg},
            timeout=10
        )
        print("[API] Telegram status:", response.status_code)
        print("[API] Telegram response:", response.text)
        return response.json()

# Create global instance
api = StudyTimerAPI()