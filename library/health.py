"""Liveness/readiness endpoint used by the container healthcheck."""

import logging

from django.db import DatabaseError, connection
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Report whether the process can reach its database.

    Deliberately unauthenticated and cheap: Docker, a load balancer or an uptime
    probe calls it, none of which hold credentials.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except DatabaseError:
        logger.exception('health: database check failed')
        return Response({'status': 'unhealthy', 'database': 'unavailable'}, status=503)
    return Response({'status': 'ok', 'database': 'ok'})
