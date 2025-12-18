from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from library.models import Book, Loan
from library.tests.factories import (
    ApiTestCase,
    make_author,
    make_book,
    make_loan,
    make_member,
    next_isbn,
    set_loan_date,
)


class BookEndpointTests(ApiTestCase):
    def test_list_is_paginated(self):
        author = make_author()
        for i in range(12):
            make_book(author=author, title=f'Book {i:02d}')
        response = self.client.get('/api/books/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 12)
        self.assertEqual(len(response.data['results']), 10)
        self.assertIsNotNone(response.data['next'])

    def test_create_book_with_author_id(self):
        author = make_author()
        response = self.client.post(
            '/api/books/',
            {
                'title': 'Use of Weapons',
                'isbn': next_isbn(),
                'genre': 'sci-fi',
                'author_id': author.id,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['author']['id'], author.id)

    def test_list_does_not_issue_a_query_per_author(self):
        for i in range(5):
            make_book(author=make_author(last_name=f'Author{i}'), title=f'T{i}')
        with self.assertNumQueries(2):  # COUNT + one joined SELECT
            self.client.get('/api/books/')


class BookLoanActionTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.book = make_book(available_copies=2)
        self.member = make_member(username='borrower')

    def test_loan_creates_loan_and_decrements_stock(self):
        response = self.client.post(
            f'/api/books/{self.book.id}/loan/', {'member_id': self.member.id}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)
        loan = Loan.objects.get(pk=response.data['loan_id'])
        self.assertFalse(loan.is_returned)
        self.assertEqual(loan.due_date, timezone.now().date() + timedelta(days=14))
        self.mock_notify.assert_called_once_with(loan.id)

    def test_loan_rejected_when_no_copies(self):
        book = make_book(available_copies=0, title='Sold Out')
        response = self.client.post(f'/api/books/{book.id}/loan/', {'member_id': self.member.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Loan.objects.count(), 0)
        self.mock_notify.assert_not_called()

    def test_loan_rejected_for_unknown_member(self):
        response = self.client.post(f'/api/books/{self.book.id}/loan/', {'member_id': 999999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 2)

    def test_loan_rejected_when_member_id_missing(self):
        response = self.client.post(f'/api/books/{self.book.id}/loan/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_loan_rejected_for_non_numeric_member_id(self):
        response = self.client.post(f'/api/books/{self.book.id}/loan/', {'member_id': 'abc'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_loan_on_unknown_book_is_404(self):
        response = self.client.post('/api/books/999999/loan/', {'member_id': self.member.id})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BookReturnActionTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.book = make_book(available_copies=0)
        self.member = make_member(username='borrower')
        self.loan = make_loan(book=self.book, member=self.member)

    def test_return_marks_loan_returned_and_restocks(self):
        response = self.client.post(
            f'/api/books/{self.book.id}/return_book/', {'member_id': self.member.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.loan.refresh_from_db()
        self.book.refresh_from_db()
        self.assertTrue(self.loan.is_returned)
        self.assertEqual(self.loan.return_date, timezone.now().date())
        self.assertEqual(self.book.available_copies, 1)

    def test_return_without_active_loan_is_400(self):
        other = make_member(username='stranger')
        response = self.client.post(
            f'/api/books/{self.book.id}/return_book/', {'member_id': other.id}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_second_return_is_rejected(self):
        url = f'/api/books/{self.book.id}/return_book/'
        self.client.post(url, {'member_id': self.member.id})
        response = self.client.post(url, {'member_id': self.member.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)

    def test_oldest_loan_is_returned_first_when_member_holds_two_copies(self):
        """Two open loans on one title used to raise MultipleObjectsReturned."""
        second = make_loan(book=self.book, member=self.member)
        set_loan_date(self.loan, timezone.now().date() - timedelta(days=5))

        response = self.client.post(
            f'/api/books/{self.book.id}/return_book/', {'member_id': self.member.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.loan.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(self.loan.is_returned)
        self.assertFalse(second.is_returned)

    def test_return_rejected_for_unknown_member(self):
        response = self.client.post(
            f'/api/books/{self.book.id}/return_book/', {'member_id': 999999}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PermissionTests(APITestCase):
    """Anonymous clients may read the catalogue but not change it."""

    def test_anonymous_can_list_books(self):
        make_book()
        self.assertEqual(self.client.get('/api/books/').status_code, status.HTTP_200_OK)

    def test_anonymous_cannot_create_book(self):
        author = make_author()
        response = self.client.post(
            '/api/books/',
            {
                'title': 'Sneaky',
                'isbn': next_isbn(),
                'genre': 'fiction',
                'author_id': author.id,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Book.objects.filter(title='Sneaky').exists())

    def test_anonymous_cannot_loan_a_book(self):
        book = make_book(available_copies=1)
        member = make_member(username='anon-borrower')
        response = self.client.post(f'/api/books/{book.id}/loan/', {'member_id': member.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Loan.objects.count(), 0)

    def test_anonymous_cannot_delete_book(self):
        book = make_book()
        response = self.client.delete(f'/api/books/{book.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())
