from django.conf import settings
from django.test import SimpleTestCase


class LoggingConfigTests(SimpleTestCase):
    def test_file_handlers_use_utf8_encoding(self):
        self.assertEqual(settings.LOGGING['handlers']['file'].get('encoding'), 'utf-8')
        self.assertEqual(settings.LOGGING['handlers']['error_file'].get('encoding'), 'utf-8')

    def test_named_loggers_with_explicit_handlers_do_not_propagate_to_root(self):
        self.assertFalse(settings.LOGGING['loggers']['django']['propagate'])
        self.assertFalse(settings.LOGGING['loggers']['apps.api_testing.views']['propagate'])
