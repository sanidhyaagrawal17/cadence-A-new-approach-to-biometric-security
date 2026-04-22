import os
import cv2
import joblib
from deepface import DeepFace

class CadenceFaceEngine:
    def __init__(self, model_dir="database/models"):
        self.model_dir = model_dir
        os.makedirs(self.model_dir, exist_ok=True)
        
        self.baseline_path = os.path.join(self.model_dir, "face_baseline.jpg")
        self.is_enrolled = os.path.exists(self.baseline_path)

    def enroll_face(self, frame):
        """
        Saves the current frame as the baseline identity for the genuine user.
        """
        try:
            # Detect face to ensure there is actually a person in the frame before saving
            faces = DeepFace.extract_faces(img_path=frame, enforce_detection=True, detector_backend='opencv')
            if len(faces) > 0:
                cv2.imwrite(self.baseline_path, frame)
                self.is_enrolled = True
                return True
        except ValueError:
            # Thrown if DeepFace cannot find a face in the image
            return False
        return False

    def verify_user(self, current_frame):
        """
        Compares the current webcam frame against the saved baseline image.
        Uses Facenet for fast CPU-friendly distance calculation.
        """
        if not self.is_enrolled:
            raise ValueError("No baseline face enrolled for the system.")

        try:
            # We use enforce_detection=False so the system doesn't crash if the user looks away
            result = DeepFace.verify(
                img1_path=self.baseline_path, 
                img2_path=current_frame, 
                model_name="Facenet",
                detector_backend="opencv",
                distance_metric="cosine",
                enforce_detection=False 
            )
            
            # result['verified'] is a boolean indicating if the faces match
            return result['verified']
            
        except Exception as e:
            print(f"Face verification error: {e}")
            return False

    def live_auth_stream(self):
        """
        A standalone testing loop to verify the face engine works directly from the webcam.
        """
        cap = cv2.VideoCapture(0)
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            status_text = "Not Enrolled"
            color = (0, 0, 255) # Red
            
            if self.is_enrolled:
                match = self.verify_user(frame)
                if match:
                    status_text = "AUTHENTICATED"
                    color = (0, 255, 0) # Green
                else:
                    status_text = "INTRUDER"
                    color = (0, 0, 255)
            
            cv2.putText(frame, status_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
            cv2.imshow("Cadence Vision Engine", frame)
            
            # Press 'e' to enroll the current face, 'q' to quit
            key = cv2.waitKey(1) & 0xFF
            if key == ord('e'):
                print("Enrolling face...")
                self.enroll_face(frame)
            elif key == ord('q'):
                break
                
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # Test execution
    engine = CadenceFaceEngine()
    engine.live_auth_stream()