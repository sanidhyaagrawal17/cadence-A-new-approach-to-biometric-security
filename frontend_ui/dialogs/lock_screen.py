from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QInputDialog, QApplication)
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QKeyEvent
import time
import numpy as np


class MockWindowsLockScreen(QDialog):
    def __init__(self, parent=None, app_instance=None):
        super().__init__(parent)
        self.app = app_instance
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.showFullScreen()
        self.setStyleSheet("""
            QDialog { background-color: #050505; }
            QLabel { color: white; font-family: 'Segoe UI', sans-serif; }
            QLineEdit { background-color: #0f0f0f; border: 1px solid #333333; color: #00ff88; padding: 15px; border-radius: 8px; font-size: 18px; font-family: 'Consolas', monospace; letter-spacing: 2px; }
            QLineEdit:focus { border: 1px solid #00ff88; background-color: #151515; }
            QLineEdit[readOnly="true"] { color: #888888; border: 1px solid #555555; }
            QPushButton { background-color: transparent; border: 1px solid #ff3333; color: #ff3333; padding: 10px 30px; border-radius: 8px; font-family: 'Segoe UI'; font-size: 14px; font-weight: bold; }
            QPushButton:hover { background-color: rgba(255, 51, 51, 0.1); }
            QPushButton#support_btn { border: 1px solid #00ff88; color: #00ff88; }
            QPushButton#support_btn:hover { background-color: rgba(0, 255, 136, 0.1); }
        """)
        self.tms = []
        self.target_len = self.app.target_len if self.app.target_len > 0 else 5
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        
        brand_layout = QHBoxLayout()
        brand_lbl = QLabel("🛡️ CADENCE SECURE ENCLAVE")
        brand_lbl.setStyleSheet("color: #00ff88; font-size: 14px; font-weight: bold; letter-spacing: 1px;")
        brand_layout.addWidget(brand_lbl)
        brand_layout.addStretch()
        main_layout.addLayout(brand_layout)
        main_layout.addStretch()
        
        center_layout = QVBoxLayout()
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.setSpacing(20)
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profile:"))
        self.profile_select = QComboBox()
        self.profile_select.addItems(self.app.db.list_profiles())
        self.profile_select.setCurrentText(self.app.active_profile)
        self.profile_select.currentTextChanged.connect(self._on_profile_changed)
        profile_row.addWidget(self.profile_select)
        profile_row.addStretch()
        center_layout.addLayout(profile_row)
        self.camera_lbl = QLabel()
        self.camera_lbl.setFixedSize(400, 300)
        self.camera_lbl.setStyleSheet("border: 2px solid #00ff88; border-radius: 8px; background-color: #0f0f0f;")
        self.camera_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl = QLabel("SYSTEM LOCKED")
        title_lbl.setStyleSheet("font-size: 36px; font-weight: 800; letter-spacing: 4px;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl = QLabel("Awaiting Dual-Layer Biometric Verification")
        sub_lbl.setStyleSheet("font-size: 14px; color: #888888;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.pwd_input = QLineEdit()
        self.pwd_input.setPlaceholderText("ENTER NEURAL RHYTHM")
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setFixedWidth(380)
        self.pwd_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.pwd_input.installEventFilter(self)
        
        self.status_lbl = QLabel("Initializing sensors... 👁️")
        self.status_lbl.setStyleSheet("font-size: 14px; color: #aaaaaa; font-family: 'Consolas', monospace;")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.camera_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
        center_layout.addSpacing(10)
        center_layout.addWidget(title_lbl)
        center_layout.addWidget(sub_lbl)
        center_layout.addSpacing(20)
        center_layout.addWidget(self.pwd_input, alignment=Qt.AlignmentFlag.AlignHCenter)
        center_layout.addWidget(self.status_lbl)
        main_layout.addLayout(center_layout)
        main_layout.addStretch()
        
        bottom_layout = QHBoxLayout()
        
        self.support_btn = QPushButton("KEY OVERRIDE")
        self.support_btn.setObjectName("support_btn")
        self.support_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.support_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.support_btn.clicked.connect(self._initiate_support_override)
        
        bottom_layout.addWidget(self.support_btn)
        bottom_layout.addStretch()
        
        self.cancel_btn = QPushButton("ABORT / RETURN TO DASHBOARD")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cancel_btn.clicked.connect(self.reject)

        # Lockout tracking for brute-force protection on the lock screen
        self.lock_attempts = 0
        self.lockout_remaining = 0
        self.lockout_timer = QTimer(self)
        self.lockout_timer.timeout.connect(self._update_lockout)
        
        bottom_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(bottom_layout)

    def _on_profile_changed(self, profile_name):
        if profile_name and profile_name != self.app.active_profile:
            self.app._switch_profile(profile_name)
            self.target_len = self.app.target_len if self.app.target_len > 0 else 5

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.ignore()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if type(event) == QKeyEvent and not event.isAutoRepeat():
                k = event.key()
                if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if obj == self.pwd_input and not self.pwd_input.isReadOnly():
                        self._evaluate_login()
                        return True
                elif k not in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_Backspace):
                    now = time.time()
                    self.tms.append(now)
        return super().eventFilter(obj, event)

    def _get_dts(self):
        return [(self.tms[i] - self.tms[i-1]) for i in range(1, len(self.tms))]

    def _initiate_support_override(self):
        device_id = self.app.db.get_device_uid()
        text, ok = QInputDialog.getText(
            self, 'Emergency Cryptographic Override', 
            f'Biometrics Locked.\n\nRead this Device ID to Customer Support: [{device_id}]\n\nEnter the cryptographic unlock key provided by Support:'
        )
        if ok and text:
            if self.app.db.verify_support_key(text):
                self.status_lbl.setText("OVERRIDE ACCEPTED. CRYPTOGRAPHIC MATCH.")
                self.status_lbl.setStyleSheet("color: #00ff88; font-size: 16px; font-weight: bold; font-family: 'Consolas', monospace;")
                QApplication.processEvents()
                time.sleep(1)
                self.accept()
            else:
                self._fail("OVERRIDE DENIED: Invalid Cryptographic Key.")

    def _evaluate_login(self):
        typed_pwd = self.pwd_input.text()
        dts = self._get_dts()
        self.pwd_input.clear()
        
        self.pwd_input.setReadOnly(True)
        
        if not self.app._password_matches(typed_pwd):
            self._fail("ACCESS DENIED: Invalid Rhythm.")
            return

        dts = self.app._normalize_timing_sequence(dts, self.target_len)
        if dts is None:
            self._fail("ACCESS DENIED: Inconsistent rhythm length. Re-type password.")
            return

        try:
            success, score = self.app.keystroke_engine.verify_quick_setup(np.array([dts]))
        except Exception as e:
            self._fail(f"SYSTEM ERROR: {str(e)}")
            return
            
        if score <= 0.45:
            self._fail(f"ACCESS DENIED: Rhythm Mismatch (Score: {score:.2f} via SVM Fast-Path)")
            return

        # TRUE 2FA: Always check face if enrolled, even if keystroke score is perfect
        if hasattr(self.app, 'live_frame') and self.app.face_engine.is_enrolled:
            self.status_lbl.setText(f"Gatekeeper Passed (SVM Score: {score:.2f}). Verifying Face...")
            self.status_lbl.setStyleSheet("color: #ffcc00; font-family: 'Consolas'; font-weight: bold;")
            QApplication.processEvents()
            
            # Use watchdog wrapper to enforce a timeout on face verification
            self.verify_thread = self.app._start_ai_task_with_timeout(
                self.app.face_engine.verify_user,
                args=(self.app.live_frame.copy(),),
                timeout_seconds=8,
                result_cb=lambda match, d=dts, s=score: self._continue_deep_evaluation(match, d, s),
                error_cb=lambda e: self._fail(f"FACE AI ERROR: {str(e)[:30]}")
            )
            return
        
        # Fallback if facial recognition isn't set up yet
        if score >= 0.80:
            self.status_lbl.setText(f"ACCESS GRANTED (Match: {score:.2f} via SVM Fast-Path)")
            self.status_lbl.setStyleSheet("color: #00ff88; font-size: 16px; font-weight: bold; font-family: 'Consolas', monospace;")
            QApplication.processEvents()
            time.sleep(0.5)
            self.accept()
        else:
            self._fail(f"ACCESS DENIED: Gray Area, but Face Scanner Not Enrolled.")

    def _continue_deep_evaluation(self, face_match, dts, svm_score):
        if not face_match:
            self._fail("ACCESS DENIED: Facial Match Failed. (Imposter Blocked)")
            return
            
        # If face passed AND initial typing was highly accurate, grant access
        if svm_score >= 0.80:
            self.status_lbl.setText(f"ACCESS GRANTED (Face Verified + SVM {svm_score:.2f})")
            self.status_lbl.setStyleSheet("color: #00ff88; font-size: 16px; font-weight: bold; font-family: 'Consolas', monospace;")
            QApplication.processEvents()
            time.sleep(0.5)
            self.accept()
            return
            
        # If face passed BUT initial typing was in the Gray Area, check LSTM
        self.status_lbl.setText("Facial Match Verified. Waking Keystroke LSTM...")
        QApplication.processEvents()
        
        # Run LSTM verification in background to avoid blocking UI
        try:
            self.lstm_thread = self.app._start_ai_task_with_timeout(
                self.app.keystroke_engine.verify_deep_learning,
                args=(np.array([dts]),),
                timeout_seconds=10,
                result_cb=lambda res: self._on_lstm_result(res),
                error_cb=lambda e: self._fail(f"LSTM ERROR: {str(e)}")
            )
        except Exception as e:
            self._fail(f"LSTM ERROR: {str(e)}")
            return

    def _on_lstm_result(self, res):
        try:
            lstm_success, lstm_score = res
            if lstm_success:
                self.status_lbl.setText(f"ACCESS GRANTED (Match: {lstm_score:.2f} via LSTM Deep-Check)")
                self.status_lbl.setStyleSheet("color: #00ff88; font-size: 16px; font-weight: bold; font-family: 'Consolas', monospace;")
                QApplication.processEvents()
                time.sleep(0.5)
                self.accept()
            else:
                self._fail(f"ACCESS DENIED: Deep Rhythm Mismatch (Score: {lstm_score:.2f} via LSTM)")
        except Exception as e:
            self._fail(f"LSTM ERROR: {str(e)}")

    def _fail(self, msg):
        self.status_lbl.setText(msg)
        self.status_lbl.setStyleSheet("color: #ff3333; font-size: 14px; font-weight: bold; font-family: 'Consolas', monospace;")
        self.tms.clear()
        # increment attempts and possibly start lockout
        try:
            self.lock_attempts += 1
        except Exception:
            self.lock_attempts = 1

        self.pwd_input.setReadOnly(False)
        self.pwd_input.setFocus()

        if self.lock_attempts >= 2:
            self._start_lockout()

    def _start_lockout(self):
        # exponential backoff similar to the dashboard lockout
        if self.lock_attempts < 2:
            return
        self.lockout_remaining = min(60, 2 ** (self.lock_attempts - 1))
        self.pwd_input.setEnabled(False)
        self.status_lbl.setText(f"Too many attempts. Retry in {self.lockout_remaining}s")
        self.status_lbl.setStyleSheet("color: #ffaa33; font-size: 14px; font-weight: bold; font-family: 'Consolas', monospace;")
        self.lockout_timer.start(1000)

    def _update_lockout(self):
        if self.lockout_remaining <= 1:
            self.lockout_timer.stop()
            self.lockout_remaining = 0
            self.lock_attempts = 0
            self.status_lbl.setText("")
            self.pwd_input.setEnabled(True)
            self.pwd_input.setReadOnly(False)
            self.pwd_input.setFocus()
            return
        self.lockout_remaining -= 1
        self.status_lbl.setText(f"Too many attempts. Retry in {self.lockout_remaining}s")
