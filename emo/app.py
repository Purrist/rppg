import os
import sys
import time
import threading
os.environ["FLASK_SKIP_DOTENV"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import cv2
import numpy as np
from flask import Flask, render_template, Response, jsonify, request

from detector import FaceDetector
from pose_estimator import PoseEstimator
from feature_extractor import FeatureExtractor
from emotion_mapper import EmotionMapper

app = Flask(__name__)


class InferenceEngine:
    def __init__(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        self.detector = FaceDetector()
        self.feat_ext = FeatureExtractor()
        persist = os.path.join(os.path.dirname(__file__), "data", "baselines.json")
        self.mapper = EmotionMapper(history=5, persist_path=persist)
        self.pose_est = None

        self.annotated = None
        self.lock = threading.Lock()
        self.running = False

        self.status = {
            "pose": "unknown",
            "emotion": "uncalibrated",
            "confidence": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0,
            "calibrating": False,
            "calib_pose": None,
            "calib_count": 0,
            "scores": {"calm": 0.0, "happy": 0.0, "sad": 0.0},
            "features": {},
        }

    def loop(self):
        self.running = True
        frame_id = 0
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            frame_id += 1

            if self.pose_est is None:
                h, w = frame.shape[:2]
                self.pose_est = PoseEstimator((h, w))

            ann = frame.copy()
            landmarks = self.detector.process(frame)

            if landmarks is not None:
                # 6DRepNet 对 MediaPipe 人脸框裁剪放大后推理
                pitch, yaw, roll = self.pose_est.estimate(frame, landmarks)
                features = self.feat_ext.extract(landmarks, (pitch, yaw, roll))

                if self.mapper.calibrating:
                    cnt = self.mapper.feed_calib(features)
                    with self.lock:
                        self.status["calib_count"] = cnt
                    cv2.putText(
                        ann,
                        f"CALIBRATING {self.mapper.calibrating.upper()} : {cnt}/30",
                        (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2,
                    )
                    # 满30帧自动停止并保存
                    if cnt >= 30:
                        ok = self.mapper.finish_calib(self.mapper.calibrating)
                        if ok:
                            with self.lock:
                                self.status["calibrating"] = False
                                self.status["calib_pose"] = None
                                self.status["calib_count"] = 0

                pose, emotion, conf, scores = self.mapper.predict(features, pitch, yaw)

                # 绘制关键点
                key_pts = [1, 33, 133, 159, 145, 263, 362, 386, 374,
                           61, 291, 13, 14, 152, 105, 334, 55, 285]
                for i in key_pts:
                    cv2.circle(ann, (int(landmarks[i][0]), int(landmarks[i][1])), 2, (0, 255, 0), -1)

                # 姿态角文字
                cv2.putText(ann, f"P:{pitch:5.1f}  Y:{yaw:5.1f}  R:{roll:5.1f}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                # 情绪标签
                color_map = {
                    "happy": (0, 255, 0),
                    "sad": (0, 0, 255),
                    "calm": (128, 128, 128),
                    "uncalibrated": (0, 255, 255),
                }
                color = color_map.get(emotion, (128, 128, 128))
                cv2.putText(ann, f"{emotion.upper()}  {conf:.2f}", (10, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

                # 特征值
                if features:
                    txt = (f"eye:{features.get('eye_open_avg',0):.3f}  "
                           f"mouthAR:{features.get('mouth_ar',0):.3f}  "
                           f"corner:{features.get('mouth_corner_lift',0):.1f}")
                    cv2.putText(ann, txt, (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                with self.lock:
                    self.status.update({
                        "pose": pose,
                        "emotion": emotion,
                        "confidence": round(conf, 3),
                        "pitch": round(pitch, 1),
                        "yaw": round(yaw, 1),
                        "roll": round(roll, 1),
                        "scores": {k: round(v, 3) for k, v in scores.items()},
                        "features": {k: round(float(v), 4) for k, v in features.items()},
                    })
            else:
                cv2.putText(ann, "NO FACE", (20, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                with self.lock:
                    self.status["emotion"] = "no_face"
                    self.status["scores"] = {"calm": 0.0, "happy": 0.0, "sad": 0.0}

            with self.lock:
                self.annotated = ann
            time.sleep(0.03)

    def get_frame_bytes(self):
        with self.lock:
            if self.annotated is None:
                return None
            ret, buf = cv2.imencode(".jpg", self.annotated)
            return buf.tobytes() if ret else None

    def get_status(self):
        with self.lock:
            st = dict(self.status)
            st["config"] = self.mapper.config
            return st

    def start_calib(self, pose):
        ok = self.mapper.start_calib(pose)
        if ok:
            with self.lock:
                self.status["calibrating"] = True
                self.status["calib_pose"] = pose
                self.status["calib_count"] = 0
        return ok

    def stop_calib(self, pose):
        ok = self.mapper.finish_calib(pose)
        with self.lock:
            self.status["calibrating"] = False
            self.status["calib_pose"] = None
        return ok

    def update_config(self, new_cfg):
        for pose, cfg in new_cfg.items():
            if pose in self.mapper.config:
                self.mapper.config[pose].update(cfg)

    def shutdown(self):
        self.running = False
        self.cap.release()
        self.detector.release()


engine = InferenceEngine()
threading.Thread(target=engine.loop, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


def gen_frames():
    while True:
        f = engine.get_frame_bytes()
        if f:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + f + b"\r\n"
            )
        time.sleep(0.03)


@app.route("/video_feed")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/status")
def api_status():
    return jsonify(engine.get_status())


@app.route("/api/calibrate/start", methods=["POST"])
def calib_start():
    data = request.get_json() or {}
    pose = data.get("pose", "front")
    ok = engine.start_calib(pose)
    return jsonify({"ok": ok, "pose": pose})


@app.route("/api/calibrate/stop", methods=["POST"])
def calib_stop():
    data = request.get_json() or {}
    pose = data.get("pose", "front")
    ok = engine.stop_calib(pose)
    return jsonify({"ok": ok, "pose": pose})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.get_json() or {}
        engine.update_config(data)
        return jsonify({"ok": True})
    return jsonify(engine.mapper.config)


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        engine.shutdown()