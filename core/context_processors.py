"""Template context shared by every page."""

from django.conf import settings as django_settings


def library_rules(request):
    """Expose the configured circulation limits to templates.

    Lets the interface say "Standard loan period: 14 days" without the number
    being written into the markup.
    """
    return {"LIBRARY_RULES": django_settings.LIBRARY_RULES}
