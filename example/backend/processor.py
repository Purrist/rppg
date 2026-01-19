import cv2
import time
import threading
import random

class EmotionProcessor:
    def __init__(self, video_url):
        self.cap = cv2.VideoCapture(video_url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.current_emotion = "neutral"
        self.confidence = 0.0
        self.fps = 0.0

        self.running = True
        self.last_time = time.time()

        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            now = time.time()
            self.fps = round(1 / (now - self.last_time + 1e-6), 1)
            self.last_time = now

            self.current_emotion = random.choice(
                ["neutral", "happy", "sad", "focused"]
            )
            self.confidence = round(random.uniform(0.6, 0.95), 2)

            time.sleep(0.03)
