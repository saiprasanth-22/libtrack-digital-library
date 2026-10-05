"""Forms for LibTrack's catalogue and lending workflows."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from .models import Book, BookCopy, Category, Loan, StudentProfile


class StudentRegistrationForm(UserCreationForm):
    """Register a Django user and their student profile in the view/service."""

    email = forms.EmailField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    student_id = forms.CharField(max_length=40)
    department = forms.CharField(max_length=120)
    semester = forms.IntegerField(min_value=1, max_value=12)
    phone = forms.CharField(max_length=32, required=False)
    enrollment_year = forms.IntegerField(min_value=1900, max_value=2200)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "first_name", "last_name")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_student_id(self):
        student_id = self.cleaned_data["student_id"].strip()
        from .models import StudentProfile
        if StudentProfile.objects.filter(student_id__iexact=student_id).exists():
            raise forms.ValidationError("This student ID is already registered.")
        return student_id

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save()
            from .models import StudentProfile
            StudentProfile.objects.create(
                user=user,
                student_id=self.cleaned_data["student_id"],
                department=self.cleaned_data["department"],
                semester=self.cleaned_data["semester"],
                phone=self.cleaned_data["phone"],
                enrollment_year=self.cleaned_data["enrollment_year"],
            )
        return user


class BookSearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=160, label="Search books")
    category = forms.ModelChoiceField(queryset=Category.objects.none(), required=False)
    subject = forms.CharField(required=False, max_length=100)
    availability = forms.ChoiceField(required=False, choices=(
        ("", "Any availability"), ("available", "Available now"), ("unavailable", "Currently borrowed"),
    ))
    sort = forms.ChoiceField(required=False, choices=(
        ("", "Relevance"), ("title", "Title"), ("year_desc", "Newest"),
    ))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.order_by("name")


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = ("title", "subtitle", "isbn", "authors", "categories", "subject",
                  "publisher", "publication_year", "edition", "language", "page_count", "description",
                  "cover_image_url", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 5}),
                   "authors": forms.SelectMultiple(attrs={"size": 5}),
                   "categories": forms.SelectMultiple(attrs={"size": 5})}


class LoanIssueForm(forms.Form):
    """Fields needed to issue a copy; final checks happen under a DB lock."""
    student = forms.ModelChoiceField(queryset=StudentProfile.objects.none())
    copy = forms.ModelChoiceField(queryset=BookCopy.objects.none())
    due_at = forms.DateTimeField(input_formats=("%Y-%m-%dT%H:%M",),
                                  widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = StudentProfile.objects.select_related("user").order_by("student_id")
        self.fields["copy"].queryset = BookCopy.objects.filter(status=BookCopy.Status.AVAILABLE).select_related("book")


class LoanReturnForm(forms.Form):
    loan = forms.ModelChoiceField(queryset=Loan.objects.none())
    notes = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["loan"].queryset = Loan.objects.filter(status=Loan.Status.ACTIVE).select_related("copy__book", "student__user")
