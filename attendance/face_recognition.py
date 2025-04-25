import cv2
import numpy as np
import base64
import os
from PIL import Image
import io

class FaceRecognizer:
    def __init__(self):
        # Initialize face detection cascade
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.faces_dir = 'attendance/face_data'
        self.min_face_size = 100  # Minimum face size in pixels
        self.max_faces = 1  # Maximum number of faces allowed
        self.similarity_threshold = 0.85  # Threshold for face matching (0-1)
        
        # Create faces directory if it doesn't exist
        if not os.path.exists(self.faces_dir):
            os.makedirs(self.faces_dir)
    
    def preprocess_image(self, image_data):
        try:
            # Decode base64 image
            image_data = image_data.split(',')[1]
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes))
            
            # Convert to numpy array
            img_array = np.array(image)
            
            # Convert to grayscale
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            return gray
        except Exception as e:
            print(f"Error preprocessing image: {str(e)}")
            return None
    
    def detect_face(self, gray):
        try:
            # Detect faces with stricter parameters
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=8,  # More strict filtering for faces
                minSize=(self.min_face_size, self.min_face_size)
            )
            
            if len(faces) == 0:
                return None, "No face detected. Ensure only your face is visible."
            
            if len(faces) > self.max_faces:
                return None, "Multiple faces detected. Ensure only your face is in the frame."
            
            # Get the first face
            (x, y, w, h) = faces[0]
            
            # Ensure face is square (reduce capturing of shoulders)
            face_height = int(1.1 * h)  # Slightly extend height
            y = max(0, y - int(0.05 * h))  # Move up slightly to avoid shoulders
            
            face = gray[y:y+face_height, x:x+w]
            
            # Resize face to standard size
            face = cv2.resize(face, (200, 200))
            
            return face, None
        except Exception as e:
            print(f"Error detecting face: {str(e)}")
            return None, "Error detecting face"
    
    def calculate_similarity(self, face1, face2):
        try:
            # Resize both faces to the same size
            face1 = cv2.resize(face1, (200, 200))
            face2 = cv2.resize(face2, (200, 200))
            
            # Calculate normalized cross correlation
            similarity = cv2.matchTemplate(face1, face2, cv2.TM_CCOEFF_NORMED)[0][0]
            return similarity
        except Exception as e:
            print(f"Error calculating similarity: {str(e)}")
            return 0
    
    def train(self, face, user_id):
        try:
            # Save the face image
            face_path = os.path.join(self.faces_dir, f'user_{user_id}.jpg')
            cv2.imwrite(face_path, face)
            return True
        except Exception as e:
            print(f"Error training face: {str(e)}")
            return False
    
    def predict(self, image_data, user_id):
        try:
            # Preprocess the image
            gray = self.preprocess_image(image_data)
            if gray is None:
                return {'success': False, 'message': 'Error preprocessing image'}
            
            # Detect and extract face
            face, error = self.detect_face(gray)
            if face is None:
                return {'success': False, 'message': error}
            
            # Load the stored face
            stored_face_path = os.path.join(self.faces_dir, f'user_{user_id}.jpg')
            if not os.path.exists(stored_face_path):
                return {'success': False, 'message': 'Face data not found. Please train your face first.'}
            
            stored_face = cv2.imread(stored_face_path, cv2.IMREAD_GRAYSCALE)
            
            # Calculate similarity
            similarity = self.calculate_similarity(face, stored_face)
            
            if similarity >= self.similarity_threshold:
                return {'success': True, 'message': 'Face verified successfully'}
            else:
                return {'success': False, 'message': 'Face verification failed. Ensure only your face is in the frame and try again.'}
                
        except Exception as e:
            print(f"Error in predict: {str(e)}")
            return {'success': False, 'message': 'Error processing face recognition'}
