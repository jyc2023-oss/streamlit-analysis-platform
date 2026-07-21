<template>
  <section class="page arc-page">
    <header class="page-heading">
      <div><h1>电弧动态检测</h1><p>Python 后台逐半周波识别，Vue 与 ECharts 在前端同步播放波形和概率。</p></div>
      <a-space><a-button :disabled="!taskId" @click="togglePlayback">{{paused?'继续播放':'暂停播放'}}</a-button><a-select v-model:value="speed" style="width:92px" :options="speedOptions"/><a-button :disabled="!taskId" @click="replay">重新播放</a-button><a-button type="primary" :loading="starting" :disabled="!datasetId||!selectedChannels.length" @click="startDetection"><ThunderboltOutlined />开始检测</a-button></a-space>
    </header>
    <section class="arc-grid">
      <aside class="panel arc-settings">
        <div class="panel-title"><strong>数据与参数</strong></div>
        <div class="settings-body">
          <label>116 数据文件</label><a-select v-model:value="datasetId" show-search option-filter-prop="label" :options="datasetOptions" @change="datasetChanged"/>
          <label>检测通道</label><a-select v-model:value="selectedChannels" mode="multiple" :options="channelOptions"/>
          <a-alert type="info" show-icon message="默认训练通道" description="默认选择116文件的第二物理通道，即文件数组 CH1、网页 CH02。"/>
          <label>单半波概率阈值</label><a-slider v-model:value="thresholdPercent" :min="1" :max="99"/><div class="parameter-value">{{thresholdPercent}}%</div>
          <label>文件判定所需半波数</label><a-input-number v-model:value="requiredHalfwaves" :min="1" style="width:100%"/>
          <label>采样率</label><a-input-number v-model:value="sampleRate" :min="1" style="width:100%"/>
          <a-divider/>
          <div class="source-caption"><span>当前文件</span><strong>{{selectedDataset?.name||'尚未选择'}}</strong><small>{{selectedDataset?.relative_path}}</small></div>
        </div>
      </aside>
      <main class="arc-workspace">
        <section class="panel progress-panel">
          <div class="progress-copy"><strong>{{phaseText}}</strong><span>后台 {{backendProcessed}}/{{backendTotal}} · 已播放 {{displayedTotal}} 个半波</span></div>
          <a-progress :percent="progressPercent" :show-info="false" stroke-color="#2680eb"/>
          <div v-if="summary" :class="['verdict',summary.folder_is_arc?'danger':'clear']"><span>文件夹结论</span><strong>{{summary.folder_result}}</strong><small>{{summary.arc_halfwaves}}/{{summary.total_halfwaves}} 个半波达到阈值</small></div>
        </section>
        <section class="panel waveform-panel">
          <div class="panel-title"><strong>当前半周波</strong><span>{{currentWaveLabel}}</span></div>
          <EChart :option="waveOption" aria-label="当前半周波波形"/>
        </section>
        <section class="panel probability-panel">
          <div class="panel-title"><strong>逐半周波有弧概率</strong><span>超过阈值的点标红</span></div>
          <EChart :option="probabilityOption" aria-label="逐半周波有弧概率"/>
        </section>
        <section v-if="taskStatus==='completed'" class="result-actions">
          <a-space><a-button type="primary" :loading="saving" @click="saveResult">保存分析任务</a-button><a-button :href="downloadUrl(`/arc/tasks/${taskId}/export/png`)">下载 PNG</a-button><a-button :href="downloadUrl(`/arc/tasks/${taskId}/export/csv`)">导出 CSV</a-button></a-space>
          <span>完整结果已交回分析后端，可保存和导出。</span>
        </section>
      </main>
    </section>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'; import { ThunderboltOutlined } from '@ant-design/icons-vue'
import EChart from '@/components/EChart.vue'; import { api, arcSocketUrl, downloadUrl } from '@/services/api'
const datasets=ref([]),datasetId=ref(),selectedChannels=ref([]),sampleRate=ref(2_000_000),thresholdPercent=ref(50),requiredHalfwaves=ref(3),starting=ref(false),saving=ref(false),taskId=ref(''),snapshot=ref(null),displayCounts=ref([]),paused=ref(false),speed=ref(2),summary=ref(null)
let socket=null,timer=null,credit=0
const speedOptions=[1,2,5,10].map(v=>({value:v,label:`${v}×`})); const selectedDataset=computed(()=>datasets.value.find(d=>d.id===datasetId.value)); const datasetOptions=computed(()=>datasets.value.map(d=>({value:d.id,label:`${d.name} · ${d.relative_path}`}))); const channelOptions=computed(()=>(selectedDataset.value?.metadata?.channels||[]).map((c,i)=>({value:c,label:`${c} · 网页 CH${String(i+1).padStart(2,'0')}`})))
const taskStatus=computed(()=>snapshot.value?.status||'idle'),backendProcessed=computed(()=>snapshot.value?.processed||0),backendTotal=computed(()=>snapshot.value?.total||0),displayedTotal=computed(()=>displayCounts.value.reduce((a,b)=>a+b,0)),progressPercent=computed(()=>backendTotal.value?Math.round(backendProcessed.value/backendTotal.value*100):0),phaseText=computed(()=>snapshot.value?.phase||'等待开始检测')
const channels=computed(()=>snapshot.value?.channels||[]); const colors=['#2680eb','#20a391','#7d63d2','#db8b29','#d64c4c']
const currentChannelIndex=computed(()=>{const available=channels.value.map((c,i)=>({i,count:Math.min(displayCounts.value[i]||0,c.probabilities?.length||0)})).filter(v=>v.count>0);return available.length?available[(displayedTotal.value-1)%available.length].i:0}); const currentCount=computed(()=>Math.min(displayCounts.value[currentChannelIndex.value]||0,channels.value[currentChannelIndex.value]?.probabilities?.length||0)); const currentWave=computed(()=>channels.value[currentChannelIndex.value]?.waveform_previews?.[Math.max(0,currentCount.value-1)]||[]); const currentWaveLabel=computed(()=>currentCount.value?`${channels.value[currentChannelIndex.value]?.label} · 第 ${currentCount.value} 个半周波`:'等待数据')
const waveOption=computed(()=>({animation:false,grid:{left:58,right:22,top:18,bottom:38},tooltip:{trigger:'axis'},xAxis:{type:'category',name:'半周波采样预览',data:currentWave.value.map((_,i)=>i),axisLabel:{show:false},splitLine:{show:false}},yAxis:{type:'value',splitLine:{lineStyle:{color:'#e2eaef'}}},series:[{type:'line',showSymbol:false,lineStyle:{width:1.4,color:colors[currentChannelIndex.value%colors.length]},data:currentWave.value}]}))
const probabilityOption=computed(()=>({animation:false,color:colors,grid:{left:62,right:28,top:48,bottom:46},tooltip:{trigger:'axis'},legend:{top:12,type:'scroll'},xAxis:{type:'value',name:'时间 (s)',nameLocation:'middle',nameGap:31,splitLine:{show:false}},yAxis:{type:'value',min:0,max:1,name:'有弧概率',splitLine:{lineStyle:{color:'#dce7ed'}}},series:[...channels.value.map((channel,index)=>{const count=Math.min(displayCounts.value[index]||0,channel.probabilities?.length||0);return{name:channel.label,type:'line',showSymbol:true,symbolSize:4,lineStyle:{width:1.1},itemStyle:{color:(p)=>p.value[1]>=thresholdPercent.value/100?'#df3434':colors[index%colors.length]},data:(channel.times||[]).slice(0,count).map((t,i)=>[t,channel.probabilities[i]])}}),{name:'判定阈值',type:'line',symbol:'none',lineStyle:{color:'#df3434',type:'dashed',width:1.3},data:[[0,thresholdPercent.value/100],[Math.max(1,...channels.value.flatMap(c=>c.times||[])),thresholdPercent.value/100]]}]}))
function datasetChanged(){const d=selectedDataset.value;const list=d?.metadata?.channels||[];selectedChannels.value=list.length>1?[list[1]]:list.slice(0,1);sampleRate.value=Number(d?.metadata?.sample_rate||2_000_000);resetTask()}
function resetTask(){socket?.close();taskId.value='';snapshot.value=null;displayCounts.value=[];summary.value=null;paused.value=false;credit=0}
function connect(id){socket?.close();socket=new WebSocket(arcSocketUrl(id));socket.onmessage=async(event)=>{const data=JSON.parse(event.data);snapshot.value=data.snapshot;while(displayCounts.value.length<channels.value.length)displayCounts.value.push(0);if(data.snapshot.status==='completed'){try{summary.value=(await api.arcResult(id)).result.summary}catch{}}};socket.onerror=()=>message.error('动态检测连接中断，请重新开始检测。')}
async function startDetection(){starting.value=true;resetTask();try{const result=await api.startArc({channels:selectedChannels.value.map((channel,i)=>({dataset_id:datasetId.value,channel,label:`2CH · CH${String((selectedDataset.value.metadata.channels||[]).indexOf(channel)+1).padStart(2,'0')}`})),sample_rate:sampleRate.value,probability_threshold:thresholdPercent.value/100,required_arc_halfwaves:requiredHalfwaves.value});taskId.value=result.taskId;snapshot.value=result.snapshot;displayCounts.value=(result.snapshot.channels||[]).map(()=>0);connect(taskId.value)}catch(e){message.error(e.message)}finally{starting.value=false}}
function tick(){if(paused.value||!snapshot.value)return;credit+=12*speed.value/10;const steps=Math.floor(credit);credit-=steps;if(!steps)return;displayCounts.value=channels.value.map((channel,index)=>Math.min(channel.probabilities?.length||0,(displayCounts.value[index]||0)+steps))}
function togglePlayback(){paused.value=!paused.value} function replay(){displayCounts.value=channels.value.map(()=>0);paused.value=false;credit=0} async function saveResult(){saving.value=true;try{const r=await api.saveArc(taskId.value);message.success(`任务已保存：${r.jobId.slice(0,10)}`)}catch(e){message.error(e.message)}finally{saving.value=false}}
onMounted(async()=>{timer=setInterval(tick,100);try{const d=await api.datasets();datasets.value=d.items.filter(item=>Number(item.metadata?.channels_count)===2);if(datasets.value.length){datasetId.value=datasets.value[0].id;datasetChanged()}}catch(e){message.error(e.message)}});onBeforeUnmount(()=>{clearInterval(timer);socket?.close()})
</script>

<style scoped>
.arc-grid{flex:1;min-height:0;display:grid;grid-template-columns:300px minmax(0,1fr);gap:10px}.arc-settings{min-height:0;overflow:auto}.settings-body{display:grid;gap:9px;padding:14px}.settings-body label{color:#526b7b;font-size:12px;font-weight:600}.parameter-value{margin-top:-12px;text-align:right;color:#1769cf;font-size:12px}.source-caption{display:grid;gap:5px}.source-caption span,.source-caption small{color:#8295a2;font-size:11px}.source-caption strong{overflow-wrap:anywhere;font-size:12px}.arc-workspace{min-height:0;display:grid;grid-template-rows:74px minmax(185px,.72fr) minmax(310px,1.28fr) 42px;gap:10px}.progress-panel{display:grid;grid-template-columns:minmax(280px,1fr) 2fr auto;align-items:center;gap:18px;padding:10px 15px}.progress-copy{display:grid;gap:5px}.progress-copy strong{font-size:14px}.progress-copy span{color:#7d919f;font-size:11px}.verdict{min-width:220px;display:grid;grid-template-columns:auto auto;gap:1px 12px;padding:6px 12px;border-left:3px solid}.verdict span,.verdict small{font-size:10px}.verdict small{grid-column:1/-1}.verdict strong{font-size:18px}.verdict.danger{color:#c73333;background:#fff3f2;border-color:#df3434}.verdict.clear{color:#27845c;background:#effaf5;border-color:#36a269}.waveform-panel,.probability-panel{min-height:0;display:grid;grid-template-rows:45px minmax(0,1fr)}.panel-title span{color:#8295a2;font-size:11px}.result-actions{display:flex;align-items:center;justify-content:space-between}.result-actions>span{color:#718693;font-size:11px}
</style>
