from django.shortcuts import render


def home(request):
    return render(request, "landing/home.html")


BOOKS = [
    {"title": "Database System Concepts", "author": "A. Silberschatz", "kind": "Computer Science", "cover": "architecture", "progress": 72},
    {"title": "Designing Data-Intensive Applications", "author": "Martin Kleppmann", "kind": "Data Systems", "cover": "topography", "progress": 46},
    {"title": "The Pragmatic Programmer", "author": "Andrew Hunt", "kind": "Software Engineering", "cover": "grid", "progress": 31},
    {"title": "Artificial Intelligence", "author": "Stuart Russell", "kind": "Machine Learning", "cover": "orbital", "progress": 58},
]


def discover(request):
    return render(request, "library/discover.html", {"books": BOOKS})


def book_detail(request):
    return render(request, "library/book_detail.html", {"book": BOOKS[0], "books": BOOKS[1:]})


def student_dashboard(request):
    return render(request, "student/dashboard.html", {"books": BOOKS})


def librarian_dashboard(request):
    return render(request, "librarian/dashboard.html", {"books": BOOKS})
