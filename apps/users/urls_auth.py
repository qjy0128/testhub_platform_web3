"""挂在 ``/api/auth/`` 下的路由：登录 / 注册 / 退出 / 令牌 / 用户清单。"""
from django.urls import path

from . import views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('token/refresh/', views.CookieAwareTokenRefreshView.as_view(), name='token_refresh'),
    # /api/auth/users/  ←  评审页面使用
    path('users/', views.UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
]
