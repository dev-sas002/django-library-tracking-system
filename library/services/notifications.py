"""Turning loans into notifications.

Message wording lives here rather than in the tasks so that the Celery layer
stays a thin adapter, and rather than in ``library.notifications`` so that the
channel seam knows nothing about loans.
"""

from library.notifications import Notification, dispatch

LOAN_CONFIRMATION = 'loan_confirmation'
OVERDUE_REMINDER = 'overdue_reminder'


def loan_confirmation(loan):
    """Confirmation sent when a loan is opened."""
    user = loan.member.user
    return Notification(
        recipient=user.email,
        subject='Book Loaned Successfully',
        body=(
            f'Hello {user.username},\n\n'
            f'You have successfully loaned "{loan.book.title}".\n'
            f'Please return it by {loan.due_date}.'
        ),
        kind=LOAN_CONFIRMATION,
        context={
            'loan_id': loan.pk,
            'book_title': loan.book.title,
            'due_date': loan.due_date,
            'username': user.username,
        },
    )


def overdue_reminder(loan, as_of=None):
    """Reminder sent for a loan that is past its due date."""
    user = loan.member.user
    days_overdue = loan.days_overdue(as_of)
    return Notification(
        recipient=user.email,
        subject='Overdue Book Loan',
        body=(
            f'Hello {user.username},\n\n'
            f'"{loan.book.title}" was due on {loan.due_date} '
            f'({days_overdue} day(s) ago). Please return it.'
        ),
        kind=OVERDUE_REMINDER,
        context={
            'loan_id': loan.pk,
            'book_title': loan.book.title,
            'due_date': loan.due_date,
            'days_overdue': days_overdue,
            'username': user.username,
        },
    )


def notify(notifications):
    """Hand notifications to the configured channels; return the number sent."""
    return dispatch(notifications)
