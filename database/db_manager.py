# database/db_manager.py
import os
import json
import secrets
import hmac
import hashlib

class DatabaseManager:
    def __init__(self, db_path="database/models/vault.json"):
        """
        Initializes a lightweight, RAM-based JSON vault for zero-latency 
        storage of cryptographic configuration, avoiding SQL overhead.
        """
        # Ensure the target directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.config_path = db_path
        
        # Enterprise Customer Support Secret (Hardcoded offline salt)
        self.__SUPPORT_MASTER_SECRET = b"CADENCE_CORP_SECURE_KEY_2026_XYZ"
        
        self.config = {}
        self._initialize_vault()

    def _initialize_vault(self):
        """Loads the vault into RAM, or creates a new one if missing."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
            except json.JSONDecodeError:
                # If file is corrupted, start fresh
                self.config = {}

        # Automatically generate a unique Device UID if it doesn't exist on first boot
        if 'device_uid' not in self.config:
            # Generate an 8-character hardware ID (e.g., 4A9F2B8C)
            self.config['device_uid'] = secrets.token_hex(4).upper()
            self._save_vault()

    def _save_vault(self):
        """Writes the RAM state to disk."""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def get_device_uid(self):
        """Retrieves the unique device identifier from RAM instantly."""
        return self.config.get('device_uid', 'UNKNOWN')

    def verify_support_key(self, input_key):
        """
        Cryptographic verification: Checks if the key provided by Customer Support
        mathematically matches the HMAC hash of this specific Device UID.
        """
        device_uid = self.get_device_uid()
        
        # Generate the expected mathematical signature
        signature = hmac.new(
            self.__SUPPORT_MASTER_SECRET, 
            device_uid.encode('utf-8'), 
            hashlib.sha256
        ).hexdigest().upper()
        
        # Extract slices to make the Support Key look like a software product key (XXXX-XXXX-XXXX)
        expected_key = f"{signature[:4]}-{signature[4:8]}-{signature[8:12]}"
        
        # Standardize user input
        cleaned_input = str(input_key).strip().upper().replace(" ", "")
        
        # Use secrets.compare_digest to prevent Timing Attacks from hackers
        return secrets.compare_digest(expected_key, cleaned_input)

# ==========================================
# SUPPORT DASHBOARD SIMULATOR (For Testing)
# ==========================================
def support_dashboard_keygen(device_uid):
    """
    Run this function independently on a different computer to act as 'Customer Support'.
    It generates the unlock key when a user calls in with their Device UID.
    """
    secret = b"CADENCE_CORP_SECURE_KEY_2026_XYZ"
    signature = hmac.new(secret, str(device_uid).encode('utf-8'), hashlib.sha256).hexdigest().upper()
    return f"{signature[:4]}-{signature[4:8]}-{signature[8:12]}"

if __name__ == "__main__":
    # If you run this file directly, it acts as the Support Team's key generator
    print("--- CADENCE CUSTOMER SUPPORT TERMINAL ---")
    uid = input("Enter Customer's Device UID: ").strip().upper()
    unlock_key = support_dashboard_keygen(uid)
    print(f"\n[IDENTITY VERIFIED]")
    print(f"Provide this exact key to the customer: {unlock_key}")