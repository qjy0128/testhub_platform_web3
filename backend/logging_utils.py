import locale
import logging


def coerce_text_for_stream(text, encoding=None):
    target_encoding = encoding or locale.getpreferredencoding(False) or 'utf-8'
    return str(text).encode(target_encoding, errors='backslashreplace').decode(
        target_encoding,
        errors='ignore',
    )


class SafeConsoleStreamHandler(logging.StreamHandler):
    """Avoid Windows console encode crashes while preserving file logs unchanged."""

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            safe_msg = coerce_text_for_stream(msg, getattr(stream, 'encoding', None))
            stream.write(safe_msg + self.terminator)
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)
