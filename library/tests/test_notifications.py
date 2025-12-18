"""The notification seam: a second channel must need no changes elsewhere."""

from django.core import mail
from django.test import TestCase, override_settings

from library.notifications import DEFAULT_CHANNELS, Notification, dispatch, get_channels
from library.notifications.base import NotificationChannel
from library.notifications.email import EmailChannel
from library.services.notifications import (
    LOAN_CONFIRMATION,
    OVERDUE_REMINDER,
    loan_confirmation,
    overdue_reminder,
)
from library.tests.factories import make_book, make_loan, make_member


class RecordingChannel(NotificationChannel):
    """A stand-in for a future SMS/push/webhook channel."""

    name = 'recording'
    batches = []

    def deliver(self, notifications):
        RecordingChannel.batches.append(list(notifications))
        return len(notifications)


RECORDING = 'library.tests.test_notifications.RecordingChannel'
EMAIL = 'library.notifications.email.EmailChannel'


def a_notification(recipient='reader@example.com'):
    return Notification(
        recipient=recipient, subject='Subject', body='Body', kind='test', context={}
    )


class ChannelRegistryTests(TestCase):
    def setUp(self):
        RecordingChannel.batches = []

    def test_email_is_the_default_channel(self):
        self.assertEqual(DEFAULT_CHANNELS, ('library.notifications.email.EmailChannel',))
        self.assertIsInstance(get_channels()[0], EmailChannel)

    @override_settings(NOTIFICATION_CHANNELS=[RECORDING])
    def test_a_new_channel_is_a_settings_change_only(self):
        self.assertEqual(dispatch([a_notification()]), 1)
        self.assertEqual(len(RecordingChannel.batches), 1)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(NOTIFICATION_CHANNELS=[EMAIL, RECORDING])
    def test_every_configured_channel_receives_the_batch(self):
        self.assertEqual(dispatch([a_notification(), a_notification('other@example.com')]), 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(len(RecordingChannel.batches[0]), 2)

    @override_settings(NOTIFICATION_CHANNELS=[RECORDING])
    def test_recipients_without_contact_details_are_dropped_once(self):
        self.assertEqual(dispatch([a_notification(recipient='')]), 0)
        self.assertEqual(RecordingChannel.batches, [])

    @override_settings(NOTIFICATION_CHANNELS=[RECORDING])
    def test_channels_receive_only_deliverable_notifications(self):
        self.assertEqual(dispatch([a_notification(), a_notification(recipient='')]), 1)
        self.assertEqual(len(RecordingChannel.batches[0]), 1)

    @override_settings(NOTIFICATION_CHANNELS=[])
    def test_no_configured_channels_is_logged_rather_than_raised(self):
        with self.assertLogs('library.notifications', level='WARNING') as captured:
            self.assertEqual(dispatch([a_notification()]), 0)
        self.assertIn('no notification channels configured', captured.output[0])

    def test_dispatching_nothing_does_nothing(self):
        self.assertEqual(dispatch([]), 0)


class EmailChannelTests(TestCase):
    def test_batch_is_sent_over_a_single_connection(self):
        notifications = [a_notification(f'reader{i}@example.com') for i in range(4)]
        self.assertEqual(EmailChannel().deliver(notifications), 4)
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(mail.outbox[0].from_email, 'admin@library.com')

    def test_empty_batch_opens_no_connection(self):
        self.assertEqual(EmailChannel().deliver([]), 0)
        self.assertEqual(len(mail.outbox), 0)


class MessageBuilderTests(TestCase):
    def test_loan_confirmation_carries_body_and_machine_readable_context(self):
        member = make_member(username='ana', email='ana@example.com')
        loan = make_loan(book=make_book(title='Excession'), member=member, due_in_days=14)

        notification = loan_confirmation(loan)

        self.assertEqual(notification.kind, LOAN_CONFIRMATION)
        self.assertEqual(notification.recipient, 'ana@example.com')
        self.assertIn('Excession', notification.body)
        self.assertEqual(notification.context['loan_id'], loan.pk)
        self.assertEqual(notification.context['due_date'], loan.due_date)

    def test_overdue_reminder_reports_how_late_the_loan_is(self):
        member = make_member(username='late', email='late@example.com')
        loan = make_loan(book=make_book(title='Kindred'), member=member, due_in_days=-5)

        notification = overdue_reminder(loan)

        self.assertEqual(notification.kind, OVERDUE_REMINDER)
        self.assertIn('5 day(s) ago', notification.body)
        self.assertEqual(notification.context['days_overdue'], 5)

    def test_member_without_an_email_produces_an_undeliverable_notification(self):
        loan = make_loan(member=make_member(username='blank', email=''))
        self.assertEqual(loan_confirmation(loan).recipient, '')
