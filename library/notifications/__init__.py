"""Notification dispatch.

Adding a channel is three steps and touches nothing that already works:

1. subclass :class:`~library.notifications.base.NotificationChannel`,
2. implement ``deliver(notifications)``,
3. add its dotted path to ``settings.NOTIFICATION_CHANNELS``.

Callers build :class:`~library.notifications.base.Notification` objects and hand
them to :func:`dispatch`. They never import a channel.
"""

import logging

from django.conf import settings
from django.utils.module_loading import import_string

from .base import Notification, NotificationChannel

logger = logging.getLogger(__name__)

DEFAULT_CHANNELS = ('library.notifications.email.EmailChannel',)

__all__ = ['DEFAULT_CHANNELS', 'Notification', 'NotificationChannel', 'dispatch', 'get_channels']


def get_channels():
    """Instantiate the configured channels.

    Deliberately not cached: instantiation is trivial, and a cache would make
    ``override_settings(NOTIFICATION_CHANNELS=...)`` silently ineffective in
    tests and in a running process reading a reloaded config.
    """
    paths = getattr(settings, 'NOTIFICATION_CHANNELS', DEFAULT_CHANNELS)
    return [import_string(path)() for path in paths]


def dispatch(notifications):
    """Deliver ``notifications`` through every configured channel.

    Returns the number of *deliverable* notifications - those with a recipient.
    Notifications for members who have no contact details are dropped here, once,
    instead of in each caller.
    """
    deliverable = [notification for notification in notifications if notification.recipient]
    if not deliverable:
        return 0

    channels = get_channels()
    if not channels:
        logger.warning(
            'dispatch: no notification channels configured; dropping %d message(s)',
            len(deliverable),
        )
        return 0

    for channel in channels:
        channel.deliver(deliverable)
    return len(deliverable)
