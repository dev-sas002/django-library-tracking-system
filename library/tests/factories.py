"""Small helpers shared by the library test modules."""

from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from library.models import Author, Book, Loan, Member


def make_author(first_name='Ursula', last_name='Le Guin', **kwargs):
    return Author.objects.create(first_name=first_name, last_name=last_name, **kwargs)


_counters = {'isbn': 0, 'user': 0}


def next_isbn():
    _counters['isbn'] += 1
    return f'978{_counters["isbn"]:010d}'


def next_username():
    _counters['user'] += 1
    return f'reader{_counters["user"]}'


def make_book(author=None, title='The Dispossessed', available_copies=1, **kwargs):
    kwargs.setdefault('isbn', next_isbn())
    kwargs.setdefault('genre', 'sci-fi')
    return Book.objects.create(
        author=author or make_author(),
        title=title,
        available_copies=available_copies,
        **kwargs,
    )


def make_member(username=None, email=None, **kwargs):
    username = username or next_username()
    email = f'{username}@example.com' if email is None else email
    user = User.objects.create_user(username=username, email=email, password='pw-for-tests')
    return Member.objects.create(user=user, **kwargs)


def make_loan(book=None, member=None, due_in_days=14, **kwargs):
    kwargs.setdefault('due_date', timezone.now().date() + timedelta(days=due_in_days))
    return Loan.objects.create(
        book=book or make_book(),
        member=member or make_member(),
        **kwargs,
    )


def set_loan_date(loan, value):
    """``loan_date`` is auto_now_add, so it can only be backdated with an UPDATE."""
    Loan.objects.filter(pk=loan.pk).update(loan_date=value)
    loan.refresh_from_db()
    return loan


class ApiTestCase(APITestCase):
    """API test base: authenticates a staff user and stubs the Celery dispatch."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username='librarian', email='librarian@example.com', password='pw-for-tests'
        )
        self.client.force_authenticate(user=self.staff)

        patcher = mock.patch('library.views.send_loan_notification.delay')
        self.mock_notify = patcher.start()
        self.addCleanup(patcher.stop)
