# database/db_manager.py
import os
import io
import json
import base64
import shutil
import secrets
import hmac
import hashlib
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from cryptography.fernet import Fernet
import joblib

class DatabaseManager:
    PASSWORD_HASH_KEY = "password_hash"
    PASSWORD_SALT_KEY = "password_salt"
    PASSWORD_ITERATIONS_KEY = "password_iterations"
    PASSWORD_ITERATIONS = 200_000
    BIOMETRIC_KEY_SALT_KEY = "biometric_key_salt"
    BIOMETRIC_KEY_ITERATIONS = 100_000
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
        
        # Enterprise Customer Support Secret: load from environment for safety.
        # Set `CADENCE_SUPPORT_SECRET` in the environment or via a .env loader.
        env_secret = os.environ.get("CADENCE_SUPPORT_SECRET")
        if env_secret:
            self.__SUPPORT_MASTER_SECRET = env_secret.encode("utf-8")
        else:
            # Explicitly set to None so callers can detect missing secret and
            # avoid silently falling back to an insecure hardcoded key.
            self.__SUPPORT_MASTER_SECRET = None
        
        self.config = {}
        self._initialize_storage()

    def _initialize_storage(self):
        os.makedirs(self.profiles_dir, exist_ok=True)
        self._migrate_legacy_single_user_data()
        self.set_active_profile("default", create_if_missing=True)

    def _sanitise_profile_name(self, name):
        profile_name = str(name or "").strip()
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", profile_name):
            raise ValueError("Invalid profile name.")
        return profile_name

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
        username = self._sanitise_profile_name(username or "default")
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
        # Face baseline is stored as encrypted binary; use .enc extension.
        return os.path.join(self.profile_dir, "face_baseline.enc")

    def log_event(self, event_type, detail=""):
        os.makedirs(self.profile_dir, exist_ok=True)
        audit_path = os.path.join(self.profile_dir, "audit.log")
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": str(event_type),
            "detail": str(detail),
        }
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

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
        material = self._derive_biometric_key_material()
        return base64.urlsafe_b64encode(material)

    def _derive_biometric_key_material(self):
        password_hash = self.config.get(self.PASSWORD_HASH_KEY)
        biometric_key_salt = self.config.get(self.BIOMETRIC_KEY_SALT_KEY)
        if not password_hash:
            raise ValueError("Password profile not initialized; cannot derive biometric key.")
        if not biometric_key_salt:
            raise ValueError("Profile requires re-enrollment: biometric key salt missing.")

        return hashlib.pbkdf2_hmac(
            "sha256",
            str(password_hash).encode("utf-8"),
            bytes.fromhex(biometric_key_salt),
            self.BIOMETRIC_KEY_ITERATIONS,
            dklen=32,
        )

    def get_biometric_cipher(self):
        return Fernet(self._derive_biometric_key())

    def save_encrypted_bytes(self, filename, content_bytes):
        cipher = self.get_biometric_cipher()
        path = os.path.join(self.profile_dir, filename)
        encrypted = cipher.encrypt(content_bytes)
        signature = hmac.new(self._derive_biometric_key_material(), encrypted, hashlib.sha256).hexdigest()
        with open(path, "wb") as f:
            f.write(encrypted)
        with open(f"{path}.hmac", "w", encoding="utf-8") as f:
            f.write(signature)
        return path

    def load_encrypted_bytes(self, filename):
        cipher = self.get_biometric_cipher()
        path = os.path.join(self.profile_dir, filename)
        with open(path, "rb") as f:
            encrypted = f.read()
        hmac_path = f"{path}.hmac"
        if not os.path.exists(hmac_path):
            raise RuntimeError("Model file integrity check failed. File may be tampered.")
        with open(hmac_path, "r", encoding="utf-8") as f:
            stored_signature = f.read().strip()
        computed_signature = hmac.new(self._derive_biometric_key_material(), encrypted, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(stored_signature, computed_signature):
            raise RuntimeError("Model file integrity check failed. File may be tampered.")
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

    def export_profile_bundle(self, bundle_path):
        os.makedirs(os.path.dirname(bundle_path) or ".", exist_ok=True)
        payload_buffer = io.BytesIO()
        with zipfile.ZipFile(payload_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for root, _, files in os.walk(self.profile_dir):
                for name in files:
                    file_path = os.path.join(root, name)
                    archive.write(file_path, os.path.relpath(file_path, self.profile_dir))

        encrypted = self.get_biometric_cipher().encrypt(payload_buffer.getvalue())
        signature = hmac.new(self._derive_biometric_key_material(), encrypted, hashlib.sha256).hexdigest()
        with open(bundle_path, "wb") as f:
            f.write(encrypted)
        with open(f"{bundle_path}.hmac", "w", encoding="utf-8") as f:
            f.write(signature)
        return bundle_path

    def import_profile_bundle(self, bundle_path):
        with open(bundle_path, "rb") as f:
            encrypted = f.read()

        hmac_path = f"{bundle_path}.hmac"
        if not os.path.exists(hmac_path):
            raise RuntimeError("Profile bundle integrity check failed. File may be tampered.")
        with open(hmac_path, "r", encoding="utf-8") as f:
            stored_signature = f.read().strip()
        computed_signature = hmac.new(self._derive_biometric_key_material(), encrypted, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(stored_signature, computed_signature):
            raise RuntimeError("Profile bundle integrity check failed. File may be tampered.")

        payload = self.get_biometric_cipher().decrypt(encrypted)
        if os.path.exists(self.profile_dir):
            shutil.rmtree(self.profile_dir, ignore_errors=True)
        os.makedirs(self.profile_dir, exist_ok=True)

        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            archive.extractall(self.profile_dir)

        self._initialize_vault()
        return True

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
        if not self.config.get(self.BIOMETRIC_KEY_SALT_KEY):
            self.config[self.BIOMETRIC_KEY_SALT_KEY] = secrets.token_bytes(16).hex()
        self.config["target_len"] = int(target_len or 0)
        self.config["mode"] = str(mode or "quick")

        for key in self.LEGACY_PASSWORD_KEYS:
            self.config.pop(key, None)

        self._save_vault()

    def verify_password(self, input_password):
        """Verifies a password and migrates matching legacy plaintext entries."""
        # Always perform both PBKDF2 derivation and legacy checks to avoid
        # timing side-channels that reveal which code path was executed.
        password_hash = self.config.get(self.PASSWORD_HASH_KEY)
        salt_hex = self.config.get(self.PASSWORD_SALT_KEY)
        iterations = int(self.config.get(self.PASSWORD_ITERATIONS_KEY, self.PASSWORD_ITERATIONS))

        # Derive candidate hash using real salt if present, otherwise use a random salt
        if salt_hex:
            _, candidate_hash, _ = self._derive_password_hash(input_password, salt_hex, iterations)
        else:
            # Use a dummy salt to keep timing consistent
            dummy_salt = secrets.token_bytes(16).hex()
            _, candidate_hash, _ = self._derive_password_hash(input_password, dummy_salt, iterations)

        hash_match = False
        if password_hash and salt_hex:
            hash_match = secrets.compare_digest(password_hash, candidate_hash)

        # Legacy check: compare against any legacy plaintexts (constant-time compare)
        legacy_match = False
        for key in self.LEGACY_PASSWORD_KEYS:
            legacy_password = self.config.get(key)
            if legacy_password is not None:
                try:
                    if secrets.compare_digest(str(legacy_password), str(input_password)):
                        legacy_match = True
                except Exception:
                    pass

        # If either method matched, migrate and return True
        if legacy_match:
            self.set_auth_profile(input_password, self.get_target_len(), self.config.get("mode", "quick"))

        return bool(hash_match or legacy_match)

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
        
        if not self.__SUPPORT_MASTER_SECRET:
            raise RuntimeError("Support secret not configured. Set CADENCE_SUPPORT_SECRET in environment.")

        # Generate the expected mathematical signature (use full HMAC digest)
        signature = hmac.new(
            self.__SUPPORT_MASTER_SECRET,
            device_uid.encode('utf-8'),
            hashlib.sha256
        ).hexdigest().upper()

        # Use 128 bits (32 hex chars) of the HMAC for the user-facing support key
        # and display it in grouped form to resist brute-force attacks.
        expected_key = f"{signature[:8]}-{signature[8:16]}-{signature[16:32]}"
        
        # Standardize user input
        cleaned_input = str(input_key).strip().upper().replace(" ", "")
        
        # Use secrets.compare_digest to prevent Timing Attacks from hackers
        return secrets.compare_digest(expected_key, cleaned_input)

# ==========================================
# SUPPORT DASHBOARD SIMULATOR (For Testing)
# ==========================================
def support_dashboard_keygen(device_uid, secret=None):
    """
    Run this function independently on a different computer to act as 'Customer Support'.
    It generates the unlock key when a user calls in with their Device UID.
    """
    # Allow callers (support tooling) to provide the secret explicitly. If not
    # provided, read from the environment. Raise an error if unavailable.
    if secret is None:
        env = os.environ.get("CADENCE_SUPPORT_SECRET")
        if not env:
            raise RuntimeError("Support secret not configured. Set CADENCE_SUPPORT_SECRET in environment.")
        secret = env.encode("utf-8")

    signature = hmac.new(secret, str(device_uid).encode('utf-8'), hashlib.sha256).hexdigest().upper()
    return f"{signature[:8]}-{signature[8:16]}-{signature[16:32]}"

if __name__ == "__main__":
    # If you run this file directly, it acts as the Support Team's key generator
    print("--- CADENCE CUSTOMER SUPPORT TERMINAL ---")
    uid = input("Enter Customer's Device UID: ").strip().upper()
    unlock_key = support_dashboard_keygen(uid)
    print(f"\n[IDENTITY VERIFIED]")
    print(f"Provide this exact key to the customer: {unlock_key}")
