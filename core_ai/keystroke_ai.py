# core_ai/keystroke_ai.py
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Mutes TensorFlow C++ hardware warnings

import numpy as np
import math
import joblib
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler

import tensorflow as tf
tf.get_logger().setLevel('ERROR')         # Mutes TensorFlow Python deprecation warnings
from tensorflow import keras # type: ignore
from keras.models import Sequential
from keras.layers import LSTM, Dense, Dropout

class CadenceKeystrokeEngine:
    def __init__(self):
        self.model_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "database", "models"))
        os.makedirs(self.model_dir, exist_ok=True)
        
        # 'scale' dynamically adapts the kernel to the variance of your specific typing
        self.svm_model = OneClassSVM(kernel='rbf', gamma='scale', nu=0.05)
        self.scaler = StandardScaler()
        self.lstm_model = self._build_lstm_model()
        
        self.svm_path = os.path.join(self.model_dir, "keystroke_svm.pkl")
        self.scaler_path = os.path.join(self.model_dir, "keystroke_scaler.pkl")
        self.lstm_path = os.path.join(self.model_dir, "keystroke_lstm.keras")
        
        self.is_quick_trained = False
        self.is_deep_trained = False
        
        self._load_models()

    def _build_lstm_model(self):
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
        if os.path.exists(self.svm_path) and os.path.exists(self.scaler_path):
            self.svm_model = joblib.load(self.svm_path)
            self.scaler = joblib.load(self.scaler_path)
            self.is_quick_trained = True
            
        if os.path.exists(self.lstm_path):
            self.lstm_model = keras.models.load_model(self.lstm_path)
            self.is_deep_trained = True

    def train_quick_setup(self, dwell_flight_data):
        if len(dwell_flight_data) == 0:
            return False
            
        raw_data = np.array(dwell_flight_data)
        
        # Gaussian Micro-Jitter: Prevents Kernel Collapse by simulating minor typing flaws
        noise = np.random.normal(0, 0.001, raw_data.shape)
        robust_data = raw_data + noise
        
        scaled_data = self.scaler.fit_transform(robust_data)
        self.svm_model.fit(scaled_data)
        
        joblib.dump(self.svm_model, self.svm_path)
        joblib.dump(self.scaler, self.scaler_path)
        
        self.is_quick_trained = True
        return True

    def verify_quick_setup(self, sequence):
        if not self.is_quick_trained:
            raise ValueError("Quick setup model is not trained yet.")
            
        sequence = np.array(sequence)
        if len(sequence.shape) == 1:
            sequence = sequence.reshape(1, -1)
            
        scaled_seq = self.scaler.transform(sequence)
        distance = self.svm_model.decision_function(scaled_seq)[0]
        
        # ========================================================
        # NEW FIX: The Forgiving Human Mapping
        # ========================================================
        if distance >= 0:
            # Perfect Machine-Like Match (Score: 0.90 to 0.99)
            score = 0.90 + (0.09 * min(distance, 1.0))
            
        elif distance >= -2.0:
            # Human Variance Zone. The AI recognizes you are close but slightly off.
            # A minor deviation (e.g., -0.2 distance) results in ~0.86 (Fast-Path Pass)
            # A moderate deviation (e.g., -0.8 distance) results in ~0.74 (Wakes Camera)
            score = 0.50 + (0.40 * (1.0 - (abs(distance) / 2.0)))
            
        else:
            # Severe Deviation / Imposter Zone (Score: 0.0 to 0.49)
            score = max(0.0, 0.49 - (abs(distance) * 0.1))
            
        success = score >= 0.85
        return success, float(score)

    def train_deep_learning(self, sequences, labels, epochs=15):
        with tf.device('/CPU:0'):
            sequences = np.array(sequences)
            if len(sequences.shape) == 2:
                sequences = np.expand_dims(sequences, axis=-1) 
            self.lstm_model.fit(sequences, labels, epochs=epochs, batch_size=1, verbose=1)
            
        self.lstm_model.save(self.lstm_path)
        self.is_deep_trained = True
        return True

    def verify_deep_learning(self, sequence):
        if not self.is_deep_trained:
            raise ValueError("Deep learning model is not trained yet.")
            
        with tf.device('/CPU:0'):
            sequence = np.array(sequence)
            if len(sequence.shape) == 1:
                sequence = sequence.reshape(1, -1, 1)
            elif len(sequence.shape) == 2:
                sequence = np.expand_dims(sequence, axis=-1)
            prediction = self.lstm_model.predict(sequence, verbose=0)
            
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
            lstm_success, lstm_score = self.verify_deep_learning(sequence)
            return lstm_success, lstm_score, "LSTM Deep-Check"