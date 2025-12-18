from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from library.serializers import BookSerializer, LoanSerializer, MemberSerializer
from library.tests.factories import make_author, make_book, make_loan, make_member, next_isbn


class BookSerializerTests(TestCase):
    def test_author_is_nested_on_read_and_id_on_write(self):
        author = make_author(first_name='Ann', last_name='Leckie')
        book = make_book(author=author, title='Ancillary Justice')
        data = BookSerializer(book).data
        self.assertEqual(data['author']['first_name'], 'Ann')
        self.assertNotIn('author_id', data)

    def test_create_requires_author_id(self):
        serializer = BookSerializer(
            data={'title': 'Orphan', 'isbn': next_isbn(), 'genre': 'fiction'}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('author_id', serializer.errors)

    def test_invalid_genre_is_rejected(self):
        author = make_author()
        serializer = BookSerializer(
            data={
                'title': 'Mystery',
                'isbn': next_isbn(),
                'genre': 'cookbook',
                'author_id': author.id,
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('genre', serializer.errors)

    def test_duplicate_isbn_is_rejected(self):
        author = make_author()
        isbn = next_isbn()
        make_book(author=author, isbn=isbn)
        serializer = BookSerializer(
            data={
                'title': 'Copy',
                'isbn': isbn,
                'genre': 'fiction',
                'author_id': author.id,
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('isbn', serializer.errors)


class MemberSerializerTests(TestCase):
    def test_user_is_nested_without_password(self):
        member = make_member(username='nina', email='nina@example.com')
        data = MemberSerializer(member).data
        self.assertEqual(
            data['user'],
            {
                'id': member.user_id,
                'username': 'nina',
                'email': 'nina@example.com',
            },
        )
        self.assertNotIn('password', str(data))


class LoanSerializerTests(TestCase):
    def test_exposes_due_date_and_is_overdue(self):
        loan = make_loan(due_in_days=-2)
        data = LoanSerializer(loan).data
        self.assertEqual(data['due_date'], loan.due_date.isoformat())
        self.assertTrue(data['is_overdue'])

    def test_is_overdue_false_for_current_loan(self):
        data = LoanSerializer(make_loan(due_in_days=7)).data
        self.assertFalse(data['is_overdue'])

    def test_loan_date_is_read_only(self):
        self.assertTrue(LoanSerializer().fields['loan_date'].read_only)

    def test_create_rejected_when_no_copies_available(self):
        book = make_book(available_copies=0)
        member = make_member(username='out-of-stock')
        serializer = LoanSerializer(data={'book_id': book.id, 'member_id': member.id})
        self.assertFalse(serializer.is_valid())
        self.assertIn('book_id', serializer.errors)

    def test_create_allowed_when_copies_available(self):
        book = make_book(available_copies=2)
        member = make_member(username='in-stock')
        serializer = LoanSerializer(data={'book_id': book.id, 'member_id': member.id})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        loan = serializer.save()
        self.assertEqual(loan.book_id, book.id)
        self.assertEqual(loan.due_date, timezone.now().date() + timedelta(days=14))

    def test_update_of_empty_stock_loan_is_not_blocked(self):
        """Returning the last copy must not be rejected by the availability guard."""
        book = make_book(available_copies=0)
        loan = make_loan(book=book)
        serializer = LoanSerializer(
            loan,
            data={'book_id': book.id, 'member_id': loan.member_id, 'is_returned': True},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
