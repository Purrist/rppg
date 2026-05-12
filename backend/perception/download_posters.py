"""
一次性下载所有海报到 static/poster/
用法：python download_posters.py
"""

import os
import requests
from pathlib import Path

POSTER_DIR = Path(__file__).parent / "static" / "poster"
POSTER_DIR.mkdir(parents=True, exist_ok=True)

HEADERS_DOUBAN = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Referer': 'https://movie.douban.com/',
}

HEADERS_NORMAL = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
}

# URL → 本地文件名
IMAGE_MAP = {
    # ===== 影视剧（豆瓣） =====
    'https://img3.doubanio.com/view/photo/l/public/p2867081710.webp': 'tv_renshijian.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2547896032.webp': 'tv_doutinghao.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2246648560.webp': 'tv_fumuaiqing.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2228728474.webp': 'tv_langyabang.webp',
    'https://img3.doubanio.com/view/photo/l/public/p1908317688.webp': 'tv_zhenhuan.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2516600066.webp': 'tv_zhifou.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2621172187.webp': 'tv_yinmi.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2897595923.webp': 'tv_manchang.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2879129075.webp': 'tv_kuangbiao.webp',
    'https://img3.doubanio.com/view/photo/l/public/p3070353969.webp': 'tv_fanhua.webp',
    # ===== 电影（豆瓣） =====
    'https://img3.doubanio.com/view/photo/l/public/p2894602802.webp': 'mv_manjh.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2886470405.webp': 'mv_liulang2.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2663579561.webp': 'mv_lihuanying.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2693751694.webp': 'mv_changjin.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2565625462.webp': 'mv_woguo.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2713015157.webp': 'mv_xuanya.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2866231115.webp': 'mv_rensheng.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2857632688.webp': 'mv_duxing.webp',
    'https://img3.doubanio.com/view/photo/l/public/p2894602693.webp': 'mv_fengshen.webp',
    'https://img3.doubanio.com/view/photo/l/public/p3051098987.webp': 'mv_rela.webp',
    # ===== 戏曲（Unsplash） =====
    'https://images.unsplash.com/photo-1608245449230-4ac19066d2d0?w=260&h=370&fit=crop': 'opera_jingju.jpg',
    'https://images.unsplash.com/photo-1528360983277-13d401cdc186?w=260&h=370&fit=crop': 'opera_kunqu.jpg',
    'https://images.unsplash.com/photo-1548013146-72479768bada?w=260&h=370&fit=crop': 'opera_yuju.jpg',
    'https://images.unsplash.com/photo-1545437276-4a7c408e7ea5?w=260&h=370&fit=crop': 'opera_huangmei.jpg',
    'https://images.unsplash.com/photo-1528605248644-14dd04022da1?w=260&h=370&fit=crop': 'opera_yueju.jpg',
    'https://images.unsplash.com/photo-1599707367812-042b7e3a6345?w=260&h=370&fit=crop': 'opera_pingju.jpg',
    'https://images.unsplash.com/photo-1566438480900-0609be27a4be?w=260&h=370&fit=crop': 'opera_chuanju.jpg',
    'https://images.unsplash.com/photo-1548248823-ce16a73b6d49?w=260&h=370&fit=crop': 'opera_yueju2.jpg',
    # ===== 新闻（Unsplash） =====
    'https://images.unsplash.com/photo-1586339949916-3e9457bef6d3?w=600&h=340&fit=crop': 'news_health.jpg',
    'https://images.unsplash.com/photo-1504711434969-e33886168d6c?w=600&h=340&fit=crop': 'news_policy.jpg',
    'https://images.unsplash.com/photo-1557804506-669a67965ba0?w=320&h=200&fit=crop': 'news_community.jpg',
    'https://images.unsplash.com/photo-1495020689067-958852a7765e?w=320&h=200&fit=crop': 'news_anticheat.jpg',
    'https://images.unsplash.com/photo-1505373877841-8d25f7d46678?w=320&h=200&fit=crop': 'news_diet.jpg',
    'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=320&h=200&fit=crop': 'news_tech.jpg',
    'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=320&h=200&fit=crop': 'news_park.jpg',
    # ===== 广场舞（Unsplash） =====
    'https://images.unsplash.com/photo-1518611012118-696072aa579a?w=280&h=180&fit=crop': 'dance_minzu.jpg',
    'https://images.unsplash.com/photo-1504609813442-a8924e83f76e?w=280&h=180&fit=crop': 'dance_basic.jpg',
    'https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=280&h=180&fit=crop': 'dance_shanzi.jpg',
    'https://images.unsplash.com/photo-1534258936925-c58bed479fcb?w=280&h=180&fit=crop': 'dance_taiji.jpg',
    'https://images.unsplash.com/photo-1518459031867-a89b944bffe4?w=280&h=180&fit=crop': 'dance_shuibing.jpg',
    'https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=280&h=180&fit=crop': 'dance_jiaoyi.jpg',
    'https://images.unsplash.com/photo-1545389336-cf090694435e?w=280&h=180&fit=crop': 'dance_jianshen.jpg',
    'https://images.unsplash.com/photo-1508807526345-15e9b5f4eaff?w=280&h=180&fit=crop': 'dance_group.jpg',
    # ===== 音乐（Unsplash） =====
    'https://images.unsplash.com/photo-1552422535-c45813c61732?w=220&h=220&fit=crop': 'music_laoge.jpg',
    'https://images.unsplash.com/photo-1507838153414-b4b713384a76?w=220&h=220&fit=crop': 'music_minge.jpg',
    'https://images.unsplash.com/photo-1465847899084-d164df4dedc6?w=220&h=220&fit=crop': 'music_hongge.jpg',
    'https://images.unsplash.com/photo-1510915361894-db8b60106cb1?w=220&h=220&fit=crop': 'music_qingyinyue.jpg',
    'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=220&h=220&fit=crop': 'music_erhu.jpg',
    'https://images.unsplash.com/photo-1514320291840-2e0a9bf2a9ae?w=220&h=220&fit=crop': 'music_guzheng.jpg',
    'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=220&h=220&fit=crop': 'music_jingju.jpg',
    'https://images.unsplash.com/photo-1457523054379-8d03ab9fc2aa?w=220&h=220&fit=crop': 'music_hulusi.jpg',
    'https://images.unsplash.com/photo-1506157786151-b8491531f063?w=220&h=220&fit=crop': 'music_gangqin.jpg',
    'https://images.unsplash.com/photo-1520523839897-bd0b52f945a0?w=220&h=220&fit=crop': 'music_sax.jpg',
    # ===== Hero =====
    'https://images.unsplash.com/photo-1594909122845-11baa439b7bf?w=900&h=400&fit=crop': 'hero_family.jpg',
}


def download_one(url, filename, overwrite=False):
    filepath = POSTER_DIR / filename
    if filepath.exists() and not overwrite:
        size_kb = filepath.stat().st_size / 1024
        print(f'  [跳过] {filename} ({size_kb:.0f}KB)')
        return True
    try:
        headers = HEADERS_DOUBAN if 'doubanio' in url else HEADERS_NORMAL
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(r.content)
        size_kb = len(r.content) / 1024
        print(f'  [完成] {filename} ({size_kb:.0f}KB)')
        return True
    except Exception as e:
        print(f'  [失败] {filename} <- {e}')
        return False


def make_placeholder(filename, text, w=260, h=185):
    filepath = POSTER_DIR / filename
    if filepath.exists():
        return
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><rect width="{w}" height="{h}" fill="#E8ECF0"/><text x="{w//2}" y="{h//2}" text-anchor="middle" dominant-baseline="middle" fill="#94A3B8" font-size="14">{text}</text></svg>'
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(svg)
    print(f'  [占位] {filename}')


def main():
    print('=' * 60)
    print('  下载海报到 static/poster/')
    print(f'  目录: {POSTER_DIR}')
    print('=' * 60)
    ok = 0
    fail = 0
    for url, filename in IMAGE_MAP.items():
        if download_one(url, filename):
            ok += 1
        else:
            fail += 1
            make_placeholder(filename, filename.rsplit('.', 1)[0])
    print('=' * 60)
    print(f'  结果: {ok} 成功, {fail} 失败')
    files = list(POSTER_DIR.iterdir())
    print(f'  目录共 {len(files)} 个文件')
    print('=' * 60)


if __name__ == '__main__':
    main()
