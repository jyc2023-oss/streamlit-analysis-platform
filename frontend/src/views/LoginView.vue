<template>
  <main class="login-page">
    <section class="login-shell">
      <aside class="login-brand">
        <div class="login-brand-content">
          <span class="login-bolt"><ThunderboltOutlined /></span>
          <h1>实验管理系统</h1>
          <p>服务器数据分析与电弧动态检测</p>
          <ul>
            <li><CheckOutlined />直接读取服务器采集数据</li>
            <li><CheckOutlined />多通道信号分析与结果归档</li>
            <li><CheckOutlined />逐半周波电弧动态检测</li>
          </ul>
        </div>
      </aside>
      <section class="login-form-panel">
        <header><h2>欢迎登录</h2><p>通过 test-manager 进入时将自动完成登录</p></header>
        <a-alert v-if="error" :message="error" type="error" show-icon closable @close="error=''" />
        <a-form layout="vertical" :model="form" @finish="submit">
          <a-form-item label="用户名" name="username" :rules="[{ required:true,message:'请输入用户名' }]">
            <a-input v-model:value="form.username" size="large" autocomplete="username">
              <template #prefix><UserOutlined /></template>
            </a-input>
          </a-form-item>
          <a-form-item label="密码" name="password" :rules="[{ required:true,message:'请输入密码' }]">
            <a-input-password v-model:value="form.password" size="large" autocomplete="current-password">
              <template #prefix><LockOutlined /></template>
            </a-input-password>
          </a-form-item>
          <a-button type="primary" html-type="submit" size="large" block :loading="loading">登录分析平台</a-button>
        </a-form>
        <a-divider>统一登录</a-divider>
        <p class="sso-note">test-manager 的一次性登录接口配置完成后，此页面不会向普通用户显示。</p>
      </section>
    </section>
  </main>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CheckOutlined, LockOutlined, ThunderboltOutlined, UserOutlined } from '@ant-design/icons-vue'
import { api } from '@/services/api'
import { authState } from '@/stores/auth'

const router = useRouter(), route = useRoute()
const form = reactive({ username:'', password:'' })
const loading = ref(false), error = ref('')
async function submit(){
  loading.value=true; error.value=''
  try {
    const result=await api.login(form); authState.user=result.user; authState.loaded=true
    router.replace(String(route.query.redirect || '/dashboard'))
  } catch(e){ error.value=e.message } finally { loading.value=false }
}
</script>

<style scoped>
.login-page{min-height:100dvh;display:grid;place-items:center;padding:28px;background:radial-gradient(circle at 18% 10%,rgba(102,160,238,.15),transparent 32%),linear-gradient(135deg,#f7fafc,#eaf1f7)}
.login-shell{width:min(920px,94vw);min-height:570px;display:grid;grid-template-columns:1fr 1fr;background:#fff;border-radius:15px;overflow:hidden;box-shadow:0 18px 54px rgba(67,119,165,.16)}
.login-brand{position:relative;display:flex;align-items:center;padding:50px 44px;color:#fff;background:linear-gradient(140deg,#2d87ed,#66a0ee)}
.login-brand::after{content:"";position:absolute;inset:0;background:radial-gradient(circle at 85% 15%,rgba(255,255,255,.18),transparent 27%),linear-gradient(120deg,transparent 58%,rgba(255,255,255,.08));}
.login-brand-content{position:relative;z-index:1}.login-bolt{display:grid;place-items:center;width:78px;height:78px;margin-bottom:28px;border:1px solid rgba(255,255,255,.4);border-radius:50%;background:rgba(255,255,255,.16);font-size:34px}
.login-brand h1{margin:0 0 8px;font-size:28px;letter-spacing:1px}.login-brand p{margin:0;color:rgba(255,255,255,.88)}
.login-brand ul{list-style:none;margin:46px 0 0;padding:0;display:grid;gap:20px}.login-brand li{display:flex;align-items:center;gap:10px;font-size:14px}
.login-form-panel{padding:64px 52px 38px}.login-form-panel header{margin-bottom:34px}.login-form-panel h2{margin:0;color:#22394a;font-size:27px}.login-form-panel header p,.sso-note{color:#80919d;font-size:13px}.ant-alert{margin-bottom:18px}.sso-note{text-align:center;line-height:1.65}
</style>
