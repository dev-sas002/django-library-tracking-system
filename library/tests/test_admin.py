"""The admin goes through the loan service, so stock stays truthful there too."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from library.models import Loan
from library.tests.factories import make_book, make_loan, make_member


class LoanAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser('desk', 'desk@example.com', 'pw-for-tests')
        self.client.force_login(self.admin_user)
        self.changelist = reverse('admin:library_loan_changelist')

    def test_changelist_shows_a_labelled_status_badge(self):
        make_loan(due_in_days=-2)
        response = self.client.get(self.changelist)
        self.assertContains(response, 'loan-status--overdue')
        self.assertContains(response, '>Overdue</span>')
        self.assertContains(response, 'Library Desk')

    def test_status_filter_uses_the_derived_state(self):
        overdue = make_loan(due_in_days=-2)
        active = make_loan(due_in_days=5)
        returned = make_loan(due_in_days=-9, is_returned=True)
        cases = {'overdue': overdue, 'active': active, 'returned': returned}
        for value, expected in cases.items():
            with self.subTest(status=value):
                response = self.client.get(self.changelist, {'status': value})
                self.assertEqual(list(response.context['cl'].queryset), [expected])

    def test_adding_a_loan_takes_a_copy_off_the_shelf(self):
        book = make_book(available_copies=2)
        member = make_member()
        due = timezone.localdate() + timedelta(days=10)
        response = self.client.post(
            reverse('admin:library_loan_add'),
            {'book': book.id, 'member': member.id, 'due_date': due.isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        loan = Loan.objects.get()
        self.assertEqual(loan.due_date, due)
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 1)

    def test_adding_a_loan_for_an_empty_shelf_is_a_form_error(self):
        book = make_book(available_copies=0)
        response = self.client.post(
            reverse('admin:library_loan_add'),
            {
                'book': book.id,
                'member': make_member().id,
                'due_date': timezone.localdate().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No copies of this book are on the shelf.')
        self.assertEqual(Loan.objects.count(), 0)

    def test_past_due_date_is_a_form_error(self):
        response = self.client.post(
            reverse('admin:library_loan_add'),
            {
                'book': make_book().id,
                'member': make_member().id,
                'due_date': (timezone.localdate() - timedelta(days=1)).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'due_date must be between')
        self.assertEqual(Loan.objects.count(), 0)

    def test_lifecycle_fields_cannot_be_edited(self):
        loan = make_loan()
        response = self.client.get(reverse('admin:library_loan_change', args=[loan.id]))
        form_fields = response.context['adminform'].form.fields
        self.assertNotIn('is_returned', form_fields)
        self.assertNotIn('book', form_fields)
        self.assertIn('due_date', form_fields)

    def test_mark_returned_action_restocks_open_loans_only(self):
        book = make_book(available_copies=0)
        open_loan = make_loan(book=book)
        closed = make_loan(book=book, is_returned=True)
        response = self.client.post(
            self.changelist,
            {'action': 'mark_returned', '_selected_action': [open_loan.id, closed.id]},
            follow=True,
        )
        self.assertContains(response, 'Returned 1 loan(s).')
        self.assertContains(response, 'Skipped 1 loan(s)')
        open_loan.refresh_from_db()
        self.assertTrue(open_loan.is_returned)
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 1)

    def test_bulk_delete_restocks_open_loans(self):
        book = make_book(available_copies=0)
        loans = [make_loan(book=book), make_loan(book=book), make_loan(book=book, is_returned=True)]
        self.client.post(
            self.changelist,
            {
                'action': 'delete_selected',
                '_selected_action': [loan.id for loan in loans],
                'post': 'yes',
            },
        )
        self.assertEqual(Loan.objects.count(), 0)
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 2)


class BrowsableApiBrandingTests(TestCase):
    def test_api_root_uses_the_library_desk_template(self):
        response = self.client.get('/api/', HTTP_ACCEPT='text/html')
        self.assertContains(response, 'Library Desk')
        self.assertContains(response, 'library/desk-api.css')
