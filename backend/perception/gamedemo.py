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
from flask import Flask, render_template, jsonify, request

logging.getLogger('werkzeug').setLevel(logging.CRITICAL)
logging.getLogger('flask').setLevel(logging.CRITICAL)
logging.basicConfig(level=logging.CRITICAL)

app = Flask(__name__)
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
    'reactionTimes': []
}

current_moles = []
mole_show_times = {}
is_bomb = {}
hide_timers = {}
game_timer = None


def get_difficulty_config(difficulty):
    return DIFFICULTY_CONFIG.get(difficulty, DIFFICULTY_CONFIG[1])


def calculate_accuracy():
    total = game_state['hitCount'] + game_state['missCount']
    if total > 0:
        return f"{(game_state['hitCount'] / total * 100):.1f}"
    return '--'


def add_result(result_type, reaction_time, score):
    result = {
        'type': result_type,
        'time': reaction_time,
        'difficulty': game_state['difficulty'],
        'score': score
    }
    game_state['results'].append(result)
    if len(game_state['results']) > 50:
        game_state['results'] = game_state['results'][-50:]


def show_moles():
    if game_state['status'] != 'playing':
        return

    global current_moles, mole_show_times, is_bomb

    config = get_difficulty_config(game_state['difficulty'])
    
    current_moles = []
    mole_show_times = {}
    is_bomb = {}

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


def trigger_miss():
    global current_moles

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
            add_result('miss', '--', -5)
        
        current_moles.remove(hole_idx)
        mole_show_times.pop(hole_idx, None)
        is_bomb.pop(hole_idx, None)
        hide_timers.pop(hole_idx, None)

    game_state['accuracy'] = calculate_accuracy()

    if game_state['status'] == 'playing' and len(current_moles) == 0:
        next_show_time = int(time.time() * 1000) + config['interval']
        return {'next_show': next_show_time, 'moles': []}
    
    return {'next_show': hide_timers[min(hide_timers.keys())] if hide_timers else None, 
            'moles': current_moles, 'is_bomb': is_bomb}


@app.route("/")
def index():
    return render_template("game.html")


@app.route("/api/game-state", methods=['GET'])
def get_game_state():
    trigger_miss()
    return jsonify(game_state)


@app.route("/api/game-state", methods=['POST'])
def update_game_state():
    global game_state
    
    data = request.json
    if data:
        if 'difficulty' in data:
            new_diff = max(1, min(8, int(data['difficulty'])))
            game_state['difficulty'] = new_diff
            game_state['difficultyName'] = DIFFICULTY_NAMES.get(new_diff, '较难')
            data.pop('difficulty', None)
        
        game_state.update(data)
    
    return jsonify({'success': True, 'state': game_state})


@app.route("/api/game/start", methods=['POST'])
def start_game():
    global game_state, current_moles, mole_show_times, is_bomb, hide_timers
    
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
        'reactionTimes': []
    })
    
    current_moles = []
    mole_show_times = {}
    is_bomb = {}
    hide_timers = {}

    show_moles()
    
    return jsonify({
        'success': True,
        'state': game_state,
        'moles': current_moles,
        'is_bomb': is_bomb,
        'next_show': hide_timers[min(hide_timers.keys())] if hide_timers else None
    })


@app.route("/api/game/pause", methods=['POST'])
def pause_game():
    if game_state['status'] == 'playing':
        game_state['status'] = 'paused'
    elif game_state['status'] == 'paused':
        game_state['status'] = 'playing'
        show_moles()
    
    return jsonify({'success': True, 'state': game_state})


@app.route("/api/game/end", methods=['POST'])
def end_game():
    global game_state, current_moles, mole_show_times, is_bomb, hide_timers
    
    game_state['status'] = 'idle'
    game_state['running'] = False
    
    current_moles = []
    mole_show_times = {}
    is_bomb = {}
    hide_timers = {}
    
    game_state['accuracy'] = calculate_accuracy()
    
    return jsonify({'success': True, 'state': game_state})


@app.route("/api/game/hit", methods=['POST'])
def hit_mole():
    global current_moles, mole_show_times, is_bomb, hide_timers
    
    data = request.json
    hole_index = data.get('hole', -1)
    
    if game_state['status'] != 'playing' or hole_index < 0 or hole_index > 7:
        return jsonify({'success': False, 'message': '无效操作'})

    now = time.time() * 1000

    if hole_index not in current_moles:
        game_state['errorCount'] += 1
        game_state['score'] -= 5
        add_result('error', '--', -5)
        game_state['accuracy'] = calculate_accuracy()
        
        return jsonify({
            'success': True,
            'type': 'error',
            'score': game_state['score'],
            'accuracy': game_state['accuracy'],
            'moles': current_moles
        })

    reaction_time = int(now - mole_show_times.get(hole_index, now))

    if is_bomb.get(hole_index, False):
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

    config = get_difficulty_config(game_state['difficulty'])
    next_show = None
    if len(current_moles) == 0:
        next_show = int(time.time() * 1000) + config['interval']
        show_moles()
    elif hide_timers:
        next_show = hide_timers[min(hide_timers.keys())]

    return jsonify({
        'success': True,
        'type': 'bomb' if is_bomb.get(hole_index, False) else 'hit',
        'reaction_time': reaction_time,
        'score': game_state['score'],
        'accuracy': game_state['accuracy'],
        'moles': current_moles,
        'is_bomb': is_bomb,
        'next_show': next_show
    })


@app.route("/api/game/moles", methods=['GET'])
def get_moles():
    trigger_miss()
    config = get_difficulty_config(game_state['difficulty'])
    now = time.time() * 1000
    
    if game_state['status'] == 'playing' and len(current_moles) == 0:
        show_moles()
    
    next_show = hide_timers[min(hide_timers.keys())] if hide_timers else None
    
    return jsonify({
        'moles': current_moles,
        'is_bomb': is_bomb,
        'next_show': next_show,
        'config': config
    })


if __name__ == "__main__":
    print("\nWeb服务器: http://127.0.0.1:5050")
    print("API端点: http://127.0.0.1:5050/api/game-state")
    print("=" * 60 + "\n")
    
    app.run(host="127.0.0.1", port=5050, debug=False, use_reloader=False)