"""Domain errors raised by the service layer.

The service layer never imports DRF, so it signals rule violations with plain
exceptions. ``library.api_errors.domain_exception_handler`` is the single place
that turns them into HTTP responses, which keeps the views free of
``return Response({'error': ...}, status=400)`` ladders.
"""


class DomainError(Exception):
    """A library rule was violated. Always a client error, never a 500."""

    code = 'domain_error'
    message = 'The request could not be completed.'

    def __init__(self, message=None, code=None):
        self.message = message or self.message
        self.code = code or self.code
        super().__init__(self.message)


class MemberNotFound(DomainError):
    code = 'member_not_found'
    message = 'Member does not exist.'


class BookUnavailable(DomainError):
    code = 'book_unavailable'
    message = 'No available copies.'


class NoActiveLoan(DomainError):
    code = 'no_active_loan'
    message = 'Active loan does not exist.'


class LoanAlreadyReturned(DomainError):
    code = 'loan_already_returned'
    message = 'Loan has already been returned.'


class LoanOverdue(DomainError):
    code = 'loan_overdue'
    message = 'Cannot extend an overdue loan.'


class InvalidExtension(DomainError):
    code = 'invalid_extension'
    message = 'additional_days must be a positive integer.'
