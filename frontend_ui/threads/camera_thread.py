from PyQt6.QtCore import QThread, pyqtSignal
import numpy as np
import cv2
import sys


class CameraThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)
    error_signal = pyqtSignal(str)

    def __init__(self, face_engine):
        super().__init__()
        self.face_engine = face_engine
        self.running = True
        # target frames per second (can be changed at runtime)
        self.target_fps = 45

    def run(self):
        backend = cv2.CAP_DSHOW if sys.platform == 'win32' else cv2.CAP_ANY
        cap = cv2.VideoCapture(0, backend)
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            # request a higher capture FPS where supported
            try:
                cap.set(cv2.CAP_PROP_FPS, 45)
            except Exception:
                pass
            if not cap.isOpened():
                self.error_signal.emit("Camera could not be opened. Check permissions or device.")
                return
            while self.running:
                # use grab/retrieve to lower latency on some backends
                try:
                    grabbed = cap.grab()
                except Exception:
                    grabbed = False
                if grabbed:
                    try:
                        ret, cap_frame = cap.retrieve()
                    except Exception:
                        ret = False
                        cap_frame = None
                    if ret and cap_frame is not None:
                        self.change_pixmap_signal.emit(cap_frame)
                # compute sleep based on target_fps
                try:
                    sleep_ms = max(5, int(1000.0 / float(self.target_fps)))
                except Exception:
                    sleep_ms = 22
                self.msleep(sleep_ms)
        finally:
            try:
                cap.release()
            except Exception:
                pass

    def stop(self):
        self.running = False
        self.wait()


class BackgroundVerifyThread(QThread):
    verification_signal = pyqtSignal(bool)

    def __init__(self, face_engine, frame_provider, interval_seconds=15):
        super().__init__()
        self.face_engine = face_engine
        self.frame_provider = frame_provider
        self.interval_seconds = max(5, int(interval_seconds))
        self.running = True

    def run(self):
        while self.running:
            frame = self.frame_provider()
            if frame is not None and getattr(self.face_engine, 'is_enrolled', False):
                try:
                    verified = bool(self.face_engine.verify_user(frame.copy()))
                except Exception:
                    verified = False
                self.verification_signal.emit(verified)

            for _ in range(self.interval_seconds * 10):
                if not self.running:
                    break
                self.msleep(100)

    def stop(self):
        self.running = False
        self.wait()
