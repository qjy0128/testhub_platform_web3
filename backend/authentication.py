import logging

from django.db import OperationalError, close_old_connections, connections
from rest_framework_simplejwt.authentication import JWTAuthentication

logger = logging.getLogger(__name__)

MYSQL_TRANSIENT_ERROR_CODES = {2003, 2006, 2013}


def is_transient_mysql_connection_error(exc):
    if exc is None:
        return False

    args = getattr(exc, 'args', ()) or ()
    if args:
        first_arg = args[0]
        if isinstance(first_arg, int) and first_arg in MYSQL_TRANSIENT_ERROR_CODES:
            return True
        if isinstance(first_arg, tuple) and first_arg:
            nested_code = first_arg[0]
            if isinstance(nested_code, int) and nested_code in MYSQL_TRANSIENT_ERROR_CODES:
                return True

    error_text = str(exc).lower()
    return (
        'can\'t connect to mysql server' in error_text
        or 'mysql server has gone away' in error_text
        or 'lost connection to mysql server' in error_text
        or 'winerror 10022' in error_text
    )


class ResilientJWTAuthentication(JWTAuthentication):
    """Retry one time after transient MySQL connection failures during auth."""

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except OperationalError as exc:
            if not is_transient_mysql_connection_error(exc):
                raise

            logger.warning(
                "Transient MySQL connection error during JWT authentication; retrying once: %s",
                exc,
            )
            close_old_connections()
            connections.close_all()
            return super().authenticate(request)
