import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import logger from '@/utils/logger'

// Keep only shell/auth views in the entry chunk; feature pages are lazy-loaded.
import Login from '@/views/auth/Login.vue'
import Register from '@/views/auth/Register.vue'
import Layout from '@/layout/index.vue'
import Home from '@/views/Home.vue'

const ProjectList = () => import('@/views/projects/ProjectList.vue')
const DataFactory = () => import('@/views/data-factory/DataFactory.vue')
const ApiDashboard = () => import('@/views/api-testing/Dashboard.vue')
const ApiProjectManagement = () => import('@/views/api-testing/ProjectManagement.vue')
const ApiInterfaceManagement = () => import('@/views/api-testing/InterfaceManagement.vue')
const ApiAutomationTesting = () => import('@/views/api-testing/AutomationTesting.vue')
const ApiRequestHistory = () => import('@/views/api-testing/RequestHistory.vue')
const ApiEnvironmentManagement = () => import('@/views/api-testing/EnvironmentManagement.vue')
const ApiReportView = () => import('@/views/api-testing/ReportView.vue')
const ApiScheduledTasks = () => import('@/views/api-testing/ScheduledTasks.vue')
const ApiAIServiceConfig = () => import('@/views/api-testing/AIServiceConfig.vue')
const NotificationLogs = () => import('@/views/notification/NotificationLogs.vue')
const UiDashboard = () => import('@/views/ui-automation/dashboard/Dashboard.vue')
const UiProjectList = () => import('@/views/ui-automation/projects/ProjectList.vue')
const UiElementManagerEnhanced = () => import('@/views/ui-automation/elements/ElementManagerEnhanced.vue')
const UiTestCaseManager = () => import('@/views/ui-automation/test-cases/TestCaseManager.vue')
const UiScriptEditorEnhanced = () => import('@/views/ui-automation/scripts/ScriptEditorEnhanced.vue')
const UiScriptList = () => import('@/views/ui-automation/scripts/ScriptList.vue')
const UiSuiteList = () => import('@/views/ui-automation/suites/SuiteList.vue')
const UiExecutionList = () => import('@/views/ui-automation/executions/ExecutionList.vue')
const UiReportList = () => import('@/views/ui-automation/reports/ReportList.vue')
const UiScheduledTasks = () => import('@/views/ui-automation/scheduled-tasks/ScheduledTasks.vue')
const UiNotificationLogs = () => import('@/views/ui-automation/notification/NotificationLogs.vue')
const UiAITesting = () => import('@/views/ui-automation/ai/AITesting.vue')
const UiAICaseList = () => import('@/views/ui-automation/ai/AICaseList.vue')
const UiAIExecutionRecords = () => import('@/views/ui-automation/ai/AIExecutionRecords.vue')
const AiTesting = () => import('@/views/ai-testing/AiTestingView.vue')

/** @type {import('vue-router').RouteRecordRaw[]} */
const routes = [
  {
    path: '/',
    redirect: '/home'
  },
  {
    path: '/home',
    name: 'Home',
    component: Home,
    meta: { requiresAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { requiresGuest: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: Register,
    meta: { requiresGuest: true }
  },
  {
    path: '/ai-generation/assistant',
    name: 'Assistant',
    component: () => import('@/views/assistant/AssistantView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/ai-generation',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'modules'
      },
      {
        path: 'modules',
        name: 'ModuleMap',
        component: () => import('@/views/modules/ModuleMap.vue')
      },
      {
        path: 'assets',
        name: 'UnifiedAssets',
        component: () => import('@/views/modules/StarAssetDashboard.vue')
      },
      {
        path: 'audit-center',
        name: 'AuditCenter',
        component: () => import('@/views/modules/AuditCenterView.vue')
      },
      {
        path: 'requirement-analysis',
        name: 'RequirementAnalysis',
        component: () => import('@/views/requirement-analysis/RequirementAnalysisView.vue')
      },
      {
        path: 'projects',
        name: 'Projects',
        component: ProjectList
      },
      {
        path: 'scheduled-jobs',
        name: 'UnifiedScheduledJobs',
        component: () => import('@/views/projects/UnifiedScheduledJobs.vue')
      },
      {
        path: 'ai-testing',
        name: 'AiTesting',
        component: AiTesting
      },
      {
        path: 'knowledge-base',
        name: 'KnowledgeBase',
        component: () => import('@/views/knowledge-base/KnowledgeBaseView.vue')
      },
      {
        path: 'ocr-service',
        name: 'OcrService',
        component: () => import('@/views/ocr-service/OcrServiceView.vue')
      },
      {
        path: 'projects/:id',
        name: 'ProjectDetail',
        component: () => import('@/views/projects/ProjectDetail.vue')
      },
      {
        path: 'testcases',
        name: 'TestCases',
        component: () => import('@/views/testcases/TestCaseList.vue')
      },
      {
        path: 'testcases/create',
        name: 'CreateTestCase',
        component: () => import('@/views/testcases/TestCaseForm.vue')
      },
      {
        path: 'testcases/:id',
        name: 'TestCaseDetail',
        component: () => import('@/views/testcases/TestCaseDetail.vue')
      },
      {
        path: 'testcases/:id/edit',
        name: 'EditTestCase',
        component: () => import('@/views/testcases/TestCaseEdit.vue')
      },
      {
        path: 'versions',
        name: 'Versions',
        component: () => import('@/views/versions/VersionList.vue')
      },
      {
        path: 'reviews',
        name: 'Reviews',
        component: () => import('@/views/reviews/ReviewList.vue')
      },
      {
        path: 'reviews/create',
        name: 'CreateReview',
        component: () => import('@/views/reviews/ReviewForm.vue')
      },
      {
        path: 'reviews/:id',
        name: 'ReviewDetail',
        component: () => import('@/views/reviews/ReviewDetail.vue')
      },
      {
        path: 'reviews/:id/edit',
        name: 'EditReview',
        component: () => import('@/views/reviews/ReviewForm.vue')
      },
      {
        path: 'review-templates',
        name: 'ReviewTemplates',
        component: () => import('@/views/reviews/ReviewTemplateList.vue')
      },
      {
        path: 'testsuites',
        name: 'TestSuites',
        component: () => import('@/views/testsuites/TestSuiteList.vue')
      },
      {
        path: 'executions',
        name: 'Executions',
        component: () => import('@/views/executions/ExecutionListView.vue')
      },
      {
        path: 'executions/:id',
        name: 'ExecutionDetail',
        component: () => import('@/views/executions/ExecutionDetailView.vue')
      },
      {
        path: 'reports',
        name: 'AiTestReport',
        component: () => import('@/views/reports/AiTestReport.vue')
      },
      {
        path: 'generated-testcases',
        name: 'GeneratedTestCases',
        component: () => import('@/views/requirement-analysis/GeneratedTestCaseList.vue')
      },
      {
        path: 'task-detail/:taskId',
        name: 'TaskDetail',
        component: () => import('@/views/requirement-analysis/TaskDetail.vue')
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/profile/UserProfile.vue')
      }
    ]
  },
  {
    path: '/api-testing',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'dashboard'
      },
      {
        path: 'dashboard',
        name: 'ApiDashboard',
        component: ApiDashboard
      },
      {
        path: 'projects',
        name: 'ApiProjects',
        component: ApiProjectManagement
      },
      {
        path: 'interfaces',
        name: 'ApiInterfaces',
        component: ApiInterfaceManagement
      },
      {
        path: 'automation',
        name: 'ApiAutomation',
        component: ApiAutomationTesting
      },
      {
        path: 'history',
        name: 'ApiHistory',
        component: ApiRequestHistory
      },
      {
        path: 'environments',
        name: 'ApiEnvironments',
        component: ApiEnvironmentManagement
      },
      {
        path: 'reports',
        name: 'ApiReports',
        component: ApiReportView
      },
      {
        path: 'scheduled-tasks',
        name: 'ApiScheduledTasks',
        component: ApiScheduledTasks
      },
      {
        path: 'ai-service-config',
        name: 'ApiAIServiceConfig',
        component: ApiAIServiceConfig
      },
      {
        path: 'notification-logs',
        name: 'ApiNotificationLogs',
        component: NotificationLogs
      }
    ]
  },
  {
    path: '/ui-automation',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'dashboard'
      },
      {
        path: 'dashboard',
        name: 'UiDashboard',
        component: UiDashboard
      },
      {
        path: 'projects',
        name: 'UiProjects',
        component: UiProjectList
      },
      {
        path: 'elements-enhanced',
        name: 'UiElementsEnhanced',
        component: UiElementManagerEnhanced
      },
      {
        path: 'test-cases',
        name: 'UiTestCases',
        component: UiTestCaseManager
      },
      {
        path: 'scripts-enhanced',
        name: 'UiScriptsEnhanced',
        component: UiScriptEditorEnhanced
      },
      {
        path: 'scripts/editor',
        name: 'UiScriptEditor',
        component: UiScriptEditorEnhanced
      },
      {
        path: 'scripts',
        name: 'UiScripts',
        component: UiScriptList
      },
      {
        path: 'suites',
        name: 'UiSuites',
        component: UiSuiteList
      },
      {
        path: 'executions',
        name: 'UiExecutions',
        component: UiExecutionList
      },
      {
        path: 'reports',
        name: 'UiReports',
        component: UiReportList
      },
      {
        path: 'scheduled-tasks',
        name: 'UiScheduledTasks',
        component: UiScheduledTasks
      },
      {
        path: 'notification-logs',
        name: 'UiNotificationLogs',
        component: UiNotificationLogs
      }
    ]
  },
  {
    path: '/ai-intelligent-mode',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'testing'
      },
      {
        path: 'testing',
        name: 'AITesting',
        component: UiAITesting
      },
      {
        path: 'cases',
        name: 'AICaseList',
        component: UiAICaseList
      },
      {
        path: 'execution-records',
        name: 'AIExecutionRecords',
        component: UiAIExecutionRecords
      }
    ]
  },
  {
    path: '/data-factory',
    name: 'DataFactory',
    component: DataFactory,
    meta: { requiresAuth: true }
  },
  {
    path: '/configuration',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        component: () => import('@/views/configuration/ConfigurationCenter.vue'),
        children: [
          {
            path: '',
            redirect: 'ai-model'
          },
          {
            path: 'ai-model',
            name: 'ConfigAIModel',
            component: () => import('@/views/requirement-analysis/AIModelConfig.vue')
          },
          {
            path: 'prompt-config',
            name: 'ConfigPromptConfig',
            component: () => import('@/views/requirement-analysis/PromptConfig.vue')
          },
          {
            path: 'generation-config',
            name: 'ConfigGenerationConfig',
            component: () => import('@/views/requirement-analysis/GenerationConfigView.vue')
          },
          {
            path: 'ui-env',
            name: 'ConfigUIEnv',
            component: () => import('@/views/configuration/UIEnvironmentConfig.vue')
          },
          {
            path: 'app-env',
            name: 'ConfigAppEnv',
            component: () => import('@/views/app-automation/settings/AppSettings.vue')
          },
          {
            path: 'ai-mode',
            name: 'ConfigAIMode',
            component: () => import('@/views/configuration/AIIntelligentModeConfig.vue')
          },
          {
            path: 'scheduled-task',
            name: 'ConfigScheduledTask',
            component: () => import('@/views/ui-automation/notification/NotificationConfigs.vue')
          },
          {
            path: 'dify',
            name: 'DifyConfig',
            component: () => import('@/views/configuration/DifyConfig.vue')
          }
        ]
      }
    ]
  },
  // APP自动化测试路由
  {
    path: '/app-automation',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'dashboard'
      },
      {
        path: 'dashboard',
        name: 'AppAutomationDashboard',
        component: () => import('@/views/app-automation/dashboard/Dashboard.vue')
      },
      {
        path: 'projects',
        name: 'AppProjectList',
        component: () => import('@/views/app-automation/projects/ProjectList.vue')
      },
      {
        path: 'devices',
        name: 'AppDeviceList',
        component: () => import('@/views/app-automation/devices/DeviceList.vue')
      },
      {
        path: 'packages',
        name: 'AppPackageList',
        component: () => import('@/views/app-automation/packages/PackageList.vue')
      },
      {
        path: 'elements',
        name: 'AppElementList',
        component: () => import('@/views/app-automation/elements/ElementList.vue')
      },
      {
        path: 'scene-builder',
        name: 'AppSceneBuilder',
        component: () => import('@/views/app-automation/test-cases/SceneBuilder.vue'),
        meta: { title: '用例编排' }
      },
      {
        path: 'test-cases',
        name: 'AppTestCaseList',
        component: () => import('@/views/app-automation/test-cases/TestCaseList.vue')
      },
      {
        path: 'test-suites',
        name: 'AppTestSuiteList',
        component: () => import('@/views/app-automation/suites/SuiteList.vue')
      },
      {
        path: 'scheduled-tasks',
        name: 'AppScheduledTasks',
        component: () => import('@/views/app-automation/scheduled-tasks/ScheduledTasks.vue')
      },
      {
        path: 'notification-logs',
        name: 'AppNotificationLogs',
        component: () => import('@/views/app-automation/notification/NotificationLogs.vue')
      },
      {
        path: 'executions',
        name: 'AppExecutionList',
        component: () => import('@/views/app-automation/executions/ExecutionList.vue')
      },
      {
        path: 'reports',
        name: 'AppReportList',
        component: () => import('@/views/app-automation/reports/ReportList.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore()

  logger.debug('route guard:', {
    to: to.path,
    from: from.path,
    hasToken: !!userStore.accessToken,
    hasUser: !!userStore.user,
    isAuthenticated: userStore.isAuthenticated,
  })

  if (!userStore.user && userStore.accessToken) {
    try {
      await userStore.initAuth()
    } catch (error) {
      logger.warn('auth init failed', error)
    }
  }

  if (to.meta.requiresAuth && !userStore.isAuthenticated) {
    next('/login')
  } else if (to.meta.requiresGuest && userStore.isAuthenticated) {
    next('/home')
  } else {
    next()
  }
})

router.afterEach((to, from) => {
  logger.debug(`navigated ${from.path} -> ${to.path}`)
})

export default router
