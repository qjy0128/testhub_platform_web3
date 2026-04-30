from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Count, Q
from .models import TestCaseReview, ReviewAssignment, TestCaseReviewComment, ReviewTemplate
from .serializers import (
    TestCaseReviewSerializer, TestCaseReviewCreateSerializer,
    ReviewAssignmentSerializer, TestCaseReviewCommentSerializer, 
    TestCaseReviewCommentCreateSerializer,
    ReviewTemplateSerializer, ReviewTemplateCreateSerializer
)
from apps.testcases.models import TestCase
from apps.users.models import User
from apps.projects.unified import accessible_projects_for_user


class TestCaseReviewViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return TestCaseReviewCreateSerializer
        return TestCaseReviewSerializer
    
    def get_queryset(self):
        accessible_projects = accessible_projects_for_user(self.request.user)
        queryset = TestCaseReview.objects.select_related('creator').prefetch_related(
            'projects', 'testcases', 'reviewers', 'comments', 'reviewassignment_set__reviewer'
        ).filter(projects__in=accessible_projects).distinct()
        
        # 过滤参数
        project_id = self.request.query_params.get('project', None)
        status_param = self.request.query_params.get('status', None)
        reviewer_id = self.request.query_params.get('reviewer', None)
        
        if project_id:
            queryset = queryset.filter(projects__id=project_id)
        if status_param:
            queryset = queryset.filter(status=status_param)
        if reviewer_id:
            queryset = queryset.filter(reviewers__id=reviewer_id)
            
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)
    
    @action(detail=True, methods=['post'])
    def assign_reviewers(self, request, pk=None):
        """分配评审人员"""
        review = self.get_object()
        reviewer_ids = request.data.get('reviewer_ids', [])
        
        for reviewer_id in reviewer_ids:
            try:
                reviewer = User.objects.get(id=reviewer_id)
                ReviewAssignment.objects.get_or_create(
                    review=review,
                    reviewer=reviewer,
                    defaults={'assigned_at': timezone.now()}
                )
            except User.DoesNotExist:
                continue
                
        return Response({'message': '评审人员分配成功'})
    
    @action(detail=True, methods=['post'])
    def submit_review(self, request, pk=None):
        """提交评审结果"""
        review = self.get_object()
        try:
            assignment = ReviewAssignment.objects.get(
                review=review, 
                reviewer=request.user
            )
            assignment.status = request.data.get('status', 'approved')
            assignment.comment = request.data.get('comment', '')
            assignment.checklist_results = request.data.get('checklist_results', {})
            assignment.reviewed_at = timezone.now()
            assignment.save()
            
            # 检查是否所有评审人都已完成评审
            pending_count = ReviewAssignment.objects.filter(
                review=review, 
                status='pending'
            ).count()
            
            if pending_count == 0:
                # 检查评审结果，如果所有人都通过则设为已通过
                approved_count = ReviewAssignment.objects.filter(
                    review=review, 
                    status='approved'
                ).count()
                total_count = ReviewAssignment.objects.filter(review=review).count()
                
                if approved_count == total_count:
                    review.status = 'approved'
                else:
                    review.status = 'rejected'
                    
                review.completed_at = timezone.now()
                review.save()
                
            return Response({'message': '评审提交成功'})
            
        except ReviewAssignment.DoesNotExist:
            return Response(
                {'error': '您未被分配为此评审的评审人'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    
    @action(detail=False, methods=['get'])
    def my_reviews(self, request):
        """获取我的评审任务"""
        reviews = self.get_queryset().filter(reviewers=request.user)
        
        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)
    @action(detail=False, methods=['get'], url_path='center')
    def center(self, request):
        queryset = self.get_queryset()
        now = timezone.now()
        open_statuses = ['pending', 'in_progress']
        status_counts = {
            item['status']: item['count']
            for item in queryset.values('status').annotate(count=Count('id')).order_by('status')
        }
        priority_counts = {
            item['priority']: item['count']
            for item in queryset.values('priority').annotate(count=Count('id')).order_by('priority')
        }
        assignment_qs = ReviewAssignment.objects.filter(review__in=queryset)
        my_assignment_qs = assignment_qs.filter(reviewer=request.user)
        overdue_qs = queryset.filter(status__in=open_statuses, deadline__lt=now)
        my_pending_qs = queryset.filter(
            reviewassignment__reviewer=request.user,
            reviewassignment__status='pending',
        ).distinct()
        active_reviews = queryset.filter(status__in=open_statuses).order_by('deadline', '-created_at')[:20]

        return Response({
            'summary': {
                'total': queryset.count(),
                'open': queryset.filter(status__in=open_statuses).count(),
                'pending': status_counts.get('pending', 0),
                'in_progress': status_counts.get('in_progress', 0),
                'approved': status_counts.get('approved', 0),
                'rejected': status_counts.get('rejected', 0),
                'overdue': overdue_qs.count(),
                'my_pending': my_pending_qs.count(),
                'assignments_pending': assignment_qs.filter(status='pending').count(),
                'assignments_completed': assignment_qs.exclude(status='pending').count(),
                'my_assignments_pending': my_assignment_qs.filter(status='pending').count(),
            },
            'status_counts': status_counts,
            'priority_counts': priority_counts,
            'overdue_reviews': TestCaseReviewSerializer(overdue_qs.order_by('deadline')[:10], many=True).data,
            'my_pending_reviews': TestCaseReviewSerializer(my_pending_qs.order_by('deadline', '-created_at')[:10], many=True).data,
            'active_reviews': TestCaseReviewSerializer(active_reviews, many=True).data,
        })


class TestCaseReviewCommentViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return TestCaseReviewCommentCreateSerializer
        return TestCaseReviewCommentSerializer
    
    def get_queryset(self):
        review_id = self.request.query_params.get('review', None)
        testcase_id = self.request.query_params.get('testcase', None)
        
        queryset = TestCaseReviewComment.objects.select_related('author', 'testcase', 'review')
        
        if review_id:
            queryset = queryset.filter(review_id=review_id)
        if testcase_id:
            queryset = queryset.filter(testcase_id=testcase_id)
            
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class ReviewTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ReviewTemplateCreateSerializer
        return ReviewTemplateSerializer
    
    def get_queryset(self):
        project_id = self.request.query_params.get('project', None)
        queryset = ReviewTemplate.objects.select_related('creator').prefetch_related('project', 'default_reviewers')
        
        if project_id:
            queryset = queryset.filter(project__id=project_id)
            
        return queryset.filter(is_active=True)
    
    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)
