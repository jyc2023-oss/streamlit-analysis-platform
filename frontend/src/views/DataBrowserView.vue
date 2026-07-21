<template>
  <section class="page">
    <header class="page-heading">
      <div><h1>数据浏览</h1><p>直接查看服务器已经完成索引的 BIN 和 MAT 数据。</p></div>
      <a-space><a-input-search v-model:value="search" placeholder="文件名或目录" allow-clear @search="load"/><a-button @click="load"><ReloadOutlined />刷新</a-button><a-button v-if="authState.user?.role==='admin'" type="primary" :loading="scanning" @click="scan">重新扫描目录</a-button></a-space>
    </header>
    <section class="browser-grid">
      <aside class="panel tree-panel">
        <div class="panel-title"><strong>服务器目录</strong><span>{{ total }} 个文件</span></div>
        <div class="tree-scroll"><a-skeleton v-if="loading" active :paragraph="{rows:10}"/><a-tree v-else show-line block-node :tree-data="tree" @select="selectTree"/></div>
      </aside>
      <section class="panel file-panel">
        <div class="panel-title"><strong>数据文件</strong><span>{{ selectedFolder || '全部目录' }}</span></div>
        <a-table :data-source="filteredItems" :columns="columns" :loading="loading" row-key="id" size="small" :pagination="{pageSize:18,showSizeChanger:true}">
          <template #bodyCell="{column,record}">
            <template v-if="column.key==='name'"><button class="file-link" @click="openFile(record)">{{record.name}}</button></template>
            <template v-else-if="column.key==='status'"><span><i :class="['status-dot',record.status]"></i>{{statusText[record.status]||record.status}}</span></template>
            <template v-else-if="column.key==='channels'">{{record.metadata?.channels_count ?? '—'}} 通道</template>
            <template v-else-if="column.key==='size'">{{formatBytes(record.size_bytes)}}</template>
          </template>
        </a-table>
      </section>
    </section>
    <a-drawer v-model:open="drawer" title="文件信息" width="520">
      <a-descriptions v-if="current" bordered :column="1" size="small">
        <a-descriptions-item label="文件名">{{current.name}}</a-descriptions-item><a-descriptions-item label="位置">{{current.relative_path}}</a-descriptions-item><a-descriptions-item label="格式">{{current.extension}}</a-descriptions-item><a-descriptions-item label="采样率">{{current.metadata?.sample_rate || '—'}} Hz</a-descriptions-item><a-descriptions-item label="通道"><a-tag v-for="channel in current.metadata?.channels||[]" :key="channel">{{channel}}</a-tag></a-descriptions-item>
      </a-descriptions>
    </a-drawer>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { api } from '@/services/api'; import { authState } from '@/stores/auth'
const items=ref([]),tree=ref([]),loading=ref(false),scanning=ref(false),search=ref(''),selectedFolder=ref(''),drawer=ref(false),current=ref(null),total=ref(0)
const columns=[{title:'文件名',key:'name',width:360},{title:'目录',dataIndex:'relative_path',ellipsis:true},{title:'通道',key:'channels',width:90},{title:'大小',key:'size',width:100},{title:'状态',key:'status',width:90},{title:'更新时间',dataIndex:'modified_at',width:190}]
const statusText={ready:'可用',pending:'等待',error:'错误',missing:'缺失'}
const filteredItems=computed(()=>items.value.filter(item=>!selectedFolder.value||item.relative_path.replaceAll('\\','/').startsWith(selectedFolder.value)))
function formatBytes(v){if(v<1024)return `${v} B`;if(v<1024**2)return `${(v/1024).toFixed(1)} KB`;if(v<1024**3)return `${(v/1024**2).toFixed(1)} MB`;return `${(v/1024**3).toFixed(2)} GB`}
async function load(){loading.value=true;try{const [files,nodes]=await Promise.all([api.datasets(search.value),api.datasetTree()]);items.value=files.items;total.value=files.total;tree.value=nodes.nodes}catch(e){message.error(e.message)}finally{loading.value=false}}
function selectTree(keys,info){const key=keys[0]||'';if(String(key).startsWith('folder:'))selectedFolder.value=String(key).slice(7);if(info.node?.dataset)openFile(info.node.dataset)}
function openFile(item){current.value=item;drawer.value=true}
async function scan(){scanning.value=true;try{const result=await api.scan();message.success(`扫描完成：发现 ${result.seen} 个文件`);await load()}catch(e){message.error(e.message)}finally{scanning.value=false}}
onMounted(load)
</script>

<style scoped>
.browser-grid{flex:1;min-height:0;display:grid;grid-template-columns:310px minmax(0,1fr);gap:10px}.tree-panel,.file-panel{min-height:0;overflow:hidden}.tree-scroll{height:calc(100% - 45px);padding:10px;overflow:auto}.panel-title span{color:#8095a3;font-size:12px}.file-panel :deep(.ant-table-wrapper){padding:10px}.file-link{max-width:100%;padding:0;border:0;color:#1769cf;background:none;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}.file-link:hover{text-decoration:underline}
</style>
