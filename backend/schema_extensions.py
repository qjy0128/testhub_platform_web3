"""drf-spectacular schema extensions."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ResilientJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Expose custom JWT authenticator as standard Bearer auth in OpenAPI."""

    target_class = "backend.authentication.ResilientJWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
