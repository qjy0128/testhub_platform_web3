// 轻量级前端 logger。
// - 开发环境：直接走 console；
// - 生产环境：debug/info 静默，warn/error 走 console.error 以便监控接管。
//
// vite.config.js 的 esbuild.pure 会在生产构建时丢弃 console.log/info/debug/warn，
// 这里把这些调用统一走 logger 就能保持入口一致。

const isDev = import.meta.env.DEV

export const logger = {
  debug(...args) {
    if (isDev) console.debug(...args)
  },
  info(...args) {
    if (isDev) console.info(...args)
  },
  warn(...args) {
    if (isDev) {
      console.warn(...args)
    } else {
      // 生产环境保留 warn 以便错误监控接管
      console.error('[warn]', ...args)
    }
  },
  error(...args) {
    console.error(...args)
  },
}

export default logger
