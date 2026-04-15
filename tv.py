import requests
import time
import urllib.parse
from flask import Flask, render_template_string, request

app = Flask(__name__)
DEFAULT_COVER = "https://via.placeholder.com/400x225?text=无封面"

# ===================== 核心配置 =====================
# 视频解析接口
PARSE_API = "https://api.bugpk.com/api/videosjx"
API_CALL_DELAY = 3  # 接口限制：3秒调用1次
last_call_time = 0

# 影视分类配置
CATEGORIES = [
    {
        "id": "movie",
        "name": "电影",
        "api_url": "https://movie.douban.com/j/search_subjects?type=movie&tag=热门&page_limit=20",
        "icon": "🎬"
    },
    {
        "id": "tv",
        "name": "电视剧",
        "api_url": "https://movie.douban.com/j/search_subjects?type=tv&tag=热门&page_limit=20",
        "icon": "📺"
    },
    {
        "id": "opera",
        "name": "戏曲",
        "api_url": "https://movie.douban.com/j/search_subjects?type=movie&tag=戏曲&page_limit=20",
        "icon": "🎭"
    },
    {
        "id": "anime",
        "name": "动漫",
        "api_url": "https://movie.douban.com/j/search_subjects?type=tv&tag=动画&page_limit=20",
        "icon": "🐱"
    }
]

# ===================== 数据解析函数 =====================
def parse_douban(data):
    videos = []
    for item in data.get("subjects", []):
        videos.append({
            "title": item.get("title", "无标题"),
            "cover": item.get("cover", DEFAULT_COVER),  # 优先使用豆瓣封面，失败时使用默认封面
            "link": item.get("url", ""),
            "rate": item.get("rate", "无评分")
        })
    return videos

# 获取视频列表
def get_videos(category_id):
    try:
        # 找到对应的分类配置
        category = next((c for c in CATEGORIES if c["id"] == category_id), CATEGORIES[0])
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://movie.douban.com/"
        }
        res = requests.get(category["api_url"], headers=headers, timeout=10)
        res.raise_for_status()
        return parse_douban(res.json())
    except Exception as e:
        print(f"获取数据失败: {e}")
    return []

# ===================== 视频解析 =====================
def get_play_url(video_page_url):
    global last_call_time
    # 遵守3秒调用限制
    now = time.time()
    if now - last_call_time < API_CALL_DELAY:
        wait_time = API_CALL_DELAY - (now - last_call_time)
        time.sleep(wait_time)
    last_call_time = time.time()

    try:
        # 确保URL编码正确
        params = {"url": video_page_url}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        print(f"正在解析: {video_page_url}")
        response = requests.get(PARSE_API, params=params, headers=headers, timeout=15)
        print(f"解析接口返回: {response.text}")
        data = response.json()

        if data.get("code") == 200 and data.get("url"):
            return data["url"]
        return None
    except Exception as e:
        print(f"解析失败: {e}")
        return None

# ===================== 网页前端 =====================
@app.route("/")
def index():
    category_id = request.args.get('category', 'movie')
    videos = get_videos(category_id)
    
    # 生成分类导航HTML
    category_nav = ''
    for cat in CATEGORIES:
        active = 'active' if cat['id'] == category_id else ''
        category_nav += f'''<a href="/?category={cat['id']}" class="nav-link {active}">
            <span class="fs-5">{cat['icon']}</span> {cat['name']}
        </a>'''
    
    return render_template_string('''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎬 老年人影视</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { 
            background: #f8f9fa; 
            color: #333; 
            padding-top: 100px; 
            min-height: 100vh; 
            font-size: 18px; /* 增大字体 */
        }
        .navbar { 
            background: #4a90e2; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 1rem 0; /* 增加导航栏高度 */
        }
        .navbar-brand { 
            font-size: 1.5rem; /* 增大品牌名称字体 */
            font-weight: bold;
            color: white !important;
        }
        .nav-link { 
            color: white !important;
            font-size: 1.1rem; /* 增大导航链接字体 */
            margin: 0 15px; /* 增加导航链接间距 */
            padding: 10px 15px !important;
            border-radius: 8px;
            transition: all 0.3s;
        }
        .nav-link:hover, .nav-link.active { 
            background: rgba(255,255,255,0.2);
        }
        .card { 
            background: white; 
            border: 1px solid #ddd; 
            margin-bottom: 30px; 
            transition: transform 0.3s, box-shadow 0.3s; 
            border-radius: 12px;
            overflow: hidden;
        }
        .card:hover { 
            transform: translateY(-5px); 
            box-shadow: 0 10px 20px rgba(0,0,0,0.1);
        }
        .card-img-top { 
            height: 320px; /* 增大封面图片高度 */
            object-fit: cover;
        }
        .card-body { 
            padding: 20px; /* 增加卡片内边距 */
        }
        .card-title { 
            font-size: 1.2rem; /* 增大标题字体 */
            font-weight: bold;
            margin-bottom: 15px;
        }
        .rate-badge { 
            background: #ffc107; 
            color: #000; 
            font-weight: bold; 
            padding: 5px 12px; /* 增大徽章大小 */
            border-radius: 20px; 
            font-size: 1rem; /* 增大徽章字体 */
        }
        .btn-danger { 
            font-size: 1.1rem; /* 增大按钮字体 */
            padding: 12px 20px; /* 增大按钮大小 */
            font-weight: bold;
            border-radius: 8px;
        }
        .empty-result { 
            text-align: center; 
            padding: 80px 20px; /* 增加空结果区域大小 */
            background: #f0f0f0;
            border-radius: 12px;
            margin: 30px 0;
        }
        .empty-result h3 { 
            font-size: 1.5rem; /* 增大空结果标题字体 */
            margin-bottom: 20px;
        }
        .empty-result p { 
            font-size: 1.1rem; /* 增大空结果文本字体 */
        }
    </style>
</head>
<body>
<nav class="navbar navbar-dark fixed-top">
    <div class="container">
        <a class="navbar-brand" href="/">🎬 老年人影视</a>
        <div class="d-flex">
            {category_nav}
        </div>
    </div>
</nav>

<div class="container mt-4">
    <div class="row g-5">
        {% for v in videos %}
        <div class="col-6 col-md-4 col-lg-3">
            <div class="card h-100">
                <img src="{{v.cover}}" class="card-img-top" alt="{{v.title}}" onerror="this.src='{{DEFAULT_COVER}}'">
                <div class="card-body">
                    <h5 class="card-title">{{v.title}}</h5>
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <span class="rate-badge">⭐ {{v.rate}}</span>
                    </div>
                    <a href="/play?url={{v.link}}" class="btn btn-danger w-100">▶️ 立即播放</a>
                </div>
            </div>
        </div>
        {% else %}
        <div class="col-12">
            <div class="empty-result">
                <div class="display-1 mb-4">🎬</div>
                <h3>暂无视频数据</h3>
                <p>可能是网络连接问题，请稍后重试</p>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
</body>
</html>
''', videos=videos, DEFAULT_COVER=DEFAULT_COVER, CATEGORIES=CATEGORIES)

# 播放页
@app.route("/play")
def play():
    video_url = request.args.get("url", "")
    if not video_url:
        return render_template_string('''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>❌ 参数错误</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { 
            background: #f8f9fa; 
            color: #333; 
            height: 100vh; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            font-size: 18px; /* 增大字体 */
        }
        .card { 
            background: white; 
            text-align: center; 
            padding: 60px; /* 增加内边距 */
            border-radius: 12px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            max-width: 500px;
            width: 90%;
        }
        h2 { 
            font-size: 2rem; /* 增大标题字体 */
            margin-bottom: 30px;
            color: #dc3545;
        }
        .btn-primary { 
            font-size: 1.2rem; /* 增大按钮字体 */
            padding: 15px 30px; /* 增大按钮大小 */
            font-weight: bold;
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="card">
        <h2>❌ 参数错误</h2>
        <a href="/" class="btn btn-primary mt-4">← 返回首页</a>
    </div>
</body>
</html>
''')

    # 获取解析后的播放地址
    play_url = get_play_url(video_url)
    
    if not play_url:
        return render_template_string('''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>❌ 解析失败</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { 
            background: #f8f9fa; 
            color: #333; 
            height: 100vh; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            font-size: 18px; /* 增大字体 */
        }
        .card { 
            background: white; 
            text-align: center; 
            padding: 60px; /* 增加内边距 */
            border-radius: 12px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            max-width: 500px;
            width: 90%;
        }
        h3 { 
            font-size: 1.8rem; /* 增大标题字体 */
            margin-bottom: 25px;
            color: #dc3545;
        }
        p { 
            font-size: 1.1rem; /* 增大文本字体 */
            line-height: 1.6;
            margin-bottom: 30px;
        }
        .btn-primary { 
            font-size: 1.2rem; /* 增大按钮字体 */
            padding: 15px 30px; /* 增大按钮大小 */
            font-weight: bold;
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="display-1 mb-4">😢</div>
        <h3>视频解析失败</h3>
        <p>可能原因：<br>1. 该电影暂无在线资源<br>2. 解析接口暂时不可用<br>3. 请等待3秒后重试</p>
        <a href="/" class="btn btn-primary">← 返回首页</a>
    </div>
</body>
</html>
''')

    # 使用DPlayer播放m3u8视频
    return render_template_string('''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>▶️ 正在播放</title>
    <script src="https://cdn.jsdelivr.net/npm/dplayer@1.27.1/dist/DPlayer.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@1.4.14/dist/hls.min.js"></script>
    <style>
        * { margin: 0; padding: 0; }
        body { background: #000; }
        #dplayer { height: 100vh; width: 100%; }
        .back-btn { 
            position: fixed; 
            top: 30px; 
            left: 30px; 
            z-index: 9999; 
            background: rgba(0,0,0,0.8); 
            color: white; 
            padding: 15px 25px; /* 增大按钮大小 */
            border-radius: 8px; 
            text-decoration: none; 
            border: 2px solid rgba(255,255,255,0.5);
            font-size: 1.2rem; /* 增大字体 */
            font-weight: bold;
            transition: all 0.3s;
        }
        .back-btn:hover { 
            background: rgba(0,0,0,0.95); 
            color: white; 
            transform: scale(1.05);
        }
    </style>
</head>
<body>
    <a href="/" class="back-btn">← 返回首页</a>
    <div id="dplayer"></div>
    <script>
        const dp = new DPlayer({
            container: document.getElementById('dplayer'),
            video: {
                url: '{{play_url}}',
                type: 'hls'
            },
            autoplay: true,
            theme: '#dc3545',
            volume: 0.8, // 默认音量设置为80%
            mutex: true
        });
    </script>
</body>
</html>
''', play_url=play_url)

if __name__ == "__main__":
    print("="*60)
    print("老年人影视网站已启动！")
    print("请访问: http://127.0.0.1:5500")
    print("="*60)
    app.run(host="127.0.0.1", port=5500, debug=False)