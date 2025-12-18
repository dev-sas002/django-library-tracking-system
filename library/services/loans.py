"""Loan lifecycle rules.

This module is the only place that knows what "loaning", "returning" and
"extending" mean. Views translate HTTP into arguments and results back into
JSON; Celery tasks translate schedules into calls. Neither re-implements a rule.

The state machine
-----------------

::

    (new) --loan_book--> ACTIVE --return_book--> RETURNED (terminal)
                           |  ^                    ^
                due date   |  | extend_loan        |
                  passes   v  |                    |
                        OVERDUE --return_book------+

``ACTIVE -> OVERDUE`` is the only transition no caller performs: it happens
because a date passes. ``extend_loan`` is a self-transition and is therefore
only legal from ``ACTIVE`` - extending a debt that is already late would let a
member escape the overdue process indefinitely.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from library.models import Book, Loan, LoanStatus, Member

from .exceptions import (
    BookUnavailable,
    InvalidDueDate,
    InvalidExtension,
    LoanAlreadyReturned,
    LoanOverdue,
    MemberNotFound,
    NoActiveLoan,
)

#: Which statuses each action may be applied to. Declarative so the rules can be
#: read - and tested - without following the control flow of each function.
ALLOWED_TRANSITIONS = {
    LoanStatus.ACTIVE: frozenset({LoanStatus.OVERDUE, LoanStatus.RETURNED}),
    LoanStatus.OVERDUE: frozenset({LoanStatus.RETURNED}),
    LoanStatus.RETURNED: frozenset(),
}

#: Statuses from which a loan may be extended.
EXTENDABLE_STATUSES = frozenset({LoanStatus.ACTIVE})

#: Upper bound on one extension. Beyond being a sane policy, it keeps
#: ``due_date + timedelta(days=n)`` clear of ``OverflowError``.
MAX_EXTENSION_DAYS = 365

#: How far ahead a new loan's due date may be set when the caller picks one.
MAX_LOAN_PERIOD_DAYS = 365


def resolve_member(member_id):
    """Return the :class:`~library.models.Member` for ``member_id``.

    Raises :class:`MemberNotFound` for missing, blank and non-numeric ids so
    that callers get one predictable failure rather than three.
    """
    if member_id in (None, ''):
        raise MemberNotFound()
    try:
        member = Member.objects.select_related('user').filter(pk=member_id).first()
    except (ValueError, TypeError):
        raise MemberNotFound() from None
    if member is None:
        raise MemberNotFound()
    return member


def parse_additional_days(raw_value):
    """Coerce the ``additional_days`` payload field to an integer in 1..MAX_EXTENSION_DAYS."""
    if raw_value is None or raw_value == '':
        raise InvalidExtension('additional_days is required.', code='additional_days_required')
    not_an_integer = InvalidExtension(
        'additional_days must be an integer.', code='additional_days_not_an_integer'
    )
    # JSON true is an int to Python and int(2.7) is 2; neither is a day count.
    if isinstance(raw_value, bool) or (isinstance(raw_value, float) and not raw_value.is_integer()):
        raise not_an_integer
    try:
        additional_days = int(raw_value)
    except (TypeError, ValueError, OverflowError):
        raise not_an_integer from None
    if not 1 <= additional_days <= MAX_EXTENSION_DAYS:
        raise InvalidExtension(f'additional_days must be between 1 and {MAX_EXTENSION_DAYS}.')
    return additional_days


def check_due_date(due_date, today=None):
    """Refuse a chosen due date that is already past or implausibly far out."""
    today = today or timezone.localdate()
    latest = today + timedelta(days=MAX_LOAN_PERIOD_DAYS)
    if not today <= due_date <= latest:
        raise InvalidDueDate(f'due_date must be between {today} and {latest}.')


@transaction.atomic
def loan_book(*, book, member, due_date=None):
    """Open a loan for ``member`` and take a copy of ``book`` off the shelf.

    The stock check and the decrement happen under a row lock, so two concurrent
    requests cannot both observe the last copy as available. Without a
    ``due_date`` the loan runs for ``DEFAULT_LOAN_PERIOD_DAYS``.
    """
    if due_date is not None:
        check_due_date(due_date)
    locked_book = Book.objects.select_for_update().get(pk=book.pk)
    if locked_book.available_copies < 1:
        raise BookUnavailable()

    loan = Loan.objects.create(book=locked_book, member=member, due_date=due_date)
    Book.objects.filter(pk=locked_book.pk).update(available_copies=F('available_copies') - 1)
    return loan


@transaction.atomic
def return_book(*, book, member):
    """Close ``member``'s oldest open loan for ``book`` and restock the copy.

    A member may hold several copies of one title, so the oldest open loan is
    closed first; ``.get()`` would raise ``MultipleObjectsReturned`` here.
    """
    loan = (
        Loan.objects.select_for_update()
        .for_book(book)
        .for_member(member)
        .open()
        .oldest_first()
        .first()
    )
    if loan is None:
        raise NoActiveLoan()
    return _close(loan)


@transaction.atomic
def return_loan(loan):
    """Close one specific loan and restock its copy."""
    locked = Loan.objects.select_for_update().get(pk=loan.pk)
    if locked.is_returned:
        raise LoanAlreadyReturned()
    return _close(locked)


@transaction.atomic
def delete_loan(loan):
    """Delete a loan record, putting the copy back first if it was still out."""
    locked = Loan.objects.select_for_update().get(pk=loan.pk)
    if not locked.is_returned:
        Book.objects.filter(pk=locked.book_id).update(available_copies=F('available_copies') + 1)
    locked.delete()


def _close(loan):
    loan.is_returned = True
    loan.return_date = timezone.localdate()
    loan.save(update_fields=['is_returned', 'return_date'])
    Book.objects.filter(pk=loan.book_id).update(available_copies=F('available_copies') + 1)
    return loan


def extend_loan(*, loan, additional_days):
    """Push ``loan``'s due date out by ``additional_days``.

    Only legal while the loan is ``ACTIVE``; the two illegal statuses get
    distinct errors so the caller can tell "already back on the shelf" from
    "too late to extend".
    """
    additional_days = parse_additional_days(additional_days)

    status = loan.status
    if status not in EXTENDABLE_STATUSES:
        if status is LoanStatus.RETURNED:
            raise LoanAlreadyReturned()
        raise LoanOverdue()

    loan.due_date = loan.due_date + timedelta(days=additional_days)
    loan.save(update_fields=['due_date'])
    return loan
