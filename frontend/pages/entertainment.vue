<template>
  <div class="page-root">
    <!-- 顶栏 -->
    <div class="page-header">
      <!-- 分类导航 -->
      <div class="flex items-center gap-1.5 overflow-x-auto" style="flex:1;justify-content:center">
        <button class="nav-pill" :class="{active:activeNav==='all'}" @click="scrollTo('all')">全部</button>
        <button v-for="s in sections" :key="s.id" class="nav-pill" :class="{active:activeNav===s.id}" @click="scrollTo(s.id)">
          {{s.title}}
        </button>
      </div>
      <!-- 搜索 -->
      <div class="search-box">
        <i class="fas fa-search"></i>
        <input v-model="searchQuery" placeholder="搜索节目..." @input="onSearch">
      </div>
    </div>

    <!-- 主体 -->
    <div class="page-body" @scroll="onScroll" ref="bodyRef">

      <!-- Hero 推荐 -->
      <div class="hero-card mb-4" @click="openModal(heroItem)">
        <img :src="heroItem.img" :alt="heroItem.title">
        <div class="hero-overlay">
          <div class="hero-play"><i class="fas fa-play" style="font-size:18px;margin-left:2px;color:#fff"></i></div>
          <span class="text-xs font-semibold text-white mb-2" style="color: #ffffff;">今日推荐</span>
          <h2 class="text-white font-bold text-2xl" style="font-family:'Space Grotesk'; color: #ffffff;">{{heroItem.title}}</h2>
          <p class="text-white text-sm mt-2" style="color: #ffffff;">{{heroItem.sub}}</p>
        </div>
      </div>

      <!-- 六大板块 -->
      <div v-for="s in filteredSections" :key="s.id" :id="'sec-'+s.id" class="mb-5">
        <div class="sec-header">
          <div class="sec-title">
            <div class="sec-dot" :style="{background:s.color}"></div>
            <i :class="s.icon" :style="{color:s.color,fontSize:'13px'}"></i>
            <h3 class="font-bold text-sm">{{s.title}}</h3>
            <span class="text-[10px] text-slate-400">{{s.items.length}}个节目</span>
          </div>
          <div class="sec-more" @click="showToast('更多'+s.title+'内容加载中...')">更多<i class="fas fa-chevron-right" style="font-size:8px"></i></div>
        </div>

        <!-- 影视剧/电影/戏曲：海报卡片 -->
        <div v-if="s.layout==='poster'" class="scroll-row">
          <div class="poster-card" v-for="(item,i) in s.items" :key="i" @click="openModal(item)">
            <div class="img-wrap">
              <img :src="item.img" :alt="item.title" :loading="i < 4 ? 'eager' : 'lazy'">
              <div v-if="item.tag" class="tag" :style="{background:s.color}">{{item.tag}}</div>
              <div class="play-ico"><i class="fas fa-play" style="font-size:10px;margin-left:1px;color:#fff"></i></div>
            </div>
            <div class="p-title">{{item.title}}</div>
            <div class="p-sub">{{item.sub}}</div>
          </div>
        </div>

        <!-- 新闻：特色+列表 -->
        <div v-if="s.layout==='news'">
          <div class="news-featured">
            <div class="news-big" v-for="(item,i) in s.items.slice(0,2)" :key="i" @click="openModal(item)">
              <img :src="item.img" :alt="item.title" loading="eager">
              <div class="n-overlay">
                <h4>{{item.title}}</h4>
                <span><i class="fas fa-clock mr-1"></i>{{item.sub}}</span>
              </div>
            </div>
          </div>
          <div class="scroll-row">
            <div class="wide-card" v-for="(item,i) in s.items.slice(2)" :key="i" @click="openModal(item)">
              <div class="w-img"><img :src="item.img" :alt="item.title" :loading="i < 3 ? 'eager' : 'lazy'"></div>
              <div class="w-info">
                <div class="w-title">{{item.title}}</div>
                <div class="w-sub"><i class="fas fa-eye mr-0.5"></i>{{item.sub}}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 广场舞：横版卡片 -->
        <div v-if="s.layout==='wide'" class="scroll-row">
          <div class="wide-card" v-for="(item,i) in s.items" :key="i" @click="openModal(item)">
            <div class="w-img"><img :src="item.img" :alt="item.title" :loading="i < 4 ? 'eager' : 'lazy'"></div>
            <div class="w-info">
              <div class="w-title">{{item.title}}</div>
              <div class="w-sub"><i class="fas fa-users mr-0.5"></i>{{item.sub}}</div>
            </div>
          </div>
        </div>

        <!-- 音乐：圆形卡片 -->
        <div v-if="s.layout==='music'" class="scroll-row">
          <div class="music-card" v-for="(item,i) in s.items" :key="i" @click="openModal(item)">
            <div class="m-img">
              <img :src="item.img" :alt="item.title" :loading="i < 4 ? 'eager' : 'lazy'">
              <div class="m-play"><i class="fas fa-play" style="font-size:14px;margin-left:2px;color:#fff"></i></div>
            </div>
            <div class="m-title">{{item.title}}</div>
            <div class="m-artist">{{item.sub}}</div>
          </div>
        </div>
      </div>

      <!-- 搜索无结果 -->
      <div v-if="searchQuery && filteredSections.length===0" class="text-center py-16">
        <i class="fas fa-search text-3xl text-slate-300 mb-3 block"></i>
        <p class="text-sm text-slate-400">没有找到与"{{searchQuery}}"相关的内容</p>
      </div>

    </div>

    <!-- 播放弹窗 -->
    <div v-if="showModalFlag" class="modal-bg" @click.self="closeModal">
      <div class="modal-box">
        <div class="modal-vid">
          <img :src="modalItem.img" :alt="modalItem.title">
          <button class="modal-close" @click="closeModal"><i class="fas fa-xmark" style="color:#fff;"></i></button>
          <div class="big-play" @click="playVideo"><i class="fas fa-play" style="font-size:24px;margin-left:4px;color:#fff;"></i></div>
        </div>
        <div class="modal-info">
          <h3 class="font-bold text-xl" style="font-family:'Space Grotesk'">{{modalItem.title}}</h3>
          <p class="text-sm text-slate-500 mt-2">{{modalItem.sub}}</p>
          <p class="text-sm text-slate-400 mt-4 leading-relaxed">精彩内容即将播放，请稍候。如需观看完整节目，请确认网络连接正常。</p>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div v-if="toastMsg" class="toast">{{toastMsg}}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'

const activeNav = ref('all')
const searchQuery = ref('')
const showModalFlag = ref(false)
const modalItem = ref({})
const toastMsg = ref('')
const bodyRef = ref(null)

const heroItem = ref({
  title: '人世间',
  sub: '年度口碑佳作 · 五十集全家共赏 · 感受人间温情',
  img: '/poster/hero_family.jpg'
})

const sections = ref([
  {
    id: 'opera', title: '戏曲', icon: 'fas fa-masks-theater', color: '#7C3AED', layout: 'poster',
    items: [
      { title: '京剧名段赏析', sub: '京剧 · 梅派经典', tag: '经典', img: '/poster/opera_jingju.jpg', sectionTitle: '戏曲', sectionColor: '#7C3AED' },
      { title: '昆曲牡丹亭', sub: '昆曲 · 汤显祖', tag: '', img: '/poster/opera_kunqu.jpg', sectionTitle: '戏曲', sectionColor: '#7C3AED' },
      { title: '豫剧花木兰', sub: '豫剧 · 巾帼英雄', tag: '名剧', img: '/poster/opera_yuju.jpg', sectionTitle: '戏曲', sectionColor: '#7C3AED' },
      { title: '黄梅戏天仙配', sub: '黄梅戏 · 经典爱情', tag: '', img: '/poster/opera_huangmei.jpg', sectionTitle: '戏曲', sectionColor: '#7C3AED' },
      { title: '越剧梁祝', sub: '越剧 · 经典爱情', tag: '', img: '/poster/opera_yueju.jpg', sectionTitle: '戏曲', sectionColor: '#7C3AED' },
      { title: '评剧选段', sub: '评剧 · 地方名段', tag: '', img: '/poster/opera_pingju.jpg', sectionTitle: '戏曲', sectionColor: '#7C3AED' },
      { title: '川剧变脸', sub: '川剧 · 绝活表演', tag: '绝活', img: '/poster/opera_chuanju.jpg', sectionTitle: '戏曲', sectionColor: '#7C3AED' },
      { title: '粤剧名家', sub: '粤剧 · 岭南文化', tag: '', img: '/poster/opera_yueju2.jpg', sectionTitle: '戏曲', sectionColor: '#7C3AED' },
    ]
  },
  {
    id: 'news', title: '新闻', icon: 'fas fa-newspaper', color: '#2563EB', layout: 'news',
    items: [
      { title: '春季养生指南：中老年人必看的健康守则', sub: '3小时前', img: '/poster/news_health.jpg', sectionTitle: '新闻', sectionColor: '#2563EB' },
      { title: '国家出台养老新政策，惠及亿万家庭', sub: '5小时前', img: '/poster/news_policy.jpg', sectionTitle: '新闻', sectionColor: '#2563EB' },
      { title: '社区文娱活动丰富多彩 居民乐享幸福生活', sub: '1天前 · 2.3万阅读', img: '/poster/news_community.jpg', sectionTitle: '新闻', sectionColor: '#2563EB' },
      { title: '防骗提醒：警惕针对老年人的电信诈骗新手段', sub: '1天前 · 5.1万阅读', img: '/poster/news_anticheat.jpg', sectionTitle: '新闻', sectionColor: '#2563EB' },
      { title: '多地公园升级改造 市民休闲好去处', sub: '2天前 · 1.8万阅读', img: '/poster/news_park.jpg', sectionTitle: '新闻', sectionColor: '#2563EB' },
      { title: '健康饮食新趋势：地中海饮食法详解', sub: '2天前 · 3.6万阅读', img: '/poster/news_diet.jpg', sectionTitle: '新闻', sectionColor: '#2563EB' },
      { title: '科技助老：智能手机实用技巧汇总', sub: '3天前 · 4.2万阅读', img: '/poster/news_tech.jpg', sectionTitle: '新闻', sectionColor: '#2563EB' },
      { title: '天气预报：本周全国大部气温回升', sub: '6小时前 · 8900阅读', img: '/poster/news_weather.jpg', sectionTitle: '新闻', sectionColor: '#2563EB' },
    ]
  },
  {
    id: 'tv', title: '影视剧', icon: 'fas fa-tv', color: '#FF7222', layout: 'poster',
    items: [
      { title: '人世间', sub: '都市情感 · 58集', tag: '热播', img: '/poster/tv_renshijian.jpg', sectionTitle: '影视剧', sectionColor: '#FF7222' },
      { title: '都挺好', sub: '家庭伦理 · 46集', tag: '', img: '/poster/tv_doutinghao.jpg', sectionTitle: '影视剧', sectionColor: '#FF7222' },
      { title: '父母爱情', sub: '年代情感 · 44集', tag: '经典', img: '/poster/tv_fumuaiqing.jpg', sectionTitle: '影视剧', sectionColor: '#FF7222' },
      { title: '琅琊榜', sub: '古装权谋 · 54集', tag: '经典', img: '/poster/tv_langyabang.jpg', sectionTitle: '影视剧', sectionColor: '#FF7222' },
      { title: '甄嬛传', sub: '古装宫廷 · 76集', tag: '', img: '/poster/tv_zhenhuan.jpg', sectionTitle: '影视剧', sectionColor: '#FF7222' },
      { title: '知否知否', sub: '古装家庭 · 73集', tag: '', img: '/poster/tv_zhifou.jpg', sectionTitle: '影视剧', sectionColor: '#FF7222' },
      { title: '隐秘的角落', sub: '悬疑犯罪 · 12集', tag: '高分', img: '/poster/tv_yinmi.jpg', sectionTitle: '影视剧', sectionColor: '#FF7222' },
      { title: '漫长的季节', sub: '悬疑剧情 · 12集', tag: '高分', img: '/poster/tv_manchang.jpg', sectionTitle: '影视剧', sectionColor: '#FF7222' },
      { title: '狂飙', sub: '犯罪动作 · 39集', tag: '热播', img: '/poster/tv_kuangbiao.jpg', sectionTitle: '影视剧', sectionColor: '#FF7222' },
      { title: '繁花', sub: '都市商战 · 30集', tag: '新上线', img: '/poster/tv_fanhua.jpg', sectionTitle: '影视剧', sectionColor: '#FF7222' },
    ]
  },
  {
    id: 'movie', title: '电影', icon: 'fas fa-film', color: '#D97706', layout: 'poster',
    items: [
      { title: '满江红', sub: '悬疑喜剧 · 2023', tag: '热映', img: '/poster/mv_manjh.jpg', sectionTitle: '电影', sectionColor: '#D97706' },
      { title: '流浪地球2', sub: '科幻冒险 · 2023', tag: '热映', img: '/poster/mv_liulang2.jpg', sectionTitle: '电影', sectionColor: '#D97706' },
      { title: '你好李焕英', sub: '喜剧亲情 · 2021', tag: '', img: '/poster/mv_lihuanying.jpg', sectionTitle: '电影', sectionColor: '#D97706' },
      { title: '长津湖', sub: '战争历史 · 2021', tag: '', img: '/poster/mv_changjin.jpg', sectionTitle: '电影', sectionColor: '#D97706' },
      { title: '我和我的祖国', sub: '剧情 · 2019', tag: '', img: '/poster/mv_woguo.jpg', sectionTitle: '电影', sectionColor: '#D97706' },
      { title: '悬崖之上', sub: '谍战悬疑 · 2021', tag: '高分', img: '/poster/mv_xuanya.jpg', sectionTitle: '电影', sectionColor: '#D97706' },
      { title: '人生大事', sub: '温情剧情 · 2022', tag: '', img: '/poster/mv_rensheng.jpg', sectionTitle: '电影', sectionColor: '#D97706' },
      { title: '独行月球', sub: '科幻喜剧 · 2022', tag: '', img: '/poster/mv_duxing.jpg', sectionTitle: '电影', sectionColor: '#D97706' },
      { title: '封神第一部', sub: '神话史诗 · 2023', tag: '新上线', img: '/poster/mv_fengshen.jpg', sectionTitle: '电影', sectionColor: '#D97706' },
      { title: '热辣滚烫', sub: '喜剧励志 · 2024', tag: '新上线', img: '/poster/mv_rela.jpg', sectionTitle: '电影', sectionColor: '#D97706' },
    ]
  },
  {
    id: 'dance', title: '广场舞', icon: 'fas fa-person-walking', color: '#DB2777', layout: 'wide',
    items: [
      { title: '最炫民族风 完整版教学', sub: '32步 · 入门级', img: '/poster/dance_minzu.jpg', sectionTitle: '广场舞', sectionColor: '#DB2777' },
      { title: '广场舞基础步法入门', sub: '基础教学 · 零基础', img: '/poster/dance_basic.jpg', sectionTitle: '广场舞', sectionColor: '#DB2777' },
      { title: '扇子舞 茉莉花 精讲', sub: '64步 · 进阶级', img: '/poster/dance_shanzi.jpg', sectionTitle: '广场舞', sectionColor: '#DB2777' },
      { title: '太极养生健身操', sub: '养生系列 · 慢节奏', img: '/poster/dance_taiji.jpg', sectionTitle: '广场舞', sectionColor: '#DB2777' },
      { title: '水兵舞 海军风采', sub: '48步 · 中级', img: '/poster/dance_shuibing.jpg', sectionTitle: '广场舞', sectionColor: '#DB2777' },
      { title: '交谊舞慢三基本步', sub: '基础教学 · 入门', img: '/poster/dance_jiaoyi.jpg', sectionTitle: '广场舞', sectionColor: '#DB2777' },
      { title: '燃脂塑形健身操', sub: '30分钟 · 中高强度', img: '/poster/dance_jianshen.jpg', sectionTitle: '广场舞', sectionColor: '#DB2777' },
      { title: '集体舞 欢乐节拍', sub: '群舞教学 · 互动', img: '/poster/dance_group.jpg', sectionTitle: '广场舞', sectionColor: '#DB2777' },
    ]
  },
  {
    id: 'music', title: '音乐', icon: 'fas fa-music', color: '#0D9488', layout: 'music',
    items: [
      { title: '经典老歌合集', sub: '邓丽君 · 30首', img: '/poster/music_laoge.jpg', sectionTitle: '音乐', sectionColor: '#0D9488' },
      { title: '民歌精选', sub: '彭丽媛 · 20首', img: '/poster/music_minge.jpg', sectionTitle: '音乐', sectionColor: '#0D9488' },
      { title: '红歌联唱', sub: '经典合唱 · 25首', img: '/poster/music_hongge.jpg', sectionTitle: '音乐', sectionColor: '#0D9488' },
      { title: '轻音乐放松', sub: '纯音乐 · 15首', img: '/poster/music_qingyinyue.jpg', sectionTitle: '音乐', sectionColor: '#0D9488' },
      { title: '二胡名曲', sub: '传统器乐 · 12首', img: '/poster/music_erhu.jpg', sectionTitle: '音乐', sectionColor: '#0D9488' },
      { title: '古筝欣赏', sub: '古典器乐 · 18首', img: '/poster/music_guzheng.jpg', sectionTitle: '音乐', sectionColor: '#0D9488' },
      { title: '京剧名段', sub: '戏曲唱腔 · 20段', img: '/poster/music_jingju.jpg', sectionTitle: '音乐', sectionColor: '#0D9488' },
      { title: '葫芦丝经典', sub: '民族器乐 · 10首', img: '/poster/music_hulusi.jpg', sectionTitle: '音乐', sectionColor: '#0D9488' },
      { title: '钢琴轻柔曲', sub: '放松助眠 · 15首', img: '/poster/music_gangqin.jpg', sectionTitle: '音乐', sectionColor: '#0D9488' },
      { title: '萨克斯金曲', sub: '浪漫经典 · 12首', img: '/poster/music_sax.jpg', sectionTitle: '音乐', sectionColor: '#0D9488' },
    ]
  }
])

const filteredSections = computed(() => {
  if (!searchQuery.value) return sections.value
  const q = searchQuery.value.toLowerCase()
  return sections.value.map(s => {
    const filtered = s.items.filter(item => item.title.toLowerCase().includes(q) || item.sub.toLowerCase().includes(q))
    return { ...s, items: filtered }
  }).filter(s => s.items.length > 0)
})

function scrollTo(id) {
  activeNav.value = id
  if (id === 'all') {
    bodyRef.value && bodyRef.value.scrollTo({ top: 0, behavior: 'smooth' })
    return
  }
  const el = document.getElementById('sec-' + id)
  if (el) {
    const top = el.offsetTop - 60
    bodyRef.value && bodyRef.value.scrollTo({ top, behavior: 'smooth' })
  }
}

function onScroll() {
  if (!bodyRef.value) return
  const st = bodyRef.value.scrollTop
  for (const s of sections.value) {
    const el = document.getElementById('sec-' + s.id)
    if (el && el.offsetTop - 80 <= st && el.offsetTop + el.offsetHeight > st) {
      activeNav.value = s.id
      return
    }
  }
  activeNav.value = 'all'
}

function onSearch() {}

function openModal(item) {
  modalItem.value = item
  showModalFlag.value = true
}

function closeModal() {
  showModalFlag.value = false
}

function playVideo() {}

function addFav() {
  showToast('已收藏：' + modalItem.value.title)
}

function showToast(msg) {
  toastMsg.value = msg
  setTimeout(() => { toastMsg.value = '' }, 2500)
}

onMounted(() => {
  nextTick(() => {
    bodyRef.value = bodyRef.value
  })
})
</script>

<style>
/* 页面根容器 */
.page-root { width: 100%; height: 100%; display: flex; flex-direction: column; overflow: hidden; background: #fff; margin: 0; padding: 0; }
.page-header { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; background: #fff; border-bottom: 1px solid #E8ECF0; gap: 12px; padding: 0 20px; min-height: 48px; margin: 0; }
.page-body { flex: 1; overflow-y: auto; scroll-behavior: smooth; margin: 0; padding: 0px 0px; }

/* 分类导航 */
.nav-pill { padding: 8px 20px; border-radius: 20px; font-size: 16px; font-weight: 600; cursor: pointer; border: 1px solid #E8ECF0; background: #fff; color: #64748B; transition: all .2s; white-space: nowrap; }
.nav-pill:hover { border-color: #FF7222; color: #FF7222; }
.nav-pill.active { background: #FF7222; color: #fff; border-color: #FF7222; box-shadow: 0 2px 8px rgba(255,114,34,.25); }

/* 搜索框 */
.search-box { position: relative; width: 260px; flex-shrink: 0; }
.search-box input { width: 100%; padding: 10px 16px 10px 36px; border-radius: 24px; border: 1px solid #E8ECF0; font-size: 14px; outline: none; transition: all .2s; background: #F8FAFB; }
.search-box input:focus { border-color: #FF7222; box-shadow: 0 0 0 3px rgba(255,114,34,.08); }
.search-box i { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: #94A3B8; font-size: 14px; }

/* Hero 横幅 */
.hero-card { border-radius: 16px; overflow: hidden; position: relative; height: 200px; cursor: pointer; transition: transform .3s; }
.hero-card:hover { transform: scale(1.005); }
.hero-card img { width: 100%; height: 100%; object-fit: cover; }
.hero-overlay { position: absolute; inset: 0; background: linear-gradient(0deg, rgba(0,0,0,.75) 0%, rgba(0,0,0,.1) 50%, rgba(0,0,0,.2) 100%); display: flex; flex-direction: column; justify-content: flex-end; padding: 24px; }
.hero-play { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 56px; height: 56px; border-radius: 50%; background: rgba(255,114,34,.9); display: flex; align-items: center; justify-content: center; backdrop-filter: blur(8px); transition: all .3s; box-shadow: 0 4px 20px rgba(255,114,34,.4); }
.hero-card:hover .hero-play { transform: translate(-50%,-50%) scale(1.1); box-shadow: 0 6px 30px rgba(255,114,34,.5); }

/* 板块标题 */
.sec-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sec-title { display: flex; align-items: center; gap: 8px; }
.sec-dot { width: 4px; height: 18px; border-radius: 2px; }
.sec-more { font-size: 11px; color: #94A3B8; cursor: pointer; transition: color .2s; display: flex; align-items: center; gap: 4px; }
.sec-more:hover { color: #FF7222; }

/* 横向滚动容器 */
.scroll-row { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; scroll-behavior: smooth; -webkit-overflow-scrolling: touch; }
.scroll-row::-webkit-scrollbar { height: 3px; }

/* 海报卡片 */
.poster-card { width: 130px; flex-shrink: 0; cursor: pointer; transition: transform .25s; }
.poster-card:hover { transform: translateY(-4px); }
.poster-card .img-wrap { width: 130px; height: 185px; border-radius: 10px; overflow: hidden; position: relative; background: #E2E8F0; }
.poster-card .img-wrap img { width: 100%; height: 100%; object-fit: cover; transition: transform .4s; }
.poster-card:hover .img-wrap img { transform: scale(1.06); }
.poster-card .img-wrap .tag { position: absolute; top: 6px; left: 6px; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: 700; color: #fff; }
.poster-card .play-ico { position: absolute; bottom: 8px; right: 8px; width: 28px; height: 28px; border-radius: 50%; background: rgba(255,114,34,.85); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity .25s; backdrop-filter: blur(4px); }
.poster-card:hover .play-ico { opacity: 1; }
.poster-card .p-title { font-size: 12px; font-weight: 600; color: #1E293B; margin-top: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.poster-card .p-sub { font-size: 10px; color: #94A3B8; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 横版卡片 */
.wide-card { width: 240px; flex-shrink: 0; cursor: pointer; display: flex; gap: 10px; padding: 10px; border-radius: 10px; background: #fff; border: 1px solid #F1F5F9; transition: all .25s; align-items: center; }
.wide-card:hover { border-color: #E8ECF0; box-shadow: 0 4px 14px rgba(0,0,0,.06); transform: translateY(-2px); }
.wide-card .w-img { width: 96px; height: 64px; border-radius: 8px; overflow: hidden; flex-shrink: 0; background: #E2E8F0; }
.wide-card .w-img img { width: 100%; height: 100%; object-fit: cover; }
.wide-card .w-info { flex: 1; min-width: 0; }
.wide-card .w-title { font-size: 12px; font-weight: 600; color: #1E293B; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.4; }
.wide-card .w-sub { font-size: 10px; color: #94A3B8; margin-top: 3px; }

/* 音乐卡片 */
.music-card { width: 110px; flex-shrink: 0; cursor: pointer; transition: transform .25s; text-align: center; }
.music-card:hover { transform: translateY(-3px); }
.music-card .m-img { width: 110px; height: 110px; border-radius: 50%; overflow: hidden; margin: 0 auto; position: relative; background: #E2E8F0; box-shadow: 0 4px 16px rgba(0,0,0,.1); }
.music-card .m-img img { width: 100%; height: 100%; object-fit: cover; }
.music-card .m-img .m-play { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,.25); opacity: 0; transition: opacity .25s; border-radius: 50%; }
.music-card:hover .m-img .m-play { opacity: 1; }
.music-card .m-title { font-size: 11px; font-weight: 600; color: #1E293B; margin-top: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.music-card .m-artist { font-size: 10px; color: #94A3B8; margin-top: 1px; }

/* 新闻大卡 */
.news-featured { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.news-big { border-radius: 12px; overflow: hidden; position: relative; height: 160px; cursor: pointer; transition: transform .3s; }
.news-big:hover { transform: scale(1.01); }
.news-big img { width: 100%; height: 100%; object-fit: cover; }
.news-big .n-overlay { position: absolute; inset: 0; background: linear-gradient(0deg, rgba(0,0,0,.7) 0%, transparent 60%); display: flex; flex-direction: column; justify-content: flex-end; padding: 14px; }
.news-big .n-overlay h4 { color: #fff; font-size: 14px; font-weight: 700; line-height: 1.4; }
.news-big .n-overlay span { color: rgba(255,255,255,.7); font-size: 10px; margin-top: 4px; }

/* 弹窗 */
.modal-bg { position: fixed; inset: 0; background: rgba(15,23,42,.7); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 1000; animation: fadeIn .2s ease; }
.modal-box { background: #fff; border-radius: 24px; width: 90%; max-width: 600px; overflow: hidden; box-shadow: 0 28px 60px rgba(0,0,0,.25); animation: slideUp .3s ease; }
.modal-vid { width: 100%; aspect-ratio: 16/9; background: #0F172A; position: relative; display: flex; align-items: center; justify-content: center; }
.modal-vid img { width: 100%; height: 100%; object-fit: cover; opacity: .4; }
.modal-vid .big-play { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 72px; height: 72px; border-radius: 50%; background: rgba(255,114,34,.95); display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 6px 24px rgba(255,114,34,.5); z-index: 10; transition: all .3s; }
.modal-vid .big-play:hover { transform: translate(-50%,-50%) scale(1.1); }
.modal-info { padding: 24px; }
.modal-close { position: absolute; top: 14px; right: 14px; width: 36px; height: 36px; border-radius: 50%; background: rgba(0,0,0,.5); color: #fff; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all .2s; z-index: 2; border: none; font-size: 16px; }
.modal-close:hover { background: rgba(0,0,0,.7); transform: scale(1.1); }

/* Toast */
.toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); padding: 10px 24px; border-radius: 10px; background: #1E293B; color: #fff; font-size: 13px; font-weight: 500; z-index: 2000; box-shadow: 0 8px 24px rgba(0,0,0,.2); animation: slideUp .3s ease, fadeOut .3s ease 2s forwards; }

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fadeOut { from { opacity: 1; } to { opacity: 0; } }
</style>