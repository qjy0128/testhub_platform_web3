"""字段级对称加密。

用 ``cryptography.fernet.Fernet`` 把敏感字段在写入数据库时加密，读出时解密。
密钥从 settings ``FIELD_ENCRYPTION_KEY``（base64 urlsafe，44 字节）读取，
默认基于 ``SECRET_KEY`` 派生（开发期方便，生产环境必须显式配独立 key）。

设计说明：
- 旧的明文记录在解密失败时会按原值返回，便于灰度迁移。
- 新写入一律加密。
- 加密后值带前缀 ``enc:v1:``，作为版本标识，未来轮换密钥时可识别。
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)

_PREFIX = 'enc:v1:'


def _derive_key_from_secret() -> bytes:
    """SECRET_KEY → 32 字节 SHA-256 → base64 urlsafe (44 chars)，可作为 Fernet key。"""
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if key:
        if isinstance(key, str):
            key = key.encode('utf-8')
    else:
        key = _derive_key_from_secret()
    return Fernet(key)


class EncryptedTextField(models.TextField):
    """落库时透明加密的 TextField。"""

    description = 'Encrypted text field'

    def from_db_value(self, value, expression, connection):
        return self._decrypt(value)

    def to_python(self, value):
        return self._decrypt(value)

    def get_prep_value(self, value):
        if value is None or value == '':
            return value
        if isinstance(value, str) and value.startswith(_PREFIX):
            return value
        return _PREFIX + _get_fernet().encrypt(str(value).encode('utf-8')).decode('utf-8')

    @staticmethod
    def _decrypt(value):
        if value is None:
            return None
        if not isinstance(value, str) or not value.startswith(_PREFIX):
            return value  # 兼容旧明文
        token = value[len(_PREFIX):]
        try:
            return _get_fernet().decrypt(token.encode('utf-8')).decode('utf-8')
        except InvalidToken:
            logger.error('Failed to decrypt EncryptedTextField — wrong FIELD_ENCRYPTION_KEY?')
            return ''


class EncryptedCharField(models.CharField):
    """落库时透明加密的 CharField。注意 max_length 需大于密文长度。"""

    description = 'Encrypted char field'

    def from_db_value(self, value, expression, connection):
        return EncryptedTextField._decrypt(value)

    def to_python(self, value):
        return EncryptedTextField._decrypt(value)

    def get_prep_value(self, value):
        if value is None or value == '':
            return value
        if isinstance(value, str) and value.startswith(_PREFIX):
            return value
        return _PREFIX + _get_fernet().encrypt(str(value).encode('utf-8')).decode('utf-8')
