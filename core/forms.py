"""Django forms for authentication, catalogue management and circulation.

Templates render these forms directly so that labels, help text and error
messages stay attached to their inputs and remain screen-reader friendly.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (Author, Book, BookCopy, BookSubjectMapping, Category, Course,
                     CurriculumScheme, DigitalMaterial, Loan, Semester,
                     StudentProfile, Subject)

User = get_user_model()

#: File extensions a librarian may attach as a digital material.
ALLOWED_MATERIAL_EXTENSIONS = {"pdf", "epub", "txt", "csv", "pptx", "docx", "md"}
MAX_MATERIAL_UPLOAD_MB = 10


class LoginForm(AuthenticationForm):
    """Sign-in form with placeholders and non-field error styling."""

    def __init__(self, *args, username_placeholder="student", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["placeholder"] = username_placeholder

    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "autocomplete": "username", "placeholder": "student",
            "class": "field-input"}),
        label="Username")
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "autocomplete": "current-password", "placeholder": "Your password",
            "class": "field-input"}),
        label="Password")

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Those sign-in details did not match an account.",
        "inactive": "This account has been deactivated. Please contact the librarian.",
    }

    def clean(self):
        """Explain a deactivated account instead of reporting a wrong password.

        Django's auth backend refuses inactive users before the form gets a
        chance to describe why. The account is only named when the supplied
        password is correct, so this does not leak which usernames exist.
        """
        try:
            return super().clean()
        except forms.ValidationError:
            data = getattr(self, "cleaned_data", None) or {}
            user = User.objects.filter(username=data.get("username", "")).first()
            if (user is not None and not user.is_active
                    and user.check_password(data.get("password", ""))):
                raise forms.ValidationError(self.error_messages["inactive"], code="inactive")
            raise


class StudentRegistrationForm(UserCreationForm):
    """Creates the Django user and the linked student profile together."""

    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    email = forms.EmailField(label="Email address")
    student_id = forms.CharField(max_length=32, label="Registration number")
    department = forms.CharField(max_length=100, label="Course / department")
    semester = forms.IntegerField(min_value=1, max_value=12, label="Semester")
    phone = forms.CharField(max_length=24, required=False, label="Phone (optional)")
    enrollment_year = forms.IntegerField(
        min_value=1900, max_value=2200, required=False, label="Enrollment year (optional)")

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": "field-input", "autocomplete": "username", "placeholder": "choose a username"})
        self.fields["email"].widget.attrs.update(
            {"class": "field-input", "autocomplete": "email", "placeholder": "you@college.edu"})
        for name in ("first_name", "last_name", "student_id", "department", "semester",
                     "phone", "enrollment_year", "password1", "password2"):
            self.fields[name].widget.attrs.setdefault("class", "field-input")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_student_id(self):
        student_id = self.cleaned_data["student_id"].strip()
        if StudentProfile.objects.filter(student_id__iexact=student_id).exists():
            raise ValidationError("This registration number is already registered.")
        return student_id.upper()

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        if not commit:
            return user
        user.save()
        profile = StudentProfile.objects.create(
            user=user,
            student_id=self.cleaned_data["student_id"],
            department=self.cleaned_data["department"],
            semester=self.cleaned_data["semester"],
            phone=self.cleaned_data.get("phone", ""),
            enrollment_year=self.cleaned_data.get("enrollment_year"),
        )
        from .models import ReadingList
        ReadingList.objects.create(student=profile, name="My reading list", is_default=True)
        return user


class StudentProfileForm(forms.ModelForm):
    """Lets a student edit their own academic details."""

    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    email = forms.EmailField(label="Email address")

    class Meta:
        model = StudentProfile
        fields = ("first_name", "last_name", "email", "department", "semester",
                  "phone", "enrollment_year")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance.user
        self.fields["first_name"].initial = user.first_name
        self.fields["last_name"].initial = user.last_name
        self.fields["email"].initial = user.email
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field-input")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.user_id).exists():
            raise ValidationError("Another account already uses this email address.")
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.email = self.cleaned_data["email"]
        if commit:
            user.save(update_fields=["first_name", "last_name", "email"])
            profile.save()
        return profile


class BookSearchForm(forms.Form):
    """Catalogue search box, academic filters and sort control.

    Every filter is optional and combinable: BCA -> Semester V -> Statistical
    Computing and R -> Recommended books is four fields used together on one
    GET request, all applied server-side.
    """

    SORT_CHOICES = (
        ("title", "Title (A–Z)"),
        ("author", "Author (A–Z)"),
        ("newest", "Newest first"),
        ("availability", "Availability"),
    )
    AVAILABILITY_CHOICES = (
        ("", "Any availability"),
        ("available", "Available now"),
        ("unavailable", "Currently borrowed"),
    )

    q = forms.CharField(required=False, max_length=160,
                        widget=forms.TextInput(attrs={
                            "placeholder": "Search title, author, ISBN or keyword…",
                            "class": "field-input", "aria-label": "Search the catalogue"}),
                        label="Search")
    category = forms.ModelChoiceField(required=False, queryset=Category.objects.none(),
                                      empty_label="All categories", label="Category")
    course = forms.ModelChoiceField(required=False, queryset=Course.objects.none(),
                                    empty_label="All courses", label="Course")
    scheme = forms.ModelChoiceField(required=False, queryset=CurriculumScheme.objects.none(),
                                    empty_label="All curricula", label="Curriculum scheme")
    semester = forms.ModelChoiceField(required=False, queryset=Semester.objects.none(),
                                      empty_label="All semesters", label="Semester")
    subject = forms.ModelChoiceField(required=False, queryset=Subject.objects.none(),
                                     empty_label="All subjects", label="Subject")
    classification = forms.ChoiceField(required=False,
                                       choices=[("", "All classifications")]
                                       + list(Subject.Classification.choices),
                                       widget=forms.Select(attrs={"class": "field-input"}),
                                       label="Classification")
    resource_type = forms.ChoiceField(required=False,
                                      choices=[("", "All resource types")]
                                      + list(BookSubjectMapping.ResourceType.choices),
                                      widget=forms.Select(attrs={"class": "field-input"}),
                                      label="Resource type")
    recommendation = forms.ChoiceField(required=False,
                                       choices=[("", "Any status")]
                                       + list(BookSubjectMapping.Recommendation.choices),
                                       widget=forms.Select(attrs={"class": "field-input"}),
                                       label="Recommendation")
    availability = forms.ChoiceField(required=False, choices=AVAILABILITY_CHOICES,
                                     widget=forms.Select(attrs={"class": "field-input"}),
                                     label="Availability")
    sort = forms.ChoiceField(required=False, choices=SORT_CHOICES,
                             widget=forms.Select(attrs={"class": "field-input"}), label="Sort by")

    FILTER_FIELDS = ("q", "category", "course", "scheme", "semester", "subject",
                     "classification", "resource_type", "recommendation",
                     "availability")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.order_by("name")
        self.fields["course"].queryset = Course.objects.filter(is_active=True).order_by("name")
        self.fields["scheme"].queryset = (CurriculumScheme.objects.filter(is_active=True)
                                          .select_related("course").order_by("course__code"))
        self.fields["semester"].queryset = (Semester.objects.filter(is_active=True)
                                            .select_related("curriculum_scheme__course")
                                            .order_by("curriculum_scheme__course__code", "number"))
        self.fields["subject"].queryset = (Subject.objects.filter(is_active=True,
                                                                  semester__isnull=False)
                                           .select_related("semester")
                                           .order_by("semester__number", "name"))
        for name in ("category", "course", "scheme", "semester", "subject",
                     "classification", "resource_type", "recommendation",
                     "availability", "sort"):
            self.fields[name].widget.attrs.setdefault("class", "field-input")

    @property
    def is_filtered(self):
        return any(self.data.get(name) for name in self.FILTER_FIELDS)


class BookForm(forms.ModelForm):
    """Add / edit a catalogue title. Copy count is managed separately."""

    total_copies = forms.IntegerField(
        min_value=0, max_value=500, initial=1, required=False, label="Total copies",
        help_text="Number of physical copies to hold for this title.",
        widget=forms.NumberInput(attrs={"class": "field-input", "min": 0, "max": 500}))
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(), required=False,
        widget=forms.Select(attrs={"class": "field-input"}), label="Category")
    isbn = forms.CharField(
        required=False, max_length=20, label="ISBN",
        widget=forms.TextInput(attrs={"class": "field-input"}),
        help_text="Digits and hyphens only. Must be unique.")
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.all(), required=False, label="Subject / department",
        widget=forms.Select(attrs={"class": "field-input"}))
    new_authors = forms.CharField(
        required=False, label="New author name(s)",
        help_text="Type authors not listed above, separated with commas.",
        widget=forms.TextInput(attrs={
            "class": "field-input", "placeholder": "Example: R. Elmasri, S. Navathe"}))

    class Meta:
        model = Book
        fields = ("title", "subtitle", "isbn", "authors", "new_authors", "category", "subject",
                  "publisher", "publication_year", "edition", "language", "page_count",
                  "description", "cover", "featured", "is_active")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "class": "field-input"}),
            "authors": forms.SelectMultiple(attrs={"size": 6, "class": "field-input"}),
            "subject": forms.Select(attrs={"class": "field-input"}),
            "cover": forms.ClearableFileInput(attrs={"class": "field-input"}),
            "featured": forms.CheckboxInput(attrs={"class": "field-checkbox"}),
            "is_active": forms.CheckboxInput(attrs={"class": "field-checkbox"}),
            "title": forms.TextInput(attrs={"class": "field-input"}),
            "subtitle": forms.TextInput(attrs={"class": "field-input"}),
            "isbn": forms.TextInput(attrs={"class": "field-input"}),
            "publisher": forms.TextInput(attrs={"class": "field-input"}),
            "publication_year": forms.NumberInput(attrs={"class": "field-input"}),
            "edition": forms.TextInput(attrs={"class": "field-input"}),
            "language": forms.TextInput(attrs={"class": "field-input"}),
            "page_count": forms.NumberInput(attrs={"class": "field-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The model carries a default, but a ModelForm still treats the field
        # as required, so make it optional and fall back on save.
        self.fields["language"].required = False
        self.fields["language"].initial = self.fields["language"].initial or "English"
        self.fields["authors"].label = "Existing author(s)"
        self.fields["authors"].help_text = (
            "Select one or more existing authors, or type new names below.")
        self.fields["total_copies"].help_text = (
            "Currently on the shelf: %(count)s."
            % {"count": self.instance.total_copies if self.instance.pk else 0})

    def clean_isbn(self):
        isbn = (self.cleaned_data.get("isbn") or "").strip()
        if isbn and not isbn.replace("-", "").isdigit():
            raise ValidationError("An ISBN may only contain digits and hyphens.")
        return isbn

    def clean_cover(self):
        cover = self.cleaned_data.get("cover")
        if cover and cover.size > 4 * 1024 * 1024:
            raise ValidationError("Cover images must be smaller than 4 MB.")
        return cover

    def save(self, commit=True):
        """Persist the book and mirror the chosen category onto the M2M table."""
        book = super().save(commit=False)
        if not book.language:
            book.language = "English"
        category = self.cleaned_data.get("category")
        if commit:
            book.save()
            selected_authors = list(self.cleaned_data.get("authors") or [])
            typed_names = [name.strip() for name in
                           (self.cleaned_data.get("new_authors") or "").replace(";", ",").split(",")
                           if name.strip()]
            for name in typed_names:
                author = Author.objects.filter(name__iexact=name).first()
                if author is None:
                    author = Author.objects.create(name=name)
                if author not in selected_authors:
                    selected_authors.append(author)
            book.authors.set(selected_authors)
            if category:
                book.categories.set([category])
            else:
                book.categories.clear()
        return book


class BookCopyForm(forms.ModelForm):
    """Manage a single physical copy."""

    class Meta:
        model = BookCopy
        fields = ("accession_number", "status", "shelf_location", "acquired_on", "notes")
        widgets = {
            "status": forms.Select(attrs={"class": "field-input"}),
            "acquired_on": forms.DateInput(attrs={"type": "date", "class": "field-input"}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": "field-input"}),
            "accession_number": forms.TextInput(attrs={"class": "field-input"}),
            "shelf_location": forms.TextInput(attrs={"class": "field-input"}),
        }

    def clean(self):
        cleaned = super().clean()
        copy = self.instance
        if copy.pk and copy.status in (BookCopy.Status.AVAILABLE,):
            active = copy.loans.filter(status__in=Loan.ON_LOAN_STATUSES).exists()
            if active and not self.data.get("status"):
                raise ValidationError(
                    "This copy is currently on loan and cannot be marked available.")
        return cleaned


class DigitalMaterialForm(forms.ModelForm):
    """Add or edit a digital learning resource."""

    class Meta:
        model = DigitalMaterial
        fields = ("title", "description", "material_type", "book", "subject",
                  "categories", "authors", "file", "external_url",
                  "publication_date", "is_public")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4, "class": "field-input"}),
            "material_type": forms.Select(attrs={"class": "field-input"}),
            "book": forms.Select(attrs={"class": "field-input"}),
            "subject": forms.Select(attrs={"class": "field-input"}),
            "categories": forms.SelectMultiple(attrs={"size": 5, "class": "field-input"}),
            "authors": forms.SelectMultiple(attrs={"size": 5, "class": "field-input"}),
            "file": forms.ClearableFileInput(attrs={"class": "field-input"}),
            "external_url": forms.URLInput(attrs={"class": "field-input",
                                                  "placeholder": "https://…"}),
            "publication_date": forms.DateInput(attrs={"type": "date", "class": "field-input"}),
            "is_public": forms.CheckboxInput(attrs={"class": "field-checkbox"}),
            "title": forms.TextInput(attrs={"class": "field-input"}),
        }

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            return uploaded
        extension = (uploaded.name.rsplit(".", 1)[-1] or "").lower()
        if extension not in ALLOWED_MATERIAL_EXTENSIONS:
            raise ValidationError(
                "Unsupported file type. Allowed: %s."
                % ", ".join(sorted(ALLOWED_MATERIAL_EXTENSIONS)))
        if uploaded.size > MAX_MATERIAL_UPLOAD_MB * 1024 * 1024:
            raise ValidationError("Files must be smaller than %d MB." % MAX_MATERIAL_UPLOAD_MB)
        return uploaded

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("file") and not cleaned.get("external_url"):
            raise ValidationError("Attach a file or provide an external URL.")
        return cleaned


class LoanIssueForm(forms.Form):
    """Counter-top issue form used by the librarian."""

    student = forms.ModelChoiceField(queryset=StudentProfile.objects.none())
    book = forms.ModelChoiceField(queryset=Book.objects.none())
    due_at = forms.DateTimeField(
        required=False, input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "class": "field-input"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = (
            StudentProfile.objects.filter(is_active=True)
            .select_related("user").order_by("student_id"))
        self.fields["book"].queryset = Book.objects.filter(is_active=True).order_by("title")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field-input")


class LoanReturnForm(forms.Form):
    """Notes recorded when the desk takes a book back."""

    loan = forms.ModelChoiceField(queryset=Loan.objects.none(), widget=forms.HiddenInput)
    notes = forms.CharField(required=False, max_length=500,
                            widget=forms.Textarea(attrs={"rows": 2, "class": "field-input"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only live loans can be returned; closed records are filtered out so a
        # second submission cannot reopen a settled transaction.
        self.fields["loan"].queryset = Loan.objects.filter(
            status__in=Loan.ON_LOAN_STATUSES).select_related("book", "student__user")


class BookReviewForm(forms.Form):
    """A reader's rating of a book they borrowed and returned."""

    RATING_CHOICES = [(value, f"{value} star" + ("s" if value != 1 else ""))
                      for value in range(1, 6)]

    rating = forms.TypedChoiceField(
        choices=RATING_CHOICES, coerce=int,
        widget=forms.RadioSelect(attrs={"class": "rating-input"}))
    title = forms.CharField(required=False, max_length=160,
                            widget=forms.TextInput(
                                attrs={"class": "field-input",
                                       "placeholder": "Sum it up in a line (optional)"}))
    body = forms.CharField(required=False, max_length=4000,
                           widget=forms.Textarea(
                               attrs={"rows": 3, "class": "field-input",
                                      "placeholder": "What worked, what didn't? (optional)"}))
