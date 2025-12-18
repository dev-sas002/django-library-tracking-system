from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Author, Book, Loan, Member


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ['id', 'first_name', 'last_name', 'biography']


class BookSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    author_id = serializers.PrimaryKeyRelatedField(
        queryset=Author.objects.all(), source='author', write_only=True
    )

    class Meta:
        model = Book
        fields = ['id', 'title', 'author', 'author_id', 'isbn', 'genre', 'available_copies']


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class MemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='user', write_only=True
    )

    class Meta:
        model = Member
        fields = ['id', 'user', 'user_id', 'membership_date']


class LoanSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)
    book_id = serializers.PrimaryKeyRelatedField(
        queryset=Book.objects.all(), source='book', write_only=True
    )
    member = MemberSerializer(read_only=True)
    member_id = serializers.PrimaryKeyRelatedField(
        queryset=Member.objects.all(), source='member', write_only=True
    )
    is_overdue = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Loan
        fields = [
            'id',
            'book',
            'book_id',
            'member',
            'member_id',
            'loan_date',
            'due_date',
            'return_date',
            'is_returned',
            'is_overdue',
            'status',
        ]
        read_only_fields = ['loan_date']

    def get_is_overdue(self, obj):
        return obj.is_overdue()

    def validate(self, attrs):
        book = attrs.get('book')
        # Only guard stock when a new loan is being opened; updates (e.g. marking
        # a loan returned) must not be blocked by a currently empty shelf.
        if self.instance is None and book is not None and book.available_copies < 1:
            raise serializers.ValidationError({'book_id': 'No available copies of this book.'})
        return attrs
