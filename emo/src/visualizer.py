import cv2

class Visualizer:
    COLORS = {
        'neutral': (128,128,128), 'happy': (0,255,0), 'sad': (255,0,0),
        'surprised': (0,255,255), 'angry': (0,0,255), 'fearful': (255,0,255),
        'disgusted': (0,128,128), 'uncalibrated': (128,128,128),
    }
    
    def draw(self, frame, landmarks, pose, emotion, confidence, features=None):
        h, w = frame.shape[:2]
        p, y, r = pose
        
        if landmarks is not None:
            key_pts = [1, 33, 133, 159, 145, 263, 362, 386, 374,
                       61, 291, 13, 14, 152, 105, 334, 55, 285]
            for i in key_pts:
                cv2.circle(frame, (int(landmarks[i][0]), int(landmarks[i][1])), 2, (0,255,0), -1)
        
        cv2.putText(frame, f"P:{p:5.1f}  Y:{y:5.1f}  R:{r:5.1f}", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
        
        color = self.COLORS.get(emotion, (128,128,128))
        cv2.putText(frame, f"{emotion.upper()}  {confidence:.2f}", 
                    (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        
        if features:
            txt = (f"eye:{features.get('eye_open_avg',0):.3f}  "
                   f"mouthAR:{features.get('mouth_ar',0):.3f}  "
                   f"corner:{features.get('mouth_corner_lift',0):.1f}")
            cv2.putText(frame, txt, (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
        
        if emotion == 'uncalibrated':
            cv2.putText(frame, "Press [C] to calibrate neutral face", 
                        (w//5, h//2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        return frame