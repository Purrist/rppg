import cv2
import numpy as np
import time
from flask import Flask, Response

app = Flask(__name__)
cap = cv2.VideoCapture(0)

def gen():
    while True:
        ret, frame = cap.read()
        if ret:
            _, buf = cv2.imencode('.jpg', frame)
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n'
        time.sleep(0.033)

@app.route('/video_feed')
def video_feed():
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return '<html><body><img src="/video_feed"></body></html>'

if __name__ == '__main__':
    print('Starting server on http://127.0.0.1:5001')
    app.run(host='127.0.0.1', port=5001, debug=False)
