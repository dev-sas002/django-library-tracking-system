from datetime import timedelta

from django.utils import timezone
from rest_framework import status

from library.models import Loan, LoanStatus
from library.tests.factories import ApiTestCase, make_author, make_book, make_loan, make_member


class LoanEndpointTests(ApiTestCase):
    def test_create_loan_takes_a_copy_off_the_shelf(self):
        book = make_book(available_copies=3)
        member = make_member(username='api-borrower')
        response = self.client.post('/api/loans/', {'book_id': book.id, 'member_id': member.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 2)
        self.assertEqual(response.data['book']['available_copies'], 2)
        self.mock_notify.assert_called_once_with(response.data['id'])

    def test_create_loan_with_a_past_due_date_is_refused(self):
        book = make_book(available_copies=1)
        response = self.client.post(
            '/api/loans/',
            {'book_id': book.id, 'member_id': make_member().id, 'due_date': '2001-01-01'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid_due_date')
        self.assertEqual(Loan.objects.count(), 0)
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 1)

    def test_create_loan_rejected_when_out_of_stock(self):
        book = make_book(available_copies=0)
        member = make_member(username='api-borrower')
        response = self.client.post('/api/loans/', {'book_id': book.id, 'member_id': member.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Loan.objects.count(), 0)

    def test_detail_payload_exposes_nested_book_and_member(self):
        loan = make_loan()
        response = self.client.get(f'/api/loans/{loan.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['book']['id'], loan.book_id)
        self.assertEqual(response.data['member']['user']['username'], loan.member.user.username)
        self.assertIn('due_date', response.data)

    def test_list_avoids_per_row_lookups(self):
        author = make_author()
        for i in range(5):
            make_loan(
                book=make_book(author=author, title=f'B{i}'),
                member=make_member(username=f'm{i}', email=f'm{i}@example.com'),
            )
        with self.assertNumQueries(2):  # COUNT + one joined SELECT
            self.client.get('/api/loans/')


class ExtendDueDateTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.loan = make_loan(due_in_days=7)
        self.url = f'/api/loans/{self.loan.id}/extend_due_date/'

    def test_extends_by_requested_days(self):
        original = self.loan.due_date
        response = self.client.post(self.url, {'additional_days': 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.due_date, original + timedelta(days=5))
        self.assertEqual(response.data['due_date'], self.loan.due_date.isoformat())

    def test_accepts_numeric_string(self):
        original = self.loan.due_date
        response = self.client.post(self.url, {'additional_days': '3'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.due_date, original + timedelta(days=3))

    def test_missing_additional_days_is_400(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('additional_days', response.data['error'])

    def test_non_integer_additional_days_is_400(self):
        response = self.client.post(self.url, {'additional_days': 'lots'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_or_negative_days_is_400(self):
        for value in (0, -3):
            with self.subTest(value=value):
                response = self.client.post(self.url, {'additional_days': value})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.due_date, timezone.now().date() + timedelta(days=7))

    def test_huge_extension_is_400_not_500(self):
        response = self.client.post(self.url, {'additional_days': 3_000_000}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid_extension')

    def test_fractional_days_are_not_truncated(self):
        original = self.loan.due_date
        response = self.client.post(self.url, {'additional_days': 2.7}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.due_date, original)

    def test_returned_loan_cannot_be_extended(self):
        loan = make_loan(due_in_days=7, is_returned=True)
        response = self.client.post(
            f'/api/loans/{loan.id}/extend_due_date/', {'additional_days': 2}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_overdue_loan_cannot_be_extended(self):
        loan = make_loan(due_in_days=-1)
        response = self.client.post(
            f'/api/loans/{loan.id}/extend_due_date/', {'additional_days': 2}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_loan_due_today_can_still_be_extended(self):
        loan = make_loan(due_in_days=0)
        response = self.client.post(
            f'/api/loans/{loan.id}/extend_due_date/', {'additional_days': 2}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unknown_loan_is_404(self):
        response = self.client.post('/api/loans/999999/extend_due_date/', {'additional_days': 2})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_cannot_extend(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url, {'additional_days': 2})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class LoanErrorContractTests(ApiTestCase):
    """Domain errors are rendered by a single DRF exception handler."""

    def test_error_body_carries_a_human_message_and_a_machine_code(self):
        loan = make_loan(due_in_days=-1)
        response = self.client.post(
            f'/api/loans/{loan.id}/extend_due_date/', {'additional_days': 2}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Cannot extend an overdue loan.')
        self.assertEqual(response.data['code'], 'loan_overdue')

    def test_returned_and_overdue_loans_get_distinct_codes(self):
        returned = make_loan(due_in_days=4, is_returned=True)
        response = self.client.post(
            f'/api/loans/{returned.id}/extend_due_date/', {'additional_days': 2}
        )
        self.assertEqual(response.data['code'], 'loan_already_returned')

    def test_unknown_member_on_loan_action_has_a_code(self):
        book = make_book(available_copies=1)
        response = self.client.post(f'/api/books/{book.id}/loan/', {'member_id': 999999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'member_not_found')

    def test_drf_validation_errors_still_use_the_default_shape(self):
        response = self.client.post('/api/loans/', {'book_id': 999999, 'member_id': 999999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('book_id', response.data)


class LoanStatusFieldTests(ApiTestCase):
    def test_status_is_serialised_for_each_state(self):
        cases = {
            LoanStatus.ACTIVE: make_loan(due_in_days=5),
            LoanStatus.OVERDUE: make_loan(due_in_days=-5),
            LoanStatus.RETURNED: make_loan(due_in_days=-5, is_returned=True),
        }
        for expected, loan in cases.items():
            with self.subTest(status=expected):
                response = self.client.get(f'/api/loans/{loan.id}/')
                self.assertEqual(response.data['status'], expected.value)

    def test_status_is_read_only(self):
        loan = make_loan(due_in_days=5)
        response = self.client.patch(
            f'/api/loans/{loan.id}/', {'status': LoanStatus.RETURNED.value}
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        loan.refresh_from_db()
        self.assertFalse(loan.is_returned)


class LoanLifecycleEndpointTests(ApiTestCase):
    """The generic CRUD routes cannot sidestep the stock bookkeeping."""

    def setUp(self):
        super().setUp()
        self.book = make_book(available_copies=0)
        self.loan = make_loan(book=self.book)

    def test_patching_is_returned_is_not_allowed(self):
        response = self.client.patch(
            f'/api/loans/{self.loan.id}/', {'is_returned': True}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.loan.refresh_from_db()
        self.assertFalse(self.loan.is_returned)

    def test_put_cannot_move_a_loan_to_another_book(self):
        other = make_book(available_copies=0, title='Elsewhere')
        response = self.client.put(
            f'/api/loans/{self.loan.id}/',
            {'book_id': other.id, 'member_id': self.loan.member_id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.book_id, self.book.id)

    def test_return_closes_the_loan_and_restocks(self):
        response = self.client.post(f'/api/loans/{self.loan.id}/return/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], LoanStatus.RETURNED.value)
        self.assertEqual(response.data['return_date'], timezone.localdate().isoformat())
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)

    def test_second_return_is_refused_without_restocking_twice(self):
        self.client.post(f'/api/loans/{self.loan.id}/return/')
        response = self.client.post(f'/api/loans/{self.loan.id}/return/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'loan_already_returned')
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)

    def test_deleting_an_open_loan_puts_the_copy_back(self):
        response = self.client.delete(f'/api/loans/{self.loan.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Loan.objects.filter(pk=self.loan.id).exists())
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)

    def test_deleting_a_returned_loan_leaves_stock_alone(self):
        returned = make_loan(book=self.book, is_returned=True)
        self.client.delete(f'/api/loans/{returned.id}/')
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 0)

    def test_anonymous_cannot_return_or_delete(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.post(f'/api/loans/{self.loan.id}/return/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.delete(f'/api/loans/{self.loan.id}/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
