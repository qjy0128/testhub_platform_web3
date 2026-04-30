from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    display_name: str
    description: str
    category: str
    frontend_path: str = ''
    project_model_path: str = ''
    scheduled_task_model_path: str = ''
    tag_type: str = 'info'
    status: str = 'available'
    star_module: bool = False

    @property
    def supports_project_binding(self):
        return bool(self.project_model_path)

    @property
    def supports_scheduled_jobs(self):
        return bool(self.scheduled_task_model_path)

    def as_dict(self):
        return {
            'key': self.key,
            'display_name': self.display_name,
            'description': self.description,
            'category': self.category,
            'frontend_path': self.frontend_path,
            'tag_type': self.tag_type,
            'status': self.status,
            'star_module': self.star_module,
            'supports_project_binding': self.supports_project_binding,
            'supports_scheduled_jobs': self.supports_scheduled_jobs,
        }


API_TESTING = 'api_testing'
UI_AUTOMATION = 'ui_automation'
APP_AUTOMATION = 'app_automation'
AI_TESTING = 'ai_testing'
KNOWLEDGE_BASE = 'knowledge_base'
OCR_SERVICE = 'ocr_service'
SCHEDULER = 'scheduler'
TESTCASES = 'testcases'
TESTSUITES = 'testsuites'
REVIEWS = 'reviews'
UNIFIED_PROJECTS = 'unified_projects'


MODULE_DEFINITIONS = (
    ModuleDefinition(
        key=API_TESTING,
        display_name='API Testing',
        description='API projects, collections, environments, and scheduled tasks',
        category='testing',
        frontend_path='/api-testing',
        project_model_path='api_testing.ApiProject',
        scheduled_task_model_path='api_testing.ScheduledTask',
        tag_type='primary',
    ),
    ModuleDefinition(
        key=UI_AUTOMATION,
        display_name='UI Automation',
        description='Web UI automation projects, elements, scripts, suites, and execution',
        category='testing',
        frontend_path='/ui-automation',
        project_model_path='ui_automation.UiProject',
        scheduled_task_model_path='ui_automation.UiScheduledTask',
        tag_type='success',
    ),
    ModuleDefinition(
        key=APP_AUTOMATION,
        display_name='APP Automation',
        description='APP automation projects, devices, elements, cases, suites, and execution',
        category='testing',
        frontend_path='/app-automation',
        project_model_path='app_automation.AppProject',
        scheduled_task_model_path='app_automation.AppScheduledTask',
        tag_type='warning',
    ),
    ModuleDefinition(
        key=AI_TESTING,
        display_name='AI Testing',
        description='AI plans and runs browser tasks from natural language instructions',
        category='ai',
        frontend_path='/ai-generation/ai-testing',
        tag_type='danger',
        star_module=True,
    ),
    ModuleDefinition(
        key=KNOWLEDGE_BASE,
        display_name='Knowledge Base',
        description='Document vector storage, retrieval augmentation, and Q&A',
        category='ai',
        frontend_path='/ai-generation/knowledge-base',
        tag_type='info',
        star_module=True,
    ),
    ModuleDefinition(
        key=OCR_SERVICE,
        display_name='OCR Service',
        description='Unified OCR engine management and text extraction APIs',
        category='ai',
        frontend_path='/ai-generation/ocr-service',
        tag_type='info',
        star_module=True,
    ),
    ModuleDefinition(
        key=SCHEDULER,
        display_name='Scheduler',
        description='Unified schedules, dependencies, retries, and execution logs',
        category='platform',
        frontend_path='/ai-generation/scheduled-jobs',
        tag_type='info',
        star_module=True,
    ),
    ModuleDefinition(
        key=TESTCASES,
        display_name='Test Cases',
        description='Unified test case assets, versions, and AI-generated case adoption',
        category='asset',
        frontend_path='/ai-generation/testcases',
        tag_type='primary',
        star_module=True,
    ),
    ModuleDefinition(
        key=TESTSUITES,
        display_name='Test Suites',
        description='Unified test suites and cross-module scenario orchestration',
        category='asset',
        frontend_path='/ai-generation/testsuites',
        tag_type='success',
        star_module=True,
    ),
    ModuleDefinition(
        key=REVIEWS,
        display_name='Reviews',
        description='Test case review workflows and AI-assisted pre-review',
        category='asset',
        frontend_path='/ai-generation/reviews',
        tag_type='warning',
        star_module=True,
    ),
    ModuleDefinition(
        key=UNIFIED_PROJECTS,
        display_name='Unified Projects',
        description='Unified cross-module project view and permission hub',
        category='platform',
        frontend_path='/ai-generation/projects',
        tag_type='info',
        star_module=True,
    ),
)

REGISTERED_MODULES = {definition.key: definition for definition in MODULE_DEFINITIONS}


def get_module_definition(module):
    return REGISTERED_MODULES.get(module)


def iter_module_definitions(
    *,
    bindable_only=False,
    scheduled_only=False,
    star_only=False,
    available_only=False,
):
    definitions = MODULE_DEFINITIONS
    if bindable_only:
        definitions = [definition for definition in definitions if definition.supports_project_binding]
    if scheduled_only:
        definitions = [definition for definition in definitions if definition.supports_scheduled_jobs]
    if star_only:
        definitions = [definition for definition in definitions if definition.star_module]
    if available_only:
        definitions = [definition for definition in definitions if definition.status == 'available']
    return definitions


def get_module_choices(*, bindable_only=False, scheduled_only=False):
    return [
        (definition.key, definition.display_name)
        for definition in iter_module_definitions(
            bindable_only=bindable_only,
            scheduled_only=scheduled_only,
        )
    ]


def get_bindable_module_keys():
    return [definition.key for definition in iter_module_definitions(bindable_only=True)]


def get_scheduled_module_keys():
    return [definition.key for definition in iter_module_definitions(scheduled_only=True)]


def get_module_project_model_path(module):
    definition = get_module_definition(module)
    return definition.project_model_path if definition else ''


def get_scheduled_task_model_path(module):
    definition = get_module_definition(module)
    return definition.scheduled_task_model_path if definition else ''


def build_module_count_summary(*, bindable_only=False, scheduled_only=False):
    return {
        definition.key: 0
        for definition in iter_module_definitions(
            bindable_only=bindable_only,
            scheduled_only=scheduled_only,
        )
    }
