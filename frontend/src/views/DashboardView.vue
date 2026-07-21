<template>
  <section class="page dashboard-page">
    <header class="welcome-panel">
      <div><p>数据分析工作台</p><h1>您好，{{ authState.user?.username }}</h1><span>采集数据、信号分析和电弧检测均已接入统一版页面。</span></div>
      <a-button type="primary" size="large" @click="router.push('/arc')"><ThunderboltOutlined />开始电弧检测</a-button>
    </header>
    <section class="metric-strip">
      <article><FolderOpenOutlined /><div><span>可用数据文件</span><strong class="mono-number">{{ stats.datasets }}</strong></div></article>
      <article><HistoryOutlined /><div><span>历史分析任务</span><strong class="mono-number">{{ stats.jobs }}</strong></div></article>
      <article><DeploymentUnitOutlined /><div><span>支持的数据格式</span><strong>BIN / MAT</strong></div></article>
      <article><ApiOutlined /><div><span>分析后端</span><strong class="service-ready">运行正常</strong></div></article>
    </section>
    <section class="panel quick-panel">
      <div class="panel-title"><strong>快捷入口</strong><span>进入常用的数据处理模块</span></div>
      <div class="quick-grid">
        <button v-for="item in quickLinks" :key="item.path" type="button" @click="router.push(item.path)">
          <span class="quick-icon"><component :is="item.icon" /></span><strong>{{ item.title }}</strong><small>{{ item.description }}</small>
        </button>
      </div>
    </section>
  </section>
</template>

<script setup>
import { h, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ApiOutlined, BarChartOutlined, DeploymentUnitOutlined, FolderOpenOutlined, HistoryOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import { authState } from '@/stores/auth'
import { api } from '@/services/api'
const router=useRouter(); const stats=reactive({datasets:'—',jobs:'—'})
const quickLinks=[
  {path:'/data',title:'数据浏览',description:'按目录查看服务器采集文件',icon:h(FolderOpenOutlined)},
  {path:'/analysis',title:'分析中心',description:'波形、FFT、小波和滤波分析',icon:h(BarChartOutlined)},
  {path:'/arc',title:'电弧识别',description:'逐半周波动态检测',icon:h(ThunderboltOutlined)},
  {path:'/history',title:'历史任务',description:'查询和下载已保存结果',icon:h(HistoryOutlined)},
]
onMounted(async()=>{try{const [d,j]=await Promise.all([api.datasets(),api.jobs()]);stats.datasets=d.total;stats.jobs=j.total}catch{}})
</script>

<style scoped>
.welcome-panel{min-height:142px;display:flex;align-items:center;justify-content:space-between;padding:22px 30px;color:#263f51;background:linear-gradient(105deg,#fff 0,#eaf6ff 65%,#d7edff 100%);border:1px solid #fff;box-shadow:var(--shadow)}
.welcome-panel p{margin:0 0 7px;color:#2680eb;font-weight:600}.welcome-panel h1{margin:0 0 7px;font-size:27px}.welcome-panel span{color:#758b99;font-size:13px}
.metric-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.metric-strip article{min-height:96px;display:flex;align-items:center;gap:16px;padding:17px 20px;background:#fff;border:1px solid var(--line);box-shadow:var(--shadow);font-size:26px;color:#2680eb}.metric-strip article div{display:grid;gap:5px}.metric-strip span{color:#738796;font-size:12px}.metric-strip strong{color:#263f51;font-size:20px}.metric-strip .service-ready{color:#359468;font-size:16px}
.quick-panel{flex:1}.panel-title>span{color:#8295a2;font-size:12px}.quick-grid{height:calc(100% - 45px);display:grid;grid-template-columns:repeat(4,1fr);gap:14px;padding:18px}.quick-grid button{min-height:175px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;border:1px solid #e1eaf0;background:#f9fcfe;color:#2b4659;cursor:pointer;transition:transform 180ms,border-color 180ms,box-shadow 180ms}.quick-grid button:hover{transform:translateY(-3px);border-color:#7db7f2;box-shadow:0 9px 24px rgba(38,128,235,.13);background:#fff}.quick-icon{width:58px;height:58px;display:grid;place-items:center;border-radius:50%;color:#2680eb;background:#e8f3ff;font-size:27px}.quick-grid strong{font-size:16px}.quick-grid small{color:#8295a2}
</style>
