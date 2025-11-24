# encrypted_gspread_connection.py - Works with your existing environment variable structure
import gspread
import json
import os
import tempfile
from cryptography.fernet import Fernet
from dotenv import load_dotenv

def get_encrypted_credentials_file():
    """
    Creates a temporary credentials file from encrypted environment variables.
    This replaces your gspread_credentials_file path.
    """
    try:
        # Load environment variables
        load_dotenv()
        
        # Get encrypted data from environment variables
        encryption_key = os.getenv('ENCRYPTION_KEY')
        encrypted_creds = os.getenv('ENCRYPTED_CREDENTIALS')
        
        if not encryption_key or not encrypted_creds:
            # Fallback to original file if encryption not available
            print("⚠ Encrypted credentials not found, using fallback...")
            return None
        
        # Decrypt the credentials
        fernet = Fernet(encryption_key.encode())
        decrypted_creds = fernet.decrypt(encrypted_creds.encode()).decode()
        
        # Create temporary file with decrypted credentials
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        temp_file.write(decrypted_creds)
        temp_file.flush()
        temp_file.close()
        
        print("✅ Using encrypted credentials")
        return temp_file.name
        
    except Exception as e:
        print(f"❌ Failed to decrypt credentials: {e}")
        return None

def cleanup_temp_credentials(temp_file_path):
    """Clean up temporary credentials file"""
    try:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
    except Exception as e:
        print(f"⚠ Failed to cleanup temp file: {e}")

# Modified service account function that works with your existing code structure
def service_account(filename=None):
    """
    Drop-in replacement for gspread.service_account() that handles encryption
    """
    # If encrypted credentials are available, use them
    temp_creds_file = get_encrypted_credentials_file()
    
    if temp_creds_file:
        try:
            # Use encrypted credentials
            gc = gspread.service_account(filename=temp_creds_file)
            # Clean up temp file immediately after creating client
            cleanup_temp_credentials(temp_creds_file)
            return gc
        except Exception as e:
            # Clean up temp file on error
            cleanup_temp_credentials(temp_creds_file)
            print(f"❌ Failed to use encrypted credentials: {e}")
            raise
    
    # Fallback to original file if encryption not available
    if filename:
        print(f"📄 Using original credentials file: {filename}")
        return gspread.service_account(filename=filename)
    else:
        raise ValueError("No credentials available - neither encrypted nor file path provided")

# Alternative: Direct dictionary-based approach (more secure)
def service_account_from_encrypted():
    """
    Alternative method using service_account_from_dict (more secure - no temp files)
    """
    try:
        load_dotenv()
        
        encryption_key = os.getenv('ENCRYPTION_KEY')
        encrypted_creds = os.getenv('ENCRYPTED_CREDENTIALS')
        
        if not encryption_key or not encrypted_creds:
            raise ValueError("Missing ENCRYPTION_KEY or ENCRYPTED_CREDENTIALS")
        
        # Decrypt the credentials
        fernet = Fernet(encryption_key.encode())
        decrypted_creds = fernet.decrypt(encrypted_creds.encode()).decode()
        creds_dict = json.loads(decrypted_creds)
        
        # Create client directly from dictionary (no temp files)
        gc = gspread.service_account_from_dict(creds_dict)
        print("✅ Using encrypted credentials (secure method)")
        return gc
        
    except Exception as e:
        print(f"❌ Failed to create client from encrypted credentials: {e}")
        raise