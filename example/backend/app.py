import sys
from types import ModuleType

# === 启动补丁：解决 Protobuf 3.20.x 兼容性问题 ===
try:
    import google.protobuf
    if not hasattr(google.protobuf, 'runtime_version'):
        mock_runtime = ModuleType('runtime_version')
        mock_runtime.ValidateProtobufRuntimeVersion = lambda *args, **kwargs: None
        google.protobuf.runtime_version = mock_runtime
        sys.modules['google.protobuf.runtime_version'] = mock_runtime
except ImportError:
    pass

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from flask import Flask, Response
from flask_cors import CORS
# 核心导入：确保从 processor.py 导入 EmotionProcessor 类
from processor import EmotionProcessor

app = Flask(__name__)
CORS(app)

# 全局变量存储引擎实例
engine = None

@app.route('/video_feed')
def video_feed():
    def gen():
        while True:
            if engine:
                frame = engine.get_processed_frame()
                if frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # 默认 IP 或从命令行获取
    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.137.97:8080/video"
    
    print("--- 正在启动系统 ---")
    try:
        # 正确实例化类
        engine = EmotionProcessor(target_url)
        print("🚀 AI 处理引擎已就绪")
    except Exception as e:
        print(f"❌ 引擎启动失败: {e}")
        sys.exit(1)

    print(f"📡 服务地址: http://localhost:8080/video_feed")
    # 运行 Flask
    app.run(host='0.0.0.0', port=8080, threaded=True)