"""自定义 SMTP backend：支持显式开关来兼容证书有问题的内部 SMTP 网关。"""
from __future__ import annotations

import smtplib
import ssl

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend


def _build_ssl_context() -> ssl.SSLContext:
    # 默认使用 Python 标准库的安全默认值（验证证书 / 主机名）。
    # 若内部 SMTP 网关无法提供合法证书，可在 .env 显式设置
    # ``EMAIL_INSECURE_SSL=True`` 才会回退到不验证模式。
    if getattr(settings, 'EMAIL_INSECURE_SSL', False):
        return ssl._create_unverified_context()
    return ssl.create_default_context()


class CustomEmailBackend(EmailBackend):
    def open(self):
        if self.connection:
            return False

        ssl_context = _build_ssl_context()

        try:
            if self.use_ssl:
                self.connection = smtplib.SMTP_SSL(
                    self.host,
                    self.port,
                    context=ssl_context,
                    timeout=self.timeout,
                )
            else:
                self.connection = smtplib.SMTP(
                    self.host,
                    self.port,
                    timeout=self.timeout,
                )
                if self.use_tls:
                    self.connection.starttls(context=ssl_context)

            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except Exception:
            if not self.fail_silently:
                raise
            return False
