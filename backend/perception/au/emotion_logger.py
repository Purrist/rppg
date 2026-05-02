# emotion_logger.py - 情绪记录模块
import os
import json
import time
import threading
from datetime import datetime
from collections import deque

class EmotionLogger:
    def __init__(self, data_dir='emodata', max_file_duration=300, min_interval=1.0):
        self.data_dir = data_dir
        self.max_file_duration = max_file_duration  # 5分钟 = 300秒
        self.min_interval = min_interval  # 最小记录间隔（秒）
        self.current_file = None
        self.current_data = None
        self.file_start_time = None
        self.record_count = 0
        self.last_log_time = 0
        self.lock = threading.Lock()
        self.enabled = True
        os.makedirs(data_dir, exist_ok=True)
        self._start_new_file()

    def _start_new_file(self):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'emotion_log_{timestamp}.json'
        self.current_file = os.path.join(self.data_dir, filename)
        self.current_data = {
            'start_time': timestamp,
            'records': [],
            'summary': {'au': {}, 'fer': {}, 'fusion': {}}
        }
        self.file_start_time = time.time()
        self.record_count = 0
        print(f"[EmotionLogger] 开始新的记录文件: {filename}")

    def _should_rotate(self):
        if time.time() - self.file_start_time >= self.max_file_duration:
            return True
        return False

    def _save_current_file(self):
        if self.current_data and self.record_count > 0:
            self.current_data['end_time'] = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.current_data['record_count'] = self.record_count
            with open(self.current_file, 'w', encoding='utf-8') as f:
                json.dump(self.current_data, f, ensure_ascii=False, indent=2)
            print(f"[EmotionLogger] 保存记录文件: {self.current_file} ({self.record_count} 条记录)")

    def log(self, au_result, fer_result, fusion_result):
        if not self.enabled:
            return
        with self.lock:
            try:
                now = time.time()
                if now - self.last_log_time < self.min_interval:
                    return
                self.last_log_time = now

                if self._should_rotate():
                    self._save_current_file()
                    self._start_new_file()

                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                record = {
                    'timestamp': timestamp,
                    'elapsed': round(time.time() - self.file_start_time, 2),
                    'au': {
                        'emotion': au_result.get('emotion', 'unknown'),
                        'confidence': au_result.get('confidence', 0),
                        'scores': au_result.get('scores', {}),
                        'pose': au_result.get('pose', '-'),
                        'pitch': au_result.get('pitch', 0),
                        'yaw': au_result.get('yaw', 0),
                        'au_features': au_result.get('au', {})
                    },
                    'fer': {
                        'label': fer_result.get('label', 'unknown'),
                        'conf': fer_result.get('conf', 0),
                        'probs_3': fer_result.get('probs_3', {})
                    },
                    'fusion': {
                        'emotion': fusion_result.get('emotion', 'unknown'),
                        'confidence': fusion_result.get('confidence', 0),
                        'scores': fusion_result.get('scores', {})
                    }
                }

                self.current_data['records'].append(record)
                self.record_count += 1

                self._update_summary(self.current_data['summary'], au_result, fer_result, fusion_result)

            except Exception as e:
                print(f"[EmotionLogger] 记录错误: {e}")

    def _update_summary(self, summary, au_result, fer_result, fusion_result):
        au_em = au_result.get('emotion', 'unknown')
        fer_em = fer_result.get('label', 'unknown')
        fus_em = fusion_result.get('emotion', 'unknown')

        for em in [au_em, fer_em, fus_em]:
            if em not in ('unknown', 'no_face', 'uncalibrated', 'out_of_range', 'speaking'):
                if em not in summary['au']:
                    summary['au'][em] = 0
                summary['au'][em] += 1

        for em in [fer_em]:
            if em not in ('unknown', 'no_face'):
                if em not in summary['fer']:
                    summary['fer'][em] = 0
                summary['fer'][em] += 1

        for em in [fus_em]:
            if em not in ('unknown', 'no_face', 'uncalibrated', 'out_of_range', 'speaking'):
                if em not in summary['fusion']:
                    summary['fusion'][em] = 0
                summary['fusion'][em] += 1

    def flush(self):
        with self.lock:
            self._save_current_file()

    def close(self):
        self.enabled = False
        with self.lock:
            self._save_current_file()
            print("[EmotionLogger] 记录器已关闭")
