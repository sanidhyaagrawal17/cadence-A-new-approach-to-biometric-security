# database/db_manager.py
import os
import json
import joblib

class DatabaseManager:
    def __init__(self):
        self.db_path = "database/models"
        os.makedirs(self.db_path, exist_ok=True)
        self.config_file = os.path.join(self.db_path, "user_config.json")

    def save_model(self, model, filename):
        path = os.path.join(self.db_path, filename)
        joblib.dump(model, path)

    def load_model(self, filename):
        path = os.path.join(self.db_path, filename)
        if os.path.exists(path):
            return joblib.load(path)
        return None

    def save_config(self, pwd, is_deep_mode, key_len):
        data = {"pwd": pwd, "deep_mode": is_deep_mode, "key_len": key_len}
        with open(self.config_file, 'w') as f:
            json.dump(data, f)

    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return None