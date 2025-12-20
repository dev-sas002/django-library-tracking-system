"""Email delivery - the only channel shipped today."""

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from .base import NotificationChannel


class EmailChannel(NotificationChannel):
    """Send a batch over a single SMTP connection.

    ``get_connection()`` is opened once per batch and closed by
    ``send_messages``; the previous implementation paid a connection handshake
    per member, which dominated the runtime of the nightly overdue job.
    """

    name = 'email'

    def deliver(self, notifications):
        messages = [
            EmailMessage(
                subject=notification.subject,
                body=notification.body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[notification.recipient],
            )
            for notification in notifications
            if notification.recipient
        ]
        if not messages:
            return 0
        connection = get_connection()
        return connection.send_messages(messages) or 0
