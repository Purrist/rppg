"""
娱乐中心 - Flask 后端
使用免费图片服务提供影视剧/电影海报
"""

from flask import Flask, jsonify, send_file, request
import requests
import time
import json
import os

app = Flask(__name__)

# ============================================================
# 数据配置 - 使用预定义的海报图片
# ============================================================

def build_sections():
    """构建六大板块数据"""

    # ---- 影视剧 ----
    tv_items = [
        {'title': '人世间', 'sub': '都市情感 · 2022 · 9.4分', 'tag': '热播', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2867081710.webp'},
        {'title': '都挺好', 'sub': '家庭伦理 · 2019 · 7.7分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2547896032.webp'},
        {'title': '父母爱情', 'sub': '年代情感 · 2014 · 9.4分', 'tag': '经典', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2246648560.webp'},
        {'title': '琅琊榜', 'sub': '古装权谋 · 2015 · 9.4分', 'tag': '经典', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2228728474.webp'},
        {'title': '甄嬛传', 'sub': '古装宫廷 · 2011 · 9.4分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p1908317688.webp'},
        {'title': '知否知否应是绿肥红瘦', 'sub': '古装家庭 · 2018 · 7.9分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2516600066.webp'},
        {'title': '隐秘的角落', 'sub': '悬疑犯罪 · 2020 · 8.8分', 'tag': '高分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2621172187.webp'},
        {'title': '漫长的季节', 'sub': '悬疑剧情 · 2023 · 9.4分', 'tag': '高分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2897595923.webp'},
        {'title': '狂飙', 'sub': '犯罪动作 · 2023 · 8.5分', 'tag': '热播', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2879129075.webp'},
        {'title': '繁花', 'sub': '都市商战 · 2024 · 8.7分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p3070353969.webp'},
    ]

    # ---- 电影 ----
    movie_items = [
        {'title': '满江红', 'sub': '悬疑喜剧 · 2023 · 7.8分', 'tag': '热映', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2894602802.webp'},
        {'title': '流浪地球2', 'sub': '科幻冒险 · 2023 · 8.3分', 'tag': '热映', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2886470405.webp'},
        {'title': '你好，李焕英', 'sub': '喜剧亲情 · 2021 · 7.7分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2663579561.webp'},
        {'title': '长津湖', 'sub': '战争历史 · 2021 · 7.4分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2693751694.webp'},
        {'title': '我和我的祖国', 'sub': '剧情 · 2019 · 7.7分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2565625462.webp'},
        {'title': '悬崖之上', 'sub': '谍战悬疑 · 2021 · 7.4分', 'tag': '高分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2713015157.webp'},
        {'title': '人生大事', 'sub': '温情剧情 · 2022 · 7.3分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2866231115.webp'},
        {'title': '独行月球', 'sub': '科幻喜剧 · 2022 · 6.8分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2857632688.webp'},
        {'title': '封神第一部', 'sub': '神话史诗 · 2023 · 7.8分', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p2894602693.webp'},
        {'title': '热辣滚烫', 'sub': '喜剧励志 · 2024 · 7.0分', 'tag': '新上线', 
         'img': 'https://img3.doubanio.com/view/photo/l/public/p3051098987.webp'},
    ]

    # ---- 戏曲 ----
    opera_items = [
        {'title': '京剧名段赏析', 'sub': '京剧 · 梅派经典', 'tag': '经典', 
         'img': 'https://images.unsplash.com/photo-1608245449230-4ac19066d2d0?w=260&h=370&fit=crop'},
        {'title': '昆曲牡丹亭', 'sub': '昆曲 · 汤显祖', 
         'img': 'https://images.unsplash.com/photo-1528360983277-13d401cdc186?w=260&h=370&fit=crop'},
        {'title': '豫剧花木兰', 'sub': '豫剧 · 巾帼英雄', 'tag': '名剧', 
         'img': 'https://images.unsplash.com/photo-1548013146-72479768bada?w=260&h=370&fit=crop'},
        {'title': '黄梅戏天仙配', 'sub': '黄梅戏 · 经典爱情', 
         'img': 'https://images.unsplash.com/photo-1545437276-4a7c408e7ea5?w=260&h=370&fit=crop'},
        {'title': '越剧梁祝', 'sub': '越剧 · 经典爱情', 
         'img': 'https://images.unsplash.com/photo-1528605248644-14dd04022da1?w=260&h=370&fit=crop'},
        {'title': '评剧选段', 'sub': '评剧 · 地方名段', 
         'img': 'https://images.unsplash.com/photo-1599707367812-042b7e3a6345?w=260&h=370&fit=crop'},
        {'title': '川剧变脸', 'sub': '川剧 · 绝活表演', 'tag': '绝活', 
         'img': 'https://images.unsplash.com/photo-1566438480900-0609be27a4be?w=260&h=370&fit=crop'},
        {'title': '粤剧名家', 'sub': '粤剧 · 岭南文化', 
         'img': 'https://images.unsplash.com/photo-1548248823-ce16a73b6d49?w=260&h=370&fit=crop'},
    ]

    # ---- 新闻 ----
    news_items = [
        {'title': '春季养生指南：中老年人必看的健康守则', 'sub': '3小时前', 
         'img': 'https://images.unsplash.com/photo-1586339949916-3e9457bef6d3?w=600&h=340&fit=crop'},
        {'title': '国家出台养老新政策，惠及亿万家庭', 'sub': '5小时前', 
         'img': 'https://images.unsplash.com/photo-1504711434969-e33886168d6c?w=600&h=340&fit=crop'},
        {'title': '社区文娱活动丰富多彩 居民乐享幸福生活', 'sub': '1天前 · 2.3万阅读', 
         'img': 'https://images.unsplash.com/photo-1557804506-669a67965ba0?w=320&h=200&fit=crop'},
        {'title': '防骗提醒：警惕针对老年人的电信诈骗', 'sub': '1天前 · 5.1万阅读', 
         'img': 'https://images.unsplash.com/photo-1495020689067-958852a7765e?w=320&h=200&fit=crop'},
        {'title': '健康饮食新趋势：地中海饮食法详解', 'sub': '2天前 · 3.6万阅读', 
         'img': 'https://images.unsplash.com/photo-1505373877841-8d25f7d46678?w=320&h=200&fit=crop'},
        {'title': '科技助老：智能手机实用技巧汇总', 'sub': '3天前 · 4.2万阅读', 
         'img': 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=320&h=200&fit=crop'},
        {'title': '多地公园升级改造 市民休闲好去处', 'sub': '2天前 · 1.8万阅读', 
         'img': 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=320&h=200&fit=crop'},
    ]

    # ---- 广场舞 ----
    dance_items = [
        {'title': '最炫民族风 完整版教学', 'sub': '32步 · 入门级', 
         'img': 'https://images.unsplash.com/photo-1518611012118-696072aa579a?w=280&h=180&fit=crop'},
        {'title': '广场舞基础步法入门', 'sub': '基础教学 · 零基础', 
         'img': 'https://images.unsplash.com/photo-1504609813442-a8924e83f76e?w=280&h=180&fit=crop'},
        {'title': '扇子舞 茉莉花 精讲', 'sub': '64步 · 进阶级', 
         'img': 'https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=280&h=180&fit=crop'},
        {'title': '太极养生健身操', 'sub': '养生系列 · 慢节奏', 
         'img': 'https://images.unsplash.com/photo-1534258936925-c58bed479fcb?w=280&h=180&fit=crop'},
        {'title': '水兵舞 海军风采', 'sub': '48步 · 中级', 
         'img': 'https://images.unsplash.com/photo-1518459031867-a89b944bffe4?w=280&h=180&fit=crop'},
        {'title': '交谊舞慢三基本步', 'sub': '基础教学 · 入门', 
         'img': 'https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=280&h=180&fit=crop'},
        {'title': '燃脂塑形健身操', 'sub': '30分钟 · 中高强度', 
         'img': 'https://images.unsplash.com/photo-1545389336-cf090694435e?w=280&h=180&fit=crop'},
        {'title': '集体舞 欢乐节拍', 'sub': '群舞教学 · 互动', 
         'img': 'https://images.unsplash.com/photo-1508807526345-15e9b5f4eaff?w=280&h=180&fit=crop'},
    ]

    # ---- 音乐 ----
    music_items = [
        {'title': '经典老歌合集', 'sub': '邓丽君 · 30首', 
         'img': 'https://images.unsplash.com/photo-1552422535-c45813c61732?w=220&h=220&fit=crop'},
        {'title': '民歌精选', 'sub': '彭丽媛 · 20首', 
         'img': 'https://images.unsplash.com/photo-1507838153414-b4b713384a76?w=220&h=220&fit=crop'},
        {'title': '红歌联唱', 'sub': '经典合唱 · 25首', 
         'img': 'https://images.unsplash.com/photo-1465847899084-d164df4dedc6?w=220&h=220&fit=crop'},
        {'title': '轻音乐放松', 'sub': '纯音乐 · 15首', 
         'img': 'https://images.unsplash.com/photo-1510915361894-db8b60106cb1?w=220&h=220&fit=crop'},
        {'title': '二胡名曲', 'sub': '传统器乐 · 12首', 
         'img': 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=220&h=220&fit=crop'},
        {'title': '古筝欣赏', 'sub': '古典器乐 · 18首', 
         'img': 'https://images.unsplash.com/photo-1514320291840-2e0a9bf2a9ae?w=220&h=220&fit=crop'},
        {'title': '京剧名段', 'sub': '戏曲唱腔 · 20段', 
         'img': 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=220&h=220&fit=crop'},
        {'title': '葫芦丝经典', 'sub': '民族器乐 · 10首', 
         'img': 'https://images.unsplash.com/photo-1457523054379-8d03ab9fc2aa?w=220&h=220&fit=crop'},
        {'title': '钢琴轻柔曲', 'sub': '放松助眠 · 15首', 
         'img': 'https://images.unsplash.com/photo-1506157786151-b8491531f063?w=220&h=220&fit=crop'},
        {'title': '萨克斯金曲', 'sub': '浪漫经典 · 12首', 
         'img': 'https://images.unsplash.com/photo-1520523839897-bd0b52f945a0?w=220&h=220&fit=crop'},
    ]

    # 为所有板块补充sectionTitle/sectionColor
    for item in tv_items:
        item.update({'sectionTitle': '影视剧', 'sectionColor': '#E8363A'})
    for item in movie_items:
        item.update({'sectionTitle': '电影', 'sectionColor': '#D97706'})
    for item in opera_items:
        item.update({'sectionTitle': '戏曲', 'sectionColor': '#7C3AED'})
    for item in news_items:
        item.update({'sectionTitle': '新闻', 'sectionColor': '#2563EB'})
    for item in dance_items:
        item.update({'sectionTitle': '广场舞', 'sectionColor': '#DB2777'})
    for item in music_items:
        item.update({'sectionTitle': '音乐', 'sectionColor': '#0D9488'})

    return [
        {'id': 'tv', 'title': '影视剧', 'icon': 'fas fa-tv', 'color': '#E8363A', 'layout': 'poster', 'items': tv_items},
        {'id': 'news', 'title': '新闻', 'icon': 'fas fa-newspaper', 'color': '#2563EB', 'layout': 'news', 'items': news_items},
        {'id': 'opera', 'title': '戏曲', 'icon': 'fas fa-masks-theater', 'color': '#7C3AED', 'layout': 'poster', 'items': opera_items},
        {'id': 'movie', 'title': '电影', 'icon': 'fas fa-film', 'color': '#D97706', 'layout': 'poster', 'items': movie_items},
        {'id': 'dance', 'title': '广场舞', 'icon': 'fas fa-person-walking', 'color': '#DB2777', 'layout': 'wide', 'items': dance_items},
        {'id': 'music', 'title': '音乐', 'icon': 'fas fa-music', 'color': '#0D9488', 'layout': 'music', 'items': music_items},
    ]

# ============================================================
# 路由
# ============================================================

@app.route('/')
def index():
    return send_file('templates/entertainment.html')


@app.route('/api/sections')
def api_sections():
    """返回六大板块数据（JSON）"""
    q = request.args.get('q', '').strip().lower()
    sections = build_sections()

    if q:
        filtered = []
        for s in sections:
            matched = [item for item in s['items']
                       if q in item.get('title', '').lower() or q in item.get('sub', '').lower()]
            if matched:
                filtered.append({**s, 'items': matched})
        return jsonify(filtered)

    return jsonify(sections)


@app.route('/api/hero')
def api_hero():
    """返回Hero推荐数据"""
    sections = build_sections()
    for s in sections:
        if s['id'] == 'tv':
            if s['items']:
                item = s['items'][0]
                return jsonify({
                    'title': item['title'],
                    'sub': item.get('sub', ''),
                    'img': item['img']
                })
    return jsonify({
        'title': '家庭影院',
        'sub': '温馨时刻 · 全家共赏',
        'img': 'https://images.unsplash.com/photo-1594909122845-11baa439b7bf?w=900&h=400&fit=crop'
    })


@app.route('/api/refresh')
def api_refresh():
    """刷新数据"""
    return jsonify({'status': 'ok', 'message': '数据已刷新'})


# ============================================================
# 启动
# ============================================================
if __name__ == '__main__':
    print('=' * 50)
    print('  娱乐中心 - 启动中...')
    print('  使用预定义的豆瓣图片数据')
    print('=' * 50)

    app.run(host='0.0.0.0', port=5001, debug=True)
