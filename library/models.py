"""Domain models for the library.

The loan state machine lives here: :class:`LoanStatus` names the three states a
loan can be in, :class:`LoanQuerySet` gives each state a queryable predicate, and
:mod:`library.services.loans` owns the transitions between them.

``Loan.is_returned`` stays the single persisted fact about a loan's lifecycle;
``OVERDUE`` is derived from ``due_date`` rather than denormalised into a column,
so there is no scheduled job whose only purpose is to keep a status column
truthful. The composite indexes below make the derived predicates cheap.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

# Number of days a book may be borrowed before it becomes overdue.
DEFAULT_LOAN_PERIOD_DAYS = 14


def _default_due_date():
    return timezone.localdate() + timedelta(days=DEFAULT_LOAN_PERIOD_DAYS)


class LoanStatus(models.TextChoices):
    """The three states a loan can occupy.

    ACTIVE   - open and not yet past ``due_date``.
    OVERDUE  - open and past ``due_date``; derived, never stored.
    RETURNED - closed; terminal.
    """

    ACTIVE = 'active', 'Active'
    OVERDUE = 'overdue', 'Overdue'
    RETURNED = 'returned', 'Returned'


class Author(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    biography = models.TextField(blank=True)

    class Meta:
        ordering = ['last_name', 'first_name', 'id']
        indexes = [
            models.Index(fields=['last_name', 'first_name'], name='author_name_idx'),
        ]

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


class Book(models.Model):
    GENRE_CHOICES = [
        ('fiction', 'Fiction'),
        ('nonfiction', 'Non-Fiction'),
        ('sci-fi', 'Sci-Fi'),
        ('biography', 'Biography'),
    ]

    title = models.CharField(max_length=200)
    author = models.ForeignKey(Author, related_name='books', on_delete=models.CASCADE)
    isbn = models.CharField(max_length=13, unique=True)
    genre = models.CharField(max_length=50, choices=GENRE_CHOICES)
    available_copies = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['title', 'id']
        indexes = [
            # The catalogue is ordered by title and paginated; without this the
            # database sorts the whole table for every page request.
            models.Index(fields=['title', 'id'], name='book_title_idx'),
        ]

    def __str__(self):
        return self.title


class Member(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    membership_date = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.user.username


class LoanQuerySet(models.QuerySet):
    """Every loan lookup the application performs, named once."""

    def with_related(self):
        """Join everything the serializers and notification templates read."""
        return self.select_related('book', 'book__author', 'member', 'member__user')

    def open(self):
        """Loans that have not been returned (``ACTIVE`` or ``OVERDUE``)."""
        return self.filter(is_returned=False)

    def returned(self):
        return self.filter(is_returned=True)

    def overdue(self, as_of=None):
        """Open loans whose due date is strictly in the past.

        Backed by ``loan_open_due_idx``; ordered by due date so the oldest
        debts are notified first and the scan is a forward index walk.
        """
        return (
            self.open()
            .filter(due_date__lt=as_of or timezone.localdate())
            .order_by('due_date', 'id')
        )

    def active(self, as_of=None):
        """Open loans that are not yet overdue."""
        return self.open().filter(due_date__gte=as_of or timezone.localdate())

    def for_member(self, member):
        return self.filter(member=member)

    def for_book(self, book):
        return self.filter(book=book)

    def oldest_first(self):
        return self.order_by('loan_date', 'id')


class Loan(models.Model):
    book = models.ForeignKey(Book, related_name='loans', on_delete=models.CASCADE)
    member = models.ForeignKey(Member, related_name='loans', on_delete=models.CASCADE)
    loan_date = models.DateField(auto_now_add=True)
    return_date = models.DateField(null=True, blank=True)
    is_returned = models.BooleanField(default=False)
    due_date = models.DateField(default=_default_due_date)

    objects = LoanQuerySet.as_manager()

    class Meta:
        ordering = ['-id']
        indexes = [
            # check_overdue_loans() scans exactly this predicate. Leading with
            # is_returned keeps the closed rows - the bulk of a mature table -
            # out of the range scan entirely.
            models.Index(fields=['is_returned', 'due_date'], name='loan_open_due_idx'),
            # "the member's oldest open loan for this book" (return_book).
            models.Index(fields=['book', 'is_returned', 'loan_date'], name='loan_book_open_idx'),
            # "everything this member currently holds".
            models.Index(fields=['member', 'is_returned'], name='loan_member_open_idx'),
        ]

    def __str__(self):
        return f'{self.book.title} loaned to {self.member.user.username}'

    def save(self, *args, **kwargs):
        if self.pk is None and self.due_date is None:
            base_date = self.loan_date or timezone.localdate()
            self.due_date = base_date + timedelta(days=DEFAULT_LOAN_PERIOD_DAYS)
        super().save(*args, **kwargs)

    def is_overdue(self, on_date=None):
        """True when the loan is still open and past its due date."""
        if self.is_returned or self.due_date is None:
            return False
        return self.due_date < (on_date or timezone.localdate())

    @property
    def status(self):
        """The loan's current :class:`LoanStatus`, derived from stored fields."""
        if self.is_returned:
            return LoanStatus.RETURNED
        if self.is_overdue():
            return LoanStatus.OVERDUE
        return LoanStatus.ACTIVE

    def days_overdue(self, on_date=None):
        """How many days late the loan is; ``0`` when it is not overdue."""
        if not self.is_overdue(on_date):
            return 0
        return ((on_date or timezone.localdate()) - self.due_date).days
