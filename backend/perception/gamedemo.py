# -*- coding: utf-8 -*-
"""
打地鼠游戏演示模块
提供一个完整的打地鼠游戏，包含8级难度系统
游戏逻辑完全在后端实现
"""
import os
import sys
import time
import random
import logging
import threading
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

logging.getLogger('werkzeug').setLevel(logging.CRITICAL)
logging.getLogger('flask').setLevel(logging.CRITICAL)
logging.basicConfig(level=logging.CRITICAL)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:*"}})
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

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

DIFFICULTY_CONFIG = {
    1: {'show_time': 2500, 'interval': 1800, 'bomb_chance': 0.0, 'max_moles': 1},
    2: {'show_time': 2100, 'interval': 1500, 'bomb_chance': 0.08, 'max_moles': 1},
    3: {'show_time': 1800, 'interval': 1300, 'bomb_chance': 0.12, 'max_moles': 2},
    4: {'show_time': 1500, 'interval': 1100, 'bomb_chance': 0.16, 'max_moles': 2},
    5: {'show_time': 1300, 'interval': 950, 'bomb_chance': 0.20, 'max_moles': 2},
    6: {'show_time': 1100, 'interval': 800, 'bomb_chance': 0.25, 'max_moles': 3},
    7: {'show_time': 900, 'interval': 700, 'bomb_chance': 0.30, 'max_moles': 3},
    8: {'show_time': 750, 'interval': 600, 'bomb_chance': 0.35, 'max_moles': 3}
}

game_state = {
    'status': 'idle',
    'running': False,
    'timeLeft': 180,
    'score': 0,
    'difficulty': 4,
    'difficultyName': '较难',
    'accuracy': '--',
    'results': [],
    'hitCount': 0,
    'missCount': 0,
    'errorCount': 0,
    'reactionTimes': [],
    'seq': 0
}

current_moles = []
mole_show_times = {}
is_bomb = {}
hide_timers = {}
game_timer = None

game_lock = threading.Lock()
pause_event = threading.Event()
miss_check_timer = None
miss_check_interval = 50
game_timer_thread = None
game_timer_running = False


def game_timer_loop():
    """游戏计时器循环，每秒递减时间"""
    global game_timer_running
    while game_timer_running:
        pause_event.wait()
        
        with game_lock:
            if game_state['status'] == 'playing':
                game_state['timeLeft'] -= 1
                if game_state['timeLeft'] <= 0:
                    game_state['timeLeft'] = 0
                    game_state['status'] = 'idle'
                    game_state['running'] = False
                    game_timer_running = False
                    break
        time.sleep(1)


def get_difficulty_config(difficulty):
    return DIFFICULTY_CONFIG.get(difficulty, DIFFICULTY_CONFIG[1])


def calculate_accuracy():
    total = game_state['hitCount'] + game_state['missCount']
    if total > 0:
        return f"{(game_state['hitCount'] / total * 100):.1f}"
    return '--'


def add_result(result_type, reaction_time, score):
    game_state['seq'] += 1
    result = {
        'seq': game_state['seq'],
        'type': result_type,
        'time': reaction_time,
        'difficulty': game_state['difficulty'],
        'score': score
    }
    game_state['results'].append(result)
    if len(game_state['results']) > 50:
        game_state['results'] = game_state['results'][-50:]


def show_moles_unsafe():
    """不安全的显示地鼠函数，需要外部加锁"""
    if game_state['status'] != 'playing':
        return

    config = get_difficulty_config(game_state['difficulty'])
    
    current_moles.clear()
    mole_show_times.clear()
    is_bomb.clear()
    hide_timers.clear()

    available_holes = list(range(8))
    selected_holes = []

    main_idx = random.randint(0, len(available_holes) - 1)
    selected_holes.append(available_holes[main_idx])
    available_holes.pop(main_idx)

    bomb_count = 0
    if random.random() < config['bomb_chance']:
        bomb_count = 1 if random.random() < 0.5 else 2
    
    for _ in range(min(bomb_count, len(available_holes))):
        bomb_idx = random.randint(0, len(available_holes) - 1)
        selected_holes.append(available_holes[bomb_idx])
        available_holes.pop(bomb_idx)

    for i, hole_index in enumerate(selected_holes):
        current_moles.append(hole_index)
        mole_show_times[hole_index] = time.time() * 1000
        is_bomb[hole_index] = i > 0
        hide_timers[hole_index] = int(time.time() * 1000) + config['show_time']


def trigger_miss_unsafe():
    """不安全的超时检测函数，需要外部加锁"""
    if game_state['status'] != 'playing':
        return

    config = get_difficulty_config(game_state['difficulty'])
    now = time.time() * 1000

    missed_holes = []
    for hole_idx in list(current_moles):
        if hide_timers.get(hole_idx, 0) <= now:
            missed_holes.append(hole_idx)

    for hole_idx in missed_holes:
        if not is_bomb.get(hole_idx, False):
            game_state['missCount'] += 1
            game_state['score'] -= 5
            add_result('miss', 0, -5)
        
        if hole_idx in current_moles:
            current_moles.remove(hole_idx)
        mole_show_times.pop(hole_idx, None)
        is_bomb.pop(hole_idx, None)
        hide_timers.pop(hole_idx, None)

    game_state['accuracy'] = calculate_accuracy()

    if game_state['status'] == 'playing' and len(current_moles) == 0:
        show_moles_unsafe()


def check_miss_loop():
    """线程安全的地鼠超时检测循环"""
    while True:
        with game_lock:
            if game_state['status'] == 'idle':
                break
            if game_state['status'] == 'playing':
                trigger_miss_unsafe()
        
        time.sleep(miss_check_interval / 1000.0)


def start_miss_check_timer():
    """启动安全的地鼠超时检测定时器"""
    global miss_check_timer
    
    with game_lock:
        pause_event.set()
        
        if miss_check_timer is None or not miss_check_timer.is_alive():
            miss_check_timer = threading.Thread(target=check_miss_loop, daemon=True)
            miss_check_timer.start()


def stop_miss_check_timer():
    """停止地鼠超时检测定时器"""
    pause_event.clear()


@app.route("/")
def index():
    return render_template("game.html")


@app.route("/api/game-state", methods=['GET'])
def get_game_state():
    with game_lock:
        return jsonify(game_state)


@app.route("/api/game-state", methods=['POST'])
def update_game_state():
    """游戏状态更新 - 注意：难度只能通过 /api/game/difficulty 端点设置（仅限 perception）"""
    with game_lock:
        data = request.json
        if data:
            if 'difficulty' in data:
                data.pop('difficulty', None)
            if 'difficultyName' in data:
                data.pop('difficultyName', None)
            
            game_state.update(data)
    
        return jsonify({'success': True, 'state': game_state})


@app.route("/api/game/difficulty", methods=['POST'])
def set_difficulty():
    """设置游戏难度 - 只能通过此端点从 perception (DDA) 设置"""
    with game_lock:
        data = request.json
        if data and 'difficulty' in data:
            new_diff = max(1, min(8, int(data['difficulty'])))
            game_state['difficulty'] = new_diff
            game_state['difficultyName'] = DIFFICULTY_NAMES.get(new_diff, '较难')
            return jsonify({'success': True, 'difficulty': new_diff, 'difficultyName': game_state['difficultyName']})
    
    return jsonify({'success': False, 'message': '无效请求'})


@app.route("/api/game/start", methods=['POST'])
def start_game():
    global game_timer_thread, game_timer_running
    
    with game_lock:
        game_state.update({
            'status': 'playing',
            'running': True,
            'timeLeft': 180,
            'score': 0,
            'accuracy': '--',
            'results': [],
            'hitCount': 0,
            'missCount': 0,
            'errorCount': 0,
            'reactionTimes': [],
            'seq': 0
        })
        
        current_moles.clear()
        mole_show_times.clear()
        is_bomb.clear()
        hide_timers.clear()

        show_moles_unsafe()
    
    start_miss_check_timer()
    
    game_timer_running = True
    game_timer_thread = threading.Thread(target=game_timer_loop, daemon=True)
    game_timer_thread.start()
    
    with game_lock:
        return jsonify({
            'success': True,
            'state': game_state,
            'moles': current_moles.copy(),
            'is_bomb': is_bomb.copy(),
            'next_show': hide_timers[min(hide_timers.keys())] if hide_timers else None
        })


@app.route("/api/game/pause", methods=['POST'])
def pause_game():
    with game_lock:
        if game_state['status'] == 'playing':
            game_state['status'] = 'paused'
            pause_event.clear()
        elif game_state['status'] == 'paused':
            game_state['status'] = 'playing'
            show_moles_unsafe()
            pause_event.set()
        
        return jsonify({'success': True, 'state': game_state})


@app.route("/api/game/end", methods=['POST'])
def end_game():
    global game_timer_running
    
    game_timer_running = False
    
    with game_lock:
        game_state['status'] = 'idle'
        game_state['running'] = False
        
        current_moles.clear()
        mole_show_times.clear()
        is_bomb.clear()
        hide_timers.clear()
        
        stop_miss_check_timer()
        
        game_state['accuracy'] = calculate_accuracy()
    
        return jsonify({'success': True, 'state': game_state})


@app.route("/api/game/hit", methods=['POST'])
def hit_mole():
    data = request.json
    hole_index = data.get('hole', -1)
    
    with game_lock:
        if game_state['status'] != 'playing' or hole_index < 0 or hole_index > 7:
            return jsonify({'success': False, 'message': '无效操作'})

        now = time.time() * 1000

        if hole_index not in current_moles:
            game_state['errorCount'] += 1
            game_state['score'] -= 5
            add_result('error', 0, -5)
            game_state['accuracy'] = calculate_accuracy()
            
            return jsonify({
                'success': True,
                'type': 'error',
                'score': game_state['score'],
                'accuracy': game_state['accuracy'],
                'moles': current_moles.copy()
            })

        reaction_time = int(now - mole_show_times.get(hole_index, now))
        is_bomb_hit = is_bomb.get(hole_index, False)

        if is_bomb_hit:
            game_state['score'] -= 10
            add_result('bomb', reaction_time, -10)
        else:
            game_state['hitCount'] += 1
            game_state['score'] += 5
            game_state['reactionTimes'].append(reaction_time)
            add_result('hit', reaction_time, 5)

        current_moles.remove(hole_index)
        mole_show_times.pop(hole_index, None)
        is_bomb.pop(hole_index, None)
        hide_timers.pop(hole_index, None)

        game_state['accuracy'] = calculate_accuracy()

        return jsonify({
            'success': True,
            'type': 'bomb' if is_bomb_hit else 'hit',
            'reaction_time': reaction_time,
            'score': game_state['score'],
            'accuracy': game_state['accuracy'],
            'moles': current_moles.copy(),
            'is_bomb': is_bomb.copy(),
            'next_show': hide_timers[min(hide_timers.keys())] if hide_timers else None
        })


@app.route("/api/game/moles", methods=['GET'])
def get_moles():
    with game_lock:
        config = get_difficulty_config(game_state['difficulty'])
        next_show = hide_timers[min(hide_timers.keys())] if hide_timers else None
        
        return jsonify({
            'moles': current_moles.copy(),
            'is_bomb': is_bomb.copy(),
            'next_show': next_show,
            'config': config
        })


@app.route("/api/game/sync", methods=['GET'])
def sync_game():
    """合并接口：一次性获取游戏状态和地鼠信息"""
    with game_lock:
        config = get_difficulty_config(game_state['difficulty'])
        next_show = hide_timers[min(hide_timers.keys())] if hide_timers else None
        
        return jsonify({
            'game_state': {
                'timeLeft': game_state['timeLeft'],
                'score': game_state['score'],
                'difficulty': game_state['difficulty'],
                'difficultyName': game_state['difficultyName'],
                'accuracy': game_state['accuracy'],
                'running': game_state['running'],
                'status': game_state['status'],
                'results': game_state['results'][-20:],
                'hitCount': game_state['hitCount'],
                'missCount': game_state['missCount']
            },
            'moles': current_moles.copy(),
            'is_bomb': is_bomb.copy(),
            'next_show': next_show,
            'config': config
        })


if __name__ == "__main__":
    print("\nWeb服务器: http://127.0.0.1:5050")
    print("API端点: http://127.0.0.1:5050/api/game-state")
    print("=" * 60 + "\n")
    
    app.run(host="127.0.0.1", port=5050, debug=False, use_reloader=False)