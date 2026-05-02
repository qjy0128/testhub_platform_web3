# Backward-compat shim. The real implementation now lives in apps.core.email_backend
# so SMTP behavior isn't tied to the api_testing module.
from apps.core.email_backend import CustomEmailBackend

__all__ = ['CustomEmailBackend']
