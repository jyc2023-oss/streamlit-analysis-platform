<template>
  <a-config-provider :locale="zhCN" :theme="theme">
    <router-view />
  </a-config-provider>
</template>

<script setup>
import zhCN from 'ant-design-vue/es/locale/zh_CN'

const theme = {
  token: {
    colorPrimary: '#2680eb',
    borderRadius: 4,
    fontFamily: "'Segoe UI Variable Text', 'PingFang SC', 'Microsoft YaHei', sans-serif",
  },
}
</script>
