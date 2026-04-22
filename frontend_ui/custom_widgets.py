# frontend_ui/custom_widgets.py
from PyQt6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush

class TimingChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.data = []

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
        self.setFixedHeight(36)
        self.setStyleSheet("SessionBar { background-color: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 6px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(QLabel(f"#{index + 1}", styleSheet="color: #666; font-size: 11px; min-width: 24px; background: transparent;"))
        layout.addWidget(QLabel(f"{key_count} keys", styleSheet="color: #aaa; font-size: 11px; background: transparent;"))
        layout.addStretch()
        layout.addWidget(QLabel(f"avg {avg_ms}ms", styleSheet="color: #00ff88; font-size: 11px; font-weight: bold; background: transparent;"))

class ModeButton(QFrame):
    clicked = pyqtSignal()
    def __init__(self, text, icon, desc):
        super().__init__()
        self.setFixedHeight(94)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        
        top = QHBoxLayout()
        self.icon_lbl = QLabel(icon, styleSheet="font-size: 18px; background: transparent;")
        self.title_lbl = QLabel(text, styleSheet="color: #ccc; font-weight: bold; font-size: 15px; background: transparent;")
        top.addWidget(self.icon_lbl)
        top.addWidget(self.title_lbl)
        top.addStretch()
        layout.addLayout(top)
        
        layout.addWidget(QLabel(desc, styleSheet="color: #777; font-size: 12px; background: transparent;"))
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

class SidebarCard(QFrame):
    clicked = pyqtSignal()
    def __init__(self, title, desc, icon_text, is_active=False):
        super().__init__()
        self.setFixedHeight(120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)

        header = QHBoxLayout()
        header.addWidget(QLabel(icon_text, styleSheet="color: #00ff88; font-size: 18px; background: transparent;"))
        header.addWidget(QLabel(title, styleSheet="color: white; font-weight: bold; font-size: 14px; background: transparent;"))
        header.addStretch()
        self.layout.addLayout(header)

        lbl = QLabel(desc, styleSheet="color: #888; font-size: 11px; background: transparent;")
        lbl.setWordWrap(True)
        self.layout.addWidget(lbl)

        self.status = QLabel("", styleSheet="color: #00ff88; font-size: 10px; font-weight: bold; background: transparent;")
        self.layout.addWidget(self.status)
        self.set_active(is_active)

    def set_active(self, active):
        self.is_active = active
        self.status.setText("● ACTIVE" if active else "")
        if active:
            self.setStyleSheet("SidebarCard { background-color: #1a1a1a; border: 1px solid #00ff88; border-radius: 8px; }")
        else:
            self.setStyleSheet("SidebarCard { background-color: #111111; border: 1px solid #333333; border-radius: 8px; } SidebarCard:hover { border: 1px solid #555; }")

    def mousePressEvent(self, event):
        self.clicked.emit()