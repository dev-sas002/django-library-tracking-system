from datetime import timedelta

from django.db.utils import IntegrityError
from django.test import TestCase
from django.utils import timezone

from library.models import DEFAULT_LOAN_PERIOD_DAYS, Author, Book, Loan
from library.tests.factories import make_author, make_book, make_loan, make_member, next_isbn


class AuthorModelTests(TestCase):
    def test_str_is_full_name(self):
        author = make_author(first_name='Iain', last_name='Banks')
        self.assertEqual(str(author), 'Iain Banks')

    def test_default_ordering_is_by_last_then_first_name(self):
        make_author(first_name='Zadie', last_name='Smith')
        make_author(first_name='Ada', last_name='Palmer')
        make_author(first_name='Bea', last_name='Palmer')
        self.assertEqual(
            [a.last_name + ',' + a.first_name for a in Author.objects.all()],
            ['Palmer,Ada', 'Palmer,Bea', 'Smith,Zadie'],
        )


class BookModelTests(TestCase):
    def test_str_is_title(self):
        self.assertEqual(str(make_book(title='Excession')), 'Excession')

    def test_isbn_is_unique(self):
        isbn = next_isbn()
        make_book(isbn=isbn)
        with self.assertRaises(IntegrityError):
            make_book(title='Duplicate', isbn=isbn)

    def test_default_ordering_is_by_title(self):
        make_book(title='Zoo')
        make_book(title='Anvil')
        self.assertEqual([b.title for b in Book.objects.all()], ['Anvil', 'Zoo'])


class LoanModelTests(TestCase):
    def test_due_date_defaults_to_loan_period(self):
        loan = Loan.objects.create(book=make_book(), member=make_member())
        self.assertEqual(
            loan.due_date,
            timezone.now().date() + timedelta(days=DEFAULT_LOAN_PERIOD_DAYS),
        )

    def test_save_fills_due_date_when_explicitly_none(self):
        """The save() override must not be a no-op: a None due_date gets backfilled."""
        loan = Loan(book=make_book(), member=make_member(), due_date=None)
        loan.save()
        loan.refresh_from_db()
        self.assertEqual(
            loan.due_date,
            timezone.now().date() + timedelta(days=DEFAULT_LOAN_PERIOD_DAYS),
        )

    def test_save_persists_the_row(self):
        loan = make_loan()
        self.assertIsNotNone(loan.pk)
        self.assertEqual(Loan.objects.count(), 1)

    def test_explicit_due_date_is_respected(self):
        due = timezone.now().date() + timedelta(days=3)
        loan = make_loan(due_in_days=3)
        self.assertEqual(loan.due_date, due)

    def test_is_overdue_true_when_past_due_and_open(self):
        loan = make_loan(due_in_days=-1)
        self.assertTrue(loan.is_overdue())

    def test_is_overdue_false_on_due_date_itself(self):
        loan = make_loan(due_in_days=0)
        self.assertFalse(loan.is_overdue())

    def test_is_overdue_false_when_returned(self):
        loan = make_loan(due_in_days=-5, is_returned=True)
        self.assertFalse(loan.is_overdue())

    def test_is_overdue_accepts_reference_date(self):
        loan = make_loan(due_in_days=5)
        self.assertFalse(loan.is_overdue())
        self.assertTrue(loan.is_overdue(on_date=timezone.now().date() + timedelta(days=6)))

    def test_str_mentions_book_and_member(self):
        member = make_member(username='ana')
        loan = make_loan(book=make_book(title='Inversions'), member=member)
        self.assertEqual(str(loan), 'Inversions loaned to ana')
