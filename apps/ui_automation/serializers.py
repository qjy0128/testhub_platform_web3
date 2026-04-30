from rest_framework import serializers
from copy import deepcopy
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from apps.core.notification_safety import redact_webhook_url, validate_notification_webhook_bots
from typing import Any
from .models import (
    UiProject, LocatorStrategy, Element, TestScript, TestSuite,
    TestSuiteScript, TestSuiteTestCase, TestExecution, TestEnvironment, Screenshot,
    ElementGroup, PageObject, PageObjectElement, ScriptStep, ScriptElementUsage,
    TestCase, TestCaseStep, TestCaseExecution, OperationRecord,
    UiScheduledTask, UiNotificationLog, UiTaskNotificationSetting,
    AICase, AIExecutionRecord, WalletBrowserConfig
)
from django.contrib.auth import get_user_model

User = get_user_model()


def _request_user(serializer):
    request = serializer.context.get('request')
    return getattr(request, 'user', None)


def _is_ui_automation_admin(user):
    return getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)


def _accessible_ui_projects_for_user(user):
    if not getattr(user, 'is_authenticated', False):
        return UiProject.objects.none()
    if _is_ui_automation_admin(user):
        return UiProject.objects.all()

    user_id = getattr(user, 'pk', None)
    if user_id is None:
        return UiProject.objects.none()
    return UiProject.objects.filter(
        models.Q(owner_id=user_id) | models.Q(members__id=user_id)
    ).distinct()


def _accessible_element_groups_for_user(user):
    return ElementGroup.objects.filter(project__in=_accessible_ui_projects_for_user(user))


def _accessible_elements_for_user(user):
    return Element.objects.filter(project__in=_accessible_ui_projects_for_user(user))


def _accessible_page_objects_for_user(user):
    return PageObject.objects.filter(project__in=_accessible_ui_projects_for_user(user))


def _accessible_test_scripts_for_user(user):
    return TestScript.objects.filter(project__in=_accessible_ui_projects_for_user(user))


def _accessible_test_suites_for_user(user):
    return TestSuite.objects.filter(project__in=_accessible_ui_projects_for_user(user))


def _accessible_test_cases_for_user(user):
    return TestCase.objects.filter(project__in=_accessible_ui_projects_for_user(user))


def _accessible_test_executions_for_user(user):
    return TestExecution.objects.filter(project__in=_accessible_ui_projects_for_user(user))


def _accessible_ai_cases_for_user(user):
    return AICase.objects.filter(
        models.Q(project__in=_accessible_ui_projects_for_user(user)) |
        models.Q(project__isnull=True)
    ).distinct()


def _scope_related_queryset(serializer, field_name, queryset):
    field = serializer.fields.get(field_name)
    if field is not None and hasattr(field, 'queryset'):
        field.queryset = queryset


def _get_accessible_project_or_error(serializer, project_id):
    user = _request_user(serializer)
    try:
        return _accessible_ui_projects_for_user(user).get(id=project_id)
    except UiProject.DoesNotExist:
        raise serializers.ValidationError("Project does not exist or is not accessible.")


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email')
        ref_name = 'UiAutomationUser'


class UiProjectSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    members = UserSerializer(many=True, read_only=True)
    unified_projects = serializers.SerializerMethodField()

    class Meta:
        model = UiProject
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_unified_projects(self, obj) -> list[dict[str, Any]]:
        try:
            from apps.projects.models import MetaProject, ProjectModuleBinding
        except Exception:
            return []
        bindings = ProjectModuleBinding.objects.filter(
            module=ProjectModuleBinding.MODULE_UI_AUTOMATION,
            object_id=obj.id,
        ).select_related('project')
        rows = []
        for binding in bindings:
            meta_node = MetaProject.objects.filter(
                project=binding.project,
                module=ProjectModuleBinding.MODULE_UI_AUTOMATION,
                object_id=obj.id,
            ).first()
            rows.append({
                'binding_id': binding.id,
                'project_id': binding.project_id,
                'project_name': binding.project.name,
                'meta_project_id': meta_node.id if meta_node else None,
                'display_name': binding.display_name,
                'is_primary': binding.is_primary,
            })
        return rows


class UiProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UiProject
        fields = ('name', 'description', 'status', 'base_url', 'start_date', 'end_date', 'owner', 'members')


class UiProjectUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UiProject
        fields = ('name', 'description', 'status', 'base_url', 'start_date', 'end_date', 'members')


class LocatorStrategySerializer(serializers.ModelSerializer):
    class Meta:
        model = LocatorStrategy
        fields = '__all__'


class ElementSerializer(serializers.ModelSerializer):
    project = UiProjectSerializer(read_only=True)
    locator_strategy = LocatorStrategySerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    project_id = serializers.IntegerField(write_only=True)
    group_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    locator_strategy_id = serializers.IntegerField()  # 显式定义，支持读写

    class Meta:
        model = Element
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by')

    def validate_project_id(self, value):
        """验证项目ID是否有效"""
        _get_accessible_project_or_error(self, value)
        return value

    def validate_locator_strategy_id(self, value):
        """验证定位策略ID是否有效"""
        if value is not None:
            try:
                LocatorStrategy.objects.get(id=value)
            except LocatorStrategy.DoesNotExist:
                raise serializers.ValidationError("请选择有效的定位策略")
        return value

    def validate_group_id(self, value):
        """验证分组ID是否有效"""
        if value is not None:  # 允许None值
            try:
                _accessible_element_groups_for_user(_request_user(self)).get(id=value)
            except ElementGroup.DoesNotExist:
                raise serializers.ValidationError("Element group does not exist or is not accessible.")
        return value

    def validate(self, attrs):
        project_id = attrs.get('project_id', getattr(self.instance, 'project_id', None))
        group_id = attrs.get('group_id')
        if project_id and group_id:
            try:
                group = _accessible_element_groups_for_user(_request_user(self)).get(id=group_id)
            except ElementGroup.DoesNotExist:
                raise serializers.ValidationError({'group_id': 'Element group does not exist or is not accessible.'})
            if group.project_id != project_id:
                raise serializers.ValidationError({'group_id': 'Element group must belong to the selected project.'})
        return attrs

    def create(self, validated_data):
        # 处理外键字段
        project_id = validated_data.pop('project_id')
        locator_strategy_id = validated_data.pop('locator_strategy_id', None)
        group_id = validated_data.pop('group_id', None)

        validated_data['project'] = _get_accessible_project_or_error(self, project_id)

        if locator_strategy_id:
            validated_data['locator_strategy'] = LocatorStrategy.objects.get(id=locator_strategy_id)

        if group_id:
            validated_data['group'] = _accessible_element_groups_for_user(_request_user(self)).get(id=group_id)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        # 处理外键字段
        project_id = validated_data.pop('project_id', None)
        locator_strategy_id = validated_data.pop('locator_strategy_id', None)
        group_id = validated_data.pop('group_id', None)

        if project_id:
            validated_data['project'] = _get_accessible_project_or_error(self, project_id)

        if locator_strategy_id:
            validated_data['locator_strategy'] = LocatorStrategy.objects.get(id=locator_strategy_id)

        if group_id is not None:  # 允许设置为None来清除分组
            if group_id:
                validated_data['group'] = _accessible_element_groups_for_user(_request_user(self)).get(id=group_id)
            else:
                validated_data['group'] = None

        return super().update(instance, validated_data)


class TestScriptSerializer(serializers.ModelSerializer):
    project = UiProjectSerializer(read_only=True)
    project_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = TestScript
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class TestScriptCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestScript
        fields = ('project', 'name', 'description', 'script_type', 'content', 'language', 'framework')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user is not None:
            _scope_related_queryset(self, 'project', _accessible_ui_projects_for_user(user))


class TestScriptUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestScript
        fields = ('name', 'description', 'script_type', 'content')


class TestSuiteScriptSerializer(serializers.ModelSerializer):
    test_script = TestScriptSerializer(read_only=True)
    test_script_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = TestSuiteScript
        fields = ('id', 'test_script', 'test_script_id', 'order')


class TestSuiteTestCaseSerializer(serializers.ModelSerializer):
    test_case = serializers.SerializerMethodField()
    test_case_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = TestSuiteTestCase
        fields = ('id', 'test_case', 'test_case_id', 'order')

    def get_test_case(self, obj) -> dict[str, Any]:
        """获取测试用例信息"""
        test_case = obj.test_case
        return {
            'id': test_case.id,
            'name': test_case.name,
            'description': test_case.description,
            'status': test_case.status,
            'priority': test_case.priority,
            'created_at': test_case.created_at
        }


class TestSuiteSerializer(serializers.ModelSerializer):
    project = UiProjectSerializer(read_only=True)
    scripts = TestScriptSerializer(many=True, read_only=True)
    test_cases_data = serializers.SerializerMethodField()
    project_id = serializers.IntegerField(write_only=True)
    suite_scripts = TestSuiteScriptSerializer(many=True, read_only=True)
    suite_test_cases = TestSuiteTestCaseSerializer(many=True, read_only=True)
    test_case_count = serializers.SerializerMethodField()

    class Meta:
        model = TestSuite
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'execution_status', 'passed_count', 'failed_count')
        ref_name = 'UiAutomationTestSuite'

    def get_test_cases_data(self, obj) -> list[dict[str, Any]]:
        """获取测试用例数据"""
        return TestSuiteTestCaseSerializer(obj.suite_test_cases.all(), many=True).data

    def get_test_case_count(self, obj) -> int:
        """获取测试用例数量"""
        return obj.suite_test_cases.count()


class TestSuiteCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestSuite
        fields = ('id', 'project', 'name', 'description')
        read_only_fields = ('id',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user is not None:
            _scope_related_queryset(self, 'project', _accessible_ui_projects_for_user(user))


class TestSuiteUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestSuite
        fields = ('name', 'description')


class TestSuiteWithScriptsSerializer(serializers.ModelSerializer):
    project = UiProjectSerializer(read_only=True)
    suite_scripts = TestSuiteScriptSerializer(many=True, read_only=True)

    class Meta:
        model = TestSuite
        fields = '__all__'


class TestExecutionSerializer(serializers.ModelSerializer):
    project = UiProjectSerializer(read_only=True)
    test_suite = TestSuiteSerializer(read_only=True)
    test_script = TestScriptSerializer(read_only=True)
    executed_by = UserSerializer(read_only=True)
    project_id = serializers.IntegerField(write_only=True)
    test_suite_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    test_script_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    executed_by_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    # 添加计算字段
    test_suite_name = serializers.SerializerMethodField()
    executed_by_name = serializers.SerializerMethodField()
    pass_rate = serializers.SerializerMethodField()

    class Meta:
        model = TestExecution
        fields = '__all__'
        read_only_fields = (
            'created_at', 'started_at', 'finished_at', 'duration',
            'total_cases', 'passed_cases', 'failed_cases', 'skipped_cases'
        )
        ref_name = 'UiAutomationTestExecution'

    def get_test_suite_name(self, obj) -> str:
        """获取测试套件名称"""
        return obj.test_suite.name if obj.test_suite else '-'
    
    def get_executed_by_name(self, obj) -> str:
        """获取执行人姓名"""
        return obj.executed_by.username if obj.executed_by else '-'

    def get_pass_rate(self, obj) -> float:
        """获取通过率"""
        return obj.pass_rate


class TestExecutionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestExecution
        fields = ('project', 'test_suite', 'test_script', 'environment', 'executed_by')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user is not None:
            _scope_related_queryset(self, 'project', _accessible_ui_projects_for_user(user))
            _scope_related_queryset(self, 'test_suite', _accessible_test_suites_for_user(user))
            _scope_related_queryset(self, 'test_script', _accessible_test_scripts_for_user(user))

    def validate(self, attrs):
        project = attrs.get('project', getattr(self.instance, 'project', None))
        test_suite = attrs.get('test_suite', getattr(self.instance, 'test_suite', None))
        test_script = attrs.get('test_script', getattr(self.instance, 'test_script', None))
        if project and test_suite and test_suite.project_id != project.id:
            raise serializers.ValidationError({'test_suite': 'Test suite must belong to the selected project.'})
        if project and test_script and test_script.project_id != project.id:
            raise serializers.ValidationError({'test_script': 'Test script must belong to the selected project.'})
        return attrs


class ScreenshotSerializer(serializers.ModelSerializer):
    execution = TestExecutionSerializer(read_only=True)
    execution_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Screenshot
        fields = '__all__'
        read_only_fields = ('created_at', 'captured_at')

    def validate_execution_id(self, value):
        try:
            _accessible_test_executions_for_user(_request_user(self)).get(id=value)
        except TestExecution.DoesNotExist:
            raise serializers.ValidationError("Execution does not exist or is not accessible.")
        return value


# 新增的serializers
class ElementGroupSerializer(serializers.ModelSerializer):
    project = UiProjectSerializer(read_only=True)
    project_id = serializers.IntegerField(write_only=True)
    elements_count = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = ElementGroup
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_elements_count(self, obj) -> int:
        """获取分组下的元素数量"""
        return obj.elements.count()

    def get_children(self, obj) -> list[dict[str, Any]]:
        """获取子分组"""
        children = obj.elementgroup_set.all()
        return ElementGroupSerializer(children, many=True, context=self.context).data


class ElementGroupCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ElementGroup
        fields = ('project', 'name', 'description', 'parent_group', 'order')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user is not None:
            projects = _accessible_ui_projects_for_user(user)
            _scope_related_queryset(self, 'project', projects)
            _scope_related_queryset(self, 'parent_group', ElementGroup.objects.filter(project__in=projects))

    def validate(self, attrs):
        project = attrs.get('project', getattr(self.instance, 'project', None))
        parent_group = attrs.get('parent_group', getattr(self.instance, 'parent_group', None))
        if project and parent_group and parent_group.project_id != project.id:
            raise serializers.ValidationError({'parent_group': 'Parent group must belong to the selected project.'})
        return attrs


class ElementEnhancedSerializer(serializers.ModelSerializer):
    """增强的元素序列化器，包含新字段"""
    project = UiProjectSerializer(read_only=True)
    group = ElementGroupSerializer(read_only=True)
    locator_strategy = LocatorStrategySerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    parent_element = serializers.SerializerMethodField()
    children_elements = serializers.SerializerMethodField()
    all_locators = serializers.SerializerMethodField()
    usage_scripts = serializers.SerializerMethodField()

    # Write-only fields for foreign keys
    project_id = serializers.IntegerField(write_only=True)
    group_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    locator_strategy_id = serializers.IntegerField()  # 允许读写,支持回显
    parent_element_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Element
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'usage_count', 'last_validated')

    def get_parent_element(self, obj) -> dict[str, Any] | None:
        """获取父元素信息"""
        if obj.parent_element:
            return {
                'id': obj.parent_element.id,
                'name': obj.parent_element.name,
                'page': obj.parent_element.page
            }
        return None

    def get_children_elements(self, obj) -> list[dict[str, Any]]:
        """获取子元素"""
        children = obj.element_set.all()
        return [{
            'id': child.id,
            'name': child.name,
            'element_type': child.element_type
        } for child in children]

    def get_all_locators(self, obj) -> dict[str, Any]:
        """获取所有定位器（主要+备用）"""
        return obj.get_all_locators()

    def get_usage_scripts(self, obj) -> list[dict[str, Any]]:
        """获取使用此元素的脚本列表"""
        usages = obj.script_usages.select_related('script').all()[:5]  # 只返回前5个
        return [{
            'script_id': usage.script.id,
            'script_name': usage.script.name,
            'usage_type': usage.usage_type,
            'frequency': usage.frequency
        } for usage in usages]

    def validate_project_id(self, value):
        _get_accessible_project_or_error(self, value)
        return value

    def validate_group_id(self, value):
        if value is not None:
            try:
                _accessible_element_groups_for_user(_request_user(self)).get(id=value)
            except ElementGroup.DoesNotExist:
                raise serializers.ValidationError("Element group does not exist or is not accessible.")
        return value

    def validate_parent_element_id(self, value):
        if value is not None:
            if self.instance and value == self.instance.id:
                raise serializers.ValidationError("Element cannot be its own parent.")
            try:
                _accessible_elements_for_user(_request_user(self)).get(id=value)
            except Element.DoesNotExist:
                raise serializers.ValidationError("Parent element does not exist or is not accessible.")
        return value

    def validate(self, attrs):
        project_id = attrs.get('project_id', getattr(self.instance, 'project_id', None))
        group_id = attrs.get('group_id')
        parent_element_id = attrs.get('parent_element_id')

        if project_id and group_id:
            group = _accessible_element_groups_for_user(_request_user(self)).get(id=group_id)
            if group.project_id != project_id:
                raise serializers.ValidationError({'group_id': 'Element group must belong to the selected project.'})

        if project_id and parent_element_id:
            parent = _accessible_elements_for_user(_request_user(self)).get(id=parent_element_id)
            if parent.project_id != project_id:
                raise serializers.ValidationError({'parent_element_id': 'Parent element must belong to the selected project.'})

        return attrs

    def create(self, validated_data):
        # 处理外键字段
        project_id = validated_data.pop('project_id')
        locator_strategy_id = validated_data.pop('locator_strategy_id')
        group_id = validated_data.pop('group_id', None)
        parent_element_id = validated_data.pop('parent_element_id', None)

        validated_data['project'] = _get_accessible_project_or_error(self, project_id)
        validated_data['locator_strategy'] = LocatorStrategy.objects.get(id=locator_strategy_id)

        if group_id:
            validated_data['group'] = _accessible_element_groups_for_user(_request_user(self)).get(id=group_id)

        if parent_element_id:
            validated_data['parent_element'] = _accessible_elements_for_user(_request_user(self)).get(id=parent_element_id)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        # 处理外键字段
        project_id = validated_data.pop('project_id', None)
        locator_strategy_id = validated_data.pop('locator_strategy_id', None)
        group_id = validated_data.pop('group_id', None)
        parent_element_id = validated_data.pop('parent_element_id', None)

        if project_id:
            validated_data['project'] = _get_accessible_project_or_error(self, project_id)

        if locator_strategy_id:
            validated_data['locator_strategy'] = LocatorStrategy.objects.get(id=locator_strategy_id)

        if group_id is not None:  # 允许设置为None来清除分组
            if group_id:
                validated_data['group'] = _accessible_element_groups_for_user(_request_user(self)).get(id=group_id)
            else:
                validated_data['group'] = None

        if parent_element_id is not None:  # 允许设置为None来清除父元素
            if parent_element_id:
                validated_data['parent_element'] = _accessible_elements_for_user(_request_user(self)).get(id=parent_element_id)
            else:
                validated_data['parent_element'] = None

        return super().update(instance, validated_data)


class PageObjectSerializer(serializers.ModelSerializer):
    project = UiProjectSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    elements_count = serializers.SerializerMethodField()
    elements = serializers.SerializerMethodField()
    project_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = PageObject
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'template_code')

    def get_elements_count(self, obj) -> int:
        """获取页面对象包含的元素数量"""
        return obj.page_object_elements.count()

    def get_elements(self, obj) -> list[dict[str, Any]]:
        """获取页面对象包含的元素"""
        po_elements = obj.page_object_elements.select_related('element').all()
        return [{
            'id': po_element.id,
            'element_id': po_element.element.id,
            'element_name': po_element.element.name,
            'method_name': po_element.method_name,
            'is_property': po_element.is_property,
            'order': po_element.order
        } for po_element in po_elements]


class PageObjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageObject
        fields = ('project', 'name', 'class_name', 'url_pattern', 'description')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user is not None:
            _scope_related_queryset(self, 'project', _accessible_ui_projects_for_user(user))

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class PageObjectElementSerializer(serializers.ModelSerializer):
    page_object = PageObjectSerializer(read_only=True)
    element = ElementEnhancedSerializer(read_only=True)
    page_object_id = serializers.IntegerField(write_only=True)
    element_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = PageObjectElement
        fields = '__all__'
        read_only_fields = ('created_at',)

    def validate_method_name(self, value):
        """验证方法名称是否符合命名规范"""
        import re
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', value):
            raise serializers.ValidationError("方法名称只能包含字母、数字和下划线，且不能以数字开头")
        return value

    def validate_page_object_id(self, value):
        try:
            _accessible_page_objects_for_user(_request_user(self)).get(id=value)
        except PageObject.DoesNotExist:
            raise serializers.ValidationError("Page object does not exist or is not accessible.")
        return value

    def validate_element_id(self, value):
        try:
            _accessible_elements_for_user(_request_user(self)).get(id=value)
        except Element.DoesNotExist:
            raise serializers.ValidationError("Element does not exist or is not accessible.")
        return value

    def validate(self, attrs):
        page_object = _accessible_page_objects_for_user(_request_user(self)).get(id=attrs['page_object_id'])
        element = _accessible_elements_for_user(_request_user(self)).get(id=attrs['element_id'])
        if element.project_id != page_object.project_id:
            raise serializers.ValidationError({'element_id': 'Element must belong to the page object project.'})
        return attrs


class ScriptStepSerializer(serializers.ModelSerializer):
    script = TestScriptSerializer(read_only=True)
    target_element = ElementEnhancedSerializer(read_only=True)
    page_object = PageObjectSerializer(read_only=True)

    script_id = serializers.IntegerField(write_only=True)
    target_element_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    page_object_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = ScriptStep
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def validate(self, data):
        """验证步骤配置"""
        script_id = data.get('script_id')
        target_element_id = data.get('target_element_id')
        page_object_id = data.get('page_object_id')
        action_type = data.get('action_type')

        # 某些操作类型需要指定目标元素
        if action_type in ['CLICK', 'INPUT', 'SELECT', 'HOVER', 'VERIFY'] and not target_element_id and not page_object_id:
            raise serializers.ValidationError("此操作类型需要指定目标元素或页面对象")

        if script_id:
            try:
                script = _accessible_test_scripts_for_user(_request_user(self)).get(id=script_id)
            except TestScript.DoesNotExist:
                raise serializers.ValidationError({'script_id': 'Script does not exist or is not accessible.'})
            if target_element_id:
                try:
                    target_element = _accessible_elements_for_user(_request_user(self)).get(id=target_element_id)
                except Element.DoesNotExist:
                    raise serializers.ValidationError({'target_element_id': 'Target element does not exist or is not accessible.'})
                if target_element.project_id != script.project_id:
                    raise serializers.ValidationError({'target_element_id': 'Target element must belong to the script project.'})
            if page_object_id:
                try:
                    page_object = _accessible_page_objects_for_user(_request_user(self)).get(id=page_object_id)
                except PageObject.DoesNotExist:
                    raise serializers.ValidationError({'page_object_id': 'Page object does not exist or is not accessible.'})
                if page_object.project_id != script.project_id:
                    raise serializers.ValidationError({'page_object_id': 'Page object must belong to the script project.'})

        return data


class ScriptElementUsageSerializer(serializers.ModelSerializer):
    script = TestScriptSerializer(read_only=True)
    element = ElementEnhancedSerializer(read_only=True)
    script_id = serializers.IntegerField(write_only=True)
    element_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ScriptElementUsage
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def validate(self, attrs):
        try:
            script = _accessible_test_scripts_for_user(_request_user(self)).get(id=attrs['script_id'])
        except TestScript.DoesNotExist:
            raise serializers.ValidationError({'script_id': 'Script does not exist or is not accessible.'})
        try:
            element = _accessible_elements_for_user(_request_user(self)).get(id=attrs['element_id'])
        except Element.DoesNotExist:
            raise serializers.ValidationError({'element_id': 'Element does not exist or is not accessible.'})
        if element.project_id != script.project_id:
            raise serializers.ValidationError({'element_id': 'Element must belong to the script project.'})
        return attrs


class ScriptAnalysisSerializer(serializers.Serializer):
    """脚本分析结果序列化器"""
    element_usages = ScriptElementUsageSerializer(many=True, read_only=True)
    missing_elements = serializers.ListField(child=serializers.CharField(), read_only=True)
    recommendations = serializers.ListField(child=serializers.CharField(), read_only=True)
    complexity_score = serializers.IntegerField(read_only=True)


class ElementValidationSerializer(serializers.Serializer):
    """元素验证结果序列化器"""
    is_valid = serializers.BooleanField(read_only=True)
    validation_message = serializers.CharField(read_only=True)
    suggestions = serializers.ListField(child=serializers.CharField(), read_only=True)


class CodeGenerationSerializer(serializers.Serializer):
    """代码生成序列化器"""
    language = serializers.ChoiceField(choices=[('javascript', 'JavaScript'), ('python', 'Python')], default='javascript')
    framework = serializers.ChoiceField(choices=[('playwright', 'Playwright'), ('selenium', 'Selenium')], default='playwright')
    include_comments = serializers.BooleanField(default=True)

    def validate(self, data):
        # 可以添加更多验证逻辑
        return data


class TestCaseStepSerializer(serializers.ModelSerializer):
    """测试用例步骤序列化器"""
    element_name = serializers.CharField(source='element.name', read_only=True)
    element_locator = serializers.CharField(source='element.locator_value', read_only=True)

    class Meta:
        model = TestCaseStep
        fields = [
            'id', 'step_number', 'action_type', 'element', 'element_name', 'element_locator',
            'input_value', 'wait_time', 'assert_type', 'assert_value', 'description', 'created_at'
        ]
        ref_name = 'UiAutomationTestCaseStep'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user is not None:
            _scope_related_queryset(self, 'element', _accessible_elements_for_user(user))


class TestCaseSerializer(serializers.ModelSerializer):
    """测试用例序列化器"""
    steps = TestCaseStepSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = TestCase
        fields = [
            'id', 'name', 'description', 'project', 'project_name', 'status', 'priority',
            'created_by', 'created_by_name', 'created_at', 'updated_at', 'steps'
        ]
        read_only_fields = ['created_by']
        ref_name = 'UiAutomationTestCase'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user is not None:
            _scope_related_queryset(self, 'project', _accessible_ui_projects_for_user(user))

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class TestCaseExecutionSerializer(serializers.ModelSerializer):
    """测试用例执行记录序列化器"""
    test_case_name = serializers.CharField(source='test_case.name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    test_suite_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TestCaseExecution
        fields = [
            'id', 'test_case', 'test_case_name', 'project', 'project_name',
            'test_suite', 'test_suite_name', 'execution_source', 'status',
            'engine', 'browser', 'headless', 'execution_logs', 'error_message',
            'screenshots', 'execution_time', 'started_at', 'finished_at',
            'created_by', 'created_by_name', 'created_at'
        ]
        read_only_fields = ['created_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user is not None:
            _scope_related_queryset(self, 'project', _accessible_ui_projects_for_user(user))
            _scope_related_queryset(self, 'test_case', _accessible_test_cases_for_user(user))
            _scope_related_queryset(self, 'test_suite', _accessible_test_suites_for_user(user))

    def validate(self, attrs):
        project = attrs.get('project', getattr(self.instance, 'project', None))
        test_case = attrs.get('test_case', getattr(self.instance, 'test_case', None))
        test_suite = attrs.get('test_suite', getattr(self.instance, 'test_suite', None))
        if project and test_case and test_case.project_id != project.id:
            raise serializers.ValidationError({'test_case': 'Test case must belong to the selected project.'})
        if project and test_suite and test_suite.project_id != project.id:
            raise serializers.ValidationError({'test_suite': 'Test suite must belong to the selected project.'})
        return attrs

    def get_test_suite_name(self, obj) -> str | None:
        """获取测试套件名称"""
        return obj.test_suite.name if obj.test_suite else None
    
    def get_created_by_name(self, obj) -> str:
        """获取创建人姓名"""
        return obj.created_by.username if obj.created_by else '-'

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class TestCaseRunSerializer(serializers.Serializer):
    """测试用例运行序列化器"""
    test_case_id = serializers.IntegerField()
    project_id = serializers.IntegerField()
    browser = serializers.ChoiceField(choices=['chrome', 'firefox', 'safari'], default='chrome')

    def validate_test_case_id(self, value):
        try:
            _accessible_test_cases_for_user(_request_user(self)).get(id=value)
        except TestCase.DoesNotExist:
            raise serializers.ValidationError("测试用例不存在")
        return value

    def validate_project_id(self, value):
        _get_accessible_project_or_error(self, value)
        return value

    def validate(self, attrs):
        test_case = _accessible_test_cases_for_user(_request_user(self)).get(id=attrs['test_case_id'])
        if test_case.project_id != attrs['project_id']:
            raise serializers.ValidationError({'test_case_id': 'Test case must belong to the selected project.'})
        return attrs


class OperationRecordSerializer(serializers.ModelSerializer):
    """操作记录序列化器"""
    user_name = serializers.CharField(source='user.username', read_only=True)
    operation_type_display = serializers.CharField(source='get_operation_type_display', read_only=True)
    resource_type_display = serializers.CharField(source='get_resource_type_display', read_only=True)

    class Meta:
        model = OperationRecord
        fields = [
            'id', 'operation_type', 'operation_type_display', 'resource_type',
            'resource_type_display', 'resource_id', 'resource_name', 'description',
            'user', 'user_name', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


# ==================== 定时任务和通知相关序列化器 ====================

class UiScheduledTaskSerializer(serializers.ModelSerializer):
    """UI定时任务序列化器"""
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    test_suite_name = serializers.CharField(source='test_suite.name', read_only=True)
    task_type_display = serializers.CharField(source='get_task_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    trigger_type_display = serializers.CharField(source='get_trigger_type_display', read_only=True)
    notification_type_display = serializers.SerializerMethodField()

    class Meta:
        model = UiScheduledTask
        fields = [
            'id', 'name', 'description', 'task_type', 'task_type_display',
            'trigger_type', 'trigger_type_display', 'cron_expression',
            'interval_seconds', 'execute_at', 'project', 'project_name',
            'test_suite', 'test_suite_name', 'test_cases',
            'engine', 'browser', 'headless',
            'notify_on_success', 'notify_on_failure', 'notification_type', 'notification_type_display', 'notify_emails',
            'status', 'status_display',
            'last_run_time', 'next_run_time', 'total_runs',
            'successful_runs', 'failed_runs', 'last_result', 'error_message',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'created_by', 'last_run_time', 'next_run_time', 'total_runs',
            'successful_runs', 'failed_runs', 'last_result',
            'error_message', 'created_at', 'updated_at'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        if user is not None:
            _scope_related_queryset(self, 'project', _accessible_ui_projects_for_user(user))
            _scope_related_queryset(self, 'test_suite', _accessible_test_suites_for_user(user))

    def get_notification_type_display(self, obj) -> str:
        """获取通知类型显示"""
        if obj.notification_type:
            return obj.get_notification_type_display()
        return "-"

    def validate(self, attrs):
        """验证定时任务配置"""
        trigger_type = attrs.get('trigger_type', getattr(self.instance, 'trigger_type', None))

        if trigger_type == 'CRON':
            cron_expression = attrs.get('cron_expression', getattr(self.instance, 'cron_expression', None))
            if not cron_expression:
                raise serializers.ValidationError("Cron表达式不能为空")

        elif trigger_type == 'INTERVAL':
            interval_seconds = attrs.get('interval_seconds', getattr(self.instance, 'interval_seconds', None))
            if not interval_seconds:
                raise serializers.ValidationError("间隔秒数不能为空")
            if interval_seconds < 60:
                raise serializers.ValidationError("间隔秒数不能小于60秒")

        elif trigger_type == 'ONCE':
            execute_at = attrs.get('execute_at', getattr(self.instance, 'execute_at', None))
            if not execute_at:
                raise serializers.ValidationError("执行时间不能为空")
            if execute_at <= timezone.now():
                raise serializers.ValidationError("执行时间必须大于当前时间")

        # 验证任务类型配置
        task_type = attrs.get('task_type', getattr(self.instance, 'task_type', None))
        project = attrs.get('project', getattr(self.instance, 'project', None))
        test_suite = attrs.get('test_suite', getattr(self.instance, 'test_suite', None))

        if task_type == 'TEST_SUITE' and not test_suite:
            raise serializers.ValidationError("测试套件不能为空")
        if project and test_suite and test_suite.project_id != project.id:
            raise serializers.ValidationError({'test_suite': 'Test suite must belong to the selected project.'})

        if task_type == 'TEST_CASE':
            test_cases = attrs.get('test_cases', getattr(self.instance, 'test_cases', []))
            if not test_cases or len(test_cases) == 0:
                raise serializers.ValidationError("至少选择一个测试用例")
            try:
                test_case_ids = [int(case_id) for case_id in test_cases]
            except (TypeError, ValueError):
                raise serializers.ValidationError({'test_cases': 'Test case ids must be integers.'})
            allowed_cases = _accessible_test_cases_for_user(_request_user(self))
            if project:
                allowed_cases = allowed_cases.filter(project=project)
            found_ids = set(allowed_cases.filter(id__in=test_case_ids).values_list('id', flat=True))
            if found_ids != set(test_case_ids):
                raise serializers.ValidationError({'test_cases': 'One or more test cases are not accessible in the selected project.'})

        return attrs

    def create(self, validated_data):
        """创建定时任务"""
        validated_data['created_by'] = self.context['request'].user
        instance = super().create(validated_data)
        # 计算下次运行时间
        instance.next_run_time = instance.calculate_next_run()
        instance.save()

        # 创建对应的通知设置（如果启用了通知）
        if instance.notify_on_success or instance.notify_on_failure:
            from .models import UiTaskNotificationSetting
            from apps.core.models import UnifiedNotificationConfig

            # 确定通知类型（默认为webhook）
            notification_type = validated_data.get('notification_type', 'webhook')

            # 根据通知类型选择合适的通知配置
            notification_config = None
            if notification_type in ['webhook', 'both']:
                # 如果需要Webhook通知，优先选择Webhook配置
                notification_config = UnifiedNotificationConfig.objects.filter(
                    config_type__in=['webhook_wechat', 'webhook_feishu', 'webhook_dingtalk'],
                    is_active=True
                ).first()

            if not notification_config:
                # 如果没有找到webhook配置或者是邮件通知，使用默认配置
                notification_config = UnifiedNotificationConfig.objects.filter(
                    is_default=True,
                    is_active=True
                ).first()

            # 创建通知设置
            UiTaskNotificationSetting.objects.create(
                task=instance,
                notification_type=notification_type,
                is_enabled=True,
                notify_on_success=instance.notify_on_success,
                notify_on_failure=instance.notify_on_failure,
                notification_config=notification_config
            )

        return instance

    def update(self, instance, validated_data):
        """更新定时任务"""
        # 更新任务基本信息
        instance = super().update(instance, validated_data)

        # 重新计算下次运行时间
        instance.next_run_time = instance.calculate_next_run()
        instance.save()

        # 更新通知设置
        if instance.notify_on_success or instance.notify_on_failure:
            from .models import UiTaskNotificationSetting
            from apps.core.models import UnifiedNotificationConfig

            # 确定通知类型（默认为webhook）
            notification_type = validated_data.get('notification_type', 'webhook')

            # 根据通知类型选择合适的通知配置
            notification_config = None
            if notification_type in ['webhook', 'both']:
                # 如果需要Webhook通知，优先选择Webhook配置
                notification_config = UnifiedNotificationConfig.objects.filter(
                    config_type__in=['webhook_wechat', 'webhook_feishu', 'webhook_dingtalk'],
                    is_active=True
                ).first()

            if not notification_config:
                # 如果没有找到webhook配置或者是邮件通知，使用默认配置
                notification_config = UnifiedNotificationConfig.objects.filter(
                    is_default=True,
                    is_active=True
                ).first()

            # 获取或创建通知设置
            notification_setting, created = UiTaskNotificationSetting.objects.get_or_create(
                task=instance,
                defaults={
                    'notification_type': notification_type,
                    'is_enabled': True,
                    'notify_on_success': instance.notify_on_success,
                    'notify_on_failure': instance.notify_on_failure,
                    'notification_config': notification_config
                }
            )

            # 如果通知设置已存在，更新它
            if not created:
                notification_setting.notification_type = notification_type
                notification_setting.is_enabled = True
                notification_setting.notify_on_success = instance.notify_on_success
                notification_setting.notify_on_failure = instance.notify_on_failure
                notification_setting.notification_config = notification_config
                notification_setting.save()
        else:
            # 如果不需要通知，禁用通知设置
            from .models import UiTaskNotificationSetting
            UiTaskNotificationSetting.objects.filter(task=instance).update(is_enabled=False)

        return instance


class AICaseSerializer(serializers.ModelSerializer):
    project = UiProjectSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    project_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = AICase
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by')

    def validate_project_id(self, value):
        if value is not None:
            _get_accessible_project_or_error(self, value)
        return value

    def create(self, validated_data):
        project_id = validated_data.pop('project_id', None)
        if project_id is not None:
            validated_data['project'] = _get_accessible_project_or_error(self, project_id)
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        project_id = validated_data.pop('project_id', None)
        if project_id is not None:
            validated_data['project'] = _get_accessible_project_or_error(self, project_id)
        return super().update(instance, validated_data)


class WalletBrowserConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletBrowserConfig
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by')

    def validate(self, attrs):
        instance = self.instance or WalletBrowserConfig()
        for key, value in attrs.items():
            setattr(instance, key, value)

        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            if hasattr(exc, 'message_dict'):
                raise serializers.ValidationError(exc.message_dict)
            raise serializers.ValidationError(exc.messages)

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class AIExecutionRecordSerializer(serializers.ModelSerializer):
    project = UiProjectSerializer(read_only=True)
    ai_case = AICaseSerializer(read_only=True)
    executed_by = UserSerializer(read_only=True)
    project_id = serializers.IntegerField(write_only=True)
    ai_case_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    ai_case_name = serializers.CharField(source='ai_case.name', read_only=True)
    executed_by_name = serializers.CharField(source='executed_by.username', read_only=True)

    class Meta:
        model = AIExecutionRecord
        fields = [
            'id', 'project', 'project_id', 'project_name', 'ai_case', 'ai_case_id', 'ai_case_name', 'case_name',
            'task_description',
            'execution_mode', 'status', 'start_time', 'end_time', 'duration',
            'logs', 'steps_completed', 'planned_tasks', 'executed_by', 'executed_by_name',
            'gif_path', 'screenshots_sequence',
            'wallet_mode', 'wallet_provider', 'wallet_target_chain', 'wallet_session'
        ]
        read_only_fields = ('start_time', 'end_time', 'duration', 'executed_by', 'gif_path', 'screenshots_sequence')

    def validate_project_id(self, value):
        _get_accessible_project_or_error(self, value)
        return value

    def validate_ai_case_id(self, value):
        if value is not None:
            try:
                _accessible_ai_cases_for_user(_request_user(self)).get(id=value)
            except AICase.DoesNotExist:
                raise serializers.ValidationError("AI case does not exist or is not accessible.")
        return value

    def validate(self, attrs):
        project_id = attrs.get('project_id', getattr(self.instance, 'project_id', None))
        ai_case_id = attrs.get('ai_case_id')
        if project_id and ai_case_id:
            ai_case = _accessible_ai_cases_for_user(_request_user(self)).get(id=ai_case_id)
            if ai_case.project_id and ai_case.project_id != project_id:
                raise serializers.ValidationError({'ai_case_id': 'AI case must belong to the selected project.'})
        return attrs

    def create(self, validated_data):
        project_id = validated_data.pop('project_id')
        ai_case_id = validated_data.pop('ai_case_id', None)
        validated_data['project'] = _get_accessible_project_or_error(self, project_id)
        if ai_case_id is not None:
            validated_data['ai_case'] = _accessible_ai_cases_for_user(_request_user(self)).get(id=ai_case_id)
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['executed_by'] = request.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        project_id = validated_data.pop('project_id', None)
        ai_case_id = validated_data.pop('ai_case_id', None)
        if project_id is not None:
            validated_data['project'] = _get_accessible_project_or_error(self, project_id)
        if ai_case_id is not None:
            validated_data['ai_case'] = _accessible_ai_cases_for_user(_request_user(self)).get(id=ai_case_id)
        return super().update(instance, validated_data)



class UiNotificationLogSerializer(serializers.ModelSerializer):
    """UI通知日志序列化器"""
    recipient_names = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    retry_status = serializers.SerializerMethodField()
    task_type_display = serializers.SerializerMethodField()
    actual_notification_type_display = serializers.SerializerMethodField()

    class Meta:
        model = UiNotificationLog
        fields = [
            'id', 'task', 'task_name', 'notification_type',
            'notification_type_display', 'actual_notification_type_display', 'task_type_display',
            'sender_name', 'sender_email',
            'recipient_names', 'webhook_bot_info', 'notification_content',
            'status', 'status_display', 'error_message', 'response_info',
            'created_at', 'sent_at', 'retry_count', 'retry_status'
        ]
        read_only_fields = ['created_at', 'sent_at']

    def get_recipient_names(self, obj) -> str:
        """获取收件人姓名列表"""
        return obj.get_recipient_names()

    def get_retry_status(self, obj) -> str:
        """获取重试状态"""
        return obj.get_retry_status()

    def get_task_type_display(self, obj) -> str:
        """获取任务类型显示 - 使用保存的快照值"""
        if obj.task_type:
            # 使用保存的任务类型快照
            task_type_choices = dict(UiScheduledTask.TASK_TYPE_CHOICES)
            return task_type_choices.get(obj.task_type, obj.task_type)
        # 如果 task_type 为空，返回未记录，不要从 task 对象获取（避免显示修改后的值）
        return '未记录'

    def get_actual_notification_type_display(self, obj) -> str:
        """获取实际的通知类型显示 - 根据实际发送的通知来判断"""
        # 优先检查webhook_bot_info,如果存在则说明是webhook通知
        if obj.webhook_bot_info:
            bot_type = obj.webhook_bot_info.get('bot_type', '') or obj.webhook_bot_info.get('type', '')
            # 根据机器人类型返回友好名称
            type_map = {
                'wechat': '企微机器人',
                'feishu': '飞书机器人',
                'dingtalk': '钉钉机器人'
            }
            return type_map.get(bot_type, 'Webhook机器人')

        # 检查recipient_info,如果存在则说明是邮箱通知
        if obj.recipient_info:
            if isinstance(obj.recipient_info, list) and len(obj.recipient_info) > 0:
                return '邮箱通知'
            elif isinstance(obj.recipient_info, dict) and obj.recipient_info.get('email'):
                return '邮箱通知'

        # 如果都没有,回退到任务的notification_type
        if obj.task:
            notification_type = obj.task.notification_type
            type_map = {
                'email': '邮箱通知',
                'webhook': 'Webhook机器人',
                'both': '两种都发送'
            }
            return type_map.get(notification_type, notification_type)

        return '-'


class UiTaskNotificationSettingSerializer(serializers.ModelSerializer):
    """UI任务通知设置序列化器"""
    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    notification_config_name = serializers.CharField(source='notification_config.name', read_only=True)
    active_types = serializers.SerializerMethodField()
    webhook_bots_display = serializers.SerializerMethodField()

    class Meta:
        model = UiTaskNotificationSetting
        fields = [
            'id', 'task', 'notification_type', 'notification_type_display',
            'notification_config', 'notification_config_name', 'is_enabled',
            'notify_on_success', 'notify_on_failure', 'notify_on_timeout',
            'notify_on_error', 'custom_webhook_bots', 'webhook_bots_display', 'active_types',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'webhook_bots_display']
        extra_kwargs = {
            'custom_webhook_bots': {'write_only': True, 'required': False, 'allow_null': True},
        }

    def get_active_types(self, obj) -> str:
        """获取激活的通知类型"""
        types = obj.get_active_notification_types()
        type_names = []
        if 'email' in types:
            type_names.append('邮箱')
        if 'webhook' in types:
            type_names.append('Webhook机器人')
        return ', '.join(type_names) if type_names else "无"

    def _bot_display(self, bot, source):
        return {
            'type': bot.get('type'),
            'name': bot.get('name'),
            'webhook_url': redact_webhook_url(bot.get('webhook_url')),
            'has_secret': bool(bot.get('secret')),
            'enabled': bot.get('enabled'),
            'enable_ui_automation': bot.get('enable_ui_automation'),
            'enable_api_testing': bot.get('enable_api_testing'),
            'source': source,
        }

    def get_webhook_bots_display(self, obj) -> list:
        display_list = []

        notification_config = obj.get_notification_config() if hasattr(obj, 'get_notification_config') else None
        if notification_config:
            for bot in notification_config.get_webhook_bots():
                display_list.append(self._bot_display(bot, 'notification_config'))

        for bot_type, bot_config in (obj.custom_webhook_bots or {}).items():
            if not isinstance(bot_config, dict):
                continue
            display_list.append(self._bot_display({'type': bot_type, **bot_config}, 'custom'))

        return display_list

    def _without_masked_credentials(self, webhook_bots):
        if not isinstance(webhook_bots, dict):
            return webhook_bots

        cleaned_bots = deepcopy(webhook_bots)
        for bot_config in cleaned_bots.values():
            if not isinstance(bot_config, dict):
                continue
            for field in ('webhook_url', 'secret'):
                value = bot_config.get(field)
                if isinstance(value, str) and ('***' in value or not value.strip()):
                    bot_config.pop(field, None)
        return cleaned_bots

    def validate_custom_webhook_bots(self, value):
        try:
            return validate_notification_webhook_bots(self._without_masked_credentials(value))
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def _merge_custom_webhook_bots(self, instance, webhook_bots):
        if webhook_bots is None or not isinstance(webhook_bots, dict):
            return webhook_bots

        merged_bots = deepcopy(instance.custom_webhook_bots or {})
        for bot_type, bot_config in webhook_bots.items():
            if not isinstance(bot_config, dict):
                merged_bots[bot_type] = bot_config
                continue

            existing_config = dict(merged_bots.get(bot_type) or {})
            cleaned_config = self._without_masked_credentials({bot_type: bot_config}).get(bot_type, {})
            existing_config.update(cleaned_config)
            merged_bots[bot_type] = existing_config
        return merged_bots

    def update(self, instance, validated_data):
        if 'custom_webhook_bots' in validated_data:
            validated_data['custom_webhook_bots'] = self._merge_custom_webhook_bots(
                instance,
                validated_data['custom_webhook_bots'],
            )
        return super().update(instance, validated_data)
