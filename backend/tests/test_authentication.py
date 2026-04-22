from unittest import TestCase
from unittest.mock import patch

from django.db import OperationalError

from backend.authentication import (
    ResilientJWTAuthentication,
    is_transient_mysql_connection_error,
)


class TransientMysqlConnectionErrorTests(TestCase):
    def test_detects_mysql_operational_error_code(self):
        self.assertTrue(is_transient_mysql_connection_error(OperationalError(2003, 'connect failed')))

    def test_detects_winerror_10022_text(self):
        self.assertTrue(
            is_transient_mysql_connection_error(
                OperationalError("Can't connect to MySQL server on '127.0.0.1' ([WinError 10022] invalid)")
            )
        )

    def test_ignores_unrelated_operational_error(self):
        self.assertFalse(is_transient_mysql_connection_error(OperationalError('syntax error')))


class ResilientJwtAuthenticationTests(TestCase):
    @patch('backend.authentication.connections.close_all')
    @patch('backend.authentication.close_old_connections')
    @patch('rest_framework_simplejwt.authentication.JWTAuthentication.authenticate')
    def test_retries_once_after_transient_mysql_error(
        self,
        super_authenticate,
        close_old_connections,
        close_all,
    ):
        request = object()
        expected = ('user', 'token')
        super_authenticate.side_effect = [
            OperationalError(2003, "Can't connect to MySQL server on '127.0.0.1' ([WinError 10022] invalid)"),
            expected,
        ]

        result = ResilientJWTAuthentication().authenticate(request)

        self.assertEqual(result, expected)
        self.assertEqual(super_authenticate.call_count, 2)
        close_old_connections.assert_called_once_with()
        close_all.assert_called_once_with()

    @patch('backend.authentication.connections.close_all')
    @patch('backend.authentication.close_old_connections')
    @patch('rest_framework_simplejwt.authentication.JWTAuthentication.authenticate')
    def test_does_not_retry_non_transient_error(
        self,
        super_authenticate,
        close_old_connections,
        close_all,
    ):
        request = object()
        super_authenticate.side_effect = OperationalError('syntax error')

        with self.assertRaises(OperationalError):
            ResilientJWTAuthentication().authenticate(request)

        self.assertEqual(super_authenticate.call_count, 1)
        close_old_connections.assert_not_called()
        close_all.assert_not_called()
