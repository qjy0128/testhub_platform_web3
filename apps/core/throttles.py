"""共享节流类。

settings.py 的 ``DEFAULT_THROTTLE_RATES`` 里登记了 ``ai`` / ``wallet`` 等 scope，
但 DRF 不会自动挂；视图必须显式声明 ``throttle_classes`` 才会生效。
本模块把"按业务命名 throttle"做成可复用的子类，避免每处都写
``ScopedRateThrottle`` + ``throttle_scope = 'xxx'``。
"""
from rest_framework.throttling import ScopedRateThrottle


class AIRateThrottle(ScopedRateThrottle):
    """匹配 settings 里的 ``'ai': '20/min'``。挂在所有调用付费 AI 的端点上。"""

    scope = 'ai'


class WalletRateThrottle(ScopedRateThrottle):
    """匹配 settings 里的 ``'wallet': '30/min'``。"""

    scope = 'wallet'
