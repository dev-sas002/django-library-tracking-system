from django.contrib import admin

from .models import Author, Book, Loan, Member


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


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('book', 'member', 'loan_date', 'due_date', 'return_date', 'status')
    list_filter = ('is_returned', 'due_date')
    search_fields = ('book__title', 'member__user__username')
    list_select_related = ('book', 'member__user')

    @admin.display(description='Status')
    def status(self, obj):
        return obj.status.label
