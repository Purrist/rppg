import socket
from app import app

def get_host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    ip = get_host_ip()
    port = 8080
    print(f"\n" + "="*50)
    print(f"🔥 项目已在局域网启动!")
    print(f"📱 手机/其他设备访问: http://{ip}:3000")
    print(f"💻 后端 API 地址: http://{ip}:{port}")
    print("="*50 + "\n")
    
    # host="0.0.0.0" 是局域网访问的关键
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)