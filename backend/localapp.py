import socket
from app import app

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    local_ip = get_ip()
    print(f"\n" + "="*50)
    print(f"📡 局域网前端访问: http://{local_ip}:3000")
    print(f"⚙️  后端 API 地址: http://{local_ip}:8080")
    print("="*50 + "\n")
    app.run(host="0.0.0.0", port=8080, debug=False)