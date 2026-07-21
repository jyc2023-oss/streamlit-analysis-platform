<template>
  <section class="page">
    <header class="page-heading"><div><h1>系统管理</h1><p>统一版用户状态与 test-manager SSO 接入信息。</p></div><a-button @click="load">刷新</a-button></header>
    <section class="system-grid">
      <section class="panel"><div class="panel-title"><strong>用户账号</strong></div><a-table :columns="columns" :data-source="users" row-key="id" size="small" :pagination="false"><template #bodyCell="{column,record}"><template v-if="column.key==='role'"><a-tag :color="record.role==='admin'?'blue':'default'">{{record.role==='admin'?'管理员':'分析人员'}}</a-tag></template><template v-else-if="column.key==='active'"><a-switch :checked="Boolean(record.is_active)" :disabled="record.id===authState.user?.id" @change="value=>changeStatus(record,value)"/></template></template></a-table></section>
      <aside class="panel"><div class="panel-title"><strong>统一登录状态</strong></div><div class="sso-status"><a-result :status="authState.ssoEnabled?'success':'info'" :title="authState.ssoEnabled?'SSO 验证接口已配置':'等待 test-manager 接口'" :sub-title="authState.ssoEnabled?'用户可从 test-manager 免登录进入。':'配置 MANAGER_SSO_VERIFY_URL 后自动启用。'"/><a-descriptions bordered :column="1" size="small"><a-descriptions-item label="主系统地址">{{authState.managerUrl||'尚未配置'}}</a-descriptions-item><a-descriptions-item label="会话方式">HttpOnly Cookie</a-descriptions-item><a-descriptions-item label="本地应急登录">已保留</a-descriptions-item></a-descriptions></div></aside>
    </section>
  </section>
</template>
<script setup>
import { onMounted,ref } from 'vue';import {message} from 'ant-design-vue';import {api} from '@/services/api';import {authState} from '@/stores/auth'
const users=ref([]);const columns=[{title:'ID',dataIndex:'id',width:70},{title:'用户名',dataIndex:'username'},{title:'角色',key:'role',width:110},{title:'创建时间',dataIndex:'created_at',width:190},{title:'启用',key:'active',width:80}];async function load(){try{users.value=(await api.users()).items}catch(e){message.error(e.message)}}async function changeStatus(record,active){try{await api.userStatus(record.id,active);record.is_active=active?1:0;message.success('账号状态已更新')}catch(e){message.error(e.message)}}onMounted(load)
</script>
<style scoped>.system-grid{flex:1;display:grid;grid-template-columns:minmax(600px,1.7fr) minmax(360px,1fr);gap:10px}.system-grid>.panel{min-height:0;overflow:auto}.system-grid :deep(.ant-table-wrapper){padding:10px}.sso-status{padding:8px 18px 18px}.sso-status :deep(.ant-result){padding:26px 10px}</style>
