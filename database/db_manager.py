# database/db_manager.py
import os
import io
import json
import base64
import shutil
import secrets
import hmac
import hashlib
import tempfile
from cryptography.fernet import Fernet
import joblib

class DatabaseManager:
    PASSWORD_HASH_KEY = "password_hash"
    PASSWORD_SALT_KEY = "password_salt"
    PASSWORD_ITERATIONS_KEY = "password_iterations"
    PASSWORD_ITERATIONS = 200_000
    LEGACY_PASSWORD_KEYS = ("pwd", "password")

    def __init__(self, base_dir="database"):
        """Initializes profile-aware local vault and encrypted biometric storage."""
        self.base_dir = os.path.abspath(base_dir)
        self.profiles_dir = os.path.join(self.base_dir, "profiles")
        self.legacy_models_dir = os.path.join(self.base_dir, "models")
        self.legacy_vault_path = os.path.join(self.legacy_models_dir, "vault.json")
        self.active_profile = "default"
        self.profile_dir = ""
        self.config_path = ""
        
        # Enterprise Customer Support Secret (Hardcoded offline salt)
        self.__SUPPORT_MASTER_SECRET = b"CADENCE_CORP_SECURE_KEY_2026_XYZ"
        
        self.config = {}
        self._initialize_storage()

    def _initialize_storage(self):
        os.makedirs(self.profiles_dir, exist_ok=True)
        self._migrate_legacy_single_user_data()
        self.set_active_profile("default", create_if_missing=True)

    def _migrate_legacy_single_user_data(self):
        default_dir = os.path.join(self.profiles_dir, "default")
        default_cfg = os.path.join(default_dir, "user_config.json")

        if os.path.exists(default_cfg):
            return

        os.makedirs(default_dir, exist_ok=True)

        if os.path.exists(self.legacy_vault_path):
            try:
                shutil.copy2(self.legacy_vault_path, default_cfg)
            except Exception:
                with open(default_cfg, "w", encoding="utf-8") as f:
                    json.dump({}, f, indent=4)
        else:
            with open(default_cfg, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=4)

        for fname in (
            "keystroke_svm.pkl",
            "keystroke_scaler.pkl",
            "keystroke_lstm.keras",
            "face_baseline.jpg",
            "face_baseline.enc",
            "vault.key",
        ):
            src = os.path.join(self.legacy_models_dir, fname)
            dst = os.path.join(default_dir, fname)
            if os.path.exists(src) and not os.path.exists(dst):
                try:
                    shutil.move(src, dst)
                except Exception:
                    shutil.copy2(src, dst)

    def list_profiles(self):
        profiles = []
        for entry in sorted(os.listdir(self.profiles_dir)):
            path = os.path.join(self.profiles_dir, entry)
            if os.path.isdir(path):
                profiles.append(entry)
        if "default" not in profiles:
            profiles.insert(0, "default")
        return profiles

    def set_active_profile(self, username, create_if_missing=False):
        username = str(username or "default").strip() or "default"
        profile_dir = os.path.join(self.profiles_dir, username)
        if not os.path.exists(profile_dir):
            if not create_if_missing:
                raise ValueError(f"Profile '{username}' does not exist.")
            os.makedirs(profile_dir, exist_ok=True)

        self.active_profile = username
        self.profile_dir = profile_dir
        self.config_path = os.path.join(profile_dir, "user_config.json")
        self._initialize_vault()

    def create_profile(self, username):
        self.set_active_profile(username, create_if_missing=True)
        self._save_vault()

    def get_active_profile(self):
        return self.active_profile

    def get_profile_dir(self):
        return self.profile_dir

    def get_model_dir(self):
        return self.profile_dir

    def get_face_baseline_path(self):
        return os.path.join(self.profile_dir, "face_baseline.jpg")

    def _initialize_vault(self):
        """Loads the vault into RAM, or creates a new one if missing."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except json.JSONDecodeError:
                # If file is corrupted, start fresh
                self.config = {}
        else:
            self.config = {}

        # Automatically generate a unique Device UID if it doesn't exist on first boot
        if 'device_uid' not in self.config:
            # Generate an 8-character hardware ID (e.g., 4A9F2B8C)
            self.config['device_uid'] = secrets.token_hex(4).upper()
            self._save_vault()

    def _save_vault(self):
        """Writes the RAM state to disk."""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4)

    def _derive_biometric_key(self):
        password_hash = self.config.get(self.PASSWORD_HASH_KEY)
        password_salt = self.config.get(self.PASSWORD_SALT_KEY)
        if not password_hash or not password_salt:
            raise ValueError("Password profile not initialized; cannot derive biometric key.")

        digest = hashlib.sha256(f"{password_hash}:{password_salt}".encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def get_biometric_cipher(self):
        return Fernet(self._derive_biometric_key())

    def save_encrypted_bytes(self, filename, content_bytes):
        cipher = self.get_biometric_cipher()
        path = os.path.join(self.profile_dir, filename)
        encrypted = cipher.encrypt(content_bytes)
        with open(path, "wb") as f:
            f.write(encrypted)
        return path

    def load_encrypted_bytes(self, filename):
        cipher = self.get_biometric_cipher()
        path = os.path.join(self.profile_dir, filename)
        with open(path, "rb") as f:
            encrypted = f.read()
        return cipher.decrypt(encrypted)

    def save_model(self, filename, obj):
        buffer = io.BytesIO()
        joblib.dump(obj, buffer)
        self.save_encrypted_bytes(filename, buffer.getvalue())

    def load_model(self, filename):
        payload = self.load_encrypted_bytes(filename)
        return joblib.load(io.BytesIO(payload))

    def save_keras_model(self, filename, model):
        temp_path = None
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".keras")
            temp_path = temp_file.name
            temp_file.close()
            model.save(temp_path)
            with open(temp_path, "rb") as f:
                payload = f.read()
            self.save_encrypted_bytes(filename, payload)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def load_keras_model(self, filename, keras_loader):
        payload = self.load_encrypted_bytes(filename)
        temp_path = None
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".keras")
            temp_path = temp_file.name
            temp_file.close()
            with open(temp_path, "wb") as f:
                f.write(payload)
            return keras_loader(temp_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def _derive_password_hash(self, password, salt_hex=None, iterations=None):
        """Derives a salted PBKDF2-HMAC hash for the local password vault."""
        if iterations is None:
            iterations = self.PASSWORD_ITERATIONS
        salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            str(password).encode("utf-8"),
            salt,
            iterations,
        )
        return salt.hex(), digest.hex(), iterations

    def set_auth_profile(self, password, target_len=0, mode="quick"):
        """Stores authentication metadata without persisting the raw password."""
        salt_hex, digest_hex, iterations = self._derive_password_hash(password)
        self.config[self.PASSWORD_SALT_KEY] = salt_hex
        self.config[self.PASSWORD_HASH_KEY] = digest_hex
        self.config[self.PASSWORD_ITERATIONS_KEY] = iterations
        self.config["target_len"] = int(target_len or 0)
        self.config["mode"] = str(mode or "quick")

        for key in self.LEGACY_PASSWORD_KEYS:
            self.config.pop(key, None)

        self._save_vault()

    def verify_password(self, input_password):
        """Verifies a password and migrates matching legacy plaintext entries."""
        password_hash = self.config.get(self.PASSWORD_HASH_KEY)
        salt_hex = self.config.get(self.PASSWORD_SALT_KEY)
        iterations = int(self.config.get(self.PASSWORD_ITERATIONS_KEY, self.PASSWORD_ITERATIONS))

        if password_hash and salt_hex:
            _, candidate_hash, _ = self._derive_password_hash(input_password, salt_hex, iterations)
            return secrets.compare_digest(password_hash, candidate_hash)

        for key in self.LEGACY_PASSWORD_KEYS:
            legacy_password = self.config.get(key)
            if legacy_password is not None and secrets.compare_digest(str(legacy_password), str(input_password)):
                self.set_auth_profile(input_password, self.get_target_len(), self.config.get("mode", "quick"))
                return True

        return False

    def has_password(self):
        has_hash = bool(self.config.get(self.PASSWORD_HASH_KEY) and self.config.get(self.PASSWORD_SALT_KEY))
        has_legacy = any(self.config.get(key) is not None for key in self.LEGACY_PASSWORD_KEYS)
        return has_hash or has_legacy

    def get_target_len(self):
        return int(self.config.get("target_len", 0) or 0)

    def clear_auth_profile(self):
        for key in (
            self.PASSWORD_HASH_KEY,
            self.PASSWORD_SALT_KEY,
            self.PASSWORD_ITERATIONS_KEY,
            "target_len",
            "mode",
            *self.LEGACY_PASSWORD_KEYS,
        ):
            self.config.pop(key, None)
        self._save_vault()

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
