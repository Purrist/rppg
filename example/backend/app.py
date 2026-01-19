from flask import Flask, jsonify, Response
from flask_cors import CORS
import cv2

app = Flask(__name__)
CORS(app)  # 先用最宽松的

camera = cv2.VideoCapture(0)  # 或你的 IP Webcam URL


@app.route("/")
def index():
    return jsonify({"msg": "backend alive"})


def gen_frames():
    while True:
        success, frame = camera.read()
        if not success:
            continue
        _, buffer = cv2.imencode(".jpg", frame)
        frame_bytes = buffer.tobytes()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )


@app.route("/video")
def video():
    return Response(
        gen_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/status")
def status():
    return jsonify({
        "emotion": "neutral",
        "confidence": 0.5,
        "fps": 25
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
