"""Operational surfaces: the health probe and the seed command."""

from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from library.management.commands.seed_library import BOOKS
from library.models import Author, Book, Loan, Member


class HealthEndpointTests(APITestCase):
    def test_reports_ok_without_credentials(self):
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'status': 'ok', 'database': 'ok'})


class SeedLibraryCommandTests(TestCase):
    def seed(self, *args):
        out = StringIO()
        call_command('seed_library', *args, stdout=out)
        return out.getvalue()

    def test_creates_a_populated_catalogue(self):
        output = self.seed()

        self.assertEqual(Author.objects.count(), 5)
        self.assertEqual(Book.objects.count(), 10)
        self.assertEqual(Member.objects.count(), 5)
        self.assertEqual(Loan.objects.count(), 10)
        self.assertIn('Seeded', output)

    def test_seeds_a_mix_of_states_so_the_demo_is_not_empty(self):
        self.seed()

        self.assertGreater(Loan.objects.overdue().count(), 0)
        self.assertGreater(Loan.objects.active().count(), 0)
        self.assertGreater(Loan.objects.returned().count(), 0)

    def test_open_loans_are_reflected_in_available_copies(self):
        """Stock on the shelf plus stock on loan must equal the catalogued total."""
        self.seed()
        catalogued = {title: copies for title, _, _, _, copies in BOOKS}

        for book in Book.objects.all():
            on_loan = Loan.objects.for_book(book).open().count()
            self.assertEqual(book.available_copies + on_loan, catalogued[book.title])

    def test_is_idempotent(self):
        self.seed()
        counts = (Author.objects.count(), Book.objects.count(), Loan.objects.count())
        self.seed()
        self.assertEqual(
            (Author.objects.count(), Book.objects.count(), Loan.objects.count()), counts
        )

    def test_creates_the_demo_librarian_once(self):
        self.seed()
        self.seed()
        librarians = User.objects.filter(username='librarian')
        self.assertEqual(librarians.count(), 1)
        self.assertTrue(librarians.get().is_staff)

    def test_flush_loans_rebuilds_the_loan_table(self):
        self.seed()
        Loan.objects.all().delete()
        self.seed('--flush-loans')
        self.assertEqual(Loan.objects.count(), 10)
