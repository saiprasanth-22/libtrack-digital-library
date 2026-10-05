"""Test runner used by ``manage.py test``.

The project always configures the hashed manifest static files storage so that
``collectstatic`` produces a manifest regardless of the ``DJANGO_DEBUG`` value
in force at the time. The test suite has no collectstatic step, so this runner
temporarily swaps in the plain storage backend and restores it afterwards.
"""

from django.conf import settings
from django.test.runner import DiscoverRunner


class LibTrackTestRunner(DiscoverRunner):

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._storages = settings.STORAGES
        settings.STORAGES = {
            **self._storages,
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }

    def teardown_test_environment(self, **kwargs):
        settings.STORAGES = self._storages
        super().teardown_test_environment(**kwargs)
