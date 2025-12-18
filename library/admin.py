"""The librarian's back office.

Loans are opened, returned and deleted through :mod:`library.services.loans`
here too, so the admin cannot leave ``available_copies`` out of step with the
loans that are actually out.
"""

from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Author, Book, Loan, LoanStatus, Member
from .services import DomainError
from .services import loans as loan_service

admin.site.site_header = 'Library Desk'
admin.site.site_title = 'Library Desk'
admin.site.index_title = 'Circulation and catalogue'


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name')
    search_fields = ('last_name', 'first_name')


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'genre', 'isbn', 'available_copies')
    list_filter = ('genre',)
    search_fields = ('title', 'isbn')
    list_select_related = ('author',)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'membership_date')
    search_fields = ('user__username', 'user__email')
    list_select_related = ('user',)


class LoanStatusFilter(admin.SimpleListFilter):
    """Filter on the derived status, which has no column to filter on."""

    title = 'status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return LoanStatus.choices

    def queryset(self, request, queryset):
        by_status = {
            LoanStatus.ACTIVE: queryset.active,
            LoanStatus.OVERDUE: queryset.overdue,
            LoanStatus.RETURNED: queryset.returned,
        }
        narrow = by_status.get(self.value())
        return narrow() if narrow else queryset


class LoanAdminForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = ['book', 'member', 'due_date']

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk is not None:
            return cleaned
        book = cleaned.get('book')
        if book is not None and book.available_copies < 1:
            self.add_error('book', 'No copies of this book are on the shelf.')
        due_date = cleaned.get('due_date')
        if due_date is not None:
            try:
                loan_service.check_due_date(due_date)
            except DomainError as exc:
                self.add_error('due_date', exc.message)
        return cleaned


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    form = LoanAdminForm
    # Status sits next to the title so it stays visible on a phone, where the
    # admin table scrolls sideways.
    list_display = ('book', 'status', 'member', 'due_date', 'loan_date', 'return_date')
    list_filter = (LoanStatusFilter, 'due_date')
    search_fields = ('book__title', 'member__user__username')
    list_select_related = ('book', 'member__user')
    autocomplete_fields = ('book', 'member')
    actions = ('mark_returned',)

    def get_readonly_fields(self, request, obj=None):
        lifecycle = ('loan_date', 'is_returned', 'return_date')
        return ('book', 'member', *lifecycle) if obj else lifecycle

    @admin.display(description='Status')
    def status(self, obj):
        current = obj.status
        return format_html(
            '<span class="loan-status loan-status--{}">{}</span>', current.value, current.label
        )

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        loan = loan_service.loan_book(book=obj.book, member=obj.member, due_date=obj.due_date)
        obj.pk, obj.loan_date = loan.pk, loan.loan_date

    def delete_model(self, request, obj):
        loan_service.delete_loan(obj)

    def delete_queryset(self, request, queryset):
        for loan in queryset:
            loan_service.delete_loan(loan)

    @admin.action(description='Mark selected loans as returned')
    def mark_returned(self, request, queryset):
        closed = 0
        for loan in queryset.open():
            loan_service.return_loan(loan)
            closed += 1
        skipped = queryset.count() - closed
        self.message_user(request, f'Returned {closed} loan(s).', messages.SUCCESS)
        if skipped:
            self.message_user(
                request, f'Skipped {skipped} loan(s) that were already returned.', messages.WARNING
            )
