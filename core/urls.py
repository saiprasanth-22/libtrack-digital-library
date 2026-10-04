from django.urls import path
from . import views

app_name = "core"
urlpatterns = [path("", views.home, name="home")]
urlpatterns += [
    path("discover/", views.discover, name="discover"),
    path("books/database-system-concepts/", views.book_detail, name="book_detail"),
    path("student/", views.student_dashboard, name="student"),
    path("librarian/", views.librarian_dashboard, name="librarian"),
]
