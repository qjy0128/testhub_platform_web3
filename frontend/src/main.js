import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElLoading } from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/el-loading.css'
import { useUserStore } from '@/stores/user'
import i18n from './locales'

import App from './App.vue'
import router from './router'
import './assets/css/global.scss'

// 注：组件由 unplugin-vue-components + ElementPlusResolver 自动按需引入。
// 指令（v-loading 等）需要显式 use，不会被自动按需引入。

async function init() {
  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)

  try {
    const userStore = useUserStore()
    await userStore.initAuth()
  } catch (error) {
    // 获取用户信息失败说明未登录；交给路由守卫处理。
  }

  app.use(router)
  app.use(i18n)
  app.use(ElLoading)
  app.mount('#app')
}

init()
