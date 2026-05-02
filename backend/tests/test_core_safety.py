"""apps.core 工具的关键路径回归测试。

覆盖：
- ``url_safety`` SSRF 防护
- ``upload_safety`` 文件大小 / 扩展名 / 危险扩展名 校验
- ``encrypted_fields`` 加密往返 + 兼容旧明文
- ``throttles`` 类的 scope 配置
"""
from __future__ import annotations

from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

# 这些测试都不接触 ORM；不需要 ``pytestmark = pytest.mark.django_db``。


# --------------------------------------------------------------------------- #
# SSRF
# --------------------------------------------------------------------------- #

class TestSSRFGuard:
    def test_rejects_loopback(self):
        from apps.core.url_safety import validate_outbound_http_url
        with pytest.raises(ValueError):
            validate_outbound_http_url('http://127.0.0.1:8000/x')

    def test_rejects_link_local(self):
        from apps.core.url_safety import validate_outbound_http_url
        with pytest.raises(ValueError):
            validate_outbound_http_url('http://169.254.169.254/latest/meta-data/')

    def test_rejects_non_http(self):
        from apps.core.url_safety import validate_outbound_http_url
        with pytest.raises(ValueError):
            validate_outbound_http_url('file:///etc/passwd')

    def test_accepts_public_url(self):
        from apps.core.url_safety import validate_outbound_http_url
        # 公网 URL 不应抛异常；不实际拨号
        assert validate_outbound_http_url('https://api.openai.com/v1') == 'https://api.openai.com/v1'

    @override_settings(ALLOW_INTERNAL_OUTBOUND_URLS=True)
    def test_opt_in_allows_loopback(self):
        from apps.core.url_safety import validate_outbound_http_url
        assert validate_outbound_http_url('http://127.0.0.1:9000/x').endswith('/x')


# --------------------------------------------------------------------------- #
# 上传校验
# --------------------------------------------------------------------------- #

def _fake_file(name='ok.pdf', size=1024):
    """构造一个 SimpleUploadedFile-like 占位对象。"""
    class _F:
        pass
    f = _F()
    f.name = name
    f.size = size
    return f


class TestUploadSafety:
    def test_size_validator_rejects_oversized(self):
        from apps.core.upload_safety import FileSizeValidator
        v = FileSizeValidator(max_size=1024)
        with pytest.raises(ValidationError):
            v(_fake_file(size=2048))

    def test_size_validator_passes(self):
        from apps.core.upload_safety import FileSizeValidator
        v = FileSizeValidator(max_size=1024)
        v(_fake_file(size=512))  # 不抛 = 通过

    def test_extension_validator_rejects_dangerous(self):
        from apps.core.upload_safety import (
            ATTACHMENT_EXTENSIONS,
            SafeExtensionValidator,
        )
        v = SafeExtensionValidator(ATTACHMENT_EXTENSIONS)
        with pytest.raises(ValidationError):
            v(_fake_file(name='evil.exe'))
        with pytest.raises(ValidationError):
            v(_fake_file(name='evil.html'))

    def test_extension_validator_rejects_unlisted(self):
        from apps.core.upload_safety import SafeExtensionValidator
        v = SafeExtensionValidator(['pdf', 'txt'])
        with pytest.raises(ValidationError):
            v(_fake_file(name='photo.png'))

    def test_extension_validator_accepts_listed(self):
        from apps.core.upload_safety import SafeExtensionValidator
        v = SafeExtensionValidator(['pdf', 'txt'])
        v(_fake_file(name='doc.PDF'))


# --------------------------------------------------------------------------- #
# 字段级加密
# --------------------------------------------------------------------------- #

class TestEncryptedField:
    def test_round_trip(self):
        from apps.core.encrypted_fields import EncryptedCharField, _PREFIX
        f = EncryptedCharField()
        plain = 'sk-this-is-a-secret-1234567890'
        ciphertext = f.get_prep_value(plain)
        assert ciphertext.startswith(_PREFIX)
        assert plain not in ciphertext  # 真正加密了，不是 base64 包装明文
        assert f.to_python(ciphertext) == plain

    def test_legacy_plaintext_passthrough(self):
        """旧记录是明文（无前缀），to_python 应原样返回，便于灰度迁移。"""
        from apps.core.encrypted_fields import EncryptedCharField
        f = EncryptedCharField()
        assert f.to_python('legacy_plain_value') == 'legacy_plain_value'

    def test_empty_unchanged(self):
        from apps.core.encrypted_fields import EncryptedCharField
        f = EncryptedCharField()
        assert f.get_prep_value('') == ''
        assert f.get_prep_value(None) is None

    def test_idempotent(self):
        """二次写入已加密值不应再加密一遍。"""
        from apps.core.encrypted_fields import EncryptedCharField
        f = EncryptedCharField()
        ct1 = f.get_prep_value('key1')
        ct2 = f.get_prep_value(ct1)
        assert ct1 == ct2


# --------------------------------------------------------------------------- #
# Throttles
# --------------------------------------------------------------------------- #

class TestThrottleScopes:
    def test_ai_scope(self):
        from apps.core.throttles import AIRateThrottle
        assert AIRateThrottle.scope == 'ai'

    def test_wallet_scope(self):
        from apps.core.throttles import WalletRateThrottle
        assert WalletRateThrottle.scope == 'wallet'

    def test_settings_define_rates(self):
        """settings 中必须存在对应的 throttle rate 配置。"""
        from django.conf import settings
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        assert 'ai' in rates
        assert 'wallet' in rates
        assert 'login' in rates
        assert 'register' in rates
