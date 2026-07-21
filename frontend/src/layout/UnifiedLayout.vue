<template>
  <a-layout class="app-shell">
    <a-layout-header class="app-header">
      <button class="brand" type="button" @click="router.push('/dashboard')">
        <span class="brand-mark"><ThunderboltOutlined /></span>
        <span class="brand-title">实验管理系统</span>
        <span class="brand-division">数据分析</span>
      </button>

      <a-menu
        mode="horizontal"
        theme="light"
        class="main-navigation"
        :selected-keys="[route.path]"
        :items="menuItems"
        @click="({ key }) => router.push(key)"
      />

      <div class="user-area">
        <a-button v-if="authState.managerUrl" type="text" class="header-action" @click="returnToManager">
          <template #icon><RollbackOutlined /></template>返回主系统
        </a-button>
        <span class="user-avatar"><UserOutlined /></span>
        <span class="user-name">{{ authState.user?.username }}</span>
        <a-button type="text" class="header-icon" aria-label="退出登录" @click="confirmLogout">
          <template #icon><LogoutOutlined /></template>
        </a-button>
      </div>
    </a-layout-header>

    <nav class="sub-tabs" aria-label="数据分析模块">
      <button
        v-for="item in menuItems"
        :key="item.key"
        type="button"
        :class="{ active: route.path === item.key }"
        @click="router.push(item.key)"
      >{{ item.label }}</button>
    </nav>

    <a-layout-content id="main-content" class="app-content">
      <router-view v-slot="{ Component }">
        <keep-alive include="DataBrowserView,AnalysisView,ArcDetectionView">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </a-layout-content>

    <footer class="visited-tabs" aria-label="当前访问页面">
      <span class="visited-label">当前位置</span>
      <span class="visited-item active">{{ route.meta.title }}</span>
      <span class="connection-state"><i></i>分析服务已连接</span>
    </footer>
  </a-layout>
</template>

<script setup>
import { computed, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Modal } from 'ant-design-vue'
import {
  AppstoreOutlined, BarChartOutlined, FolderOpenOutlined, HistoryOutlined,
  LogoutOutlined, RollbackOutlined, SettingOutlined, ThunderboltOutlined, UserOutlined,
} from '@ant-design/icons-vue'
import { authState, clearCurrentUser } from '@/stores/auth'

const router = useRouter()
const route = useRoute()

const menuItems = computed(() => {
  const items = [
    { key: '/dashboard', label: '工作台', icon: () => h(AppstoreOutlined) },
    { key: '/data', label: '数据浏览', icon: () => h(FolderOpenOutlined) },
    { key: '/analysis', label: '分析中心', icon: () => h(BarChartOutlined) },
    { key: '/arc', label: '电弧识别', icon: () => h(ThunderboltOutlined) },
    { key: '/history', label: '历史任务', icon: () => h(HistoryOutlined) },
  ]
  if (authState.user?.role === 'admin') {
    items.push({ key: '/system', label: '系统管理', icon: () => h(SettingOutlined) })
  }
  return items
})

function returnToManager() { window.location.assign(authState.managerUrl) }

function confirmLogout() {
  Modal.confirm({
    title: '确认退出', content: '退出后需要重新通过实验管理系统进入。',
    okText: '确认', cancelText: '取消',
    async onOk() { await clearCurrentUser(); router.replace('/login') },
  })
}
</script>
