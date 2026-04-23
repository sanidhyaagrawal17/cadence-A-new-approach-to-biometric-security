# core_ai/face_ai.py
import os
import cv2
import numpy as np
from deepface import DeepFace
from cryptography.fernet import Fernet

class CadenceFaceEngine:
    def __init__(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.model_dir = os.path.join(current_dir, "..", "database", "models")
        os.makedirs(self.model_dir, exist_ok=True)
        
        # 1. Initialize AES Encryption
        self.key_path = os.path.join(self.model_dir, "vault.key")
        self._init_crypto()

        # 2. Target the encrypted custom binary instead of a .jpg
        self.baseline_path = os.path.join(self.model_dir, "face_baseline.enc")
        self.is_enrolled = os.path.exists(self.baseline_path)

    def _init_crypto(self):
        """Generates or loads the AES-256 vault key for biometric encryption."""
        # If no key exists, generate a new one and lock it down
        if not os.path.exists(self.key_path):
            self.cipher_key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(self.cipher_key)
        else:
            with open(self.key_path, 'rb') as f:
                self.cipher_key = f.read()
                
        self.cipher = Fernet(self.cipher_key)

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
            optimized_frame = self.enhance_lighting(frame)
            
            # Detect face to ensure there is actually a person in the frame
            faces = DeepFace.extract_faces(img_path=optimized_frame, enforce_detection=True, detector_backend='opencv')
            
            if len(faces) > 0:
                # Encode the image array into a raw byte buffer in RAM (Never written to disk as an image)
                success, buffer = cv2.imencode('.jpg', optimized_frame)
                if not success:
                    return False
                
                # Encrypt the raw bytes using the vault key
                encrypted_data = self.cipher.encrypt(buffer.tobytes())
                
                # Save the unreadable binary blob to the hard drive
                with open(self.baseline_path, 'wb') as f:
                    f.write(encrypted_data)
                    
                self.is_enrolled = True
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
            decrypted_bytes = self.cipher.decrypt(encrypted_data)
            
            # 3. Decode the bytes back into a NumPy array for DeepFace
            np_arr = np.frombuffer(decrypted_bytes, np.uint8)
            baseline_img_array = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            optimized_frame = self.enhance_lighting(current_frame)
            
            # DeepFace accepts the decrypted NumPy array directly (no file path needed)
            result = DeepFace.verify(
                img1_path=baseline_img_array, 
                img2_path=optimized_frame, 
                model_name="Facenet",
                detector_backend="opencv",
                distance_metric="cosine",
                enforce_detection=False 
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