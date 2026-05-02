import logging

from django.conf import settings
from django.contrib.auth import login, logout
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .models import User
from .serializers import LoginSerializer, UserCreateSerializer, UserSerializer

logger = logging.getLogger(__name__)


class LoginRateThrottle(ScopedRateThrottle):
    scope = 'login'


def _set_refresh_cookie(response, refresh_token: str) -> None:
    """把 refresh token 写入 httpOnly cookie；前端永不直接持有。"""
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        refresh_token,
        httponly=True,
        secure=settings.JWT_REFRESH_COOKIE_SECURE,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        path=settings.JWT_REFRESH_COOKIE_PATH,
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
    )


def _clear_refresh_cookie(response) -> None:
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        path=settings.JWT_REFRESH_COOKIE_PATH,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
    )


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_current_user(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@method_decorator(csrf_exempt, name='dispatch')
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all().order_by('username')
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'register'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {'user': UserSerializer(user).data, 'token': token.key},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([LoginRateThrottle])
@csrf_exempt
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data['user']
    login(request, user)

    refresh = RefreshToken.for_user(user)
    response = Response({
        'user': UserSerializer(user).data,
        'access': str(refresh.access_token),
        # refresh 仍在 body 返回，便于尚未升级的旧客户端读取；
        # 同时写入 httpOnly cookie，新前端将以 cookie 为准。
        'refresh': str(refresh),
        'message': '登录成功',
    })
    _set_refresh_cookie(response, str(refresh))
    return response


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@csrf_exempt
def logout_view(request):
    """用户退出登录，将refresh token加入黑名单"""
    refresh_token = (
        request.data.get('refresh')
        or request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
    )
    if refresh_token:
        try:
            RefreshToken(refresh_token).blacklist()
        except Exception:
            logger.warning("blacklist refresh token failed", exc_info=True)

    try:
        request.user.auth_token.delete()
    except Token.DoesNotExist:
        pass
    except AttributeError:
        pass

    logout(request)
    response = Response({'message': '退出成功'})
    _clear_refresh_cookie(response)
    return response


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def profile_view(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


class CookieAwareTokenRefreshView(TokenRefreshView):
    """支持从 httpOnly cookie 读取 refresh token，并在轮转时写回新 cookie。"""

    def post(self, request, *args, **kwargs):
        if not request.data.get('refresh'):
            cookie_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
            if cookie_token:
                # DRF 的 request.data 是不可变的 QueryDict / dict；使用 _full_data 重写
                if hasattr(request.data, '_mutable'):
                    request.data._mutable = True  # type: ignore[attr-defined]
                    request.data['refresh'] = cookie_token
                    request.data._mutable = False  # type: ignore[attr-defined]
                else:
                    try:
                        request.data['refresh'] = cookie_token
                    except TypeError:
                        request._full_data = {**request.data, 'refresh': cookie_token}

        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and 'refresh' in response.data:
            _set_refresh_cookie(response, response.data['refresh'])
        return response


class UserListView(generics.ListCreateAPIView):
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]
