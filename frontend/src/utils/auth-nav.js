// 集中处理"被踢回登录页"逻辑：优先用 vue-router，失败再降级。
import router from '@/router'

export async function navigateToLogin() {
  try {
    await router.replace({ path: '/login' })
  } catch (e) {
    // 如果 router 还没装配好（极端情况，例如 init 阶段）才降级到硬刷
    window.location.href = '/login'
  }
}
