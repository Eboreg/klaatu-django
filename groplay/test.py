"""
Note: This module does not contain tests, hence its name is 'test' and not
'tests'. It's for extending TestCase.
"""
import json
from typing import Any, List, Optional

from django.core import mail
from django.db.models import Model
from django.http.response import HttpResponse
from django.test import TestCase


class ExtendedTestCase(TestCase):
    def assertGetUrl(self, url: str, expected_url: Optional[str] = None):
        """Assert GET request returns status < 400 and the given URL"""
        response = self.client.get(url, follow=True)
        self.assertLess(response.status_code, 400)
        if expected_url:
            self.assertEqual(response.wsgi_request.path_info, expected_url)
        else:
            self.assertEqual(response.wsgi_request.path_info, url)

    def assertDictContains(self, actual: dict, expected: dict):
        """Assert `actual` contains all keys and values from `expected`"""
        subset = {k: v for k, v in actual.items() if k in expected}
        self.assertDictEqual(subset, expected)

    def assertListContains(self, actual: list, expected: list):
        """Assert `actual` contains all values from `expected`"""
        sublist = [v for v in actual if v in expected]
        self.assertListEqual(sublist, expected)

    def assertDictListContains(self, actual: list, expected: dict):
        """Given a list of dicts, assert it contains `expected`"""
        for d in actual:
            try:
                self.assertDictContains(d, expected)
            except AssertionError:
                pass
            else:
                return
        self.fail(f"{actual} does not contain {expected}")

    def assertModelInstanceContains(self, instance: Model, expected: dict):
        """
        Assert `instance` has the attributes and values from the `expected`
        keys and values, respectively
        """
        for k, v in expected.items():
            self.assertEqual(getattr(instance, k), v)

    def assertResponseJSONContains(
        self,
        response: HttpResponse,
        data: Any,
        status_codes: List[int] = [200, 201]
    ):
        """
        Assert response has any of `status_codes` and has a JSON body that
        either contains `data` (in case `data` is list or dict), or _is_
        `data`.
        """
        content = json.loads(response.content)
        self.assertIn(response.status_code, status_codes)
        if isinstance(content, dict) and isinstance(data, dict):
            self.assertDictContains(content, data)
        elif isinstance(content, list) and isinstance(data, list):
            self.assertListContains(content, data)
        else:
            self.assertEqual(content, data)

    def assertHasReceivedEmail(self, email: str, count: Optional[int] = None):
        """
        Assert that `count` number of emails have been sent to `email`, or
        that _any_ email has been sent to `email` in case `count` is None.
        """
        messages = [m for m in mail.outbox if email in m.to]
        if count is not None:
            self.assertEqual(len(messages), count)
        else:
            self.assertGreaterEqual(len(messages), 1)

    def assertHasNotReceivedEmail(self, email: str):
        self.assertHasReceivedEmail(email, 0)
