"""DRF exception handling for domain errors."""

from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback

from library.services.exceptions import DomainError


def domain_exception_handler(exc, context):
    """Render :class:`DomainError` as a ``400`` with a stable body.

    ``{"error": "<human message>", "code": "<machine slug>"}`` - the message is
    what a person reads, the code is what a client branches on. Everything else
    falls through to DRF's default handler.
    """
    if isinstance(exc, DomainError):
        set_rollback()
        return Response({'error': exc.message, 'code': exc.code}, status=400)
    return exception_handler(exc, context)
