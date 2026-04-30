from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone
from .models import TestPlan, TestRun, TestRunCase, TestRunCaseHistory
from apps.testcases.models import TestCase
from apps.projects.models import Project
from apps.projects.unified import accessible_projects_for_user, is_staff_user
from apps.versions.models import Version
from .serializers import (TestPlanSerializer, TestRunSerializer, TestRunCaseSerializer, 
                         TestPlanDetailSerializer, TestRunCaseDetailSerializer, 
                         TestRunCaseHistorySerializer)


def _request_id_list(request, field_name):
    if hasattr(request.data, 'getlist'):
        values = request.data.getlist(field_name)
    else:
        values = request.data.get(field_name, [])

    if values in (None, ''):
        return []
    if isinstance(values, (str, int)):
        values = [values]

    try:
        return [int(value) for value in values if value not in (None, '')]
    except (TypeError, ValueError):
        raise ValidationError({field_name: 'IDs must be integers.'})


def _accessible_project_ids(user):
    return set(accessible_projects_for_user(user).values_list('id', flat=True))


def _require_project_ids_access(user, project_ids):
    denied_ids = set(project_ids) - _accessible_project_ids(user)
    if denied_ids:
        raise PermissionDenied('You do not have access to one or more selected projects.')


def _get_accessible_version(user, version_id):
    if not version_id:
        return None
    try:
        version_pk = int(version_id)
    except (TypeError, ValueError):
        raise ValidationError({'version': 'Version ID must be an integer.'})

    version = (
        Version.objects
        .filter(id=version_pk, projects__in=accessible_projects_for_user(user))
        .distinct()
        .first()
    )
    if version is None:
        raise PermissionDenied('You do not have access to the selected version.')
    return version


def _require_test_run_access(user, test_run):
    if test_run and test_run.project_id not in _accessible_project_ids(user):
        raise PermissionDenied('You do not have access to the selected test run.')


def _require_testcase_access(user, testcase):
    if testcase and testcase.project_id not in _accessible_project_ids(user):
        raise PermissionDenied('You do not have access to the selected test case.')


class TestPlanViewSet(viewsets.ModelViewSet):
    """
    测试计划视图集
    """
    queryset = TestPlan.objects.all().order_by('-created_at')
    serializer_class = TestPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if is_staff_user(self.request.user):
            return TestPlan.objects.all().order_by('-created_at')
        accessible_projects = accessible_projects_for_user(self.request.user)
        return (
            TestPlan.objects
            .filter(Q(projects__in=accessible_projects) | Q(projects__isnull=True, creator=self.request.user))
            .distinct()
            .order_by('-created_at')
        )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TestPlanDetailSerializer
        return TestPlanSerializer

    def perform_create(self, serializer):
        # 在创建TestPlan时，设置creator并自动为每个项目创建TestRun和TestRunCase
        version = _get_accessible_version(self.request.user, self.request.data.get('version'))
        project_ids = _request_id_list(self.request, 'projects')
        testcase_ids = _request_id_list(self.request, 'testcases')

        if project_ids:
            _require_project_ids_access(self.request.user, project_ids)

        accessible_projects = accessible_projects_for_user(self.request.user)
        testcases = TestCase.objects.none()
        if testcase_ids:
            testcases = TestCase.objects.filter(
                id__in=testcase_ids,
                project__in=accessible_projects,
            )
            if project_ids:
                testcases = testcases.filter(project_id__in=project_ids)
            accessible_testcase_ids = set(testcases.values_list('id', flat=True))
            if set(testcase_ids) - accessible_testcase_ids:
                raise PermissionDenied('You do not have access to one or more selected test cases.')

        test_plan = serializer.save(creator=self.request.user, version=version)

        if project_ids:
            # 设置测试计划的项目关联
            test_plan.projects.set(project_ids)

            # 为每个项目创建TestRun
            for project in Project.objects.filter(id__in=project_ids):
                test_run = TestRun.objects.create(
                    name=f"{test_plan.name} - {project.name} Execution",
                    test_plan=test_plan,
                    project=project,
                    version=test_plan.version,
                    creator=test_plan.creator,
                    assignee=test_plan.creator  # 默认指派给自己
                )

                # 为TestRun关联测试用例
                project_testcases = list(testcases.filter(project=project))
                if project_testcases:
                    TestRunCase.objects.bulk_create([
                        TestRunCase(test_run=test_run, testcase=testcase)
                        for testcase in project_testcases
                    ])

    @action(detail=False, methods=['get'])
    def testcases_by_projects(self, request):
        """
        根据项目获取测试用例
        """
        project_ids = request.query_params.getlist('project_ids')
        if not project_ids:
            return Response({
                'error': '请先选择项目',
                'detail': '请先选择项目后再选择测试用例'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 过滤数字字符串和空值
            project_ids = [int(pid) for pid in project_ids if pid]
            
            if not project_ids:
                return Response({
                    'error': '无效的项目 ID',
                    'detail': '请选择有效的项目'
                }, status=status.HTTP_400_BAD_REQUEST)
            _require_project_ids_access(request.user, project_ids)
            
            # 获取指定项目的测试用例
            testcases = TestCase.objects.filter(
                project_id__in=project_ids,
                status__in=['draft', 'active']  # 包含草稿和激活状态的测试用例
            ).values('id', 'title', 'priority', 'test_type', 'project__name')
            
            return Response({
                'results': list(testcases)
            })
            
        except PermissionDenied:
            raise
        except ValidationError:
            raise
        except ValueError:
            return Response({
                'error': '项目 ID 格式错误',
                'detail': '请提供有效的项目 ID'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': '获取测试用例失败',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def perform_update(self, serializer):
        save_kwargs = {}
        # 在更新TestPlan时，处理版本信息
        if 'version' in self.request.data:
            save_kwargs['version'] = _get_accessible_version(self.request.user, self.request.data.get('version'))

        # 更新测试计划
        test_plan = serializer.save(**save_kwargs)
        
        # 更新项目关联
        if 'projects' in self.request.data:
            project_ids = _request_id_list(self.request, 'projects')
            _require_project_ids_access(self.request.user, project_ids)
            test_plan.projects.set(project_ids)
        
        # 更新指派人员
        assignee_ids = _request_id_list(self.request, 'assignees')
        if 'assignees' in self.request.data:
            test_plan.assignees.set(assignee_ids)


class TestRunViewSet(viewsets.ModelViewSet):
    """
    测试执行视图集
    """
    queryset = TestRun.objects.all().order_by('-created_at')
    serializer_class = TestRunSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            TestRun.objects
            .filter(project__in=accessible_projects_for_user(self.request.user))
            .order_by('-created_at')
        )

    def perform_create(self, serializer):
        test_plan = serializer.validated_data.get('test_plan')
        project = serializer.validated_data.get('project')
        if test_plan:
            accessible_plan = is_staff_user(self.request.user) or TestPlan.objects.filter(
                Q(projects__in=accessible_projects_for_user(self.request.user))
                | Q(projects__isnull=True, creator=self.request.user),
                pk=test_plan.pk,
            ).exists()
            if not accessible_plan:
                raise PermissionDenied('You do not have access to the selected test plan.')
        if project:
            _require_project_ids_access(self.request.user, [project.id])
        if test_plan and project and not test_plan.projects.filter(id=project.id).exists():
            raise ValidationError({'project': 'Project must belong to the selected test plan.'})
        serializer.save()

class TestRunCaseViewSet(viewsets.ModelViewSet):
    """
    测试执行用例视图集
    """
    queryset = TestRunCase.objects.all()
    serializer_class = TestRunCaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TestRunCase.objects.filter(
            test_run__project__in=accessible_projects_for_user(self.request.user)
        )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TestRunCaseDetailSerializer
        return TestRunCaseSerializer

    def perform_create(self, serializer):
        test_run = serializer.validated_data.get('test_run')
        testcase = serializer.validated_data.get('testcase')
        _require_test_run_access(self.request.user, test_run)
        _require_testcase_access(self.request.user, testcase)
        if test_run and testcase and test_run.project_id != testcase.project_id:
            raise ValidationError({'testcase': 'Test case must belong to the same project as the test run.'})
        serializer.save()

    def perform_update(self, serializer):
        instance = self.get_object()
        test_run = serializer.validated_data.get('test_run', instance.test_run)
        testcase = serializer.validated_data.get('testcase', instance.testcase)
        _require_test_run_access(self.request.user, test_run)
        _require_testcase_access(self.request.user, testcase)
        if test_run and testcase and test_run.project_id != testcase.project_id:
            raise ValidationError({'testcase': 'Test case must belong to the same project as the test run.'})
        serializer.save()

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """
        更新单个用例的执行状态，并自动创建历史记录
        """
        run_case = self.get_object()
        new_status = request.data.get('status')
        actual_result = request.data.get('actual_result', '')
        comments = request.data.get('comments', '')
        
        if not new_status:
            return Response({'error': 'Status is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # 创建历史记录
        TestRunCaseHistory.objects.create(
            run_case=run_case,
            status=new_status,
            actual_result=actual_result,
            comments=comments,
            executed_by=request.user,
            executed_at=timezone.now()
        )
        
        # 更新执行用例状态
        run_case.status = new_status
        run_case.actual_result = actual_result
        run_case.comments = comments
        run_case.executed_by = request.user
        run_case.executed_at = timezone.now()
        run_case.save()
        
        return Response(TestRunCaseDetailSerializer(run_case).data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        获取用例执行历史记录
        """
        run_case = self.get_object()
        history = run_case.history.all().order_by('-executed_at')
        serializer = TestRunCaseHistorySerializer(history, many=True)
        return Response(serializer.data)

class TestRunCaseHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    测试执行历史视图集（只读）
    """
    queryset = TestRunCaseHistory.objects.all().order_by('-executed_at')
    serializer_class = TestRunCaseHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            TestRunCaseHistory.objects
            .filter(run_case__test_run__project__in=accessible_projects_for_user(self.request.user))
            .order_by('-executed_at')
        )
