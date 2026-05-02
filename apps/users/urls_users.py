"""挂在 ``/api/users/`` 下的路由：当前用户信息 / 用户管理。"""
from django.urls import path

from . import views

urlpatterns = [
    path('me/', views.get_current_user, name='users_me'),
    # /api/users/users/  ←  ExecutionListView 在用
    path('users/', views.UserListView.as_view(), name='users_user-list'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='users_user-detail'),
]
