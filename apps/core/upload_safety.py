"""共享文件上传校验工具。

业务 serializer / model 应优先复用这里的 validator，
避免每个 app 重复定义大小、扩展名、MIME 列表。
"""
from __future__ import annotations

import os
from typing import Iterable

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

# 高风险扩展名：禁止上传以避免被静态服务器直接执行 / 触发 XSS。
DANGEROUS_EXTENSIONS = frozenset({
    '.exe', '.bat', '.cmd', '.com', '.msi', '.scr', '.dll', '.so', '.dylib',
    '.sh', '.ps1', '.vbs', '.js', '.jse', '.wsf', '.wsh',
    '.html', '.htm', '.svg', '.xhtml', '.xml',
    '.php', '.phtml', '.py', '.rb', '.jsp', '.jspx', '.asp', '.aspx',
})


@deconstructible
class FileSizeValidator:
    """限制单文件最大体积。"""
    message = 'File size exceeds the {limit_mb:.1f} MB limit.'
    code = 'file_too_large'

    def __init__(self, max_size: int | None = None):
        self.max_size = int(max_size or getattr(settings, 'MAX_UPLOAD_FILE_SIZE', 25 * 1024 * 1024))

    def __call__(self, value):
        size = getattr(value, 'size', None)
        if size is not None and size > self.max_size:
            raise ValidationError(
                self.message.format(limit_mb=self.max_size / (1024 * 1024)),
                code=self.code,
            )

    def __eq__(self, other):
        return isinstance(other, FileSizeValidator) and self.max_size == other.max_size


@deconstructible
class SafeExtensionValidator:
    """白名单扩展名，并显式拒绝高风险扩展名。"""
    message_disallowed = 'File extension "{ext}" is not allowed.'
    message_dangerous = 'File extension "{ext}" is blocked for security reasons.'
    code = 'unsafe_extension'

    def __init__(self, allowed_extensions: Iterable[str]):
        self.allowed = frozenset(ext.lower().lstrip('.') for ext in allowed_extensions)

    def __call__(self, value):
        name = getattr(value, 'name', '') or ''
        ext = os.path.splitext(name)[1].lower()
        if ext in DANGEROUS_EXTENSIONS:
            raise ValidationError(self.message_dangerous.format(ext=ext), code=self.code)
        if not ext or ext.lstrip('.') not in self.allowed:
            raise ValidationError(self.message_disallowed.format(ext=ext or '(none)'), code=self.code)

    def __eq__(self, other):
        return isinstance(other, SafeExtensionValidator) and self.allowed == other.allowed


# 常用预设
DOCUMENT_EXTENSIONS = ['pdf', 'doc', 'docx', 'txt', 'md', 'csv', 'xls', 'xlsx']
IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']
ATTACHMENT_EXTENSIONS = DOCUMENT_EXTENSIONS + IMAGE_EXTENSIONS + ['zip', 'json', 'log']
