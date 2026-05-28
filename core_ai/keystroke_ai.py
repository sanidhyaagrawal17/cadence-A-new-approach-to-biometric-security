# core_ai/keystroke_ai.py
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Mutes TensorFlow C++ hardware warnings

import numpy as np
import math
from contextlib import nullcontext
import joblib
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler
from database.db_manager import DatabaseManager

TF_AVAILABLE = True
try:
    import tensorflow as tf
    tf.get_logger().setLevel('ERROR')         # Mutes TensorFlow Python deprecation warnings
    from tensorflow import keras # type: ignore
    from keras.models import Sequential
    from keras.layers import LSTM, Dense, Dropout
    from keras.callbacks import EarlyStopping
except Exception:
    try:
        import keras # type: ignore
        tf = None
        from keras.models import Sequential
        from keras.layers import LSTM, Dense, Dropout
        from keras.callbacks import EarlyStopping
    except Exception:
        TF_AVAILABLE = False
        tf = None
        keras = None
        Sequential = None
        LSTM = None
        Dense = None
        Dropout = None
        EarlyStopping = None

class CadenceKeystrokeEngine:
    def __init__(self, profile_name="default"):
        self.db = DatabaseManager()
        self.db.set_active_profile(profile_name, create_if_missing=True)
        self.model_dir = self.db.get_model_dir()
        os.makedirs(self.model_dir, exist_ok=True)
        
        # 'scale' dynamically adapts the kernel to the variance of your specific typing
        self.svm_model = OneClassSVM(kernel='rbf', gamma='scale', nu=0.05)
        self.scaler = StandardScaler()
        self.lstm_model = self._build_lstm_model() if TF_AVAILABLE else None
        
        self.svm_path = os.path.join(self.model_dir, "keystroke_svm.pkl.enc")
        self.scaler_path = os.path.join(self.model_dir, "keystroke_scaler.pkl.enc")
        self.lstm_path = os.path.join(self.model_dir, "keystroke_lstm.keras.enc")
        
        self.is_quick_trained = False
        self.is_deep_trained = False
        
        self._load_models()

    def _build_lstm_model(self):
        if not TF_AVAILABLE or Sequential is None:
            raise RuntimeError("TensorFlow is unavailable in this environment.")
        model = Sequential([
            LSTM(64, input_shape=(None, 1), return_sequences=True),
            Dropout(0.2),
            LSTM(32),
            Dense(16, activation='relu'),
            Dense(1, activation='sigmoid')
        ])
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        return model

    def _load_models(self):
        legacy_svm = os.path.join(self.model_dir, "keystroke_svm.pkl")
        legacy_scaler = os.path.join(self.model_dir, "keystroke_scaler.pkl")
        if os.path.exists(self.svm_path) and os.path.exists(self.scaler_path):
            try:
                self.svm_model = self.db.load_model("keystroke_svm.pkl.enc")
                self.scaler = self.db.load_model("keystroke_scaler.pkl.enc")
                self.is_quick_trained = True
            except Exception:
                pass
        elif os.path.exists(legacy_svm) and os.path.exists(legacy_scaler):
            self.svm_model = joblib.load(legacy_svm)
            self.scaler = joblib.load(legacy_scaler)
            self.is_quick_trained = True
            
        legacy_lstm = os.path.join(self.model_dir, "keystroke_lstm.keras")
        if TF_AVAILABLE and os.path.exists(self.lstm_path):
            try:
                self.lstm_model = self.db.load_keras_model("keystroke_lstm.keras.enc", keras.models.load_model)
                self.is_deep_trained = True
            except Exception:
                pass
        elif TF_AVAILABLE and os.path.exists(legacy_lstm):
            self.lstm_model = keras.models.load_model(legacy_lstm)
            self.is_deep_trained = True

    def _validate_sequences(self, sequences):
        data = np.asarray(sequences, dtype=float)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        if data.size == 0:
            raise ValueError("Timing sequence is empty.")
        if not np.all(np.isfinite(data)):
            raise ValueError("Timing sequence contains invalid values.")
        if np.any(data <= 0):
            raise ValueError("Timing sequence contains impossible zero/negative intervals.")
        return data

    def _extract_dwell_features(self, sequence, sample_points=8):
        sequence = np.asarray(sequence, dtype=float).ravel()
        if sequence.size == 0:
            raise ValueError("Timing sequence is empty.")

        x_source = np.linspace(0.0, 1.0, num=sequence.size, endpoint=True)
        x_target = np.linspace(0.0, 1.0, num=sample_points, endpoint=True)
        curve = np.interp(x_target, x_source, sequence)

        diffs = np.diff(sequence) if sequence.size > 1 else np.array([0.0], dtype=float)
        stats = np.array([
            float(np.mean(sequence)),
            float(np.std(sequence)),
            float(np.median(sequence)),
            float(np.min(sequence)),
            float(np.max(sequence)),
            float(sequence[0]),
            float(sequence[-1]),
            float(np.mean(diffs)),
        ], dtype=float)
        return np.concatenate([curve.astype(float), stats], axis=0)

    def _prepare_feature_matrix(self, sequences):
        data = self._validate_sequences(sequences)
        return np.vstack([self._extract_dwell_features(seq) for seq in data])

    def _adaptive_svm_nu(self, feature_data):
        feature_data = np.asarray(feature_data, dtype=float)
        if feature_data.size == 0:
            return 0.05

        spread = float(np.mean(np.std(feature_data, axis=0)))
        sample_pressure = min(1.0, len(feature_data) / 20.0)
        nu = 0.03 + (0.06 * spread) + (0.08 * sample_pressure)
        return float(np.clip(nu, 0.03, 0.2))

    def _reject_outliers(self, data):
        if len(data) < 4:
            return data

        row_medians = np.median(data, axis=1)
        median = np.median(row_medians)
        mad = np.median(np.abs(row_medians - median))
        if mad == 0:
            return data

        robust_z = 0.6745 * (row_medians - median) / mad
        filtered = data[np.abs(robust_z) <= 3.5]
        return filtered if len(filtered) >= max(3, len(data) // 2) else data

    def _make_synthetic_impostors(self, sequences):
        rng = np.random.default_rng(42)
        impostors = []
        for seq in sequences:
            fake = np.array(seq, dtype=float).copy()
            rng.shuffle(fake)
            fake *= rng.uniform(0.5, 1.5)
            fake += rng.normal(0.0, 0.01, size=fake.shape)
            fake = np.clip(fake, 1e-4, None)
            impostors.append(fake)
        return np.asarray(impostors, dtype=float)

    def _augment_genuine_sequences(self, sequences, variants=5):
        rng = np.random.default_rng(7)
        augmented = []
        for seq in sequences:
            base = np.array(seq, dtype=float)
            augmented.append(base)
            for _ in range(variants):
                jitter = rng.uniform(-0.01, 0.01, size=base.shape)
                noisy = np.clip(base + jitter, 1e-4, None)
                augmented.append(noisy)
        return np.asarray(augmented, dtype=float)

    def train_quick_setup(self, dwell_flight_data):
        raw_data = self._validate_sequences(dwell_flight_data)
        raw_data = self._reject_outliers(raw_data)
        
        # Gaussian Micro-Jitter: Prevents Kernel Collapse by simulating minor typing flaws
        noise = np.random.normal(0, 0.001, raw_data.shape)
        robust_data = raw_data + noise
        feature_data = self._prepare_feature_matrix(robust_data)
        
        self.svm_model = OneClassSVM(kernel='rbf', gamma='scale', nu=self._adaptive_svm_nu(feature_data))
        scaled_data = self.scaler.fit_transform(feature_data)
        self.svm_model.fit(scaled_data)
        
        self.db.save_model("keystroke_svm.pkl.enc", self.svm_model)
        self.db.save_model("keystroke_scaler.pkl.enc", self.scaler)
        
        self.is_quick_trained = True
        return True

    def verify_quick_setup(self, sequence):
        if not self.is_quick_trained:
            raise ValueError("Quick setup model is not trained yet.")
            
        feature_seq = self._prepare_feature_matrix(sequence)

        scaled_seq = self.scaler.transform(feature_seq)
        preds = self.svm_model.predict(scaled_seq)
        score = float(np.mean(preds == 1))
        success = score >= 0.5
        return success, float(score)

    def train_deep_learning(self, sequences, labels=None, epochs=15):
        if not TF_AVAILABLE or self.lstm_model is None or tf is None:
            raise ValueError("Deep learning setup unavailable: TensorFlow runtime is not available.")

        with (tf.device('/CPU:0') if tf is not None else nullcontext()):
            data = self._validate_sequences(sequences)

            # If explicit labels are provided, use them to partition genuine vs impostor
            if labels is not None and len(labels) == len(data):
                labels_arr = np.asarray(labels).ravel()
                genuine = data[labels_arr == 1]
                impostor_src = data[labels_arr == 0]
            else:
                # No labels supplied: assume all provided sequences are genuine
                genuine = data
                impostor_src = None

            if len(genuine) < 8:
                raise ValueError("Deep learning setup requires at least 8 genuine captures.")

            augmented = self._augment_genuine_sequences(genuine, variants=5)

            # Use provided impostor sequences when available; otherwise create synthetic impostors
            if impostor_src is not None and len(impostor_src) > 0:
                impostors = impostor_src
            else:
                impostors = self._make_synthetic_impostors(augmented)

            augmented_features = self._prepare_feature_matrix(augmented)
            impostor_features = self._prepare_feature_matrix(impostors)

            train_x = np.concatenate([augmented_features, impostor_features], axis=0)
            train_y = np.concatenate([np.ones(len(augmented_features)), np.zeros(len(impostor_features))], axis=0)

            perm = np.random.default_rng(21).permutation(len(train_x))
            train_x = train_x[perm]
            train_y = train_y[perm]

            train_x = np.expand_dims(train_x, axis=-1)
            callbacks = [
                EarlyStopping(monitor='val_loss', patience=3, restore_best_weights=True)
            ]

            self.lstm_model.fit(
                train_x,
                train_y,
                epochs=epochs,
                batch_size=max(8, min(32, len(train_x) // 8)),
                validation_split=0.2,
                callbacks=callbacks,
                verbose=0,
            )

        self.db.save_keras_model("keystroke_lstm.keras.enc", self.lstm_model)
        self.is_deep_trained = True
        return True

    def verify_deep_learning(self, sequence):
        if not TF_AVAILABLE or self.lstm_model is None or tf is None:
            raise ValueError("Deep learning setup unavailable: TensorFlow runtime is not available.")
        if not self.is_deep_trained:
            raise ValueError("Deep learning model is not trained yet.")
            
        with (tf.device('/CPU:0') if tf is not None else nullcontext()):
            feature_seq = self._prepare_feature_matrix(sequence)
            feature_seq = np.expand_dims(feature_seq, axis=-1)
            prediction = self.lstm_model.predict(feature_seq, verbose=0)
            
        score = float(prediction[0][0])
        success = score >= 0.85
        return success, score

    def verify_cascade(self, sequence):
        """
        The Cascade Ensemble
        Uses SVM as a fast Gatekeeper, wakes up LSTM/Face only if unsure.
        """
        if not self.is_quick_trained or not self.is_deep_trained:
            raise ValueError("Cascade requires BOTH Quick (SVM) and Deep (LSTM) models to be trained.")
            
        seq_2d = np.array([sequence]) 
        svm_success, svm_score = self.verify_quick_setup(seq_2d)
        
        # 1. Fast Path Authorization (Highly confident it's the owner)
        if svm_score >= 0.85:
            return True, svm_score, "SVM Fast-Path"
            
        # 2. Fast Path Rejection (Clearly an imposter)
        elif svm_score <= 0.45:
            return False, svm_score, "SVM Fast-Path"
            
        # 3. The Gray Area (Wake up the Deep Learning Model)
        else:
            print(f"Gatekeeper Unsure (Score: {svm_score:.2f}). Waking Deep Check...")
            lstm_success, lstm_score = self.verify_deep_learning(np.array([sequence]))
            return lstm_success, lstm_score, "LSTM Deep-Check"
