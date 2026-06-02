from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame, QCheckBox, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage
import cv2
import numpy as np
from collections import deque


class FaceSetupView(QWidget):
    enrolled_signal = pyqtSignal(bool)
    stability_signal = pyqtSignal(int)
    # no fps signal - keep face view simple

    def __init__(self, face_engine, face_net=None, parent=None):
        super().__init__(parent)
        self.face_engine = face_engine
        # we will not use the heavy DNN in this view; keep optional param for compatibility
        self.face_net = None

        self.preview = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(360, 260)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setStyleSheet('background:#050505; border: 1px solid #071; border-radius:6px;')

        self.info = QLabel("Position your face in the green box and hold still.")
        self.info.setWordWrap(True)
        self.info.setStyleSheet('color: #88ff99;')

        self.enroll_btn = QPushButton("Enroll Face")
        self.enroll_btn.setEnabled(False)
        self.enroll_btn.setObjectName("action_btn")
        self.enroll_btn.clicked.connect(self._on_enroll)

        layout = QVBoxLayout(self)
        frame = QFrame()
        frame.setStyleSheet('background: #000; border-radius: 8px;')
        fl = QVBoxLayout(frame)
        fl.addWidget(self.preview)
        layout.addWidget(frame)
        layout.addWidget(self.info)

        # no toggles: keep a simple control row

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.enroll_btn)
        layout.addLayout(btn_row)

        # lightweight Haar cascade for detection (fast)
        self.cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        # capture state
        self.latest_frame = None
        self.box = None
        self.liveness_ok = False
        self.smoothing_len = 20
        self.box_history = deque(maxlen=self.smoothing_len)
        self.stability_count = 0
        self.required_stable_frames = 12
        self.stability_iou_threshold = 0.55
        # auto-enroll disabled by default (user requested no auto-enroll)
        self.auto_enroll_enabled = False
        self._auto_enroll_cooldown = 0

        # overlay runs at ~30Hz and performs detection/smoothing off the hot frame path
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setInterval(33)
        self._overlay_timer.timeout.connect(self._process_latest_frame)
        self._overlay_timer.start()
        # no stabilization state (we use simple detection + smoothing)

    def update_frame(self, frame):
        """Receive high-rate frames from the camera thread; keep a lightweight copy only."""
        if frame is None:
            return
        # store latest frame for overlay processing; avoid heavy ops here
        self.latest_frame = frame

    def _process_latest_frame(self):
        if self.latest_frame is None:
            return
        frame = self.latest_frame.copy()
        h, w = frame.shape[:2]

        # convert to grayscale and downscale for fast cascade detection
        small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        # tuned for speed/sensitivity: slightly lower minNeighbors and larger minSize to reduce false positives
        faces = self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(48, 48))

        detected_box = None
        if len(faces) > 0:
            faces = sorted(faces, key=lambda x: x[2] * x[3], reverse=True)
            x, y, fw, fh = faces[0]
            # scale back to original frame size
            x, y, fw, fh = int(x * 2), int(y * 2), int(fw * 2), int(fh * 2)
            detected_box = (x, y, x + fw, y + fh)

        # update smoothing history
        self.box_history.append(detected_box)
        smoothed = self._compute_smoothed_box()
        self.box = smoothed

        # liveness via face_engine fast check
        try:
            ok, msg = self.face_engine.update_liveness(frame.copy())
            self.liveness_ok = bool(ok)
            if not self.liveness_ok:
                self.info.setText(msg)
                self.enroll_btn.setEnabled(False)
            else:
                self.info.setText("Liveness confirmed. You can enroll.")
                self.enroll_btn.setEnabled(True)
        except Exception:
            self.liveness_ok = False
            self.info.setText("Liveness unavailable. Adjust lighting and position.")
            self.enroll_btn.setEnabled(False)

        # stability counter
        if self.box is not None and self.liveness_ok:
            self.stability_count += 1
        else:
            self.stability_count = 0

        if self.auto_enroll_enabled and self.stability_count >= self.required_stable_frames and self._auto_enroll_cooldown <= 0:
            self._on_enroll()
            self._auto_enroll_cooldown = 40

        if self._auto_enroll_cooldown > 0:
            self._auto_enroll_cooldown -= 1

        # render overlay to preview and emit stability
        self._refresh_overlay()

    def _refresh_overlay(self):
        if self.latest_frame is None:
            return
        frame = self.latest_frame.copy()
        h, w = frame.shape[:2]

        if self.box is not None:
            x1, y1, x2, y2 = self.box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 136), 2)
            pct = min(1.0, self.stability_count / float(self.required_stable_frames))
            cv2.rectangle(frame, (x1, y2 + 8), (x1 + int((x2 - x1) * pct), y2 + 18), (0, 255, 136), -1)
            cv2.putText(frame, f'Stable: {int(pct*100)}%', (x1, y2 + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
        else:
            cx1, cy1 = int(w * 0.25), int(h * 0.2)
            cx2, cy2 = int(w * 0.75), int(h * 0.8)
            cv2.rectangle(frame, (cx1, cy1), (cx2, cy2), (30, 80, 30), 1)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio)
        self.preview.setPixmap(pix)

        pct = 0
        if self.required_stable_frames > 0:
            pct = min(100, int((self.stability_count / float(self.required_stable_frames)) * 100))
        try:
            self.stability_signal.emit(pct)
        except Exception:
            pass

    def _on_enroll(self):
        if self.latest_frame is None:
            return
        success = self.face_engine.enroll_face(self.latest_frame.copy())
        self.enrolled_signal.emit(bool(success))
        if success:
            self.info.setText('Enrollment successful.')
            self.enroll_btn.setEnabled(False)
        else:
            self.info.setText('Enrollment failed. Try again.')

    def _compute_smoothed_box(self):
        boxes = [b for b in self.box_history if b is not None]
        if not boxes:
            return None
        arr = np.array(boxes, dtype=float)
        mean_box = arr.mean(axis=0)

        def iou(a, b):
            x1 = max(a[0], b[0]); y1 = max(a[1], b[1]); x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
            if x2 <= x1 or y2 <= y1:
                return 0.0
            inter = (x2 - x1) * (y2 - y1)
            area_a = (a[2] - a[0]) * (a[3] - a[1])
            area_b = (b[2] - b[0]) * (b[3] - b[1])
            return inter / float(area_a + area_b - inter)

        mean_box_t = tuple(mean_box.tolist())
        overlaps = [iou(mean_box_t, tuple(b.tolist())) for b in arr]
        if np.mean(overlaps) < self.stability_iou_threshold:
            latest = self.box_history[-1] if self.box_history else None
            return latest
        return tuple(int(x) for x in mean_box_t)

    def _set_auto_enroll(self, val: bool):
        self.auto_enroll_enabled = bool(val)
    # auto-enroll toggle removed; method kept for compatibility but not used

    def set_smoothing_len(self, n: int):
        self.smoothing_len = max(5, int(n))
        old = list(self.box_history)
        self.box_history = deque(old[-self.smoothing_len:], maxlen=self.smoothing_len)

    def set_iou_threshold(self, v: float):
        try:
            self.stability_iou_threshold = float(v)
        except Exception:
            pass
