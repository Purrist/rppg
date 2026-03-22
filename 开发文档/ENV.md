# env.md - 环境配置

> 本文档记录项目的开发环境配置，避免库冲突。

---

## 一、后端环境（Python 3.10.x）

### 1.1 Python环境

```
环境名：rppg
路径：D:/anaconda/envs/rppg/python.exe
```

### 1.2 核心依赖

| 库名 | 版本 | 用途 |
|------|------|------|
| Flask | 3.1.2 | Web框架 |
| Flask-SocketIO | 5.6.0 | 实时通信 |
| OpenCV | 4.8.0.76 | 图像处理 |
| MediaPipe | 0.10.9 | 姿态/面部检测 |
| DeepFace | 0.0.97 | 情绪识别 |
| NumPy | 1.26.4 | 数值计算 |

### 1.3 其他依赖

```
absl-py==2.3.1
astunparse==1.6.3
attrs==25.4.0
beautifulsoup4==4.14.3
certifi==2026.1.4
charset-normalizer==3.4.4
click==8.1.8
colorama==0.4.6
contourpy==1.3.0
Flask==3.1.2
flask-cors==6.0.2
Flask-SocketIO==5.6.0
flatbuffers==25.12.19
gast==0.7.0
google-auth==2.47.0
grpcio==1.76.0
h11==0.16.0
h5py==3.14.0
importlib_metadata==8.7.1
itsdangerous==2.2.0
Jinja2==3.1.6
keras==2.15.0
Markdown==3.9
MarkupSafe==3.0.3
mediapipe==0.10.9
ml-dtypes==0.3.2
numpy==1.26.4
oauthlib==3.3.1
opencv-python==4.8.0.76
opt_einsum==3.4.0
packaging==25.0
pillow==11.3.0
protobuf==3.20.3
python-engineio==4.13.0
python-socketio==5.16.0
requests==2.32.5
retina-face==0.0.17
simple-websocket==1.1.0
six==1.17.0
sounddevice==0.5.3
tensorboard==2.15.2
tensorflow==2.15.1
typing_extensions==4.15.0
urllib3==2.6.3
Werkzeug==3.1.5
wsproto==1.2.0
```

---

## 二、前端环境（Node.js）

### 2.1 核心依赖

| 库名 | 版本 | 用途 |
|------|------|------|
| Vue | ^3.5.26 | 前端框架 |
| Nuxt | ^4.2.2 | SSR框架 |
| Socket.io-client | ^4.8.3 | WebSocket通信 |
| vue-router | ^4.6.4 | 路由管理 |

### 2.2 Nuxt配置

```typescript
// nuxt.config.ts
export default defineNuxtConfig({
  devServer: {
    host: '0.0.0.0', // 允许外部访问
    port: 3000
  },
  ssr: false // 禁用 SSR 以适配客户端 API 调用
})
```

---

## 三、VSCode配置

### 3.1 Python环境设置

```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "D:/anaconda/envs/rppg/python.exe",
  "python.terminal.activateEnvInCurrentTerminal": true,
  "python-envs.defaultEnvManager": "ms-python.python:conda",
  "python-envs.defaultPackageManager": "ms-python.python:conda"
}
```

### 3.2 调试配置

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "后端 (Flask)",
      "type": "debugpy",
      "request": "launch",
      "program": "app.py",
      "cwd": "${workspaceFolder}/backend",
      "args": ["http://192.168.3.94:8080/video", "1"],
      "console": "integratedTerminal",
      "python": "D:/anaconda/envs/rppg/python.exe"
    },
    {
      "name": "前端 (Nuxt)",
      "type": "node-terminal",
      "request": "launch",
      "command": "npm run dev",
      "cwd": "${workspaceFolder}/frontend"
    }
  ],
  "compounds": [
    {
      "name": "一键启动 (后端+前端)",
      "configurations": ["后端 (Flask)", "前端"]
    }
  ]
}
```

---

## 四、网络配置

### 4.1 端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Flask后端 | 5000 | Python服务 |
| Nuxt前端 | 3000 | 开发服务器 |
| IP Webcam | 8080 | 平板摄像头 |

### 4.2 IP地址

```
电脑IP：192.168.3.91（示例，根据实际网络变化）
平板IP：通过IP Webcam应用显示
```

---

## 五、注意事项

### 5.1 Windows兼容性

```
SocketIO必须使用 async_mode='threading' 以防止死锁
```

### 5.2 性能建议

```
DeepFace识别频率控制在0.3-0.5秒一次
严禁在stream_worker循环中直接调用识别函数
```

### 5.3 安全词规避

```
代码注释中避免使用"监控"、"老人"、"医疗"等敏感词
改用"状态感知"、"受众"、"健康干预"等中性表达
```

---

*最后更新：2024-03-08*
