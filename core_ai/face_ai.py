# core_ai/face_ai.py
import os
import cv2
import numpy as np
from deepface import DeepFace
from database.db_manager import DatabaseManager

MP_AVAILABLE = True
try:
    import mediapipe as mp
except Exception:
    MP_AVAILABLE = False
    mp = None

class CadenceFaceEngine:
    def __init__(self, profile_name="default"):
        self.db = DatabaseManager()
        self.db.set_active_profile(profile_name, create_if_missing=True)
        self.model_dir = self.db.get_model_dir()
        os.makedirs(self.model_dir, exist_ok=True)
        self.baseline_path = self.db.get_face_baseline_path()
        self.is_enrolled = os.path.exists(self.baseline_path)
        self.required_closed_frames = 2
        self.ear_threshold = 0.25
        self.reset_liveness_state()

        self.mp_face_mesh = None
        self.mesh_detector = None
        if MP_AVAILABLE and mp is not None:
            try:
                self.mp_face_mesh = mp.solutions.face_mesh
                self.mesh_detector = self.mp_face_mesh.FaceMesh(
                    static_image_mode=False,
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
            except Exception as exc:
                print(f"[FACE CORE] MediaPipe FaceMesh unavailable; using fallback liveness/alignment. ({exc})")
                self.mp_face_mesh = None
                self.mesh_detector = None

    def reset_liveness_state(self):
        self._closed_frame_streak = 0
        self._blink_count = 0
        # Allow disabling liveness entirely via env var for testing/dev
        if os.environ.get('DISABLE_LIVENESS', '') == '1':
            self._liveness_confirmed = True
        else:
            self._liveness_confirmed = not (MP_AVAILABLE and self.mesh_detector is not None)

    def _eye_aspect_ratio(self, points):
        p2_p6 = np.linalg.norm(points[1] - points[5])
        p3_p5 = np.linalg.norm(points[2] - points[4])
        p1_p4 = np.linalg.norm(points[0] - points[3])
        if p1_p4 == 0:
            return 1.0
        return (p2_p6 + p3_p5) / (2.0 * p1_p4)

    def _align_face_frame(self, frame):
        if not MP_AVAILABLE or self.mesh_detector is None:
            return frame

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.mesh_detector.process(rgb)
        if not results.multi_face_landmarks:
            return frame

        lm = results.multi_face_landmarks[0].landmark
        h, w = frame.shape[:2]

        left_eye = np.array([lm[33].x * w, lm[33].y * h], dtype=float)
        right_eye = np.array([lm[263].x * w, lm[263].y * h], dtype=float)
        eye_center = ((left_eye + right_eye) / 2.0).tolist()
        angle = np.degrees(np.arctan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0]))

        matrix = cv2.getRotationMatrix2D(tuple(eye_center), angle, 1.0)
        return cv2.warpAffine(frame, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    def update_liveness(self, frame):
        # Honor explicit disable flag
        if os.environ.get('DISABLE_LIVENESS', '') == '1':
            self._liveness_confirmed = True
            return True, "Liveness disabled by environment variable."

        if not MP_AVAILABLE or self.mesh_detector is None:
            return True, "Liveness fallback active (MediaPipe unavailable)."

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.mesh_detector.process(rgb)
        if not results.multi_face_landmarks:
            self._closed_frame_streak = 0
            return False, "Please align your face in frame and blink once."

        lm = results.multi_face_landmarks[0].landmark
        h, w = frame.shape[:2]

        left_idx = [33, 160, 158, 133, 153, 144]
        right_idx = [362, 385, 387, 263, 373, 380]

        left_eye = np.array([[lm[i].x * w, lm[i].y * h] for i in left_idx], dtype=float)
        right_eye = np.array([[lm[i].x * w, lm[i].y * h] for i in right_idx], dtype=float)
        ear = (self._eye_aspect_ratio(left_eye) + self._eye_aspect_ratio(right_eye)) / 2.0

        if ear < self.ear_threshold:
            self._closed_frame_streak += 1
        else:
            if self._closed_frame_streak >= self.required_closed_frames:
                self._blink_count += 1
                self._liveness_confirmed = True
            self._closed_frame_streak = 0

        if self._liveness_confirmed:
            return True, "Liveness confirmed."
        return False, "Please blink to confirm liveness."

    def enhance_lighting(self, frame):
        """Applies Gamma Correction and CLAHE to completely neutralize shadows."""
        try:
            # 1. Gamma Boost for dark pixels
            gamma = 1.4 
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
            brightened = cv2.LUT(frame, table)

            # 2. CLAHE for edge micro-contrast
            lab = cv2.cvtColor(brightened, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            
            clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8))
            cl = clahe.apply(l_channel)
            
            merged_lab = cv2.merge((cl, a_channel, b_channel))
            return cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)
        except Exception:
            return frame # Fallback to original frame if enhancement fails

    def enroll_face(self, frame):
        """Extracts the face, encodes to bytes, encrypts via AES, and saves as .enc"""
        try:
            if not self._liveness_confirmed:
                print("[FACE CORE] Enrollment blocked: liveness not confirmed.")
                return False

            aligned_frame = self._align_face_frame(frame)
            optimized_frame = self.enhance_lighting(aligned_frame)
            
            # Detect face to ensure there is actually a person in the frame
            faces = DeepFace.extract_faces(img_path=optimized_frame, enforce_detection=True, detector_backend='opencv')
            
            if len(faces) > 0:
                # Encode the image array into a raw byte buffer in RAM (Never written to disk as an image)
                success, buffer = cv2.imencode('.jpg', optimized_frame)
                if not success:
                    return False
                
                # Encrypt bytes using the profile key derived from password vault material
                cipher = self.db.get_biometric_cipher()
                encrypted_data = cipher.encrypt(buffer.tobytes())
                
                # Save the unreadable binary blob to the hard drive
                with open(self.baseline_path, 'wb') as f:
                    f.write(encrypted_data)
                    
                self.is_enrolled = True
                self.reset_liveness_state()
                print(f"[FACE CORE] Encrypted Baseline successfully locked at: {self.baseline_path}")
                return True
                    
        except ValueError:
            print("[FACE CORE] No face detected. Adjust position.")
            return False
        except Exception as e:
            print(f"[FACE CORE] Unexpected enrollment crash: {e}")
            return False
            
        return False

    def verify_user(self, current_frame):
        """Decrypts the baseline in RAM and compares it against the live feed."""
        if not self.is_enrolled:
            print("[FACE CORE] Verification aborted: No baseline enrolled.")
            return False

        try:
            # 1. Read the encrypted binary from the hard drive
            with open(self.baseline_path, 'rb') as f:
                encrypted_data = f.read()
                
            # 2. Decrypt it back into raw image bytes in RAM
            cipher = self.db.get_biometric_cipher()
            decrypted_bytes = cipher.decrypt(encrypted_data)
            
            # 3. Decode the bytes back into a NumPy array for DeepFace
            np_arr = np.frombuffer(decrypted_bytes, np.uint8)
            baseline_img_array = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            aligned_frame = self._align_face_frame(current_frame)
            optimized_frame = self.enhance_lighting(aligned_frame)

            live_faces = DeepFace.extract_faces(
                img_path=optimized_frame,
                enforce_detection=True,
                detector_backend='opencv'
            )
            if len(live_faces) != 1:
                print("[FACE CORE] Verification requires exactly one live face in frame.")
                return False
            
            # DeepFace accepts the decrypted NumPy array directly (no file path needed)
            result = DeepFace.verify(
                img1_path=baseline_img_array, 
                img2_path=optimized_frame, 
                model_name="Facenet",
                detector_backend="opencv",
                distance_metric="cosine",
                enforce_detection=True 
            )
            
            return result['verified']
            
        except Exception as e:
            print(f"[FACE CORE] Decryption or Verification error: {e}")
            return False

    def live_auth_stream(self):
        """A standalone testing loop for the developer."""
        cap = cv2.VideoCapture(0)
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            status_text = "Not Enrolled"
            color = (0, 0, 255) 
            
            if self.is_enrolled:
                match = self.verify_user(frame)
                if match:
                    status_text = "AUTHENTICATED"
                    color = (0, 255, 0) 
                else:
                    status_text = "INTRUDER"
                    color = (0, 0, 255)
            
            display_frame = self.enhance_lighting(frame)
            cv2.putText(display_frame, status_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
            cv2.imshow("Cadence Vision Engine (AES Encrypted)", display_frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('e'):
                print("Enrolling face...")
                self.enroll_face(frame)
            elif key == ord('q'):
                break
                
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    engine = CadenceFaceEngine()
    engine.live_auth_stream()
