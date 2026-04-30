from django.urls import path
from . import views, project_list_views

urlpatterns = [
    path('', views.ProjectListCreateView.as_view(), name='project-list'),
    path('all/', views.get_all_projects, name='all-projects'),
    path('modules/catalog/', views.get_module_catalog, name='project-module-catalog'),
    path('star-assets/summary/', views.get_star_asset_summary, name='star-asset-summary'),
    path('star-assets/sync/', views.sync_star_assets, name='star-asset-sync'),
    path('star-assets/detail/<int:asset_id>/', views.get_star_asset_detail, name='star-asset-detail'),
    path('star-assets/detail/<int:asset_id>/adopt/', views.adopt_star_asset, name='star-asset-adopt'),
    path('star-assets/<str:module>/', views.get_star_asset_list, name='star-asset-list'),
    path('meta/', views.MetaProjectListCreateView.as_view(), name='meta-project-list'),
    path('meta/<int:pk>/', views.MetaProjectDetailView.as_view(), name='meta-project-detail'),
    path('<int:project_id>/meta/sync/', views.sync_meta_project_tree, name='meta-project-sync'),
    path('unified/', views.UnifiedProjectListView.as_view(), name='unified-project-list'),
    path('unified/<int:pk>/', views.UnifiedProjectDetailView.as_view(), name='unified-project-detail'),
    path('<int:project_id>/modules/', views.ProjectModuleBindingListCreateView.as_view(), name='project-module-list'),
    path('<int:project_id>/modules/<int:pk>/', views.ProjectModuleBindingDetailView.as_view(), name='project-module-detail'),
    path('<int:project_id>/permission-policies/', views.ProjectPermissionPolicyListCreateView.as_view(), name='project-permission-policy-list'),
    path('<int:project_id>/permission-policies/<int:pk>/', views.ProjectPermissionPolicyDetailView.as_view(), name='project-permission-policy-detail'),
    path('<int:pk>/', views.ProjectDetailView.as_view(), name='project-detail'),
    path('<int:project_id>/members/', views.get_project_members, name='get-project-members'),
    path('<int:project_id>/members/add/', views.add_project_member, name='add-member'),
    path('<int:project_id>/members/<int:member_id>/', views.remove_project_member, name='remove-member'),
    path('<int:project_id>/environments/', views.ProjectEnvironmentListCreateView.as_view(), name='environment-list'),
    path('list/', project_list_views.user_projects_list, name='user-projects-list'),
]
