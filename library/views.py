"""HTTP adapters.

Each view does three things and nothing else: read the request, call a service,
shape the response. Business rules live in :mod:`library.services.loans`, and
rule violations become ``400`` responses in
:func:`library.api_errors.domain_exception_handler`.
"""

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Author, Book, Loan, Member
from .serializers import AuthorSerializer, BookSerializer, LoanSerializer, MemberSerializer
from .services import loans as loan_service
from .tasks import send_loan_notification


class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.select_related('author')
    serializer_class = BookSerializer

    @action(detail=True, methods=['post'])
    def loan(self, request, pk=None):
        book = self.get_object()
        member = loan_service.resolve_member(request.data.get('member_id'))
        loan = loan_service.loan_book(book=book, member=member)

        send_loan_notification.delay(loan.id)
        return Response(
            {'status': 'Book loaned successfully.', 'loan_id': loan.id},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def return_book(self, request, pk=None):
        book = self.get_object()
        member = loan_service.resolve_member(request.data.get('member_id'))
        loan_service.return_book(book=book, member=member)
        return Response({'status': 'Book returned successfully.'}, status=status.HTTP_200_OK)


class MemberViewSet(viewsets.ModelViewSet):
    queryset = Member.objects.select_related('user')
    serializer_class = MemberSerializer


class LoanViewSet(viewsets.ModelViewSet):
    queryset = Loan.objects.with_related()
    serializer_class = LoanSerializer

    def perform_create(self, serializer):
        """Creating a loan through /api/loans/ must also take a copy off the shelf."""
        with transaction.atomic():
            loan = serializer.save()
            loan_service.reserve_copy(loan.book_id)

    @action(detail=True, methods=['post'], url_path='extend_due_date')
    def extend_due_date(self, request, pk=None):
        loan = self.get_object()
        loan = loan_service.extend_loan(
            loan=loan, additional_days=request.data.get('additional_days')
        )
        return Response(self.get_serializer(loan).data, status=status.HTTP_200_OK)
