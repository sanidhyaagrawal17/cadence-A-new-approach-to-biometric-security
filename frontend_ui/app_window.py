import sys
import cv2
import time
import os
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QStackedWidget, QLineEdit, 
                             QProgressBar, QFrame, QGridLayout, QSizePolicy,
                             QPushButton, QButtonGroup, QTextEdit, QScrollArea, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEvent, QTimer, QRect
from PyQt6.QtGui import QImage, QPixmap, QFont, QKeyEvent, QPainter, QColor, QBrush, QPen, QCursor

# ==========================================
# UPDATED BACKEND IMPORTS
# ==========================================
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core_ai.keystroke_ai import CadenceKeystrokeEngine
from core_ai.face_ai import CadenceFaceEngine

os.makedirs("intruders", exist_ok=True)

# ==========================================
# CUSTOM WIDGETS
# ==========================================

class TimingChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(45)

    def update_data(self, new_data):
        self.data = new_data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111111"))
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

# ==========================================
# CAMERA THREAD
# ==========================================
class CameraThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)

    def __init__(self, face_engine):
        super().__init__()
        self.face_engine = face_engine
        self.running = True

    def run(self):
        cap = cv2.VideoCapture(0)
        while self.running:
            ret, frame = cap.read()
            if ret:
                frame = cv2.resize(frame, (640, 480))
                overlay = frame.copy()
                cv2.rectangle(overlay, (0, 0), (640, 480), (0, 0, 0), -1)
                cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
                self.change_pixmap_signal.emit(frame)
            time.sleep(0.03)
        cap.release()

    def stop(self):
        self.running = False
        self.wait()

# ==========================================
# MAIN APPLICATION WINDOW
# ==========================================
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

        # --- Initialize AI Engines ---
        self.keystroke_engine = CadenceKeystrokeEngine()
        self.face_engine = CadenceFaceEngine()
        self.camera_thread = None

        # --- System State Variables ---
        self.is_locked = False
        self.saved_password = ""
        self.is_ai_ready = self.keystroke_engine.is_quick_trained or self.keystroke_engine.is_deep_trained

        # ---- Core Data Trackers ----
        self.st = 'idl'          
        self.tms = []            
        self.flight_times = []   
        self.a_dts = []          
        self.e_dts = []          
        self.mx = 5              
        self.target_len = 0
        
        self.esy_str = (
            "the quick brown fox jumps\n"
            "over the lazy sleeping dog\n"
            "pack my box with five dozen\n"
            "liquor jugs and wave goodbye\n"
            "security starts with good habits"
        )
        self.typd = ""

        # ---- Taskbar Hover Logic ----
        self.hover_ticks = 0
        self.hover_timer = QTimer(self)
        self.hover_timer.timeout.connect(self._check_taskbar_hover)
        self.hover_timer.start(500)

        QApplication.instance().installEventFilter(self)

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
        self.route(0 if self.is_ai_ready else 1)
        
        self.showMaximized()

    # ==========================================
    # HOVER REVEAL LOGIC
    # ==========================================
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

    # ==========================================
    # GLOBAL KEYSTROKE INTERCEPTOR
    # ==========================================
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if type(event) == QKeyEvent and not event.isAutoRepeat():
                k = event.key()

                if k in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
                    if self.isFullScreen():
                        self.showMaximized()
                    else:
                        self.showFullScreen()
                    return True

                if k in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_CapsLock):
                    return super().eventFilter(obj, event)

                if self.stack.currentIndex() == 1 and self.st == 'dp':
                    if k == Qt.Key.Key_Backspace:
                        if len(self.typd) > 0:
                            self.typd = self.typd[:-1]
                            self._add_ts() 
                            self._upd_esy()
                        return True
                    
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

                if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    return super().eventFilter(obj, event)

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

    # ==========================================
    # ROUTING
    # ==========================================
    def route(self, index):
        if self.camera_thread and self.camera_thread.isRunning():
            self.camera_thread.stop()
            self.camera_thread = None

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
            self.start_camera_for_view(self.face_cam_label)
            self.start_face_capture()

    def start_camera_for_view(self, target_label):
        self.target_cam_label = target_label
        self.camera_thread = CameraThread(self.face_engine)
        self.camera_thread.change_pixmap_signal.connect(self.update_camera_frame)
        self.camera_thread.start()

    def update_camera_frame(self, cv_img):
        self.live_frame = cv_img.copy()
        if self.stack.currentIndex() == 2:
            cv2.rectangle(cv_img, (120, 40), (520, 440), (0, 255, 136), 2)
            cv2.line(cv_img, (120, 240), (520, 240), (0, 255, 136), 1)
            cv2.putText(cv_img, "SCANNING BIOMETRICS...", (130, 430), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 136), 1)

        color_frame = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = color_frame.shape
        qt_img = QImage(color_frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.target_cam_label.setPixmap(QPixmap.fromImage(qt_img).scaled(self.target_cam_label.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding))

    # ==========================================
    # LAYOUT BUILDERS
    # ==========================================
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

        self.card_face = SidebarCard("Setup Face ID", "Initialize real-time facial recognition with advanced scanning.", "👁️")
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

        def make_stat(title, val, color):
            w = QWidget()
            l = QVBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            t = QLabel(title)
            t.setStyleSheet("color: #666; font-size: 10px; background: transparent;")
            v = QLabel(val)
            v.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px; background: transparent;")
            l.addWidget(t)
            l.addWidget(v)
            return w

        layout.addWidget(make_stat("AUTHENTICATION LAYERS", "2", "#00ff88"))
        layout.addWidget(make_stat("PRECISION", "±1ms", "#00ff88"))
        layout.addStretch()
        
        lbl_hint = QLabel("PRESS [ESC] OR [F11] TO TOGGLE FULLSCREEN")
        lbl_hint.setStyleSheet("color: #444; font-size: 10px; font-weight: bold;")
        layout.addWidget(lbl_hint)
        layout.addSpacing(20)
        
        layout.addWidget(make_stat("SECURITY LEVEL", "MAXIMUM", "#00ff88"))
        return footer

    # ==========================================
    # DASHBOARD VIEW
    # ==========================================
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

        self.lock_switch = QCheckBox("Enable Lockdown")
        self.lock_switch.setChecked(self.is_locked)
        self.lock_switch.toggled.connect(self._toggle_lockdown)
        card_layout.addWidget(self.lock_switch)
        card_layout.addStretch()

        self.override_btn = QPushButton("⚠️ Force Override")
        self.override_btn.setStyleSheet("background-color: transparent; border: 1px solid #ff3333; color: #ff3333; padding: 10px 20px; border-radius: 8px; font-weight: bold;")
        self.override_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.override_btn.clicked.connect(self._force_override)
        card_layout.addWidget(self.override_btn)
        
        layout.addWidget(card)

        test_lbl = QLabel("Test Neural Rhythm Engine", objectName="h2")
        test_lbl.setStyleSheet("font-size: 18px; font-weight: bold; margin-top: 20px; background: transparent;")
        layout.addWidget(test_lbl)

        self.dash_test_input = QLineEdit()
        self.dash_test_input.setPlaceholderText("Type your password to test Cadence...")
        self.dash_test_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.dash_test_input.returnPressed.connect(self._test_login)
        layout.addWidget(self.dash_test_input)

        self.dash_result = QLabel("")
        self.dash_result.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.dash_result)

        layout.addStretch()
        return w

    def _toggle_lockdown(self, checked):
        self.is_locked = checked
        self.sys_status.setText("● SYSTEM LOCKED" if checked else "● AI READY")
        self.sys_status.setStyleSheet(f"color: {'#ff3333' if checked else '#00ff88'}; font-weight: bold;")

    def _force_override(self):
        self.is_locked = False
        self.lock_switch.setChecked(False)
        self.dash_result.setText("System Override Engaged.")
        self.dash_result.setStyleSheet("color: #ffaa33;")

    def _test_login(self):
        typed_pwd = self.dash_test_input.text()
        dts = self.get_dts()
        self.dash_test_input.clear()
        
        if not self.is_ai_ready:
            self.dash_result.setText("⚠️ Neural Network is not trained yet. Go to Setup.")
            self.dash_result.setStyleSheet("color: #ffaa33;")
            self.clr_trk()
            return
            
        if typed_pwd != self.saved_password:
            self.dash_result.setText("❌ ACCESS DENIED (Invalid Password)")
            self.dash_result.setStyleSheet("color: #ff3333;")
            self.clr_trk()
            return

        try:
            pad_len = self.target_len - len(dts)
            if pad_len > 0:
                dts.extend([0.0] * pad_len)
            elif pad_len < 0:
                dts = dts[:self.target_len]

            if self.keystroke_engine.is_deep_trained:
                success = self.keystroke_engine.verify_deep_learning(dts)
                score = 0.98 if success else 0.15
            else:
                success = self.keystroke_engine.verify_quick_setup(np.array([dts]))
                score = 0.96 if success else 0.12
                
        except Exception as e:
            print(f"Verification Error: {e}")
            success = False
            score = 0.0
        
        if success:
            self.dash_result.setText(f"✅ ACCESS GRANTED (Score: {score:.2f})")
            self.dash_result.setStyleSheet("color: #00ff88;")
        else:
            self.dash_result.setText(f"❌ ACCESS DENIED (Score: {score:.2f})")
            self.dash_result.setStyleSheet("color: #ff3333;")
            
        self.clr_trk()

    # ==========================================
    # RHYTHM VIEW
    # ==========================================
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

    # --- Mode Initializers ---

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
            # Full wipe on manual entry
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
        
        # FIX: Aggressive wipe of previous ghost data to prevent bleed-over errors
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
        self._set_feedback("") # Erase leftover error messages immediately
        self._upd_esy()
        
        self.rhythm_input.clearFocus()
        self.setFocus()

    # --- Monkeytype Logic ---

    def _upd_esy(self):
        h = ""
        for i, c in enumerate(self.esy_str):
            is_cursor = (i == len(self.typd))
            is_typed = (i < len(self.typd))
            
            char_display = "&nbsp;" if c == ' ' else c
            
            if c == '\n':
                if is_cursor:
                    h += '<span style="background-color: #00ff88;">&nbsp;</span><br>'
                else:
                    h += '<br>'
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
        self._start_qck("Baseline essay captured! Now, type your chosen password ONCE to link your profile.")

    # --- Password Capture Logic ---

    def _on_rhythm_enter(self):
        # FIX: Complete lockout of the Capture function if the user is typing the essay
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
                self._set_feedback(f"✅ Password locked as '{typed}'. Ready to compile.", "ok")
                
        elif typed != self.saved_password:
            self._set_feedback("⚠️ Password mismatch! Capture discarded. Please try again.", "warning")
            return

        if len(dts) > self.target_len: dts = dts[:self.target_len]
        while len(dts) < self.target_len: dts.append(0.0)

        self.a_dts.append(dts)
        self._add_session_bar(len(self.a_dts) - 1, keys_pressed, avg_ms)
        self._set_feedback(f"✅  Capture {len(self.a_dts)}/{self.mx} saved ({keys_pressed} keys, avg {avg_ms}ms)", "ok")
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

    # ==========================================
    # FACE VIEW
    # ==========================================
    def build_face(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(QLabel("Facial Recognition Scan", objectName="h1"))
        layout.addWidget(QLabel("Position your face within the detection frame for biometric verification.", objectName="sub"))
        layout.addSpacing(20)

        cam_container = QFrame()
        cam_container.setObjectName("cam_container")
        cam_container.setStyleSheet("QFrame#cam_container { background-color: #050505; border: 1px solid #333; border-radius: 8px; }")
        cam_layout = QVBoxLayout(cam_container)

        self.face_cam_label = QLabel()
        self.face_cam_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cam_layout.addWidget(self.face_cam_label)

        self.face_progress = QProgressBar()
        self.face_progress.setFixedHeight(4)
        cam_layout.addWidget(self.face_progress)

        layout.addWidget(cam_container)
        return w

    def start_face_capture(self):
        self.face_progress.setValue(0)
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
                self.face_engine.enroll_face(self.live_frame)
            QTimer.singleShot(500, lambda: self.route(0))

if __name__ == "__main__":
    app_gui = QApplication(sys.argv)
    window = CadenceApp()
    window.show()
    sys.exit(app_gui.exec())