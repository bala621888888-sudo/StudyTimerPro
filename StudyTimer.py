# Safely initialize the encrypted gspread client so missing/invalid secrets
# don't crash app startup.
try:
    gspread_client = get_encrypted_gspread_client()
except Exception as e:
    print(f"Failed to initialize gspread client: {e}")
    gspread_client = None
