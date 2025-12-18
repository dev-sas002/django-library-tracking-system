"""Liveness/readiness endpoint used by the container healthcheck."""

from django.db import connection
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


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
    except Exception:
        return Response({'status': 'unhealthy', 'database': 'unavailable'}, status=503)
    return Response({'status': 'ok', 'database': 'ok'})
