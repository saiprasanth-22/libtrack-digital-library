"""Named URL routes for every LibTrack screen."""

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    # Public
    path("", views.home, name="home"),
    path("discover/", views.discover, name="discover"),
    path("materials/", views.materials, name="materials"),
    path("books/<slug:slug>/", views.book_detail, name="book_detail"),
    path("books/<slug:slug>/borrow/", views.borrow_book, name="borrow_book"),
    path("books/<slug:slug>/request/", views.request_book, name="request_book"),
    path("books/<slug:slug>/save/", views.save_book, name="save_book"),

    # Authentication
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/register/", views.register, name="register"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),

    # Student
    path("student/", views.student_dashboard, name="student"),
    path("student/loans/", views.student_loans, name="student_loans"),
    path("student/profile/", views.student_profile, name="student_profile"),
    path("student/profile/update/", views.student_profile_update, name="student_profile_update"),
    path("student/password/", views.student_password, name="student_password"),
    path("student/password/done/", views.student_password_done, name="student_password_done"),
    path("loans/<int:loan_id>/renew/", views.renew_loan, name="renew_loan"),
    path("loans/<int:loan_id>/return/", views.return_loan, name="return_loan"),

    # Librarian
    path("librarian/", views.librarian_dashboard, name="librarian"),
    path("librarian/books/", views.librarian_books, name="librarian_books"),
    path("librarian/books/<int:pk>/edit/", views.librarian_book_edit, name="librarian_book_edit"),
    path("librarian/books/<int:pk>/delete/", views.librarian_book_delete, name="librarian_book_delete"),
    path("librarian/books/<int:pk>/copies/", views.librarian_copies, name="librarian_copies"),
    path("librarian/students/", views.librarian_students, name="librarian_students"),
    path("librarian/students/<int:pk>/", views.librarian_student_detail, name="librarian_student_detail"),
    path("librarian/students/<int:pk>/toggle/", views.librarian_student_toggle, name="librarian_student_toggle"),
    path("librarian/circulation/", views.librarian_circulation, name="librarian_circulation"),
    path("librarian/requests/<int:pk>/approve/", views.librarian_request_approve, name="librarian_request_approve"),
    path("librarian/requests/<int:pk>/reject/", views.librarian_request_reject, name="librarian_request_reject"),
    path("librarian/materials/", views.librarian_materials, name="librarian_materials"),
    path("librarian/materials/<int:pk>/edit/", views.librarian_material_edit, name="librarian_material_edit"),
    path("librarian/materials/<int:pk>/delete/", views.librarian_material_delete, name="librarian_material_delete"),
    path("librarian/reports/", views.librarian_reports, name="librarian_reports"),
]
