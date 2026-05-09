# -*- coding: utf-8 -*-
"""
打地鼠游戏演示模块
提供一个完整的打地鼠游戏，包含8级难度系统
"""
import os
import sys
from flask import Flask, render_template

app = Flask(__name__)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route("/")
def index():
    return render_template("game.html")

if __name__ == "__main__":
    print("=" * 60)
    print("  🎮 打地鼠游戏")
    print("=" * 60)
    print("\nWeb服务器: http://127.0.0.1:5050")
    print("=" * 60 + "\n")
    
    app.run(host="127.0.0.1", port=5050, debug=False, use_reloader=False)
