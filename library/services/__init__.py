"""Application services: the library's business rules.

Nothing in this package imports Django REST Framework or Celery. Views and
tasks depend on it; it depends only on the models. That is the whole of the
layering rule, and it is what makes the rules testable without a request.
"""

from .exceptions import (
    BookUnavailable,
    DomainError,
    InvalidExtension,
    LoanAlreadyReturned,
    LoanOverdue,
    MemberNotFound,
    NoActiveLoan,
)

__all__ = [
    'BookUnavailable',
    'DomainError',
    'InvalidExtension',
    'LoanAlreadyReturned',
    'LoanOverdue',
    'MemberNotFound',
    'NoActiveLoan',
]
