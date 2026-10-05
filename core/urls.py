from django.urls import path
from . import views

app_name = "core"
urlpatterns = [path("", views.home, name="home")]
urlpatterns += [
    path("discover/", views.discover, name="discover"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/register/", views.register, name="register"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("books/database-system-concepts/", views.book_detail, name="book_detail"),
    path("books/<slug:slug>/", views.book_detail, name="book_detail_slug"),
    path("books/<slug:slug>/borrow/", views.borrow_book, name="borrow_book"),
    path("books/<slug:slug>/save/", views.save_book, name="save_book"),
    path("loans/<int:loan_id>/return/", views.return_loan, name="return_loan"),
    path("student/", views.student_dashboard, name="student"),
    path("librarian/", views.librarian_dashboard, name="librarian"),
    path("librarian/catalogue/", views.librarian_catalogue, name="librarian_catalogue"),
]
