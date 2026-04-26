import numpy as np

class FeatureExtractor:
    def __init__(self):
        self.idx = {
            'le_o': 33, 'le_i': 133, 'le_t': 159, 'le_b': 145,
            're_o': 263, 're_i': 362, 're_t': 386, 're_b': 374,
            'lb_i': 105, 'lb_o': 55, 'rb_i': 334, 'rb_o': 285,
            'ml': 61, 'mr': 291, 'mu': 13, 'md': 14,
            'nose': 1, 'chin': 152,
        }

    def extract(self, landmarks, pose):
        pitch, yaw, roll = pose
        f = {}

        le_h = self._dist(landmarks, 'le_t', 'le_b')
        le_w = self._dist(landmarks, 'le_o', 'le_i')
        re_h = self._dist(landmarks, 're_t', 're_b')
        re_w = self._dist(landmarks, 're_o', 're_i')
        f['eye_open_L'] = float(le_h / (le_w + 1e-6))
        f['eye_open_R'] = float(re_h / (re_w + 1e-6))
        f['eye_open_avg'] = float((f['eye_open_L'] + f['eye_open_R']) / 2)

        f['brow_height_L'] = float(self._point_to_line_dist(landmarks, 'lb_i', 'le_o', 'le_i'))
        f['brow_height_R'] = float(self._point_to_line_dist(landmarks, 'rb_i', 're_o', 're_i'))
        f['brow_height_avg'] = float((f['brow_height_L'] + f['brow_height_R']) / 2)
        f['brow_inner_dist'] = float(self._dist(landmarks, 'lb_i', 'rb_i'))

        mw = self._dist(landmarks, 'ml', 'mr')
        mh = self._dist(landmarks, 'mu', 'md')
        f['mouth_ar'] = float(mh / (mw + 1e-6))
        f['mouth_width'] = float(mw)

        my = (landmarks[self.idx['mu']][1] + landmarks[self.idx['md']][1]) / 2
        cy = (landmarks[self.idx['ml']][1] + landmarks[self.idx['mr']][1]) / 2
        f['mouth_corner_lift'] = float(my - cy)

        f['pitch'] = float(pitch)
        f['yaw'] = float(yaw)
        f['roll'] = float(roll)
        return f

    def _dist(self, lm, a, b):
        return float(np.linalg.norm(lm[self.idx[a]] - lm[self.idx[b]]))

    def _point_to_line_dist(self, lm, p, a, b):
        pt, a1, b1 = lm[self.idx[p]], lm[self.idx[a]], lm[self.idx[b]]
        ab = b1 - a1
        t = np.clip(np.dot(pt - a1, ab) / (np.dot(ab, ab) + 1e-6), 0, 1)
        return float(np.linalg.norm(pt - (a1 + t * ab)))