from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.db import models
from apps.core.audit import record_unified_audit
from apps.core.models import UnifiedAuditLog
from .models import (
    MetaProject,
    Project,
    ProjectEnvironment,
    ProjectMember,
    ProjectModuleBinding,
    ProjectPermissionPolicy,
    UnifiedTestAsset,
)
from .serializers import (
    MetaProjectSerializer,
    ProjectSerializer,
    ProjectCreateSerializer,
    ProjectMemberSerializer,
    ProjectEnvironmentSerializer,
    ProjectModuleBindingSerializer,
    ProjectPermissionPolicySerializer,
    UnifiedProjectSerializer,
    get_module_catalog_data,
)
from .unified import (
    accessible_meta_projects_for_user,
    accessible_projects_for_user,
    ensure_meta_project_tree,
    ensure_module_meta_node_for_binding,
    user_can_manage_project,
)
from .star_assets import (
    adopt_star_asset_as_testcase,
    get_star_asset_detail as get_star_asset_detail_payload,
    list_star_asset_rows,
    summarize_star_assets,
    sync_unified_assets_for_user,
)

class ProjectListCreateView(generics.ListCreateAPIView):
    queryset = Project.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'owner']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProjectCreateSerializer
        return ProjectSerializer
    
    def get_queryset(self):
        # 默认只显示用户参与的项目或自己创建的项目
        user = self.request.user
        return Project.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()

@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_all_projects(request):
    """获取所有项目列表，用于下拉选择等场景"""
    projects = accessible_projects_for_user(request.user).values('id', 'name', 'description', 'status')
    return Response(list(projects))


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_module_catalog(request):
    """获取统一项目可识别的模块目录。"""
    modules = get_module_catalog_data()
    bindable = request.query_params.get('bindable')
    scheduled = request.query_params.get('scheduled')
    star = request.query_params.get('star')

    def truthy(value):
        return str(value).lower() in {'1', 'true', 'yes'}

    if truthy(bindable):
        modules = [module for module in modules if module['supports_project_binding']]
    if truthy(scheduled):
        modules = [module for module in modules if module['supports_scheduled_jobs']]
    if truthy(star):
        modules = [module for module in modules if module['star_module']]

    return Response(modules)


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_star_asset_summary(request):
    return Response(summarize_star_assets(request.user))


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_star_asset_list(request, module):
    if module not in {'all', 'testcases', 'testsuites', 'reviews'}:
        return Response({'detail': 'Unsupported asset module.'}, status=status.HTTP_400_BAD_REQUEST)
    return Response(list_star_asset_rows(
        request.user,
        module,
        limit=request.query_params.get('limit'),
        filters=request.query_params,
    ))


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_star_asset_detail(request, asset_id):
    return Response(get_star_asset_detail_payload(request.user, asset_id))


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def adopt_star_asset(request, asset_id):
    try:
        asset_detail = get_star_asset_detail_payload(request.user, asset_id)
        testcase = adopt_star_asset_as_testcase(request.user, asset_id)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except PermissionError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
    record_unified_audit(
        domain='unified_assets',
        action=UnifiedAuditLog.ACTION_CREATE,
        object_type='manual_testcase',
        object_id=testcase.id,
        object_name=testcase.title,
        module=UnifiedTestAsset.MODULE_MANUAL,
        source_id=testcase.id,
        project_id=testcase.project_id,
        project_name=testcase.project.name,
        actor=request.user,
        summary='Adopted unified asset as manual test case.',
        metadata={
            'operation': 'adopt_asset',
            'source_asset_id': asset_detail.get('asset_id'),
            'source_asset_key': asset_detail.get('asset_key'),
            'source_module': asset_detail.get('module'),
            'source_type': asset_detail.get('asset_type'),
        },
    )
    return Response(
        {
            'id': testcase.id,
            'title': testcase.title,
            'project_id': testcase.project_id,
            'native_url': f'/ai-generation/testcases/{testcase.id}',
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def sync_star_assets(request):
    assets = sync_unified_assets_for_user(request.user)
    return Response({'synced': assets.count()})

class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Project.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def add_project_member(request, project_id):
    try:
        project = Project.objects.get(id=project_id)
        if project.owner != request.user:
            return Response({'error': '无权限添加成员'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = ProjectMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(project=project)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except Project.DoesNotExist:
        return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_project_members(request, project_id):
    """获取项目成员列表"""
    try:
        project = Project.objects.get(id=project_id)
        
        # 检查用户是否有权限查看项目成员
        if not (project.owner == request.user or 
                ProjectMember.objects.filter(project=project, user=request.user).exists()):
            return Response({'error': '无权限查看项目成员'}, status=status.HTTP_403_FORBIDDEN)
        
        # 获取项目成员，包括项目所有者
        members = []
        
        # 添加项目所有者
        members.append({
            'id': project.owner.id,
            'username': project.owner.username,
            'email': project.owner.email,
            'first_name': project.owner.first_name,
            'last_name': project.owner.last_name,
            'role': 'owner'
        })
        
        # 添加项目成员
        project_members = ProjectMember.objects.filter(project=project).select_related('user')
        for member in project_members:
            members.append({
                'id': member.user.id,
                'username': member.user.username,
                'email': member.user.email,
                'first_name': member.user.first_name,
                'last_name': member.user.last_name,
                'role': member.role
            })
        
        return Response(members)
    except Project.DoesNotExist:
        return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def remove_project_member(request, project_id, member_id):
    try:
        project = Project.objects.get(id=project_id)
        if project.owner != request.user:
            return Response({'error': '无权限删除成员'}, status=status.HTTP_403_FORBIDDEN)
        
        member = ProjectMember.objects.get(id=member_id, project=project)
        member.delete()
        return Response({'message': '成员删除成功'})
    except (Project.DoesNotExist, ProjectMember.DoesNotExist):
        return Response({'error': '项目或成员不存在'}, status=status.HTTP_404_NOT_FOUND)

class ProjectEnvironmentListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectEnvironmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ProjectEnvironment.objects.none()
        project_id = self.kwargs['project_id']
        return ProjectEnvironment.objects.filter(project_id=project_id)
    
    def perform_create(self, serializer):
        project_id = self.kwargs['project_id']
        serializer.save(project_id=project_id)


class UnifiedProjectListView(generics.ListAPIView):
    serializer_class = UnifiedProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'owner']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        return accessible_projects_for_user(self.request.user).prefetch_related(
            'module_bindings',
            'projectmember_set__user',
            'environments',
        )


class UnifiedProjectDetailView(generics.RetrieveAPIView):
    serializer_class = UnifiedProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return accessible_projects_for_user(self.request.user).prefetch_related(
            'module_bindings',
            'projectmember_set__user',
            'environments',
        )


class MetaProjectListCreateView(generics.ListCreateAPIView):
    serializer_class = MetaProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'node_type', 'module', 'status']
    search_fields = ['name', 'description']
    ordering_fields = ['sort_order', 'created_at', 'updated_at', 'name']
    ordering = ['sort_order', 'id']

    def get_queryset(self):
        queryset = accessible_meta_projects_for_user(self.request.user).select_related(
            'project',
            'parent',
            'owner',
        ).prefetch_related('children')
        include_all = str(self.request.query_params.get('include_all', '')).lower() in {'1', 'true', 'yes'}
        if not include_all:
            queryset = queryset.filter(parent__isnull=True)
        return queryset

    def perform_create(self, serializer):
        project = serializer.validated_data['project']
        if not user_can_manage_project(self.request.user, project):
            raise PermissionDenied('No permission to manage this project tree.')
        serializer.save(owner=self.request.user)


class MetaProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MetaProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return accessible_meta_projects_for_user(self.request.user).select_related(
            'project',
            'parent',
            'owner',
        ).prefetch_related('children')

    def _assert_manage_permission(self, instance):
        if not user_can_manage_project(self.request.user, instance.project):
            raise PermissionDenied('No permission to manage this project tree.')

    def perform_update(self, serializer):
        instance = self.get_object()
        self._assert_manage_permission(instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._assert_manage_permission(instance)
        instance.delete()


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def sync_meta_project_tree(request, project_id):
    project = get_object_or_404(accessible_projects_for_user(request.user), pk=project_id)
    if not user_can_manage_project(request.user, project):
        raise PermissionDenied('No permission to manage this project tree.')
    root = ensure_meta_project_tree(project, owner=project.owner)
    return Response(MetaProjectSerializer(root, context={'request': request}).data)


class ProjectModuleBindingListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectModuleBindingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_project(self):
        return get_object_or_404(accessible_projects_for_user(self.request.user), pk=self.kwargs['project_id'])

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ProjectModuleBinding.objects.none()
        return ProjectModuleBinding.objects.filter(project=self.get_project()).order_by('module', 'object_id')

    def perform_create(self, serializer):
        project = self.get_project()
        if not user_can_manage_project(self.request.user, project):
            raise PermissionDenied('No permission to manage this project.')
        binding = serializer.save(project=project)
        ensure_module_meta_node_for_binding(binding)


class ProjectModuleBindingDetailView(generics.DestroyAPIView):
    serializer_class = ProjectModuleBindingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_project(self):
        return get_object_or_404(accessible_projects_for_user(self.request.user), pk=self.kwargs['project_id'])

    def get_queryset(self):
        return ProjectModuleBinding.objects.filter(project=self.get_project())

    def perform_destroy(self, instance):
        if not user_can_manage_project(self.request.user, instance.project):
            raise PermissionDenied('No permission to manage this project.')
        MetaProject.objects.filter(
            project=instance.project,
            module=instance.module,
            object_id=instance.object_id,
        ).delete()
        instance.delete()


class ProjectPermissionPolicyListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectPermissionPolicySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['module', 'action', 'is_active']
    search_fields = ['action', 'description']
    ordering_fields = ['created_at', 'updated_at', 'action']
    ordering = ['module', 'action']

    def get_project(self):
        return get_object_or_404(accessible_projects_for_user(self.request.user), pk=self.kwargs['project_id'])

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ProjectPermissionPolicy.objects.none()
        return self.get_project().permission_policies.all().select_related('created_by')

    def perform_create(self, serializer):
        project = self.get_project()
        if not user_can_manage_project(self.request.user, project):
            raise PermissionDenied('No permission to manage this project.')
        serializer.save(project=project, created_by=self.request.user)


class ProjectPermissionPolicyDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectPermissionPolicySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_project(self):
        return get_object_or_404(accessible_projects_for_user(self.request.user), pk=self.kwargs['project_id'])

    def get_queryset(self):
        return self.get_project().permission_policies.all().select_related('created_by')

    def _assert_manage_permission(self, instance):
        if not user_can_manage_project(self.request.user, instance.project):
            raise PermissionDenied('No permission to manage this project.')

    def perform_update(self, serializer):
        instance = self.get_object()
        self._assert_manage_permission(instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._assert_manage_permission(instance)
        instance.delete()
