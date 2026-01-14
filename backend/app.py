from flask import Flask, render_template
import socket

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

app = Flask(
    __name__,
    template_folder="../frontend/pages"
)

@app.route("/")
def index():
    return render_template(
        "index.html",
        local_ip=get_local_ip()
    )
