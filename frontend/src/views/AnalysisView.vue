<template>
  <section class="page analysis-page">
    <header class="page-heading">
      <div><h1>分析中心</h1><p>选择服务器文件、通道和算法，结果使用 ECharts 在当前页面更新。</p></div>
      <a-space><a-button :disabled="!hasResult" @click="exportImage"><DownloadOutlined />保存图片</a-button><a-button type="primary" :loading="running" :disabled="!selectedDataset||!selectedChannels.length" @click="run">开始分析</a-button></a-space>
    </header>
    <section class="analysis-grid">
      <aside class="panel method-panel">
        <div class="panel-title"><strong>分析方法</strong></div>
        <div class="method-list">
          <button v-for="item in methods" :key="item.key" type="button" :class="{active:method===item.key}" @click="method=item.key">
            <BarChartOutlined /><span><strong>{{item.label}}</strong><small>{{item.description}}</small></span>
          </button>
        </div>
      </aside>
      <main class="panel result-panel">
        <div class="panel-title"><strong>分析结果</strong><span>{{ resultTitle }}</span></div>
        <div v-if="running" class="chart-loading"><a-skeleton active :paragraph="{rows:12}"/></div>
        <div v-else-if="!hasResult" class="empty-state"><a-empty description="选择文件和通道后开始分析"/></div>
        <EChart v-else ref="chartComponent" class="result-chart" :option="chartOption" aria-label="信号分析结果" />
        <div class="result-metrics">
          <span><small>通道数量</small><strong>{{selectedChannels.length}}</strong></span><span><small>分析点数</small><strong class="mono-number">{{Math.max(0,end-start).toLocaleString()}}</strong></span><span><small>采样率</small><strong class="mono-number">{{sampleRate.toLocaleString()}} Hz</strong></span><span><small>分析时长</small><strong class="mono-number">{{duration.toFixed(5)}} s</strong></span>
        </div>
      </main>
      <aside class="panel source-panel">
        <div class="panel-title"><strong>分析文件</strong></div>
        <div class="source-form">
          <label>服务器数据文件</label><a-select v-model:value="datasetId" show-search option-filter-prop="label" :options="datasetOptions" placeholder="选择文件" @change="datasetChanged" />
          <label>分析通道</label><a-select v-model:value="selectedChannels" mode="multiple" :max-tag-count="2" :options="channelOptions" placeholder="选择一个或多个通道"/>
          <label>采样率</label><a-input-number v-model:value="sampleRate" :min="1" style="width:100%"/>
          <div class="range-row"><div><label>起始点</label><a-input-number v-model:value="start" :min="0" :max="Math.max(0,totalSamples-1)"/></div><div><label>结束点</label><a-input-number v-model:value="end" :min="start+1" :max="totalSamples"/></div></div>
          <template v-if="method==='fft'||method==='power_spectrum'"><label>最大频率 (Hz)</label><a-input-number v-model:value="maxFrequency" :min="1" :max="sampleRate/2" style="width:100%"/></template>
          <a-alert v-if="selectedDataset" type="info" show-icon :message="selectedDataset.name" :description="selectedDataset.relative_path"/>
        </div>
      </aside>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { BarChartOutlined, DownloadOutlined } from '@ant-design/icons-vue'
import EChart from '@/components/EChart.vue'; import { api } from '@/services/api'
const datasets=ref([]),methods=ref([]),datasetId=ref(),selectedChannels=ref([]),method=ref('waveform'),sampleRate=ref(2_000_000),start=ref(0),end=ref(1),totalSamples=ref(1),maxFrequency=ref(100_000),running=ref(false),outputs=ref([])
const selectedDataset=computed(()=>datasets.value.find(item=>item.id===datasetId.value)); const datasetOptions=computed(()=>datasets.value.map(item=>({value:item.id,label:`${item.name} · ${item.relative_path}`}))); const channelOptions=computed(()=>(selectedDataset.value?.metadata?.channels||[]).map((c,i)=>({value:c,label:`${c} · 通道 ${i+1}`})))
const hasResult=computed(()=>outputs.value.length>0); const resultTitle=computed(()=>outputs.value[0]?.title||'等待分析'); const duration=computed(()=>Math.max(0,end.value-start.value)/(sampleRate.value||1))
const colors=['#2680eb','#22a699','#7d63d2','#e09132','#d64c4c','#3b9dc2']
const chartOption=computed(()=>({animation:false,color:colors,grid:{left:66,right:28,top:55,bottom:55},tooltip:{trigger:'axis'},legend:{top:12,type:'scroll'},toolbox:{right:12,feature:{dataZoom:{},restore:{},saveAsImage:{}}},dataZoom:[{type:'inside'},{type:'slider',height:18,bottom:8}],xAxis:{type:'value',name:outputs.value[0]?.xLabel||'',nameLocation:'middle',nameGap:35,splitLine:{lineStyle:{color:'#e5edf2'}}},yAxis:{type:'value',name:outputs.value[0]?.yLabel||'',splitLine:{lineStyle:{color:'#dce7ed'}}},series:outputs.value.map((output,index)=>({name:selectedChannels.value[index],type:output.kind==='bar'?'bar':'line',showSymbol:false,sampling:'lttb',progressive:5000,lineStyle:{width:1.2},data:output.x.map((x,i)=>[x,output.y[i]])}))}))
function sampleCount(dataset,channel){const shape=dataset?.metadata?.shapes?.[channel];return shape?.reduce((a,b)=>a*b,1)||dataset?.metadata?.total_samples||1}
function datasetChanged(){const d=selectedDataset.value;const channels=d?.metadata?.channels||[];selectedChannels.value=channels.slice(0,1);sampleRate.value=Number(d?.metadata?.sample_rate||2_000_000);totalSamples.value=sampleCount(d,channels[0]);start.value=0;end.value=method.value==='waveform'?totalSamples.value:Math.min(totalSamples.value,Math.floor(sampleRate.value));maxFrequency.value=Math.min(100_000,sampleRate.value/2);outputs.value=[]}
async function run(){running.value=true;outputs.value=[];try{const parameters={};if(method.value==='fft'||method.value==='power_spectrum'){parameters.min_frequency=0;parameters.max_frequency=maxFrequency.value}outputs.value=await Promise.all(selectedChannels.value.map(async channel=>(await api.preview({dataset_id:datasetId.value,channel,analysis_type:method.value,start:start.value,end:end.value,sample_rate:sampleRate.value,parameters}))))}catch(e){message.error(e.message)}finally{running.value=false}}
function exportImage(){message.info('可使用图表右上角的相机按钮保存当前图像。')}
onMounted(async()=>{try{const [d,t]=await Promise.all([api.datasets(),api.analysisTypes()]);datasets.value=d.items;methods.value=t.items;if(d.items.length){datasetId.value=d.items[0].id;datasetChanged()}}catch(e){message.error(e.message)}})
</script>

<style scoped>
.analysis-grid{flex:1;min-height:0;display:grid;grid-template-columns:220px minmax(560px,1fr) 300px;gap:10px}.method-panel,.result-panel,.source-panel{min-height:0;overflow:hidden}.method-list{padding:8px}.method-list button{width:100%;display:flex;gap:10px;align-items:flex-start;padding:11px 10px;border:0;border-left:3px solid transparent;background:none;color:#526b7b;text-align:left;cursor:pointer}.method-list button:hover{background:#f1f7fb}.method-list button.active{color:#1769cf;background:#e8f3ff;border-left-color:#2680eb}.method-list button>span{display:grid;gap:3px}.method-list strong{font-size:13px}.method-list small{color:#8799a5;font-size:10px;line-height:1.35}.result-panel{display:grid;grid-template-rows:45px minmax(0,1fr) 74px}.result-chart{min-height:0;padding:8px}.chart-loading{padding:24px}.result-metrics{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid #e0e9ee}.result-metrics span{display:grid;align-content:center;gap:5px;padding:9px 14px;border-right:1px solid #e5edf2}.result-metrics small{color:#8094a1}.result-metrics strong{font-size:15px}.source-form{display:grid;gap:9px;padding:14px}.source-form label{color:#536c7b;font-size:12px;font-weight:500}.source-form :deep(.ant-select){width:100%}.range-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}.range-row>div{display:grid;gap:8px}.range-row :deep(.ant-input-number){width:100%}
</style>
