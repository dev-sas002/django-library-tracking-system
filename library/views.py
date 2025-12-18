"""HTTP adapters.

Each view does three things and nothing else: read the request, call a service,
shape the response. Business rules live in :mod:`library.services.loans`, and
rule violations become ``400`` responses in
:func:`library.api_errors.domain_exception_handler`.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Author, Book, Loan, Member
from .serializers import AuthorSerializer, BookSerializer, LoanSerializer, MemberSerializer
from .services import loans as loan_service
from .tasks import send_loan_notification


def open_loan(*, book, member, due_date=None):
    """The one way HTTP opens a loan: through the service, then a confirmation."""
    loan = loan_service.loan_book(book=book, member=member, due_date=due_date)
    send_loan_notification.delay(loan.id)
    return loan


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
        loan = open_loan(book=book, member=member)
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
    """Open loans with POST, then extend, return or delete them. There is no PUT or PATCH.

    A generic update could close a loan or move it to another book without touching stock.
    """

    queryset = Loan.objects.with_related()
    serializer_class = LoanSerializer
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def perform_create(self, serializer):
        """Same rules, locking and confirmation as ``POST /api/books/{id}/loan/``."""
        data = serializer.validated_data
        loan = open_loan(book=data['book'], member=data['member'], due_date=data.get('due_date'))
        serializer.instance = self.get_queryset().get(pk=loan.pk)

    def perform_destroy(self, instance):
        loan_service.delete_loan(instance)

    @action(detail=True, methods=['post'], url_path='return')
    def return_loan(self, request, pk=None):
        loan = loan_service.return_loan(self.get_object())
        return Response(self.get_serializer(loan).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='extend_due_date')
    def extend_due_date(self, request, pk=None):
        loan = self.get_object()
        loan = loan_service.extend_loan(
            loan=loan, additional_days=request.data.get('additional_days')
        )
        return Response(self.get_serializer(loan).data, status=status.HTTP_200_OK)
