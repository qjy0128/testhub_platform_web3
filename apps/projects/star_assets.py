import hashlib
import json
from difflib import unified_diff

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count
from django.shortcuts import get_object_or_404

from apps.projects.models import ProjectModuleBinding, UnifiedTestAsset, UnifiedTestAssetSnapshot
from apps.projects.unified import accessible_projects_for_user, user_can_access_project
from apps.reviews.models import TestCaseReview
from apps.testcases.models import TestCase
from apps.testsuites.models import TestSuite


def _limit(value, default=50, maximum=200):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def _payload_hash(payload):
    encoded = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _json_text(payload):
    return json.dumps(payload or {}, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2, sort_keys=True)


def _native_url(asset):
    if asset.module == UnifiedTestAsset.MODULE_MANUAL:
        if asset.asset_type == UnifiedTestAsset.ASSET_TESTCASE:
            return f'/ai-generation/testcases/{asset.object_id}'
        if asset.asset_type == UnifiedTestAsset.ASSET_TESTSUITE:
            return '/ai-generation/testsuites'
        if asset.asset_type == UnifiedTestAsset.ASSET_REVIEW:
            return f'/ai-generation/reviews/{asset.object_id}'
    if asset.module == UnifiedTestAsset.MODULE_AI_TESTING:
        return '/ai-generation/ai-testing'
    if asset.module == UnifiedTestAsset.MODULE_API_TESTING:
        return '/api-testing/automation'
    if asset.module == UnifiedTestAsset.MODULE_UI_AUTOMATION:
        if asset.asset_type == UnifiedTestAsset.ASSET_TESTSUITE:
            return '/ui-automation/suites'
        return '/ui-automation/test-cases'
    if asset.module == UnifiedTestAsset.MODULE_APP_AUTOMATION:
        if asset.asset_type == UnifiedTestAsset.ASSET_TESTSUITE:
            return '/app-automation/test-suites'
        return '/app-automation/test-cases'
    return ''


def _manual_test_type_for_module(module):
    if module == UnifiedTestAsset.MODULE_API_TESTING:
        return 'api'
    if module in {UnifiedTestAsset.MODULE_UI_AUTOMATION, UnifiedTestAsset.MODULE_APP_AUTOMATION, UnifiedTestAsset.MODULE_AI_TESTING}:
        return 'ui'
    return 'functional'


def _stringify_steps(payload):
    steps = payload.get('steps')
    if isinstance(steps, str):
        return steps
    if isinstance(steps, list):
        lines = []
        for index, step in enumerate(steps, start=1):
            if isinstance(step, dict):
                number = step.get('step_number') or step.get('index') or index
                action = step.get('description') or step.get('action') or step.get('action_type') or step.get('title') or ''
                expected = step.get('expected') or step.get('assert_value') or ''
                line = f'{number}. {action}'.strip()
                if expected:
                    line = f'{line} => {expected}'
                lines.append(line)
            else:
                lines.append(f'{index}. {step}')
        return '\n'.join(lines)
    if payload.get('ui_flow'):
        return _json_text(payload.get('ui_flow'))
    if payload.get('instruction'):
        return payload.get('instruction')
    return ''


def _extract_expected_result(asset, payload):
    if payload.get('expected_result'):
        return payload.get('expected_result')
    if payload.get('assertions'):
        return _json_text(payload.get('assertions'))
    if asset.module == UnifiedTestAsset.MODULE_AI_TESTING:
        return 'AI browser task completes successfully and satisfies the requested instruction.'
    if asset.module == UnifiedTestAsset.MODULE_APP_AUTOMATION:
        return 'APP automation flow completes successfully.'
    if asset.module == UnifiedTestAsset.MODULE_UI_AUTOMATION:
        return 'UI automation flow completes successfully.'
    if asset.module == UnifiedTestAsset.MODULE_API_TESTING:
        return 'API test suite executes successfully.'
    return 'Expected result should be confirmed after adoption.'


def _upsert_asset(*, project, module, asset_type, object_id, title, status='', priority='', source_updated_at=None, version_label='', metadata=None, payload=None, created_by=None):
    metadata = metadata or {}
    payload = payload or metadata
    asset, _ = UnifiedTestAsset.objects.update_or_create(
        module=module,
        asset_type=asset_type,
        object_id=object_id,
        defaults={
            'project': project,
            'title': title,
            'status': status or '',
            'priority': priority or '',
            'source_updated_at': source_updated_at,
            'version_label': version_label or '',
            'metadata': metadata,
        },
    )
    snapshot_hash = _payload_hash(payload)
    UnifiedTestAssetSnapshot.objects.get_or_create(
        asset=asset,
        snapshot_hash=snapshot_hash,
        defaults={
            'payload': payload,
            'created_by': created_by,
        },
    )
    return asset


def _sync_manual_assets(projects):
    testcases = TestCase.objects.filter(project__in=projects).select_related(
        'project',
        'author',
        'assignee',
    ).prefetch_related('versions')
    for testcase in testcases:
        version_names = [version.name for version in testcase.versions.all()]
        payload = {
            'title': testcase.title,
            'description': testcase.description,
            'preconditions': testcase.preconditions,
            'steps': testcase.steps,
            'expected_result': testcase.expected_result,
            'priority': testcase.priority,
            'status': testcase.status,
            'test_type': testcase.test_type,
            'tags': testcase.tags,
            'versions': version_names,
        }
        _upsert_asset(
            project=testcase.project,
            module=UnifiedTestAsset.MODULE_MANUAL,
            asset_type=UnifiedTestAsset.ASSET_TESTCASE,
            object_id=testcase.id,
            title=testcase.title,
            status=testcase.status,
            priority=testcase.priority,
            source_updated_at=testcase.updated_at,
            version_label=', '.join(version_names[:3]),
            metadata={
                'test_type': testcase.test_type,
                'tags': testcase.tags,
                'owner': testcase.author.username if testcase.author_id else '',
                'author_id': testcase.author_id,
                'assignee_id': testcase.assignee_id,
                'version_count': len(version_names),
            },
            payload=payload,
            created_by=testcase.author,
        )

    suites = TestSuite.objects.filter(project__in=projects).select_related('project', 'author').annotate(
        case_count=Count('testcases', distinct=True),
    )
    for suite in suites:
        _upsert_asset(
            project=suite.project,
            module=UnifiedTestAsset.MODULE_MANUAL,
            asset_type=UnifiedTestAsset.ASSET_TESTSUITE,
            object_id=suite.id,
            title=suite.name,
            status='active',
            source_updated_at=suite.updated_at,
            metadata={
                'case_count': suite.case_count,
                'owner': suite.author.username if suite.author_id else '',
                'author_id': suite.author_id,
            },
            payload={
                'name': suite.name,
                'description': suite.description,
                'case_count': suite.case_count,
            },
            created_by=suite.author,
        )

    reviews = TestCaseReview.objects.filter(projects__in=projects).select_related('creator').prefetch_related('projects').distinct()
    for review in reviews:
        project = next((item for item in review.projects.all() if item in projects), None)
        if project is None:
            continue
        project_ids = [item.id for item in review.projects.all()]
        _upsert_asset(
            project=project,
            module=UnifiedTestAsset.MODULE_MANUAL,
            asset_type=UnifiedTestAsset.ASSET_REVIEW,
            object_id=review.id,
            title=review.title,
            status=review.status,
            priority=review.priority,
            source_updated_at=review.updated_at,
            metadata={
                'project_ids': project_ids,
                'owner': review.creator.username if review.creator_id else '',
                'creator_id': review.creator_id,
                'deadline': review.deadline,
            },
            payload={
                'title': review.title,
                'description': review.description,
                'status': review.status,
                'priority': review.priority,
                'project_ids': project_ids,
            },
            created_by=review.creator,
        )


def _sync_bound_module_assets(projects):
    bindings = ProjectModuleBinding.objects.filter(project__in=projects)
    binding_map = {(binding.module, binding.object_id): binding.project for binding in bindings}

    try:
        from apps.ai_testing.models import AiTestingTask
    except Exception:
        AiTestingTask = None
    if AiTestingTask is not None:
        for task in AiTestingTask.objects.filter(project__in=projects).select_related('project', 'created_by').annotate(
            run_count=Count('runs', distinct=True),
        ):
            _upsert_asset(
                project=task.project,
                module=UnifiedTestAsset.MODULE_AI_TESTING,
                asset_type=UnifiedTestAsset.ASSET_TESTCASE,
                object_id=task.id,
                title=task.name,
                status=task.status,
                source_updated_at=task.updated_at,
                metadata={
                    'execution_mode': task.execution_mode,
                    'target_url': task.target_url,
                    'run_count': task.run_count,
                    'owner': task.created_by.username if task.created_by_id else '',
                },
                payload={
                    'name': task.name,
                    'description': task.description,
                    'instruction': task.instruction,
                    'target_url': task.target_url,
                    'execution_mode': task.execution_mode,
                },
                created_by=task.created_by,
            )

    try:
        from apps.api_testing.models import TestSuite as ApiTestSuite
    except Exception:
        ApiTestSuite = None
    if ApiTestSuite is not None:
        for suite in ApiTestSuite.objects.filter(project_id__in=[
            object_id for (module, object_id), _project in binding_map.items()
            if module == ProjectModuleBinding.MODULE_API_TESTING
        ]).select_related('project', 'created_by'):
            project = binding_map.get((ProjectModuleBinding.MODULE_API_TESTING, suite.project_id))
            if project:
                _upsert_asset(
                    project=project,
                    module=UnifiedTestAsset.MODULE_API_TESTING,
                    asset_type=UnifiedTestAsset.ASSET_TESTSUITE,
                    object_id=suite.id,
                    title=suite.name,
                    status='active',
                    source_updated_at=suite.updated_at,
                    metadata={
                        'source_project_id': suite.project_id,
                        'owner': suite.created_by.username if suite.created_by_id else '',
                    },
                    payload={'name': suite.name, 'description': suite.description},
                    created_by=suite.created_by,
                )

    try:
        from apps.app_automation.models import AppTestCase, AppTestSuite
    except Exception:
        AppTestCase = None
        AppTestSuite = None
    app_project_ids = [
        object_id for (module, object_id), _project in binding_map.items()
        if module == ProjectModuleBinding.MODULE_APP_AUTOMATION
    ]
    if AppTestCase is not None:
        for testcase in AppTestCase.objects.filter(project_id__in=app_project_ids).select_related('project', 'created_by'):
            project = binding_map.get((ProjectModuleBinding.MODULE_APP_AUTOMATION, testcase.project_id))
            if project:
                _upsert_asset(
                    project=project,
                    module=UnifiedTestAsset.MODULE_APP_AUTOMATION,
                    asset_type=UnifiedTestAsset.ASSET_TESTCASE,
                    object_id=testcase.id,
                    title=testcase.name,
                    status='active',
                    priority='',
                    source_updated_at=testcase.updated_at,
                    metadata={
                        'source_project_id': testcase.project_id,
                        'timeout': testcase.timeout,
                        'owner': testcase.created_by.username if testcase.created_by_id else '',
                    },
                    payload={'name': testcase.name, 'description': testcase.description, 'ui_flow': testcase.ui_flow},
                    created_by=testcase.created_by,
                )
    if AppTestSuite is not None:
        for suite in AppTestSuite.objects.filter(project_id__in=app_project_ids).select_related('project', 'created_by').annotate(
            case_count=Count('test_cases', distinct=True),
        ):
            project = binding_map.get((ProjectModuleBinding.MODULE_APP_AUTOMATION, suite.project_id))
            if project:
                _upsert_asset(
                    project=project,
                    module=UnifiedTestAsset.MODULE_APP_AUTOMATION,
                    asset_type=UnifiedTestAsset.ASSET_TESTSUITE,
                    object_id=suite.id,
                    title=suite.name,
                    status=suite.execution_status,
                    source_updated_at=suite.updated_at,
                    metadata={
                        'source_project_id': suite.project_id,
                        'case_count': suite.case_count,
                        'owner': suite.created_by.username if suite.created_by_id else '',
                    },
                    payload={'name': suite.name, 'description': suite.description, 'case_count': suite.case_count},
                    created_by=suite.created_by,
                )

    try:
        from apps.ui_automation.models import TestCase as UiTestCase, TestSuite as UiTestSuite
    except Exception:
        UiTestCase = None
        UiTestSuite = None
    ui_project_ids = [
        object_id for (module, object_id), _project in binding_map.items()
        if module == ProjectModuleBinding.MODULE_UI_AUTOMATION
    ]
    if UiTestCase is not None:
        for testcase in UiTestCase.objects.filter(project_id__in=ui_project_ids).select_related(
            'project',
            'created_by',
        ).prefetch_related('steps'):
            project = binding_map.get((ProjectModuleBinding.MODULE_UI_AUTOMATION, testcase.project_id))
            if not project:
                continue
            steps = [
                {
                    'step_number': step.step_number,
                    'action_type': step.action_type,
                    'element_id': step.element_id,
                    'input_value': step.input_value,
                    'assert_type': step.assert_type,
                    'assert_value': step.assert_value,
                    'description': step.description,
                }
                for step in testcase.steps.all()
            ]
            _upsert_asset(
                project=project,
                module=UnifiedTestAsset.MODULE_UI_AUTOMATION,
                asset_type=UnifiedTestAsset.ASSET_TESTCASE,
                object_id=testcase.id,
                title=testcase.name,
                status=testcase.status,
                priority=testcase.priority,
                source_updated_at=testcase.updated_at,
                metadata={
                    'source_project_id': testcase.project_id,
                    'step_count': len(steps),
                    'owner': testcase.created_by.username,
                    'created_by_id': testcase.created_by_id,
                },
                payload={
                    'name': testcase.name,
                    'description': testcase.description,
                    'status': testcase.status,
                    'priority': testcase.priority,
                    'steps': steps,
                },
                created_by=testcase.created_by,
            )
    if UiTestSuite is not None:
        for suite in UiTestSuite.objects.filter(project_id__in=ui_project_ids).select_related('project').annotate(
            case_count=Count('test_cases', distinct=True),
            script_count=Count('scripts', distinct=True),
        ):
            project = binding_map.get((ProjectModuleBinding.MODULE_UI_AUTOMATION, suite.project_id))
            if project:
                _upsert_asset(
                    project=project,
                    module=UnifiedTestAsset.MODULE_UI_AUTOMATION,
                    asset_type=UnifiedTestAsset.ASSET_TESTSUITE,
                    object_id=suite.id,
                    title=suite.name,
                    status=suite.execution_status,
                    source_updated_at=suite.updated_at,
                    metadata={
                        'source_project_id': suite.project_id,
                        'case_count': suite.case_count,
                        'script_count': suite.script_count,
                        'passed_count': suite.passed_count,
                        'failed_count': suite.failed_count,
                    },
                    payload={
                        'name': suite.name,
                        'description': suite.description,
                        'execution_status': suite.execution_status,
                        'case_count': suite.case_count,
                        'script_count': suite.script_count,
                        'passed_count': suite.passed_count,
                        'failed_count': suite.failed_count,
                    },
                )


def sync_unified_assets_for_user(user):
    projects = list(accessible_projects_for_user(user))
    _sync_manual_assets(projects)
    _sync_bound_module_assets(projects)
    return UnifiedTestAsset.objects.filter(project__in=projects)


def summarize_star_assets(user):
    assets = sync_unified_assets_for_user(user)
    projects = accessible_projects_for_user(user)
    testcases = assets.filter(asset_type=UnifiedTestAsset.ASSET_TESTCASE)
    testsuites = assets.filter(asset_type=UnifiedTestAsset.ASSET_TESTSUITE)
    reviews = assets.filter(asset_type=UnifiedTestAsset.ASSET_REVIEW)
    return {
        'projects': projects.count(),
        'assets': assets.count(),
        'testcases': {
            'total': testcases.count(),
            'draft': testcases.filter(status='draft').count(),
            'active': testcases.filter(status='active').count(),
            'deprecated': testcases.filter(status='deprecated').count(),
            'critical': testcases.filter(priority='critical').count(),
        },
        'testsuites': {
            'total': testsuites.count(),
            'with_cases': sum(
                1 for asset in testsuites
                if int((asset.metadata or {}).get('case_count') or 0) > 0
            ),
        },
        'reviews': {
            'total': reviews.count(),
            'pending': reviews.filter(status='pending').count(),
            'in_progress': reviews.filter(status='in_progress').count(),
            'approved': reviews.filter(status='approved').count(),
            'rejected': reviews.filter(status='rejected').count(),
        },
        'by_module': {
            item['module']: item['count']
            for item in assets.values('module').annotate(count=Count('id'))
        },
    }


def list_star_asset_rows(user, module, limit=None, filters=None):
    filters = filters or {}
    limit = _limit(limit)
    assets = sync_unified_assets_for_user(user).select_related('project')
    if module == 'testcases':
        assets = assets.filter(asset_type=UnifiedTestAsset.ASSET_TESTCASE)
    elif module == 'testsuites':
        assets = assets.filter(asset_type=UnifiedTestAsset.ASSET_TESTSUITE)
    elif module == 'reviews':
        assets = assets.filter(asset_type=UnifiedTestAsset.ASSET_REVIEW)
    elif module != 'all':
        return []

    source_module = filters.get('source_module') or filters.get('asset_module')
    if source_module:
        assets = assets.filter(module=source_module)
    status = filters.get('status')
    if status:
        assets = assets.filter(status=status)
    priority = filters.get('priority')
    if priority:
        assets = assets.filter(priority=priority)
    project_id = filters.get('project')
    if project_id:
        assets = assets.filter(project_id=project_id)
    search = (filters.get('search') or '').strip()
    if search:
        assets = assets.filter(title__icontains=search)

    rows = assets.order_by('-source_updated_at', '-updated_at')[:limit]
    return [
        {
            'id': item.object_id,
            'asset_id': item.id,
            'asset_key': item.asset_key,
            'module': item.module,
            'asset_type': item.asset_type,
            'title': item.title,
            'project_id': item.project_id,
            'project_name': item.project.name,
            'status': item.status,
            'priority': item.priority,
            'type': item.metadata.get('test_type') or item.asset_type,
            'owner': item.metadata.get('owner', ''),
            'version_count': item.metadata.get('version_count', 0),
            'case_count': item.metadata.get('case_count', 0),
            'step_count': item.metadata.get('step_count', 0),
            'script_count': item.metadata.get('script_count', 0),
            'run_count': item.metadata.get('run_count', 0),
            'reviewer_count': item.metadata.get('reviewer_count', 0),
            'native_url': _native_url(item),
            'updated_at': item.source_updated_at or item.updated_at,
        }
        for item in rows
    ]


def get_star_asset_detail(user, asset_id):
    assets = sync_unified_assets_for_user(user).select_related('project')
    asset = get_object_or_404(assets, pk=asset_id)
    snapshots = list(asset.snapshots.select_related('created_by').order_by('-created_at')[:10])
    latest = snapshots[0] if snapshots else None
    previous = snapshots[1] if len(snapshots) > 1 else None
    diff_lines = []
    if latest and previous:
        diff_lines = list(unified_diff(
            _json_text(previous.payload).splitlines(),
            _json_text(latest.payload).splitlines(),
            fromfile=f'previous:{previous.snapshot_hash[:12]}',
            tofile=f'latest:{latest.snapshot_hash[:12]}',
            lineterm='',
        ))

    return {
        'id': asset.object_id,
        'asset_id': asset.id,
        'asset_key': asset.asset_key,
        'module': asset.module,
        'asset_type': asset.asset_type,
        'title': asset.title,
        'project_id': asset.project_id,
        'project_name': asset.project.name,
        'status': asset.status,
        'priority': asset.priority,
        'version_label': asset.version_label,
        'metadata': asset.metadata,
        'native_url': _native_url(asset),
        'latest_payload': latest.payload if latest else {},
        'snapshot_diff': diff_lines,
        'snapshots': [
            {
                'id': snapshot.id,
                'snapshot_hash': snapshot.snapshot_hash,
                'created_at': snapshot.created_at,
                'created_by': snapshot.created_by.username if snapshot.created_by_id else '',
            }
            for snapshot in snapshots
        ],
        'created_at': asset.created_at,
        'updated_at': asset.source_updated_at or asset.updated_at,
    }


def adopt_star_asset_as_testcase(user, asset_id):
    asset = get_object_or_404(sync_unified_assets_for_user(user).select_related('project'), pk=asset_id)
    if asset.asset_type != UnifiedTestAsset.ASSET_TESTCASE:
        raise ValueError('Only testcase assets can be adopted as manual test cases.')
    if not user_can_access_project(user, asset.project):
        raise PermissionError('No permission to adopt this asset.')

    latest_snapshot = asset.snapshots.order_by('-created_at').first()
    payload = latest_snapshot.payload if latest_snapshot else {}
    tags = payload.get('tags') if isinstance(payload.get('tags'), list) else []
    tags = [
        *tags,
        'unified-asset',
        f'source:{asset.module}',
        f'asset:{asset.asset_key}',
    ]
    testcase = TestCase.objects.create(
        project=asset.project,
        title=asset.title,
        description=payload.get('description') or asset.metadata.get('description', ''),
        preconditions=payload.get('preconditions', ''),
        steps=_stringify_steps(payload)[:1000],
        expected_result=_extract_expected_result(asset, payload),
        priority=asset.priority if asset.priority in {'low', 'medium', 'high', 'critical'} else 'medium',
        status='draft',
        test_type=payload.get('test_type') or _manual_test_type_for_module(asset.module),
        tags=tags,
        author=user,
    )
    _upsert_asset(
        project=testcase.project,
        module=UnifiedTestAsset.MODULE_MANUAL,
        asset_type=UnifiedTestAsset.ASSET_TESTCASE,
        object_id=testcase.id,
        title=testcase.title,
        status=testcase.status,
        priority=testcase.priority,
        source_updated_at=testcase.updated_at,
        metadata={
            'test_type': testcase.test_type,
            'tags': testcase.tags,
            'owner': testcase.author.username,
            'author_id': testcase.author_id,
            'version_count': 0,
            'adopted_from': asset.asset_key,
        },
        payload={
            'title': testcase.title,
            'description': testcase.description,
            'preconditions': testcase.preconditions,
            'steps': testcase.steps,
            'expected_result': testcase.expected_result,
            'priority': testcase.priority,
            'status': testcase.status,
            'test_type': testcase.test_type,
            'tags': testcase.tags,
            'adopted_from': asset.asset_key,
        },
        created_by=user,
    )
    return testcase
