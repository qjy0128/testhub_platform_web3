"""聚合视图：保留以兼容历史 import，但 backend.urls 已切换为分别引入
``urls_auth`` 与 ``urls_users``，把两个挂载点的语义彻底分开。
"""
from .urls_auth import urlpatterns as _auth_patterns
from .urls_users import urlpatterns as _users_patterns

# 注意：当 backend.urls 直接 include 本模块时（不应再使用），
# 会同时暴露 auth 与 users 两个集合，与历史行为一致。
urlpatterns = list(_auth_patterns) + list(_users_patterns)
