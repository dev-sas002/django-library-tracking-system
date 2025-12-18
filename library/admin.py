from django.contrib import admin
from .models import Author, Book, Member, Loan

admin.site.register(Author)
admin.site.register(Book)
admin.site.register(Member)
admin.site.register(Loan)
