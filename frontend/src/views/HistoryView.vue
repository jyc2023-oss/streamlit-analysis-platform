<template>
  <section class="page">
    <header class="page-heading"><div><h1>历史任务</h1><p>查看已经保存的分析记录、算法参数和结果文件。</p></div><a-button :loading="loading" @click="load"><ReloadOutlined />刷新</a-button></header>
    <section class="panel history-panel">
      <div class="panel-title"><strong>分析记录</strong><span>共 {{items.length}} 项</span></div>
      <a-table :columns="columns" :data-source="items" row-key="id" size="small" :loading="loading" :pagination="{pageSize:18}">
        <template #bodyCell="{column,record}">
          <template v-if="column.key==='id'"><a-typography-text copyable>{{record.id.slice(0,12)}}</a-typography-text></template>
          <template v-else-if="column.key==='status'"><a-tag :color="statusColor[record.status]">{{statusText[record.status]||record.status}}</a-tag></template>
          <template v-else-if="column.key==='type'">{{typeText[record.analysis_type]||record.analysis_type}}</template>
          <template v-else-if="column.key==='parameters'"><a-button type="link" size="small" @click="showParameters(record)">查看参数</a-button></template>
        </template>
      </a-table>
    </section>
    <a-drawer v-model:open="drawer" title="任务参数" width="520"><pre>{{JSON.stringify(current?.parameters,null,2)}}</pre></a-drawer>
  </section>
</template>
<script setup>
import { onMounted,ref } from 'vue'; import { message } from 'ant-design-vue'; import { ReloadOutlined } from '@ant-design/icons-vue'; import { api } from '@/services/api'
const items=ref([]),loading=ref(false),drawer=ref(false),current=ref(null);const columns=[{title:'任务编号',key:'id',width:150},{title:'文件',dataIndex:'dataset_name',ellipsis:true},{title:'用户',dataIndex:'username',width:110},{title:'分析方法',key:'type',width:130},{title:'状态',key:'status',width:90},{title:'创建时间',dataIndex:'created_at',width:190},{title:'参数',key:'parameters',width:90}];const statusText={success:'已完成',running:'运行中',waiting:'等待',failed:'失败'},statusColor={success:'green',running:'blue',waiting:'orange',failed:'red'},typeText={arc_features:'电弧识别',waveform:'原始波形',fft:'FFT 幅值谱'}
async function load(){loading.value=true;try{items.value=(await api.jobs()).items}catch(e){message.error(e.message)}finally{loading.value=false}}function showParameters(item){current.value=item;drawer.value=true}onMounted(load)
</script>
<style scoped>.history-panel{flex:1;min-height:0;overflow:hidden}.history-panel :deep(.ant-table-wrapper){padding:10px}.panel-title span{color:#8095a3;font-size:12px}pre{padding:14px;color:#2e4b5f;background:#f2f7fa;border:1px solid #dae6ed;white-space:pre-wrap;overflow-wrap:anywhere}</style>
