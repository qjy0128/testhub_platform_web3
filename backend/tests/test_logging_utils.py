import logging
from io import StringIO
from unittest import TestCase

from backend.logging_utils import SafeConsoleStreamHandler, coerce_text_for_stream


class FakeGbkStream(StringIO):
    encoding = 'gbk'


class LoggingUtilsTests(TestCase):
    def test_coerce_text_for_gbk_stream_replaces_emoji(self):
        coerced = coerce_text_for_stream('Task complete 🏁', encoding='gbk')

        self.assertIn(r'\U0001f3c1', coerced)
        self.assertNotIn('🏁', coerced)

    def test_safe_console_handler_writes_without_unicode_error(self):
        stream = FakeGbkStream()
        handler = SafeConsoleStreamHandler(stream=stream)
        handler.setFormatter(logging.Formatter('%(message)s'))
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='Summary 📊 done',
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        output = stream.getvalue()
        self.assertIn(r'\U0001f4ca', output)
        self.assertNotIn('📊', output)
