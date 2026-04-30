from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .models import (
    MetaProject,
    Project,
    ProjectMember,
    ProjectEnvironment,
    ProjectPermissionPolicy,
    ProjectModuleBinding,
    UnifiedTestAsset,
    UnifiedTestAssetSnapshot,
)
from .module_registry import (
    build_module_count_summary,
    get_module_choices,
    get_module_definition,
    iter_module_definitions,
)
from .unified import ensure_meta_project_tree, get_module_project, get_module_project_name, user_can_access_module_project
from apps.users.serializers import UserSerializer

class ProjectSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ('id', 'name')
        ref_name = 'ProjectsProjectSimple'

class ProjectEnvironmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectEnvironment
        fields = '__all__'

class ProjectMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = ProjectMember
        fields = ['id', 'user', 'user_id', 'role', 'joined_at']

class ProjectSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    members = ProjectMemberSerializer(source='projectmember_set', many=True, read_only=True)
    environments = ProjectEnvironmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'status', 'owner', 'members', 
                 'environments', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['name', 'description', 'status']
    
    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        project = super().create(validated_data)
        ensure_meta_project_tree(project, owner=project.owner)
        return project


class ProjectModuleBindingSerializer(serializers.ModelSerializer):
    module = serializers.ChoiceField(choices=get_module_choices(bindable_only=True))
    module_name = serializers.SerializerMethodField()
    module_display = serializers.SerializerMethodField()
    module_description = serializers.SerializerMethodField()
    module_frontend_path = serializers.SerializerMethodField()
    module_tag_type = serializers.SerializerMethodField()

    class Meta:
        model = ProjectModuleBinding
        fields = [
            'id', 'project', 'module', 'module_display', 'module_description',
            'module_frontend_path', 'module_tag_type', 'object_id', 'module_name',
            'display_name', 'is_primary', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'project', 'module_name', 'created_at', 'updated_at']

    def get_module_name(self, obj) -> str:
        return obj.display_name or get_module_project_name(obj.module, obj.object_id)

    def _get_module_definition(self, obj):
        return get_module_definition(obj.module)

    def get_module_display(self, obj) -> str:
        definition = self._get_module_definition(obj)
        return definition.display_name if definition else obj.module

    def get_module_description(self, obj) -> str:
        definition = self._get_module_definition(obj)
        return definition.description if definition else ''

    def get_module_frontend_path(self, obj) -> str:
        definition = self._get_module_definition(obj)
        return definition.frontend_path if definition else ''

    def get_module_tag_type(self, obj) -> str:
        definition = self._get_module_definition(obj)
        return definition.tag_type if definition else 'info'

    def validate(self, attrs):
        module = attrs.get('module')
        object_id = attrs.get('object_id')

        if not get_module_project(module, object_id):
            raise serializers.ValidationError({'object_id': 'Module project does not exist.'})

        request = self.context.get('request')
        if request and not user_can_access_module_project(request.user, module, object_id):
            raise PermissionDenied('No permission to bind this module project.')

        duplicate = ProjectModuleBinding.objects.filter(module=module, object_id=object_id)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError('This module project is already bound.')

        return attrs


class MetaProjectSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    module_display = serializers.SerializerMethodField()
    module_description = serializers.SerializerMethodField()
    module_frontend_path = serializers.SerializerMethodField()
    module_tag_type = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = MetaProject
        fields = [
            'id',
            'project',
            'project_name',
            'parent',
            'node_type',
            'module',
            'module_display',
            'module_description',
            'module_frontend_path',
            'module_tag_type',
            'object_id',
            'name',
            'description',
            'status',
            'owner',
            'owner_username',
            'sort_order',
            'children',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']

    def _get_module_definition(self, obj):
        if not obj.module:
            return None
        return get_module_definition(obj.module)

    def get_module_display(self, obj) -> str:
        definition = self._get_module_definition(obj)
        return definition.display_name if definition else ''

    def get_module_description(self, obj) -> str:
        definition = self._get_module_definition(obj)
        return definition.description if definition else ''

    def get_module_frontend_path(self, obj) -> str:
        definition = self._get_module_definition(obj)
        return definition.frontend_path if definition else ''

    def get_module_tag_type(self, obj) -> str:
        definition = self._get_module_definition(obj)
        return definition.tag_type if definition else 'info'

    def get_children(self, obj) -> list:
        children = obj.children.all().order_by('sort_order', 'id')
        return MetaProjectSerializer(children, many=True, context=self.context).data

    def validate(self, attrs):
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        parent = attrs.get('parent') or getattr(self.instance, 'parent', None)
        module = attrs.get('module') or getattr(self.instance, 'module', '')
        object_id = attrs.get('object_id') or getattr(self.instance, 'object_id', None)

        if parent and project and parent.project_id != project.id:
            raise serializers.ValidationError({'parent': 'Parent must belong to the same unified project.'})

        if module and object_id and not get_module_project(module, object_id):
            raise serializers.ValidationError({'object_id': 'Module project does not exist.'})

        request = self.context.get('request')
        if request and module and object_id and not user_can_access_module_project(request.user, module, object_id):
            raise PermissionDenied('No permission to attach this module project.')

        return attrs


class UnifiedProjectSerializer(ProjectSerializer):
    modules = serializers.SerializerMethodField()
    module_summary = serializers.SerializerMethodField()
    scheduled_job_summary = serializers.SerializerMethodField()
    meta_project = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        fields = ProjectSerializer.Meta.fields + ['modules', 'module_summary', 'scheduled_job_summary', 'meta_project']

    def get_modules(self, obj) -> list:
        bindings = obj.module_bindings.all()
        return ProjectModuleBindingSerializer(bindings, many=True, context=self.context).data

    def get_module_summary(self, obj) -> dict:
        summary = build_module_count_summary(bindable_only=True)
        summary['total'] = 0
        for binding in obj.module_bindings.all():
            summary[binding.module] = summary.get(binding.module, 0) + 1
            summary['total'] += 1
        return summary

    def get_scheduled_job_summary(self, obj) -> dict:
        request = self.context.get('request')
        empty_summary = {
            'total': 0,
            'active': 0,
            'paused': 0,
            'completed': 0,
            'failed': 0,
            'by_module': build_module_count_summary(scheduled_only=True),
        }
        if not request or not getattr(request.user, 'is_authenticated', False):
            return empty_summary

        from apps.core.scheduled_jobs import get_scheduled_job_summary

        return get_scheduled_job_summary(request.user, obj)

    def get_meta_project(self, obj) -> dict | None:
        root = ensure_meta_project_tree(obj, owner=obj.owner)
        if root is None:
            return None
        return MetaProjectSerializer(root, context=self.context).data


def get_module_catalog_data():
    return [definition.as_dict() for definition in iter_module_definitions()]


class UnifiedTestAssetSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    asset_key = serializers.CharField(read_only=True)

    class Meta:
        model = UnifiedTestAsset
        fields = [
            'id', 'asset_key', 'project', 'project_name', 'module', 'asset_type',
            'object_id', 'title', 'status', 'priority', 'version_label',
            'source_updated_at', 'metadata', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'asset_key', 'created_at', 'updated_at']


class UnifiedTestAssetSnapshotSerializer(serializers.ModelSerializer):
    asset_key = serializers.CharField(source='asset.asset_key', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = UnifiedTestAssetSnapshot
        fields = [
            'id', 'asset', 'asset_key', 'snapshot_hash', 'payload',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['id', 'asset_key', 'created_by', 'created_at']


class ProjectPermissionPolicySerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ProjectPermissionPolicy
        fields = [
            'id',
            'project',
            'project_name',
            'module',
            'action',
            'allowed_roles',
            'is_active',
            'description',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'project', 'created_by', 'created_at', 'updated_at']

    def validate_allowed_roles(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('allowed_roles must be a list.')
        normalized = []
        valid_roles = {choice[0] for choice in ProjectMember.ROLE_CHOICES}
        for role in value:
            role_text = str(role).strip().lower()
            if role_text in valid_roles and role_text not in normalized:
                normalized.append(role_text)
        return normalized
