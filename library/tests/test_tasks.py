from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from library.models import Loan
from library.tasks import check_overdue_loans, send_loan_notification
from library.tests.factories import make_book, make_loan, make_member


class SendLoanNotificationTests(TestCase):
    def test_sends_email_to_the_member(self):
        member = make_member(username='ana', email='ana@example.com')
        loan = make_loan(book=make_book(title='Consider Phlebas'), member=member)

        sent = send_loan_notification(loan.id)

        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['ana@example.com'])
        self.assertIn('Consider Phlebas', message.body)
        self.assertIn(str(loan.due_date), message.body)

    def test_missing_loan_is_handled_without_sending(self):
        with self.assertLogs('library.tasks', level='WARNING') as captured:
            self.assertEqual(send_loan_notification(999999), 0)
        self.assertIn('999999', captured.output[0])
        self.assertEqual(len(mail.outbox), 0)

    def test_member_without_email_is_skipped(self):
        member = make_member(username='noemail', email='')
        loan = make_loan(member=member)
        self.assertEqual(send_loan_notification(loan.id), 0)
        self.assertEqual(len(mail.outbox), 0)


class CheckOverdueLoansTests(TestCase):
    def test_notifies_only_loans_past_due(self):
        overdue = make_loan(
            book=make_book(title='Overdue Title'),
            member=make_member(username='late', email='late@example.com'),
            due_in_days=-3,
        )
        make_loan(  # due today - not yet overdue
            book=make_book(title='Due Today'),
            member=make_member(username='ontime', email='ontime@example.com'),
            due_in_days=0,
        )
        make_loan(  # future
            book=make_book(title='Later'),
            member=make_member(username='future', email='future@example.com'),
            due_in_days=5,
        )

        sent = check_overdue_loans()

        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['late@example.com'])
        self.assertIn('Overdue Title', mail.outbox[0].body)
        self.assertIn('3 day(s) ago', mail.outbox[0].body)
        self.assertEqual(overdue.due_date, timezone.now().date() - timedelta(days=3))

    def test_returned_loans_are_ignored(self):
        make_loan(
            member=make_member(username='returned', email='returned@example.com'),
            due_in_days=-10,
            is_returned=True,
        )
        self.assertEqual(check_overdue_loans(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_members_without_email_are_skipped(self):
        make_loan(member=make_member(username='blank', email=''), due_in_days=-1)
        self.assertEqual(check_overdue_loans(), 0)
        self.assertEqual(len(mail.outbox), 0)


class CheckOverdueLoansScalabilityTests(TestCase):
    """The nightly job must stay bounded as the overdue backlog grows."""

    def _make_overdue(self, count):
        for i in range(count):
            make_loan(
                book=make_book(title=f'Late {i}'),
                member=make_member(username=f'late{i}', email=f'late{i}@example.com'),
                due_in_days=-(i + 1),
            )

    def test_streams_the_backlog_in_batches(self):
        self._make_overdue(7)
        with mock.patch('library.tasks.notify', side_effect=lambda batch: len(batch)) as notify:
            self.assertEqual(check_overdue_loans(batch_size=3), 7)
        # 3 + 3 + 1: the batch never grows past batch_size, whatever the backlog.
        self.assertEqual([len(call.args[0]) for call in notify.call_args_list], [3, 3, 1])

    def test_scan_is_a_single_query_regardless_of_row_count(self):
        self._make_overdue(6)
        with self.assertNumQueries(1):
            check_overdue_loans(batch_size=100)

    def test_oldest_debts_are_notified_first(self):
        self._make_overdue(3)
        check_overdue_loans()
        due_dates = [loan.due_date for loan in Loan.objects.overdue()]
        self.assertEqual(due_dates, sorted(due_dates))
        self.assertEqual(mail.outbox[0].to, ['late2@example.com'])

    def test_as_of_lets_the_job_be_replayed_for_a_past_date(self):
        make_loan(
            member=make_member(username='future-late', email='fl@example.com'),
            due_in_days=5,
        )
        self.assertEqual(check_overdue_loans(), 0)
        self.assertEqual(check_overdue_loans(as_of=timezone.localdate() + timedelta(days=10)), 1)


class NotificationChannelIntegrationTests(TestCase):
    """Both tasks go through the channel seam, not through send_mail directly."""

    @override_settings(NOTIFICATION_CHANNELS=[])
    def test_loan_confirmation_is_dropped_when_no_channel_is_configured(self):
        loan = make_loan(member=make_member(username='x', email='x@example.com'))
        with self.assertLogs('library.notifications', level='WARNING'):
            self.assertEqual(send_loan_notification(loan.id), 0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(NOTIFICATION_CHANNELS=[])
    def test_overdue_reminders_are_dropped_when_no_channel_is_configured(self):
        make_loan(member=make_member(username='y', email='y@example.com'), due_in_days=-2)
        with self.assertLogs('library.notifications', level='WARNING'):
            self.assertEqual(check_overdue_loans(), 0)
        self.assertEqual(len(mail.outbox), 0)
