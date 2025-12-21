"""The loan rules, exercised without going through HTTP."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from library.models import Loan, LoanStatus
from library.services import exceptions
from library.services import loans as loan_service
from library.tests.factories import make_book, make_loan, make_member, set_loan_date


class ResolveMemberTests(TestCase):
    def test_returns_the_member(self):
        member = make_member(username='resolvable')
        self.assertEqual(loan_service.resolve_member(member.id), member)

    def test_missing_blank_unknown_and_junk_ids_all_raise_member_not_found(self):
        for value in (None, '', 999999, 'abc'):
            with self.subTest(value=value), self.assertRaises(exceptions.MemberNotFound):
                loan_service.resolve_member(value)


class ParseAdditionalDaysTests(TestCase):
    def test_accepts_int_and_numeric_string(self):
        self.assertEqual(loan_service.parse_additional_days(5), 5)
        self.assertEqual(loan_service.parse_additional_days('5'), 5)

    def test_missing_value_reports_a_distinct_code(self):
        with self.assertRaises(exceptions.InvalidExtension) as ctx:
            loan_service.parse_additional_days(None)
        self.assertEqual(ctx.exception.code, 'additional_days_required')

    def test_non_numeric_value_reports_a_distinct_code(self):
        with self.assertRaises(exceptions.InvalidExtension) as ctx:
            loan_service.parse_additional_days('lots')
        self.assertEqual(ctx.exception.code, 'additional_days_not_an_integer')

    def test_zero_and_negative_are_rejected(self):
        for value in (0, -1):
            with self.subTest(value=value), self.assertRaises(exceptions.InvalidExtension):
                loan_service.parse_additional_days(value)


class LoanBookTests(TestCase):
    def test_opens_a_loan_and_decrements_stock(self):
        book = make_book(available_copies=2)
        member = make_member()

        loan = loan_service.loan_book(book=book, member=member)

        book.refresh_from_db()
        self.assertEqual(book.available_copies, 1)
        self.assertEqual(loan.status, LoanStatus.ACTIVE)
        self.assertEqual(loan.due_date, timezone.localdate() + timedelta(days=14))

    def test_empty_shelf_raises_and_creates_nothing(self):
        book = make_book(available_copies=0)
        with self.assertRaises(exceptions.BookUnavailable):
            loan_service.loan_book(book=book, member=make_member())
        self.assertEqual(Loan.objects.count(), 0)


class ReserveCopyTests(TestCase):
    def test_decrements_available_copies(self):
        book = make_book(available_copies=3)
        loan_service.reserve_copy(book.id)
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 2)

    def test_raises_when_the_shelf_is_empty(self):
        book = make_book(available_copies=0)
        with self.assertRaises(exceptions.BookUnavailable):
            loan_service.reserve_copy(book.id)


class ReturnBookTests(TestCase):
    def test_closes_the_loan_and_restocks(self):
        book = make_book(available_copies=0)
        member = make_member()
        make_loan(book=book, member=member)

        loan = loan_service.return_book(book=book, member=member)

        book.refresh_from_db()
        self.assertEqual(book.available_copies, 1)
        self.assertTrue(loan.is_returned)
        self.assertEqual(loan.return_date, timezone.localdate())
        self.assertEqual(loan.status, LoanStatus.RETURNED)

    def test_closes_the_oldest_open_loan_first(self):
        book = make_book(available_copies=0)
        member = make_member()
        older = make_loan(book=book, member=member)
        newer = make_loan(book=book, member=member)
        set_loan_date(older, timezone.localdate() - timedelta(days=5))

        loan_service.return_book(book=book, member=member)

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertTrue(older.is_returned)
        self.assertFalse(newer.is_returned)

    def test_no_open_loan_raises(self):
        book = make_book()
        with self.assertRaises(exceptions.NoActiveLoan):
            loan_service.return_book(book=book, member=make_member())

    def test_an_overdue_loan_can_still_be_returned(self):
        book = make_book(available_copies=0)
        member = make_member()
        loan = make_loan(book=book, member=member, due_in_days=-9)
        self.assertEqual(loan.status, LoanStatus.OVERDUE)

        returned = loan_service.return_book(book=book, member=member)
        self.assertEqual(returned.status, LoanStatus.RETURNED)


class ExtendLoanTests(TestCase):
    def test_pushes_the_due_date_out(self):
        loan = make_loan(due_in_days=4)
        original = loan.due_date

        extended = loan_service.extend_loan(loan=loan, additional_days=6)

        self.assertEqual(extended.due_date, original + timedelta(days=6))
        loan.refresh_from_db()
        self.assertEqual(loan.due_date, original + timedelta(days=6))

    def test_returned_loan_raises_loan_already_returned(self):
        loan = make_loan(due_in_days=4, is_returned=True)
        with self.assertRaises(exceptions.LoanAlreadyReturned):
            loan_service.extend_loan(loan=loan, additional_days=2)

    def test_overdue_loan_raises_loan_overdue(self):
        loan = make_loan(due_in_days=-1)
        with self.assertRaises(exceptions.LoanOverdue):
            loan_service.extend_loan(loan=loan, additional_days=2)

    def test_validation_runs_before_the_state_check(self):
        """A returned loan with a junk payload reports the payload problem."""
        loan = make_loan(due_in_days=4, is_returned=True)
        with self.assertRaises(exceptions.InvalidExtension):
            loan_service.extend_loan(loan=loan, additional_days='lots')

    def test_due_date_is_untouched_when_the_extension_is_rejected(self):
        loan = make_loan(due_in_days=4)
        original = loan.due_date
        with self.assertRaises(exceptions.InvalidExtension):
            loan_service.extend_loan(loan=loan, additional_days=0)
        loan.refresh_from_db()
        self.assertEqual(loan.due_date, original)


class StateMachineTests(TestCase):
    def test_returned_is_terminal(self):
        self.assertEqual(loan_service.ALLOWED_TRANSITIONS[LoanStatus.RETURNED], frozenset())

    def test_every_status_has_a_declared_transition_set(self):
        self.assertEqual(set(loan_service.ALLOWED_TRANSITIONS), set(LoanStatus))

    def test_only_active_loans_may_be_extended(self):
        self.assertEqual(loan_service.EXTENDABLE_STATUSES, frozenset({LoanStatus.ACTIVE}))


class LoanQuerySetTests(TestCase):
    def setUp(self):
        self.active = make_loan(due_in_days=3)
        self.overdue = make_loan(due_in_days=-3)
        self.due_today = make_loan(due_in_days=0)
        self.returned = make_loan(due_in_days=-30, is_returned=True)

    def test_open_excludes_returned(self):
        self.assertCountEqual(Loan.objects.open(), [self.active, self.overdue, self.due_today])

    def test_overdue_excludes_due_today_and_returned(self):
        self.assertEqual(list(Loan.objects.overdue()), [self.overdue])

    def test_active_includes_due_today(self):
        self.assertCountEqual(Loan.objects.active(), [self.active, self.due_today])

    def test_returned_selects_only_closed_loans(self):
        self.assertEqual(list(Loan.objects.returned()), [self.returned])

    def test_overdue_accepts_a_reference_date(self):
        future = timezone.localdate() + timedelta(days=10)
        self.assertCountEqual(
            Loan.objects.overdue(as_of=future), [self.active, self.overdue, self.due_today]
        )

    def test_with_related_avoids_follow_up_queries(self):
        with self.assertNumQueries(1):
            for loan in Loan.objects.with_related():
                self.assertIn('loaned to', str(loan))
                self.assertTrue(loan.member.user.email)


class LoanStatusPropertyTests(TestCase):
    def test_status_and_days_overdue(self):
        self.assertEqual(make_loan(due_in_days=3).status, LoanStatus.ACTIVE)
        self.assertEqual(make_loan(due_in_days=0).status, LoanStatus.ACTIVE)
        self.assertEqual(make_loan(due_in_days=-2).status, LoanStatus.OVERDUE)
        self.assertEqual(make_loan(due_in_days=-2, is_returned=True).status, LoanStatus.RETURNED)

    def test_days_overdue_is_zero_for_loans_that_are_not_late(self):
        self.assertEqual(make_loan(due_in_days=3).days_overdue(), 0)
        self.assertEqual(make_loan(due_in_days=-4, is_returned=True).days_overdue(), 0)

    def test_days_overdue_counts_whole_days(self):
        self.assertEqual(make_loan(due_in_days=-4).days_overdue(), 4)
