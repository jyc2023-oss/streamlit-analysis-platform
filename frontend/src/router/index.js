import { createRouter, createWebHashHistory } from 'vue-router'
import { loadCurrentUser } from '@/stores/auth'
import UnifiedLayout from '@/layout/UnifiedLayout.vue'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { title: '登录' } },
  {
    path: '/', component: UnifiedLayout, redirect: '/dashboard', meta: { requiresAuth: true },
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: '工作台' } },
      { path: 'data', name: 'data', component: () => import('@/views/DataBrowserView.vue'), meta: { title: '数据浏览' } },
      { path: 'analysis', name: 'analysis', component: () => import('@/views/AnalysisView.vue'), meta: { title: '分析中心' } },
      { path: 'arc', name: 'arc', component: () => import('@/views/ArcDetectionView.vue'), meta: { title: '电弧识别' } },
      { path: 'history', name: 'history', component: () => import('@/views/HistoryView.vue'), meta: { title: '历史任务' } },
      { path: 'system', name: 'system', component: () => import('@/views/SystemView.vue'), meta: { title: '系统管理', admin: true } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach(async (to) => {
  document.title = `${to.meta.title || '数据分析'} - 实验管理系统`
  if (!to.meta.requiresAuth) return true
  const user = await loadCurrentUser()
  if (!user) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.admin && user.role !== 'admin') return { name: 'dashboard' }
  return true
})

export default router
