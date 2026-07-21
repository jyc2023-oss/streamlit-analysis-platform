# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from streamlit.components.v2 import component

_HTML = r"""
<section class="arc-workbench">
  <header class="arc-workbench__header">
    <div>
      <strong data-role="phase">准备检测</strong>
      <span data-role="counter">0 / 0 半波</span>
    </div>
    <div class="arc-workbench__controls">
      <button type="button" data-action="toggle">暂停播放</button>
      <label>播放速度
        <select data-action="speed">
          <option value="1">1×</option>
          <option value="2" selected>2×</option>
          <option value="5">5×</option>
          <option value="10">10×</option>
        </select>
      </label>
      <button type="button" data-action="replay">重新播放</button>
    </div>
  </header>
  <div class="arc-workbench__progress"><i data-role="progress"></i></div>
  <div class="arc-workbench__stage">
    <div class="arc-workbench__panel arc-workbench__panel--wave">
      <div class="arc-workbench__panel-title">
        <strong>当前半周波</strong><span data-role="wave-label">等待数据</span>
      </div>
      <canvas data-role="waveform"></canvas>
    </div>
    <div class="arc-workbench__panel arc-workbench__panel--probability">
      <div class="arc-workbench__panel-title">
        <strong>逐半周波有弧概率</strong><span>超过阈值的点标红</span>
      </div>
      <canvas data-role="probability"></canvas>
      <div class="arc-workbench__legend" data-role="legend"></div>
    </div>
  </div>
  <footer data-role="message">Python 后台正在准备检测任务……</footer>
</section>
"""

_CSS = r"""
.arc-workbench {
  color:#173f3b; font-family:"Segoe UI Variable Text","Microsoft YaHei UI",sans-serif;
  min-width:0; padding:.2rem 0 .25rem;
}
.arc-workbench__header {align-items:center; display:flex; gap:1rem; justify-content:space-between;}
.arc-workbench__header > div:first-child {display:flex; flex-direction:column; gap:.15rem;}
.arc-workbench__header strong {font-size:1rem;}
.arc-workbench__header span,.arc-workbench footer {color:#667b78; font-size:.82rem;}
.arc-workbench__controls {align-items:center; display:flex; flex-wrap:wrap; gap:.45rem;}
.arc-workbench button,.arc-workbench select {
  background:#fff; border:1px solid #c8d6d3; border-radius:.48rem; color:#294d49;
  cursor:pointer; font:inherit; font-size:.78rem; padding:.36rem .58rem;
}
.arc-workbench label {align-items:center; color:#667b78; display:flex; font-size:.78rem; gap:.35rem;}
.arc-workbench__progress {background:#e2ebe9; border-radius:99px; height:6px; margin:.7rem 0; overflow:hidden;}
.arc-workbench__progress i {background:#0f8a82; display:block; height:100%; transition:width 160ms linear; width:0;}
.arc-workbench__stage {display:grid; gap:.65rem; grid-template-rows:190px 390px;}
.arc-workbench__panel {background:#fff; border:1px solid #d7e2df; border-radius:.72rem; min-height:0; padding:.65rem .75rem;}
.arc-workbench__panel-title {align-items:center; display:flex; justify-content:space-between; margin-bottom:.35rem;}
.arc-workbench__panel-title strong {font-size:.88rem;}
.arc-workbench__panel-title span {color:#718582; font-size:.76rem;}
.arc-workbench canvas {display:block; height:calc(100% - 1.7rem); width:100%;}
.arc-workbench__legend {display:flex; flex-wrap:wrap; gap:.7rem; margin:.2rem 0 0 3.1rem;}
.arc-workbench__legend span {align-items:center; color:#526b68; display:flex; font-size:.72rem; gap:.3rem;}
.arc-workbench__legend i {border-radius:50%; display:inline-block; height:7px; width:7px;}
.arc-workbench footer {min-height:1.25rem; padding-top:.48rem;}
@media (max-width:760px) {
  .arc-workbench__header {align-items:flex-start; flex-direction:column;}
  .arc-workbench__stage {grid-template-rows:160px 330px;}
}
"""

_JS = r"""
const taskStates = new Map();
const colors = ["#0f8a82", "#2563eb", "#7c3aed", "#d97706", "#0891b2", "#65a30d"];

function canvasContext(canvas) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(10, Math.floor(rect.width * ratio));
  const height = Math.max(10, Math.floor(rect.height * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width; canvas.height = height;
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return {context, width:rect.width, height:rect.height};
}

function clear(context, width, height) {
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#ffffff"; context.fillRect(0, 0, width, height);
}

function drawWaveform(state) {
  const canvas = state.root?.querySelector('[data-role="waveform"]');
  if (!canvas) return;
  const {context, width, height} = canvasContext(canvas);
  clear(context, width, height);
  const available = state.targetChannels.map((channel,index) => {
    const displayed=Math.min(state.displayCounts[index] ?? 0,channel.probabilities.length);
    const previews=channel.waveform_previews ?? [];
    return {channel,index,displayed,values:displayed>0?previews[displayed-1]:null};
  }).filter(item => (item.values ?? []).length > 1);
  if (!available.length) {
    context.fillStyle="#8aa09d"; context.font="13px sans-serif";
    context.fillText("等待 Python 返回第一个半周波……", 18, height / 2); return;
  }
  const selected = available[state.waveCursor % available.length];
  const channel = selected.channel;
  const values = selected.values;
  let min = Math.min(...values), max = Math.max(...values);
  if (Math.abs(max-min) < 1e-12) {min-=1; max+=1;}
  context.strokeStyle="#dce7e5"; context.lineWidth=1;
  context.beginPath(); context.moveTo(0,height/2); context.lineTo(width,height/2); context.stroke();
  context.strokeStyle=colors[selected.index % colors.length]; context.lineWidth=1.25;
  context.beginPath();
  values.forEach((value,index) => {
    const x=index/(values.length-1)*width;
    const y=8+(max-value)/(max-min)*(height-16);
    if(index===0) context.moveTo(x,y); else context.lineTo(x,y);
  });
  context.stroke();
  const label=state.root.querySelector('[data-role="wave-label"]');
  if(label) label.textContent=`${channel.label} · 第 ${selected.displayed} 个半周波 · ${values.length} 点预览`;
}

function drawProbability(state) {
  const canvas = state.root?.querySelector('[data-role="probability"]');
  if (!canvas) return;
  const {context, width, height} = canvasContext(canvas);
  clear(context,width,height);
  const margin={left:48,right:14,top:10,bottom:28};
  const plotWidth=Math.max(1,width-margin.left-margin.right);
  const plotHeight=Math.max(1,height-margin.top-margin.bottom);
  context.strokeStyle="#dce7e5"; context.fillStyle="#718582"; context.font="11px sans-serif";
  context.lineWidth=1;
  for(let tick=0;tick<=4;tick+=1){
    const probability=tick/4; const y=margin.top+(1-probability)*plotHeight;
    context.beginPath(); context.moveTo(margin.left,y); context.lineTo(width-margin.right,y); context.stroke();
    context.fillText(probability.toFixed(2),5,y+4);
  }
  const visible = state.targetChannels.map((channel,index) => ({
    channel,index,count:Math.min(state.displayCounts[index] ?? 0,channel.probabilities.length)
  }));
  let maxTime=1;
  visible.forEach(item => {
    if(item.count) maxTime=Math.max(maxTime,item.channel.times[item.count-1] ?? 1);
  });
  const threshold=Number(state.threshold ?? .5);
  const thresholdY=margin.top+(1-threshold)*plotHeight;
  context.save(); context.setLineDash([7,6]); context.strokeStyle="#dc2626";
  context.beginPath(); context.moveTo(margin.left,thresholdY); context.lineTo(width-margin.right,thresholdY); context.stroke();
  context.restore(); context.fillStyle="#b91c1c"; context.fillText(`阈值 ${(threshold*100).toFixed(0)}%`,width-80,thresholdY-6);
  visible.forEach(({channel,index,count}) => {
    if(!count) return;
    context.strokeStyle=colors[index%colors.length]; context.lineWidth=1.15; context.beginPath();
    for(let point=0;point<count;point+=1){
      const x=margin.left+(channel.times[point]/maxTime)*plotWidth;
      const y=margin.top+(1-channel.probabilities[point])*plotHeight;
      if(point===0) context.moveTo(x,y); else context.lineTo(x,y);
    }
    context.stroke();
    for(let point=0;point<count;point+=1){
      const probability=channel.probabilities[point];
      const x=margin.left+(channel.times[point]/maxTime)*plotWidth;
      const y=margin.top+(1-probability)*plotHeight;
      context.fillStyle=probability>=threshold?"#dc2626":colors[index%colors.length];
      context.beginPath(); context.arc(x,y,probability>=threshold?2.8:1.7,0,Math.PI*2); context.fill();
    }
  });
  context.fillStyle="#718582"; context.fillText("时间 (s)",width/2-20,height-5);
  context.fillText("0",margin.left-3,height-8); context.fillText(maxTime.toFixed(2),width-margin.right-30,height-8);
}

function updateText(state) {
  const root=state.root; if(!root) return;
  const phase=root.querySelector('[data-role="phase"]');
  const counter=root.querySelector('[data-role="counter"]');
  const progress=root.querySelector('[data-role="progress"]');
  const message=root.querySelector('[data-role="message"]');
  const backendTotal=Number(state.total || 0), backendProcessed=Number(state.processed || 0);
  const displayed=state.displayCounts.reduce((sum,value)=>sum+value,0);
  if(phase) phase.textContent=state.phase || "动态检测工作台";
  if(counter) counter.textContent=`后台 ${backendProcessed}/${backendTotal} · 已播放 ${displayed} 个半波`;
  if(progress) progress.style.width=`${backendTotal?Math.min(100,backendProcessed/backendTotal*100):0}%`;
  if(message){
    if(state.status==="error") message.textContent=`检测失败：${state.error || "未知错误"}`;
    else if(state.status==="completed" && displayed>=backendTotal) message.textContent="动态播放完成；完整检测结果已交回 Streamlit，可保存图片、CSV 和任务记录。";
    else if(state.status==="completed") message.textContent="Python 检测已完成，前端正在播放剩余概率点……";
    else message.textContent="Python 在后台逐半周波检测；当前区域由 JavaScript 独立播放，不会刷新整页。";
  }
}

function draw(state){drawWaveform(state);drawProbability(state);updateText(state);}

function animate(state,time){
  if(!state.lastTime) state.lastTime=time;
  const elapsed=Math.min(250,time-state.lastTime); state.lastTime=time;
  if(!state.paused){
    state.credit += elapsed/1000*12*state.speed;
    const steps=Math.floor(state.credit); state.credit-=steps;
    if(steps>0){
      state.targetChannels.forEach((channel,index)=>{
        state.displayCounts[index]=Math.min(channel.probabilities.length,(state.displayCounts[index]??0)+steps);
      });
      state.waveCursor=(state.waveCursor+steps)%Math.max(1,state.targetChannels.length);
    }
  }
  draw(state); state.frame=requestAnimationFrame(next=>animate(state,next));
}

function bindControls(state){
  const root=state.root;
  const toggle=root.querySelector('[data-action="toggle"]');
  const speed=root.querySelector('[data-action="speed"]');
  const replay=root.querySelector('[data-action="replay"]');
  toggle.onclick=()=>{state.paused=!state.paused;toggle.textContent=state.paused?"继续播放":"暂停播放";};
  speed.value=String(state.speed); speed.onchange=()=>{state.speed=Number(speed.value)||1;};
  replay.onclick=()=>{state.displayCounts=state.targetChannels.map(()=>0);state.credit=0;state.paused=false;toggle.textContent="暂停播放";};
}

export default function(component) {
  const {data,parentElement}=component;
  const taskId=String(data.task_id || "unknown");
  let state=taskStates.get(taskId);
  if(!state){
    state={displayCounts:[],targetChannels:[],paused:false,speed:2,credit:0,lastTime:0,waveCursor:0,frame:null};
    taskStates.set(taskId,state);
  }
  state.root=parentElement.querySelector(".arc-workbench");
  state.targetChannels=(data.channels || []).map(channel=>({
    label:String(channel.label), times:(channel.times||[]).map(Number),
    probabilities:(channel.probabilities||[]).map(Number),
    latest_waveform:(channel.latest_waveform||[]).map(Number),
    waveform_previews:(channel.waveform_previews||[]).map(values=>values.map(Number)),
  }));
  while(state.displayCounts.length<state.targetChannels.length) state.displayCounts.push(0);
  Object.assign(state,{status:data.status,phase:data.phase,processed:data.processed,total:data.total,
    threshold:data.threshold,error:data.error});
  bindControls(state); draw(state);
  if(state.frame===null) state.frame=requestAnimationFrame(time=>animate(state,time));
}
"""

_ARC_STREAM_COMPONENT = component(
    "arc_dynamic_detection_workbench",
    html=_HTML,
    css=_CSS,
    js=_JS,
)


def render_arc_stream_workbench(snapshot: dict[str, Any], *, key: str) -> None:
    _ARC_STREAM_COMPONENT(
        data=snapshot,
        key=key,
        width="stretch",
        height="content",
    )
