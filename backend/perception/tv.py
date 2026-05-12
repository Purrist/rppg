"""娱乐中心 - Flask 后端"""
from flask import Flask, send_file, send_from_directory
import os

app = Flask(__name__)

# 静态文件目录配置
app.static_folder = 'static'
app.static_url_path = '/static'


@app.route('/')
def index():
    return send_file('templates/tv.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


if __name__ == '__main__':
    print('=' * 50)
    print('  娱乐中心 - http://localhost:5001')
    print('=' * 50)
    app.run(host='0.0.0.0', port=5001, debug=True)
