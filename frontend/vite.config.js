import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const normalizeModuleId = (id) => id.replace(/\\/g, '/')

export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  esbuild: {
    drop: mode === 'production' ? ['debugger'] : [],
    pure: mode === 'production' ? ['console.log', 'console.debug'] : [],
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern-compiler', // 使用现代 Sass API
        silenceDeprecations: ['legacy-js-api'], // 静默旧警告
      }
    }
  },
  optimizeDeps: {
    esbuildOptions: {
      target: 'es2022'
    },
    force: true,
  },
  build: {
    target: 'es2022',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }

          const moduleId = normalizeModuleId(id)

          if (moduleId.includes('/node_modules/@vue/') || moduleId.includes('/node_modules/vue/') || moduleId.includes('/node_modules/vue-router/') || moduleId.includes('/node_modules/pinia/')) {
            return 'vendor-vue'
          }
          if (moduleId.includes('/node_modules/element-plus/')) {
            return 'element-plus'
          }
          if (moduleId.includes('/node_modules/@element-plus/icons-vue/')) {
            return 'element-icons'
          }
          if (moduleId.includes('/node_modules/echarts/')) {
            return 'echarts'
          }
          if (moduleId.includes('/node_modules/zrender/')) {
            return 'zrender'
          }
          if (moduleId.includes('/node_modules/xlsx/')) {
            return 'xlsx'
          }
          if (moduleId.includes('/node_modules/monaco-editor/')) {
            return 'monaco-editor'
          }
          if (moduleId.includes('/node_modules/vuedraggable/')) {
            return 'vuedraggable'
          }
          if (moduleId.includes('/node_modules/axios/') || moduleId.includes('/node_modules/dayjs/') || moduleId.includes('/node_modules/lodash-es/')) {
            return 'vendor-utils'
          }

          return 'vendor'
        }
      }
    },
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    headers: {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0',
    },
    proxy: {
      '^/api/': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/media/': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/app-automation-templates/': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/app-automation-reports/': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/ws/': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', () => {})
          proxy.on('proxyReqWs', (proxyReq, req, socket) => {
            socket.on('error', () => {})
          })
        },
      },
    },
  },
  assetsInclude: ['**/*.wasm'],
}))
