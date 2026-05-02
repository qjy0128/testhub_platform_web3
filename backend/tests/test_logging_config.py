from django.conf import settings
from django.test import SimpleTestCase


class LoggingConfigTests(SimpleTestCase):
    def test_file_handlers_use_utf8_encoding(self):
        self.assertEqual(settings.LOGGING['handlers']['file'].get('encoding'), 'utf-8')
        self.assertEqual(settings.LOGGING['handlers']['error_file'].get('encoding'), 'utf-8')

    def test_root_logger_has_handlers(self):
        """所有日志最终都要有 sink。root logger 必须挂上 file/error_file/console handler。"""
        root = settings.LOGGING['root']
        for handler in ('file', 'error_file', 'console'):
            self.assertIn(handler, root['handlers'])

    def test_named_loggers_propagate_to_root(self):
        """LOGGING 已收敛：命名 logger 不再各自配 handlers，统一通过 root 的 handlers 输出。

        这样可以保证修改 root handlers（例如生产接入 Sentry / Loki）就立即对全部
        logger 生效，无需逐个 logger 改。
        """
        loggers = settings.LOGGING.get('loggers', {})
        for name, cfg in loggers.items():
            handlers = cfg.get('handlers', [])
            propagate = cfg.get('propagate', True)
            if not handlers:
                self.assertTrue(
                    propagate,
                    f"logger '{name}' 没有自己的 handlers，必须 propagate=True 才能落到 root",
                )
