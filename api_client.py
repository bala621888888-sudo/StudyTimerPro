# api_client.py - Hide console FIRST
import sys, os
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except: pass

"""
API Client for Study Timer Backend
"""
import requests
import json


class StudyTimerAPI:
    def __init__(self):
        self.id_token = None
        self.verify_payment_url = os.getenv(
            "STUDYTIMER_VERIFY_PAYMENT_URL",
            "https://verify-payment-order-zdg7ljsrha-as.a.run.app",
        )
        # Default backends (ordered by preference)
        default_bases = [
            # primary (where you deployed create_payment_order)
            "https://asia-southeast1-leaderboard-98e8c.cloudfunctions.net",
            # extra India region (in case you deploy there later)
            "https://asia-south1-leaderboard-98e8c.cloudfunctions.net",
            # us-central1 (where verify_payment currently lives)
            "https://us-central1-leaderboard-98e8c.cloudfunctions.net",
        ]

        # Optional override via env var, always tried first
        env_base = os.getenv("STUDYTIMER_API_BASE_URL", "").strip()
        if env_base:
            # put env base first, then all defaults (without duplicates)
            self.base_urls = [env_base] + [
                b for b in default_bases if b != env_base
            ]
            self.base_url = env_base
        else:
            self.base_urls = default_bases
            self.base_url = default_bases[0]
    
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

            errors = []

            for base in self.base_urls:
                url = f"{base}/create_payment_order"
                print(f"[API] create_payment: trying {url}")

                try:
                    response = requests.post(
                        url,
                        headers=headers,
                        json=body,
                        timeout=10
                    )
                except Exception as e:
                    err = f"{url} -> {type(e).__name__}: {e}"
                    print(f"[API] ❌ Payment request error: {err}")
                    errors.append(err)
                    continue

                print(f"[API] Response status: {response.status_code}")
                print(f"[API] Response text: {response.text[:500]}")

                if response.status_code == 200:
                    try:
                        result = response.json()
                    except ValueError:
                        err = f"{url} -> Invalid JSON response"
                        print(f"[API] ❌ {err}")
                        errors.append(err)
                        continue

                    print(f"[API] ✅ Payment order created via {url}: {result.get('order_id')}")
                    return result

                err = f"{url} -> HTTP {response.status_code}: {response.text[:200]}"
                print(f"[API] ❌ Payment failed: {err}")
                errors.append(err)

            return {'success': False, 'error': '; '.join(errors) or 'Unknown error'}
                
        except Exception as e:
            print(f"[API] ❌ Payment creation exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}
    
    def verify_payment(self, order_id, payment_id, signature):
        """Verify Razorpay payment after user completes payment."""
        import requests

        # 🔹 Use ONLY your new Cloud Run endpoint here:
        url = "https://verify-payment-order-zdg7ljsrha-as.a.run.app"  # <-- paste full URL if different

        try:
            resp = requests.post(
                url,
                headers=self._headers(),
                json={
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "signature": signature,
                },
                timeout=15,
            )

            # Try to parse JSON safely
            try:
                data = resp.json()
            except ValueError:
                print("[API] verify_payment_order: Non-JSON response")
                print("      Status:", resp.status_code)
                print("      Body (first 1000 chars):")
                print(resp.text[:1000])
                return {
                    "success": False,
                    "error": "Invalid JSON from payment server",
                    "status": resp.status_code,
                }

            # If backend returned something weird like null or a list
            if not isinstance(data, dict):
                print("[API] verify_payment_order: Unexpected JSON type:", type(data))
                return {
                    "success": False,
                    "error": "Unexpected response format from payment server",
                    "status": resp.status_code,
                    "raw": data,
                }

            # Normalise: always have 'success' and 'error' keys
            success = data.get("success")

            if success is None:
                # If backend didn’t include success, infer it
                success = (resp.status_code == 200) and not data.get("error")
                data["success"] = success

            if not success and "error" not in data:
                # If not successful but no error message, add a generic one
                data["error"] = f"Backend HTTP {resp.status_code}"

            return data

        except Exception as e:
            print(f"[API] Payment verification failed (request error): {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
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
