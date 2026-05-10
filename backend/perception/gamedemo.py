# -*- coding: utf-8 -*-
"""
打地鼠游戏演示模块
提供一个完整的打地鼠游戏，包含8级难度系统
"""
import os
import sys
import logging
from flask import Flask, render_template, jsonify

# 完全禁用Flask日志
logging.getLogger('werkzeug').setLevel(logging.CRITICAL)
logging.getLogger('flask').setLevel(logging.CRITICAL)
logging.basicConfig(level=logging.CRITICAL)

app = Flask(__name__)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 难度名称映射
DIFFICULTY_NAMES = {
    1: '简单',
    2: '较易',
    3: '中等',
    4: '较难',
    5: '困难',
    6: '很难',
    7: '极难',
    8: '地狱'
}

# 游戏状态存储
# status: 'idle'=未开始, 'playing'=进行中, 'paused'=已暂停
game_state = {
    'status': 'idle',
    'running': False,
    'timeLeft': 180,
    'score': 0,
    'difficulty': 4,
    'difficultyName': '较难',
    'accuracy': '--',
    'results': []
}

@app.route("/")
def index():
    return render_template("game.html")

@app.route("/api/game-state", methods=['GET'])
def get_game_state():
    return jsonify(game_state)

@app.route("/api/game-state", methods=['POST'])
def update_game_state():
    from flask import request
    global game_state
    data = request.json
    
    if data:
        # DDA是唯一的难度调整源
        if 'difficulty' in data:
            new_diff = max(1, min(8, int(data['difficulty'])))
            game_state['difficulty'] = new_diff
            game_state['difficultyName'] = DIFFICULTY_NAMES.get(new_diff, '较难')
            # 删除 difficulty 字段，让其他字段可以被更新
            data.pop('difficulty', None)
        
        # 更新其他字段（但不接受非DDA来源的难度调整）
        game_state.update(data)
    
    return jsonify({'success': True, 'state': game_state})

if __name__ == "__main__":
    print("\nWeb服务器: http://127.0.0.1:5050")
    print("API端点: http://127.0.0.1:5050/api/game-state")
    print("=" * 60 + "\n")
    
    app.run(host="127.0.0.1", port=5050, debug=False, use_reloader=False)
