# frontend_ui/app_window.py
import sys
import cv2
import time
import os
import math
import gc
import stat
import shutil
import urllib.request
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QStackedWidget, QLineEdit, 
                             QProgressBar, QFrame, QGridLayout, QSizePolicy,
                             QPushButton, QButtonGroup, QTextEdit, QScrollArea, QCheckBox,
                             QDialog, QMessageBox, QInputDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEvent, QTimer, QRect, QDateTime
from PyQt6.QtGui import QImage, QPixmap, QFont, QKeyEvent, QPainter, QColor, QBrush, QPen, QCursor

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core_ai.keystroke_ai import CadenceKeystrokeEngine
from core_ai.face_ai import CadenceFaceEngine
from database.db_manager import DatabaseManager

os.makedirs("intruders", exist_ok=True)

class AITaskThread(QThread):
    result_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            res = self.func(*self.args, **self.kwargs)
            self.result_signal.emit(res)
        except Exception as e:
            self.error_signal.emit(str(e))

class TimingChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(45)
        self.data = []
    def update_data(self, new_data):
        self.data = new_data
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        if not self.data: return
        bar_width = 15
        spacing = 5
        max_height = self.height() - 10
        max_val = max(500, max(self.data) if self.data else 500)
        x_offset = 10
        for val in self.data[-30:]:
            h = int((val / max_val) * max_height)
            h = max(5, h)
            y = self.height() - h - 5
            painter.setBrush(QBrush(QColor("#00ff88")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(x_offset, y, bar_width, h)
            x_offset += bar_width + spacing

class SessionBar(QFrame):
    def __init__(self, index, key_count, avg_ms):
        super().__init__()
        self.setFixedHeight(30) 
        self.setStyleSheet("SessionBar { background-color: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 6px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        idx_lbl = QLabel(f"#{index + 1}")
        idx_lbl.setStyleSheet("color: #666; font-size: 11px; min-width: 24px; background: transparent;")
        layout.addWidget(idx_lbl)
        keys_lbl = QLabel(f"{key_count} keys")
        keys_lbl.setStyleSheet("color: #aaa; font-size: 11px; background: transparent;")
        layout.addWidget(keys_lbl)
        layout.addStretch()
        avg_lbl = QLabel(f"avg {avg_ms}ms")
        avg_lbl.setStyleSheet("color: #00ff88; font-size: 11px; font-weight: bold; background: transparent;")
        layout.addWidget(avg_lbl)
        dot = QLabel("●")
        dot.setStyleSheet("color: #00ff88; font-size: 8px; background: transparent;")
        layout.addWidget(dot)

class ModeButton(QFrame):
    clicked = pyqtSignal()
    def __init__(self, text, icon, desc):
        super().__init__()
        self.setFixedHeight(75) 
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)
        top_layout = QHBoxLayout()
        self.icon_lbl = QLabel(icon)
        self.icon_lbl.setStyleSheet("font-size: 18px; background: transparent;")
        self.title_lbl = QLabel(text)
        self.title_lbl.setStyleSheet("color: #ccc; font-weight: bold; font-size: 15px; background: transparent;")
        top_layout.addWidget(self.icon_lbl)
        top_layout.addWidget(self.title_lbl)
        top_layout.addStretch()
        layout.addLayout(top_layout)
        self.desc_lbl = QLabel(desc)
        self.desc_lbl.setStyleSheet("color: #777; font-size: 12px; background: transparent;")
        layout.addWidget(self.desc_lbl)
        self.is_active = False
        self.update_style()
    def update_style(self):
        if self.is_active:
            self.setStyleSheet("ModeButton { background-color: #0d2b1e; border: 1px solid #00ff88; border-radius: 8px; }")
            self.title_lbl.setStyleSheet("color: #00ff88; font-weight: bold; font-size: 15px; background: transparent;")
        else:
            self.setStyleSheet("ModeButton { background-color: #111111; border: 1px solid #333333; border-radius: 8px; } ModeButton:hover { border: 1px solid #555; }")
            self.title_lbl.setStyleSheet("color: #ccc; font-weight: bold; font-size: 15px; background: transparent;")
    def set_active(self, active):
        self.is_active = active
        self.update_style()
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

class SidebarCard(QFrame):
    clicked = pyqtSignal()
    def __init__(self, title, desc, icon_text, is_active=False):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(105) 
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.is_active = is_active
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 12, 15, 12)
        header_layout = QHBoxLayout()
        icon = QLabel(icon_text)
        icon.setStyleSheet("color: #00ff88; font-size: 18px; background: transparent;")
        title_label = QLabel(title)
        title_label.setStyleSheet("color: white; font-weight: bold; font-size: 14px; background: transparent;")
        header_layout.addWidget(icon)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        self.layout.addLayout(header_layout)
        desc_label = QLabel(desc)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        self.layout.addWidget(desc_label)
        self.status_label = QLabel("● ACTIVE" if is_active else "")
        self.status_label.setStyleSheet("color: #00ff88; font-size: 10px; font-weight: bold; background: transparent;")
        self.layout.addWidget(self.status_label)
        self.update_style()
    def update_style(self):
        if self.is_active:
            self.setStyleSheet("SidebarCard { background-color: #1a1a1a; border: 1px solid #00ff88; border-radius: 8px; }")
        else:
            self.setStyleSheet("SidebarCard { background-color: #111111; border: 1px solid #333333; border-radius: 8px; } SidebarCard:hover { border: 1px solid #555; }")
    def set_active(self, active):
        self.is_active = active
        self.status_label.setText("● ACTIVE" if active else "")
        self.update_style()
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

class CameraThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)
    def __init__(self, face_engine):
        super().__init__()
        self.face_engine = face_engine
        self.running = True
    def run(self):
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        while self.running:
            ret, cap_frame = cap.read()
            if ret:
                self.change_pixmap_signal.emit(cap_frame)
            time.sleep(0.03)
        cap.release()
    def stop(self):
        self.running = False
        self.wait()

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
        
        bottom_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(bottom_layout)

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
        
        if typed_pwd != self.app.saved_password:
            self._fail("ACCESS DENIED: Invalid Rhythm.")
            return

        pad_len = self.target_len - len(dts)
        if pad_len > 0:
            dts.extend([0.0] * pad_len)
        elif pad_len < 0:
            dts = dts[:self.target_len]

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
            
            self.verify_thread = AITaskThread(self.app.face_engine.verify_user, self.app.live_frame.copy())
            # Bind the score to the signal so the next step knows whether to skip LSTM
            self.verify_thread.result_signal.connect(lambda match, d=dts, s=score: self._continue_deep_evaluation(match, d, s))
            self.verify_thread.error_signal.connect(lambda e: self._fail(f"FACE AI ERROR: {str(e)[:30]}"))
            self.verify_thread.start()
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
        
        try:
            lstm_success, lstm_score = self.app.keystroke_engine.verify_deep_learning(dts)
        except Exception as e:
            self._fail(f"LSTM ERROR: {str(e)}")
            return
            
        if lstm_success:
            self.status_lbl.setText(f"ACCESS GRANTED (Match: {lstm_score:.2f} via LSTM Deep-Check)")
            self.status_lbl.setStyleSheet("color: #00ff88; font-size: 16px; font-weight: bold; font-family: 'Consolas', monospace;")
            QApplication.processEvents()
            time.sleep(0.5)
            self.accept()
        else:
            self._fail(f"ACCESS DENIED: Deep Rhythm Mismatch (Score: {lstm_score:.2f} via LSTM)")

    def _fail(self, msg):
        self.status_lbl.setText(msg)
        self.status_lbl.setStyleSheet("color: #ff3333; font-size: 14px; font-weight: bold; font-family: 'Consolas', monospace;")
        self.tms.clear()
        self.pwd_input.setReadOnly(False)
        self.pwd_input.setFocus()

class CadenceApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cadence Biometric Core")
        self.resize(1100, 750) 
        self.setStyleSheet("""
            QMainWindow { background-color: #0a0a0a; }
            QWidget#main_container { background-color: #0a0a0a; font-family: 'Segoe UI', sans-serif; }
            QLabel { color: white; font-family: 'Segoe UI', sans-serif; background: transparent; }
            QLineEdit { background-color: #111111; border: 1px solid #333; color: white; padding: 12px; border-radius: 8px; font-size: 16px; }
            QLineEdit:focus { border: 1px solid #00ff88; }
            QProgressBar { border: 1px solid #333; border-radius: 4px; text-align: center; background-color: #111; height: 8px; }
            QProgressBar::chunk { background-color: #00ff88; border-radius: 4px; }
            QLabel#h1 { font-size: 22px; font-weight: bold; color: white; background: transparent; }
            QLabel#sub { color: #888888; font-size: 12px; background: transparent; }
            QPushButton#action_btn { background-color: #00ff88; color: #000; font-weight: bold; border: none; border-radius: 8px; padding: 10px 20px; font-size: 14px; }
            QPushButton#action_btn:hover { background-color: #00cc6a; }
            QPushButton#action_btn:disabled { background-color: #1a3a2a; color: #558866; }
            QPushButton#ghost_btn { background-color: transparent; color: #666; border: 1px solid #333; border-radius: 8px; padding: 6px 18px; font-size: 12px; font-weight: bold; }
            QPushButton#ghost_btn:hover { border-color: #555; color: #aaa; }
            QCheckBox { color: white; font-size: 14px; font-weight: bold; background: transparent; }
            QCheckBox::indicator { width: 20px; height: 20px; border-radius: 4px; border: 2px solid #555; background-color: #111; }
            QCheckBox::indicator:checked { background-color: #ff3333; border: 2px solid #ff3333; }
        """)
        
        self.model_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "database", "models"))
        os.makedirs(self.model_dir, exist_ok=True)
        
        self.prototxt_path = os.path.join(self.model_dir, "deploy.prototxt")
        self.caffemodel_path = os.path.join(self.model_dir, "res10_300x300_ssd_iter_140000.caffemodel")
        
        if not os.path.exists(self.prototxt_path):
            urllib.request.urlretrieve("https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt", self.prototxt_path)
        if not os.path.exists(self.caffemodel_path):
            urllib.request.urlretrieve("https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel", self.caffemodel_path)
            
        self.face_net = cv2.dnn.readNetFromCaffe(self.prototxt_path, self.caffemodel_path)
        
        self.db = DatabaseManager()
        self.keystroke_engine = CadenceKeystrokeEngine()
        self.face_engine = CadenceFaceEngine()
        self.camera_thread = None
        
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        self.last_face_box = None
        self.frame_counter = 0
        self.missing_frames = 0 
        self.is_locked = False
        self.is_locking = False  
        self.saved_password = ""
        self.is_ai_ready = self.keystroke_engine.is_quick_trained or self.keystroke_engine.is_deep_trained
        self.st = 'idl'          
        self.tms = []            
        self.flight_times = []   
        self.a_dts = []          
        self.e_dts = []          
        self.mx = 5              
        self.target_len = 0
        
        if self.is_ai_ready:
            try:
                if self.keystroke_engine.is_deep_trained:
                    self.target_len = self.keystroke_engine.lstm_model.input_shape[1]
                elif self.keystroke_engine.is_quick_trained:
                    self.target_len = self.keystroke_engine.svm_model.n_features_in_
            except Exception:
                pass
        self.esy_str = ("the quick brown fox jumps\nover the lazy sleeping dog\npack my box with five dozen\nliquor jugs and wave goodbye\nsecurity starts with good habits")
        self.typd = ""
        self.hover_ticks = 0
        self.hover_timer = QTimer(self)
        self.hover_timer.timeout.connect(self._check_taskbar_hover)
        self.hover_timer.start(500)
        central_widget = QWidget()
        central_widget.setObjectName("main_container")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.build_header())
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 15, 20, 15)
        content_layout.setSpacing(20)
        self.build_sidebar(content_layout)
        self.stack = QStackedWidget()
        self.stack.setObjectName("main_stack")
        self.stack.setStyleSheet("QStackedWidget#main_stack { background-color: #111111; border-radius: 12px; border: 1px solid #222; }")
        content_layout.addWidget(self.stack, stretch=1)
        main_layout.addLayout(content_layout, stretch=1)
        main_layout.addWidget(self.build_footer())
        self.init_views()
        self.dash_test_input.installEventFilter(self)  
        self.rhythm_input.installEventFilter(self)     
        self.installEventFilter(self)                  
        self.route(0 if self.is_ai_ready else 1)
        self.showMaximized()

    def stop_camera(self):
        if self.camera_thread and self.camera_thread.isRunning():
            self.camera_thread.stop()
            self.camera_thread = None

    def _check_taskbar_hover(self):
        if self.isFullScreen() and self.isActiveWindow():
            screen_h = self.screen().geometry().height()
            mouse_y = QCursor.pos().y()
            if mouse_y >= screen_h - 5:
                self.hover_ticks += 1
                if self.hover_ticks >= 4:
                    self.showMaximized()
                    self.hover_ticks = 0
            else:
                self.hover_ticks = 0

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if type(event) == QKeyEvent and not event.isAutoRepeat():
                k = event.key()
                if k in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
                    if self.isFullScreen(): self.showMaximized()
                    else: self.showFullScreen()
                    return True
                
                if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if obj == getattr(self, 'dash_test_input', None) and not self.dash_test_input.isReadOnly():
                        self._test_login()
                        return True
                    return super().eventFilter(obj, event)

                if k in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_CapsLock):
                    return super().eventFilter(obj, event)
                
                if k == Qt.Key.Key_Backspace:
                    if self.stack.currentIndex() == 1 and self.st == 'dp':
                        if len(self.typd) > 0:
                            self.typd = self.typd[:-1]
                            self._add_ts() 
                            self._upd_esy()
                        return True
                    else:
                        if obj == self.rhythm_input:
                            self.rhythm_input.clear()
                            self.clr_trk()
                            self._set_feedback("Typo detected. Neural rhythm corrupted. Field cleared.", "warning")
                            return True
                        elif obj == getattr(self, 'dash_test_input', None):
                            self.dash_test_input.clear()
                            self.clr_trk()
                            self.dash_result.setText("Rhythm interrupted by Backspace. Field cleared.")
                            self.dash_result.setStyleSheet("color: #ffaa33;")
                            return True
                        elif self.is_locking and hasattr(self, 'lock_screen') and obj == getattr(self.lock_screen, 'pwd_input', None):
                            self.lock_screen.pwd_input.clear()
                            self.lock_screen.tms.clear()
                            self.lock_screen.status_lbl.setText("Rhythm broken. Restarting...")
                            self.lock_screen.status_lbl.setStyleSheet("color: #ffaa33;")
                            return True
                            
                if self.stack.currentIndex() == 1 and self.st == 'dp':
                    txt = event.text()
                    if txt == '\r': txt = '\n'
                    if len(self.typd) < len(self.esy_str):
                        if txt and (txt.isprintable() or txt == '\n') and txt != "":
                            self.typd += txt
                            self._add_ts()
                            self._upd_esy()
                            if len(self.typd) >= len(self.esy_str):
                                self._fin_esy()
                            return True
                    return False

                if self.stack.currentIndex() in (0, 1):
                    self._add_ts()
                    
        return super().eventFilter(obj, event)

    def _add_ts(self):
        now = time.time()
        self.tms.append(now)
        if len(self.tms) > 1:
            f_ms = int((self.tms[-1] - self.tms[-2]) * 1000)
            self.flight_times.append(f_ms)
            if self.stack.currentIndex() == 1:
                self.update_rhythm_live_stats()

    def update_rhythm_live_stats(self):
        if not self.flight_times: return
        avg = int(sum(self.flight_times) / len(self.flight_times))
        self.stat_avg.setText(f"{avg}ms")
        self.stat_keys.setText(str(len(self.flight_times)))
        self.timing_chart.update_data(self.flight_times)

    def get_dts(self):
        dts = []
        for i in range(1, len(self.tms)):
            dts.append(self.tms[i] - self.tms[i-1])
        return dts

    def clr_trk(self):
        self.tms.clear()
        self.flight_times.clear()

    def route(self, index):
        self.stop_camera()
        self.stack.setCurrentIndex(index)
        self.card_rhythm.set_active(index == 1)
        self.card_face.set_active(index == 2)
        self.card_ctrl.set_active(index == 0)
        if index == 0:
            self.clr_trk()
            self.dash_test_input.clear()
            self.dash_test_input.setFocus()
        elif index == 1:
            self._reset_ui()
        elif index == 2:
            self.target_cam_label = self.face_cam_label
            self.face_cam_label.setText("📷 Camera Inactive. Click below to activate.")
            self.face_cam_label.setStyleSheet("color: #555; font-size: 18px; background-color: #0a0a0a;")
            self.face_progress.setVisible(False)
            self.face_progress.setValue(0)
            self.start_face_btn.setVisible(True)
            self.start_face_btn.setEnabled(True)
            self.start_face_btn.setText("Turn On Camera")
            self.face_status_lbl.setText("")
            self.last_face_box = None
            self.frame_counter = 0
            self.missing_frames = 0

    def start_camera_for_view(self, target_label):
        if self.camera_thread is None or not self.camera_thread.isRunning():
            self.target_cam_label = target_label
            self.camera_thread = CameraThread(self.face_engine)
            self.camera_thread.change_pixmap_signal.connect(self.update_camera_frame)
            self.camera_thread.start()

    def update_camera_frame(self, cv_img):
        cv_img = cv2.flip(cv_img, 1)
        h, w = cv_img.shape[:2]

        gray_frame = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

        if self.stack.currentIndex() == 2 or self.is_locking:
            self.frame_counter += 1
            if self.frame_counter % 2 == 0:
                small_gray = cv2.resize(gray_frame, (w // 2, h // 2))
                
                ai_vision_frame = cv2.equalizeHist(small_gray)
                
                faces = self.face_cascade.detectMultiScale(ai_vision_frame, scaleFactor=1.1, minNeighbors=6, minSize=(60, 60))
                
                if len(faces) > 0:
                    self.missing_frames = 0 
                    faces = sorted(faces, key=lambda x: x[2]*x[3], reverse=True)
                    x, y, w_face, h_face = faces[0]
                    x, y, w_face, h_face = x*2, y*2, w_face*2, h_face*2
                    
                    if self.last_face_box is None:
                        self.last_face_box = (x, y, w_face, h_face)
                    else:
                        ox, oy, ow, oh = self.last_face_box
                        self.last_face_box = (
                            int(0.6 * x + 0.4 * ox), int(0.6 * y + 0.4 * oy),
                            int(0.6 * w_face + 0.4 * ow), int(0.6 * h_face + 0.4 * oh)
                        )
                else:
                    self.missing_frames += 1
                    if self.missing_frames > 6:
                        self.last_face_box = None

        if self.last_face_box is not None:
            x, y, w_face, h_face = self.last_face_box
            
            x1, y1 = max(0, x), max(0, y)
            x2, y2 = min(w, x + w_face), min(h, y + h_face)
            
            roi_gray = gray_frame[y1:y2, x1:x2]
            roi_color = cv_img[y1:y2, x1:x2]
            
            if roi_gray.size > 0:
                face_brightness = max(1.0, np.mean(roi_gray)) 
                
                if face_brightness < 110:
                    exponent = math.log(130.0 / 255.0) / math.log(face_brightness / 255.0)
                    table = np.array([((i / 255.0) ** exponent) * 255 for i in np.arange(0, 256)]).astype("uint8")
                    
                    cv_img[y1:y2, x1:x2] = cv2.LUT(roi_color, table)
                    gray_frame[y1:y2, x1:x2] = cv2.LUT(roi_gray, table)

        self.live_frame = cv_img.copy()

        if (self.stack.currentIndex() == 2 or self.is_locking) and self.last_face_box is not None:
            x, y, w_face, h_face = self.last_face_box
            roi_corrected = gray_frame[max(0, y):min(h, y+h_face), max(0, x):min(w, x+w_face)]
            if roi_corrected.size > 0:
                brightness = np.mean(roi_corrected)
                b_score = min(100, (brightness / 130.0) * 100) if brightness < 130 else min(100, ((255 - brightness) / 125.0) * 100)
                sharpness = cv2.Laplacian(roi_corrected, cv2.CV_64F).var()
                s_score = min(100, (sharpness / 200.0) * 100)
                vis_score = int((b_score * 0.4) + (s_score * 0.6))
                
                if vis_score >= 80: color = (0, 255, 136); status_txt = f"Visibility: {vis_score}% (OPTIMAL)"
                elif vis_score >= 50: color = (0, 200, 255); status_txt = f"Visibility: {vis_score}% (ACCEPTABLE)"
                else: color = (0, 0, 255); status_txt = f"Visibility: {vis_score}% (POOR)"
                
                cv2.rectangle(cv_img, (x, y), (x+w_face, y+h_face), color, 2)
                cv2.rectangle(cv_img, (x, y-30), (x+w_face, y), color, -1)
                cv2.putText(cv_img, status_txt, (x+5, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                
        label_text = "LIVE AUTHENTICATION FEED" if self.is_locking else "HD LIVE NEURAL PREVIEW"
        cv2.putText(cv_img, label_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 136), 2)

        color_frame = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        color_frame = np.ascontiguousarray(color_frame)
        bytes_per_line = 3 * w
        qt_img = QImage(color_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self.target_cam_label.setPixmap(QPixmap.fromImage(qt_img).scaled(
            self.target_cam_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))

    def build_header(self):
        header = QFrame()
        header.setObjectName("app_header")
        header.setFixedHeight(60)
        header.setStyleSheet("QFrame#app_header { background-color: #0f0f0f; border-bottom: 1px solid #222; }")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)
        logo = QLabel("🛡️ CADENCE BIOMETRIC")
        logo.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        layout.addWidget(logo)
        sub = QLabel("Dual-Layer Authentication System v2.0")
        sub.setStyleSheet("color: #666;")
        layout.addWidget(sub)
        layout.addStretch()
        self.sys_status = QLabel("● AI READY" if self.is_ai_ready else "● AI UNTRAINED")
        self.sys_status.setStyleSheet(f"color: {'#00ff88' if self.is_ai_ready else '#ff3333'}; font-weight: bold;")
        layout.addWidget(self.sys_status)
        return header

    def build_sidebar(self, parent_layout):
        sidebar = QFrame()
        sidebar.setFixedWidth(280)
        sidebar.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.card_ctrl = SidebarCard("System Controls", "Manage security overrides and monitor access.", "⚙️")
        self.card_ctrl.clicked.connect(lambda: self.route(0))
        layout.addWidget(self.card_ctrl)
        self.card_rhythm = SidebarCard("Setup Password Rhythm", "Configure keystroke dynamics with LSTM neural network analysis.", "⌨️")
        self.card_rhythm.clicked.connect(lambda: self.route(1))
        layout.addWidget(self.card_rhythm)
        self.card_face = SidebarCard("Setup Face ID", "Initialize real-time facial recognition with HD scanning.", "👁️")
        self.card_face.clicked.connect(lambda: self.route(2))
        layout.addWidget(self.card_face)
        layout.addStretch()
        parent_layout.addWidget(sidebar)

    def build_footer(self):
        footer = QFrame()
        footer.setObjectName("app_footer")
        footer.setFixedHeight(40)
        footer.setStyleSheet("QFrame#app_footer { background-color: #0a0a0a; border-top: 1px solid #222; }")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 5, 20, 5)
        def make_stat(title, val, color, obj_name=None):
            w = QWidget()
            l = QVBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            t = QLabel(title)
            t.setStyleSheet("color: #666; font-size: 10px; background: transparent;")
            v = QLabel(val)
            if obj_name: v.setObjectName(obj_name)
            v.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px; background: transparent;")
            l.addWidget(t)
            l.addWidget(v)
            return w
        layout.addWidget(make_stat("AUTHENTICATION LAYERS", "2", "#00ff88"))
        layout.addWidget(make_stat("DEVICE UID", f"{self.db.get_device_uid()}", "#ffcc00", "uid_label"))
        layout.addStretch()
        lbl_hint = QLabel("PRESS [ESC] OR [F11] TO TOGGLE FULLSCREEN")
        lbl_hint.setStyleSheet("color: #444; font-size: 10px; font-weight: bold;")
        layout.addWidget(lbl_hint)
        layout.addSpacing(20)
        layout.addWidget(make_stat("SECURITY LEVEL", "MAXIMUM", "#00ff88"))
        return footer

    def init_views(self):
        self.stack.addWidget(self.build_dashboard())  
        self.stack.addWidget(self.build_rhythm())     
        self.stack.addWidget(self.build_face())       

    def build_dashboard(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(25)
        title = QLabel("System Dashboard", objectName="h1")
        layout.addWidget(title)
        card = QFrame()
        card.setObjectName("dash_card")
        card.setStyleSheet("QFrame#dash_card { background-color: #151515; border: 1px solid #333; border-radius: 8px; }")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(30, 30, 30, 30)
        self.test_lock_btn = QPushButton("🔒 Test Cadence Lock Screen")
        self.test_lock_btn.setStyleSheet("""
            QPushButton { background-color: #0055ff; color: white; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px; border: none; }
            QPushButton:hover { background-color: #0044cc; }
        """)
        self.test_lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_lock_btn.clicked.connect(self._launch_mock_lock)
        card_layout.addWidget(self.test_lock_btn)
        card_layout.addStretch()
        self.wipe_btn = QPushButton("🛑 Wipe Biometrics")
        self.wipe_btn.setStyleSheet("background-color: transparent; border: 1px solid #ff3333; color: #ff3333; padding: 10px 20px; border-radius: 8px; font-weight: bold;")
        self.wipe_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wipe_btn.clicked.connect(self._wipe_system)
        card_layout.addWidget(self.wipe_btn)
        layout.addWidget(card)
        test_lbl = QLabel("Test Neural Rhythm Engine (Inline)", objectName="h2")
        test_lbl.setStyleSheet("font-size: 18px; font-weight: bold; margin-top: 20px; background: transparent;")
        layout.addWidget(test_lbl)
        self.dash_test_input = QLineEdit()
        self.dash_test_input.setPlaceholderText("Type your password to test Cadence...")
        self.dash_test_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        layout.addWidget(self.dash_test_input)
        self.dash_result = QLabel("")
        self.dash_result.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.dash_result)
        layout.addStretch()
        return w

    def _wipe_system(self):
        import shutil
        import gc
        import time
        import stat
        from tensorflow.keras import backend as K
        
        reply = QMessageBox.question(self, 'Confirm System Wipe', 
                                     "Are you sure? This will permanently delete your neural keystroke profile and your encrypted face baseline.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.stop_camera()
            self.keystroke_engine = None
            self.face_engine = None
            self.db = None
            
            K.clear_session()
            gc.collect()
            time.sleep(0.5) 
            
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            models_dir = os.path.join(base_dir, "database", "models")
            
            if os.path.exists(models_dir): 
                for root, dirs, files in os.walk(models_dir, topdown=False):
                    for name in files:
                        if name.endswith(".prototxt") or name.endswith(".caffemodel"):
                            continue
                        file_path = os.path.join(root, name)
                        os.chmod(file_path, stat.S_IWRITE) 
                        try:
                            os.remove(file_path)
                        except OSError:
                            pass
                    for name in dirs:
                        try:
                            os.rmdir(os.path.join(root, name))
                        except Exception:
                            pass
                try:
                    os.rmdir(models_dir)
                except OSError:
                    pass

            for root, dirs, files in os.walk(base_dir, topdown=False):
                for name in dirs:
                    if name == "__pycache__":
                        cache_dir = os.path.join(root, name)
                        shutil.rmtree(cache_dir, ignore_errors=True)
            
            self.db = DatabaseManager()
            self.keystroke_engine = CadenceKeystrokeEngine()
            self.face_engine = CadenceFaceEngine()
            
            self.is_ai_ready = False
            self.saved_password = ""
            self.target_len = 0
            
            self.sys_status.setText("● AI UNTRAINED")
            self.sys_status.setStyleSheet("color: #ff3333; font-weight: bold;")
            self.dash_result.setText("System Wiped. All Biometrics Destroyed.")
            self.dash_result.setStyleSheet("color: #ff3333;")

            uid_lbl = self.findChild(QLabel, "uid_label")
            if uid_lbl:
                uid_lbl.setText(self.db.get_device_uid())
            
            self.route(1)
            self._set_feedback("System wiped successfully. RAM and PyCache cleared.", "ok")

    def _launch_mock_lock(self):
        if not self.is_ai_ready:
            QMessageBox.warning(self, "AI Untrained", "Please train the Cadence Neural Network before testing the Lock Screen.")
            return
        self.is_locking = True
        self.lock_screen = MockWindowsLockScreen(self, self)
        self.start_camera_for_view(self.lock_screen.camera_lbl)
        self.lock_screen.exec()
        self.is_locking = False
        self.stop_camera()

    def _test_login(self):
        typed_pwd = self.dash_test_input.text()
        dts = self.get_dts()
        self.dash_test_input.clear()
        
        self.dash_test_input.setReadOnly(True)
        
        if not self.is_ai_ready:
            self.dash_result.setText("⚠️ Neural Network is not trained yet. Go to Setup.")
            self.dash_result.setStyleSheet("color: #ffaa33;")
            self.clr_trk()
            self.dash_test_input.setReadOnly(False)
            self.dash_test_input.setFocus()
            return
            
        if typed_pwd != self.saved_password:
            self.dash_result.setText("❌ ACCESS DENIED (Invalid Password)")
            self.dash_result.setStyleSheet("color: #ff3333;")
            self.clr_trk()
            self.dash_test_input.setReadOnly(False)
            self.dash_test_input.setFocus()
            return
            
        pad_len = self.target_len - len(dts)
        if pad_len > 0: dts.extend([0.0] * pad_len)
        elif pad_len < 0: dts = dts[:self.target_len]
        
        try:
            success, score = self.keystroke_engine.verify_quick_setup(np.array([dts]))
        except Exception as e:
            self.dash_result.setText(f"Verification Error: {e}")
            self.clr_trk()
            self.dash_test_input.setReadOnly(False)
            self.dash_test_input.setFocus()
            return
            
        if score <= 0.45:
            self.dash_result.setText(f"❌ ACCESS DENIED (Score: {score:.2f} via SVM Fast-Path)")
            self.dash_result.setStyleSheet("color: #ff3333;")
        else:
            self.dash_result.setText(f"✅ RHYTHM PASSED (Score: {score:.2f}). Proceeding to Face Check...")
            self.dash_result.setStyleSheet("color: #00ff88;")
            
        self.clr_trk()
        self.dash_test_input.setReadOnly(False)
        self.dash_test_input.setFocus()

    def build_rhythm(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(30, 20, 30, 20)
        root.setSpacing(8) 
        self.lbl_rhythm_h1 = QLabel("Initialize Security Profile", objectName="h1")
        root.addWidget(self.lbl_rhythm_h1)
        self.lbl_rhythm_sub = QLabel("Choose how you want to train your Cadence AI.", objectName="sub")
        root.addWidget(self.lbl_rhythm_sub)
        self.btn_row = QWidget()
        btn_layout = QHBoxLayout(self.btn_row)
        btn_layout.setContentsMargins(0,0,0,0)
        btn_layout.setSpacing(15)
        self.btn_q = ModeButton("Quick Setup", "⚡", "Type your chosen password 5 times.")
        self.btn_q.clicked.connect(lambda: self._start_qck())
        self.btn_d = ModeButton("Deep Learning", "🧠", "Type the baseline essay, then your password.")
        self.btn_d.clicked.connect(lambda: self._start_dp())
        btn_layout.addWidget(self.btn_q)
        btn_layout.addWidget(self.btn_d)
        root.addWidget(self.btn_row)
        self.esy_lbl = QLabel()
        self.esy_lbl.setWordWrap(True)
        self.esy_lbl.setVisible(False)
        self.esy_lbl.setObjectName("esy_lbl")
        self.esy_lbl.setMinimumHeight(150)
        self.esy_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.esy_lbl.setStyleSheet("QLabel#esy_lbl { background-color: #080808; padding: 15px; border-radius: 8px; border: 1px solid #222; }")
        root.addWidget(self.esy_lbl)
        self.inp_row = QWidget()
        inp_layout = QHBoxLayout(self.inp_row)
        inp_layout.setContentsMargins(0,0,0,0)
        self.rhythm_input = QLineEdit()
        self.rhythm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.rhythm_input.returnPressed.connect(self._on_rhythm_enter)
        self.capture_btn = QPushButton("Capture ↵")
        self.capture_btn.setObjectName("action_btn")
        self.capture_btn.setFixedHeight(40) 
        self.capture_btn.setFixedWidth(110)
        self.capture_btn.clicked.connect(self._on_rhythm_enter)
        inp_layout.addWidget(self.rhythm_input, 1)
        inp_layout.addWidget(self.capture_btn)
        self.inp_row.setVisible(False)
        root.addWidget(self.inp_row)
        self.rhythm_feedback = QLabel("")
        self.rhythm_feedback.setStyleSheet("font-size: 12px; color: #555; background: transparent;")
        root.addWidget(self.rhythm_feedback)
        self.rhythm_prog = QProgressBar()
        self.rhythm_prog.setValue(0)
        self.rhythm_prog.setTextVisible(False)
        self.rhythm_prog.setVisible(False)
        root.addWidget(self.rhythm_prog)
        grid = QGridLayout()
        grid.setSpacing(10)
        lbl_avg = QLabel("AVG TIMING"); lbl_avg.setObjectName("sub")
        self.stat_avg = QLabel("--")
        self.stat_avg.setStyleSheet("color: #00ff88; font-size: 20px; font-weight: bold; background: transparent;")
        lbl_keys = QLabel("KEYSTROKES"); lbl_keys.setObjectName("sub")
        self.stat_keys = QLabel("--")
        self.stat_keys.setStyleSheet("color: #00ff88; font-size: 20px; font-weight: bold; background: transparent;")
        lbl_sess = QLabel("SESSIONS CAPTURED"); lbl_sess.setObjectName("sub")
        self.stat_sess = QLabel("0")
        self.stat_sess.setStyleSheet("color: #00ff88; font-size: 20px; font-weight: bold; background: transparent;")
        grid.addWidget(lbl_avg, 0, 0)
        grid.addWidget(self.stat_avg, 1, 0)
        grid.addWidget(lbl_keys, 0, 1)
        grid.addWidget(self.stat_keys, 1, 1)
        grid.addWidget(lbl_sess, 0, 2)
        grid.addWidget(self.stat_sess, 1, 2)
        root.addLayout(grid)
        lbl_chart = QLabel("TIMING PATTERN"); lbl_chart.setObjectName("sub")
        root.addWidget(lbl_chart)
        self.timing_chart = TimingChart()
        root.addWidget(self.timing_chart)
        sess_header = QHBoxLayout()
        sess_title = QLabel("CAPTURED SESSIONS"); sess_title.setObjectName("sub")
        sess_header.addWidget(sess_title)
        sess_header.addStretch()
        self.clear_sess_btn = QPushButton("Clear All")
        self.clear_sess_btn.setObjectName("ghost_btn")
        self.clear_sess_btn.setFixedHeight(30)
        self.clear_sess_btn.clicked.connect(self._clr_sess)
        sess_header.addWidget(self.clear_sess_btn)
        root.addLayout(sess_header)
        self.session_scroll = QScrollArea()
        self.session_scroll.setObjectName("sess_scroll")
        self.session_scroll.setMinimumHeight(60)
        self.session_scroll.setWidgetResizable(True)
        self.session_scroll.setStyleSheet("""
            QScrollArea#sess_scroll { border: 1px solid #333; border-radius: 8px; background-color: #0d0d0d; }
            QWidget#scroll_content { background-color: transparent; }
            QScrollBar:vertical { width: 6px; background: #111; }
            QScrollBar::handle:vertical { background: #333; border-radius: 3px; }
        """)
        self.session_list_widget = QWidget()
        self.session_list_widget.setObjectName("scroll_content")
        self.session_list_layout = QVBoxLayout(self.session_list_widget)
        self.session_list_layout.setContentsMargins(6, 6, 6, 6)
        self.session_list_layout.setSpacing(4)
        self.session_list_layout.addStretch()
        self.session_scroll.setWidget(self.session_list_widget)
        root.addWidget(self.session_scroll, stretch=1)
        train_row = QHBoxLayout()
        self.train_btn = QPushButton("🧠  Train Neural Network")
        self.train_btn.setObjectName("action_btn")
        self.train_btn.setFixedHeight(40) 
        self.train_btn.setMinimumWidth(250)
        self.train_btn.setEnabled(False)
        self.train_btn.clicked.connect(self._start_training)
        train_row.addStretch()
        train_row.addWidget(self.train_btn)
        root.addLayout(train_row)
        self.train_status = QLabel("")
        self.train_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.train_status.setStyleSheet("color: #555; font-size: 11px; background: transparent;")
        root.addWidget(self.train_status)
        return w

    def _reset_ui(self):
        self.st = 'idl'
        self.mx = 5
        self.a_dts = []
        self.e_dts = []
        self.typd = ""
        self.saved_password = ""
        self.clr_trk()
        self.btn_q.set_active(False)
        self.btn_d.set_active(False)
        self.btn_row.setVisible(True)
        self.esy_lbl.setVisible(False)
        self.inp_row.setVisible(False)
        self.rhythm_prog.setVisible(False)
        self.lbl_rhythm_h1.setText("Initialize Security Profile")
        self.lbl_rhythm_sub.setText("Choose how you want to train your Cadence AI.")
        self.rhythm_input.clear()
        self.stat_avg.setText("--")
        self.stat_keys.setText("--")
        self.timing_chart.update_data([])
        self._set_feedback("")
        while self.session_list_layout.count() > 1:
            item = self.session_list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._refresh_session_ui()

    def _start_qck(self, msg=None):
        if msg is None:
            self.mx = 5
            self.a_dts = []
            self.e_dts = []
            self.saved_password = ""
            while self.session_list_layout.count() > 1:
                item = self.session_list_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
        self.st = 'qck'
        self.clr_trk()
        self.btn_q.set_active(True)
        self.btn_d.set_active(False)
        self.btn_row.setVisible(False)
        self.esy_lbl.setVisible(False)
        self.inp_row.setVisible(True)
        self.rhythm_prog.setVisible(True)
        self.lbl_rhythm_h1.setText("Quick Setup: Rhythm Capture")
        self.lbl_rhythm_sub.setText(msg if msg else "Type your chosen password and press Enter to capture your rhythm.")
        self.rhythm_input.setPlaceholderText("Enter password here...")
        self.rhythm_input.setFocus()
        self._set_feedback("")
        self._refresh_session_ui()

    def _start_dp(self):
        self.st = 'dp'
        self.mx = 1
        self.a_dts = []
        self.e_dts = []
        self.saved_password = ""
        while self.session_list_layout.count() > 1:
            item = self.session_list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.clr_trk()
        self.typd = ""
        self.btn_q.set_active(False)
        self.btn_d.set_active(True)
        self.btn_row.setVisible(False)
        self.inp_row.setVisible(False)
        self.rhythm_prog.setVisible(False)
        self.lbl_rhythm_h1.setText("Deep Learning: Baseline Capture")
        self.lbl_rhythm_sub.setText("Type the paragraph below. Errors will highlight red. Finish the paragraph to continue.")
        self.esy_lbl.setVisible(True)
        self._set_feedback("") 
        self._upd_esy()
        self.rhythm_input.clearFocus()
        self.setFocus()

    def _upd_esy(self):
        h = ""
        for i, c in enumerate(self.esy_str):
            is_cursor = (i == len(self.typd))
            is_typed = (i < len(self.typd))
            char_display = "&nbsp;" if c == ' ' else c
            if c == '\n':
                h += '<span style="background-color: #00ff88;">&nbsp;</span><br>' if is_cursor else '<br>'
                continue
            if is_typed:
                is_correct = (self.typd[i] == c)
                color = "#00ff88" if is_correct else "#ff3333"
                dec = "text-decoration: underline;" if not is_correct else ""
                h += f'<span style="color: {color}; {dec}">{char_display}</span>'
            elif is_cursor:
                h += f'<span style="color: #000000; background-color: #00ff88;">{char_display}</span>'
            else:
                h += f'<span style="color: #555555;">{char_display}</span>'
        self.esy_lbl.setText(f"<div style='font-family: Consolas; font-size: 15px; line-height: 1.4;'>{h}</div>")

    def _fin_esy(self):
        self.e_dts = self.get_dts()
        self.mx = 1
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Phase 1 Complete")
        msg_box.setText("Baseline Essay Captured Successfully!")
        msg_box.setInformativeText("The LSTM Network has captured your raw neural rhythm. Please click OK to define the actual password you will use to log in.")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setStyleSheet("QMessageBox { background-color: #111; color: white; } QLabel { color: white; } QPushButton { background-color: #00ff88; color: black; padding: 5px 15px; font-weight: bold; }")
        msg_box.exec()
        self._start_qck("Phase 2: Type your chosen password ONCE to link your profile to the neural network.")

    def _on_rhythm_enter(self):
        if self.st != 'qck': return 
        typed = self.rhythm_input.text()
        dts = self.get_dts()
        avg_ms = int(sum(dts)*1000 / len(dts)) if dts else 0
        keys_pressed = len(dts) + 1
        self.rhythm_input.clear()
        self.clr_trk()
        self.stat_avg.setText("--")
        self.stat_keys.setText("--")
        self.timing_chart.update_data([])
        if not self.a_dts:
            if len(typed) < 4:
                self._set_feedback("⚠️ Password must be at least 4 characters.", "warning")
                return
            self.saved_password = typed
            self.target_len = len(dts)
            if self.mx > 1:
                self._set_feedback(f"✅ Password locked as '{typed}'. Repeat {self.mx-1} more times to train.", "ok")
            else:
                self._set_feedback(f"✅ Password locked. Ready to compile.", "ok")
        elif typed != self.saved_password:
            self._set_feedback("⚠️ Password mismatch! Capture discarded. Please try again.", "warning")
            return
        if len(dts) > self.target_len: dts = dts[:self.target_len]
        while len(dts) < self.target_len: dts.append(0.0)
        self.a_dts.append(dts)
        self._add_session_bar(len(self.a_dts) - 1, keys_pressed, avg_ms)
        if len(self.a_dts) == 1 and self.mx > 1:
            self._set_feedback(f"✅ Password locked as '{self.saved_password}'. Capture 1/{self.mx} saved.", "ok")
        else:
            self._set_feedback(f"✅  Capture {len(self.a_dts)}/{self.mx} saved", "ok")
        self._refresh_session_ui()

    def _add_session_bar(self, idx, key_count, avg_ms):
        bar = SessionBar(idx, key_count, avg_ms)
        self.session_list_layout.insertWidget(self.session_list_layout.count() - 1, bar)
        QTimer.singleShot(50, lambda: self.session_scroll.verticalScrollBar().setValue(self.session_scroll.verticalScrollBar().maximum()))

    def _refresh_session_ui(self):
        n = len(self.a_dts)
        self.stat_sess.setText(str(n))
        pct = min(100, int((n / self.mx) * 100))
        self.rhythm_prog.setValue(pct)
        can_train = n >= self.mx
        self.train_btn.setEnabled(can_train)
        if can_train:
            self.train_btn.setText(f"🧠  Compile & Train Profile")
            self.train_status.setText("")
        else:
            self.train_status.setText(f"{self.mx - n} more captures needed to unlock training" if self.st == 'qck' else "")

    def _clr_sess(self):
        self._reset_ui()
        self._set_feedback("Sessions cleared.", "info")

    def _set_feedback(self, msg, level="info"):
        colors = {"ok": "#00cc55", "warning": "#ffaa33", "error": "#ff4444", "info": "#666666"}
        self.rhythm_feedback.setText(msg)
        self.rhythm_feedback.setStyleSheet(f"font-size: 12px; color: {colors.get(level, '#666')}; background: transparent;")

    def _start_training(self):
        if not self.a_dts: return
        self.train_btn.setEnabled(False)
        self.train_btn.setText("⏳  Training Neural Network…")
        self.train_status.setText("Running LSTM training — please wait…")
        self.train_status.setStyleSheet("color: #ffaa33; font-size: 11px; background: transparent;")

        class TrainThread(QThread):
            done = pyqtSignal(bool)
            def __init__(self, keystroke_engine, e_dts, a_dts):
                super().__init__()
                self.eng = keystroke_engine
                self.e_dts = e_dts
                self.a_dts = a_dts
            def run(self):
                try:
                    import numpy as np
                    data_array = np.array(self.a_dts)
                    if len(self.e_dts) > 0: 
                        labels = np.ones(len(data_array)) 
                        self.eng.train_deep_learning(data_array, labels)
                        self.eng.train_quick_setup(data_array) 
                    else: 
                        self.eng.train_quick_setup(data_array)
                    self.done.emit(True)
                except Exception as e:
                    print("Training Error:", e)
                    self.done.emit(False)

        self._train_thread = TrainThread(self.keystroke_engine, list(self.e_dts), list(self.a_dts))
        self._train_thread.done.connect(self._on_training_done)
        self._train_thread.start()

    def _on_training_done(self, success):
        if success:
            self.is_ai_ready = True
            try:
                if self.keystroke_engine.is_deep_trained:
                    self.target_len = self.keystroke_engine.lstm_model.input_shape[1]
                elif self.keystroke_engine.is_quick_trained:
                    self.target_len = self.keystroke_engine.svm_model.n_features_in_
            except Exception:
                pass
            self.train_btn.setText("✅  Training Complete")
            self.train_status.setText("Model saved. Neural network is now active.")
            self.train_status.setStyleSheet("color: #00cc55; font-size: 11px; background: transparent;")
            self.sys_status.setText("● AI READY")
            self.sys_status.setStyleSheet("color: #00ff88; font-weight: bold;")
            QTimer.singleShot(1500, lambda: self.route(0))
        else:
            self.train_btn.setEnabled(True)
            self.train_btn.setText("🧠  Retry Training")
            self.train_status.setText("Training failed — dimension mismatch.")
            self.train_status.setStyleSheet("color: #ff4444; font-size: 11px; background: transparent;")

    def build_face(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addWidget(QLabel("Facial Recognition Scan", objectName="h1"))
        layout.addWidget(QLabel("Position your face within the detection frame. Ensure Visibility is 'OPTIMAL' before capturing.", objectName="sub"))
        layout.addSpacing(20)
        cam_container = QFrame()
        cam_container.setObjectName("cam_container")
        cam_container.setStyleSheet("QFrame#cam_container { background-color: #050505; border: 1px solid #333; border-radius: 8px; }")
        cam_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cam_layout = QVBoxLayout(cam_container)
        self.face_cam_label = QLabel()
        self.face_cam_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.face_cam_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.face_cam_label.setMinimumSize(400, 300) 
        cam_layout.addWidget(self.face_cam_label, stretch=1)
        self.face_progress = QProgressBar()
        self.face_progress.setFixedHeight(4)
        self.face_progress.setVisible(False)
        cam_layout.addWidget(self.face_progress)
        self.start_face_btn = QPushButton("Turn On Camera")
        self.start_face_btn.setObjectName("action_btn")
        self.start_face_btn.setFixedHeight(40)
        self.start_face_btn.clicked.connect(self._handle_face_btn)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.start_face_btn)
        btn_row.addStretch()
        cam_layout.addLayout(btn_row)
        self.face_status_lbl = QLabel("")
        self.face_status_lbl.setStyleSheet("font-size: 14px; font-weight: bold; background: transparent;")
        self.face_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cam_layout.addWidget(self.face_status_lbl)
        layout.addWidget(cam_container, stretch=1) 
        return w

    def _handle_face_btn(self):
        if not self.camera_thread or not self.camera_thread.isRunning():
            self.start_camera_for_view(self.face_cam_label)
            self.start_face_btn.setText("📸 Start Capture")
            self.face_status_lbl.setText("Adjust your lighting, then press Start Capture.")
            self.face_status_lbl.setStyleSheet("color: #aaaaaa;")
        else:
            self.start_face_capture()

    def start_face_capture(self):
        self.start_face_btn.setEnabled(False)
        self.face_progress.setVisible(True)
        self.face_progress.setValue(0)
        self.face_progress.setStyleSheet("QProgressBar::chunk { background-color: #00ff88; border-radius: 4px; }")
        self.face_status_lbl.setText("Detecting Neural Landmarks...")
        self.face_status_lbl.setStyleSheet("color: #aaaaaa;")
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.update_face_scan)
        self.scan_timer.start(50)
        self.scan_val = 0

    def update_face_scan(self):
        self.scan_val += 1
        self.face_progress.setValue(self.scan_val)
        if self.scan_val >= 100:
            self.scan_timer.stop()
            if hasattr(self, 'live_frame'):
                self.face_status_lbl.setText("Compiling Neural Face Profile (Please Wait)...")
                self.face_status_lbl.setStyleSheet("color: #ffaa33;")
                QApplication.processEvents()
                
                self.enroll_thread = AITaskThread(self.face_engine.enroll_face, self.live_frame.copy())
                self.enroll_thread.result_signal.connect(self._on_enroll_finished)
                self.enroll_thread.error_signal.connect(self._on_enroll_error)
                self.enroll_thread.start()

    def _on_enroll_finished(self, success):
        if success:
            self.face_status_lbl.setText("✅ Target Locked. Profile Saved.")
            self.face_status_lbl.setStyleSheet("color: #00ff88;")
            QTimer.singleShot(1500, lambda: self.route(0))
        else:
            self.face_status_lbl.setText("❌ Detection Failed. Ensure 'OPTIMAL' visibility and try again.")
            self.face_status_lbl.setStyleSheet("color: #ff3333;")
            self.face_progress.setStyleSheet("QProgressBar::chunk { background-color: #ff3333; }")
            self.start_face_btn.setEnabled(True)
            self.start_face_btn.setText("📸 Retry Capture")

    def _on_enroll_error(self, error_msg):
        print(f"Face Enrollment Error: {error_msg}")
        self.face_status_lbl.setText("❌ AI Engine Error. Check Terminal.")
        self.face_status_lbl.setStyleSheet("color: #ff3333;")
        self.face_progress.setStyleSheet("QProgressBar::chunk { background-color: #ff3333; }")
        self.start_face_btn.setEnabled(True)
        self.start_face_btn.setText("📸 Retry Capture")

if __name__ == "__main__":
    app_gui = QApplication(sys.argv)
    window = CadenceApp()
    window.show()
    sys.exit(app_gui.exec())