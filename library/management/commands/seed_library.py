"""Populate the database with a small, realistic catalogue.

Idempotent: every object is keyed on a natural identifier, so running it twice
(which the container entrypoint does on every boot) changes nothing. The seed
deliberately includes overdue and returned loans so that ``check_overdue_loans``
and the ``status`` field have something to show on a first boot.
"""

import os
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from library.models import DEFAULT_LOAN_PERIOD_DAYS, Author, Book, Loan, Member

AUTHORS = [
    ('Ursula K.', 'Le Guin', 'American author of science fiction and fantasy.'),
    ('Iain M.', 'Banks', 'Scottish author, best known for the Culture series.'),
    ('Ann', 'Leckie', 'American science fiction and fantasy writer.'),
    ('Octavia E.', 'Butler', 'American science fiction author and MacArthur fellow.'),
    ('Mary', 'Roach', 'American author of popular science.'),
]

# (title, author last name, isbn, genre, copies)
BOOKS = [
    ('The Dispossessed', 'Le Guin', '9780061054884', 'sci-fi', 4),
    ('The Left Hand of Darkness', 'Le Guin', '9780441478125', 'sci-fi', 3),
    ('Consider Phlebas', 'Banks', '9780316005388', 'sci-fi', 2),
    ('Use of Weapons', 'Banks', '9780316030571', 'sci-fi', 2),
    ('Excession', 'Banks', '9780553575378', 'sci-fi', 1),
    ('Ancillary Justice', 'Leckie', '9780356502403', 'sci-fi', 3),
    ('Ancillary Sword', 'Leckie', '9780356502427', 'sci-fi', 2),
    ('Kindred', 'Butler', '9780807083697', 'fiction', 3),
    ('Parable of the Sower', 'Butler', '9781538732182', 'fiction', 2),
    ('Stiff', 'Roach', '9780393324822', 'nonfiction', 2),
]

# (username, first name, last name)
MEMBERS = [
    ('amara', 'Amara', 'Okafor'),
    ('bo', 'Bo', 'Lindqvist'),
    ('chen', 'Chen', 'Wei'),
    ('dalia', 'Dalia', 'Haddad'),
    ('evan', 'Evan', 'Murphy'),
]

# (member username, book title, days until due - negative means overdue, returned)
LOANS = [
    ('amara', 'The Dispossessed', 9, False),
    ('amara', 'Stiff', -4, False),
    ('bo', 'Consider Phlebas', 3, False),
    ('bo', 'Ancillary Justice', -11, False),
    ('chen', 'Kindred', 0, False),
    ('chen', 'Excession', -1, False),
    ('dalia', 'Use of Weapons', 13, False),
    ('dalia', 'Parable of the Sower', -6, True),
    ('evan', 'Ancillary Sword', 6, False),
    ('evan', 'The Left Hand of Darkness', -20, True),
]

DEFAULT_MEMBER_PASSWORD = 'library-demo'


class Command(BaseCommand):
    help = 'Create a demo catalogue, members and loans. Safe to run repeatedly.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush-loans',
            action='store_true',
            help='Delete existing loans first and re-seed them from scratch.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()

        authors = {}
        for first_name, last_name, biography in AUTHORS:
            author, _ = Author.objects.get_or_create(
                first_name=first_name,
                last_name=last_name,
                defaults={'biography': biography},
            )
            authors[last_name] = author

        books = {}
        for title, author_last_name, isbn, genre, copies in BOOKS:
            book, _ = Book.objects.get_or_create(
                isbn=isbn,
                defaults={
                    'title': title,
                    'author': authors[author_last_name],
                    'genre': genre,
                    'available_copies': copies,
                },
            )
            books[title] = book

        members = {}
        for username, first_name, last_name in MEMBERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@example.com',
                    'first_name': first_name,
                    'last_name': last_name,
                },
            )
            if created:
                user.set_password(os.getenv('SEED_MEMBER_PASSWORD', DEFAULT_MEMBER_PASSWORD))
                user.save(update_fields=['password'])
            member, _ = Member.objects.get_or_create(user=user)
            members[username] = member

        if options['flush_loans']:
            Loan.objects.all().delete()

        created_loans = 0
        for username, title, days_until_due, is_returned in LOANS:
            member = members[username]
            book = books[title]
            if Loan.objects.for_member(member).for_book(book).exists():
                continue
            due_date = today + timedelta(days=days_until_due)
            loan = Loan.objects.create(
                member=member,
                book=book,
                due_date=due_date,
                is_returned=is_returned,
                return_date=today - timedelta(days=1) if is_returned else None,
            )
            # loan_date is auto_now_add, so backdating it takes an UPDATE.
            Loan.objects.filter(pk=loan.pk).update(
                loan_date=due_date - timedelta(days=DEFAULT_LOAN_PERIOD_DAYS)
            )
            if not is_returned:
                Book.objects.filter(pk=book.pk, available_copies__gt=0).update(
                    available_copies=F('available_copies') - 1
                )
            created_loans += 1

        self._ensure_librarian()

        overdue = Loan.objects.overdue().count()
        self.stdout.write(
            self.style.SUCCESS(
                f'Seeded {Author.objects.count()} authors, {Book.objects.count()} books, '
                f'{Member.objects.count()} members, {Loan.objects.count()} loans '
                f'({created_loans} new, {overdue} currently overdue).'
            )
        )

    def _ensure_librarian(self):
        """Create the demo staff account the README's curl examples use."""
        username = os.getenv('LIBRARIAN_USERNAME', 'librarian')
        password = os.getenv('LIBRARIAN_PASSWORD', 'librarian')
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': f'{username}@example.com',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        if created:
            user.set_password(password)
            user.save(update_fields=['password'])
            self.stdout.write(
                self.style.WARNING(
                    f'Created superuser "{username}" with the default demo password. '
                    'Set LIBRARIAN_USERNAME / LIBRARIAN_PASSWORD before using this '
                    'anywhere real.'
                )
            )
