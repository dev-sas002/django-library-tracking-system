"""Celery adapters.

Like the views, these are thin: they resolve arguments to model instances, build
notifications, and hand them to the configured channels.
"""

import logging

from celery import shared_task
from django.conf import settings

from .models import Loan
from .services.notifications import loan_confirmation, notify, overdue_reminder

logger = logging.getLogger(__name__)

# Only the fields the templates and the status derivation actually read. Keeps
# each streamed chunk small when the overdue backlog is large.
_OVERDUE_FIELDS = (
    'due_date',
    'is_returned',
    'book__title',
    'member__user__username',
    'member__user__email',
)


@shared_task
def send_loan_notification(loan_id):
    """Notify the member that a loan was opened. Returns the number sent."""
    loan = Loan.objects.with_related().filter(pk=loan_id).first()
    if loan is None:
        logger.warning('send_loan_notification: loan %s no longer exists', loan_id)
        return 0
    return notify([loan_confirmation(loan)])


@shared_task
def check_overdue_loans(as_of=None, batch_size=None):
    """Notify every member holding a loan that is past its due date.

    Streamed, never materialised. The queryset is walked with ``.iterator()`` and
    notifications are flushed to the channels every ``batch_size`` rows, so peak
    memory is bounded by the batch rather than by the size of the backlog - a
    table with 100k overdue loans costs the same resident memory as one with 100.
    The scan itself is served by the ``loan_open_due_idx`` index on
    ``(is_returned, due_date)``.

    Returns the number of notifications sent.
    """
    batch_size = batch_size or getattr(settings, 'OVERDUE_NOTIFICATION_BATCH_SIZE', 500)
    overdue = (
        Loan.objects.overdue(as_of).select_related('book', 'member__user').only(*_OVERDUE_FIELDS)
    )

    sent = 0
    batch = []
    for loan in overdue.iterator(chunk_size=batch_size):
        batch.append(overdue_reminder(loan, as_of))
        if len(batch) >= batch_size:
            sent += notify(batch)
            batch = []

    if batch:
        sent += notify(batch)

    logger.info('check_overdue_loans: sent %d reminder(s)', sent)
    return sent
