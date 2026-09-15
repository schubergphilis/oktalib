#!/usr/bin/env python
# File: oktasession.py
#
# Copyright 2018 Costas Tyfoxylos
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
#

"""
The http transport for oktalib.

Everything about talking to Okta over http lives here: authentication, the rate
limit, transport retries, timeouts, pagination and the translation of a failed
response into a ``ServerError``. The rest of the library names endpoints and
interprets payloads; it never assembles a url or decides how to retry.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

import logging
from collections.abc import Generator
from typing import Any

from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .oktalibexceptions import ApiLimitReached, AuthFailed, ServerError

__author__ = 'Costas Tyfoxylos <ctyfoxylos@schubergphilis.com>'
__docformat__ = 'google'
__copyright__ = 'Copyright 2018, Costas Tyfoxylos'
__license__ = 'MIT'
__maintainer__ = 'Costas Tyfoxylos'
__email__ = '<ctyfoxylos@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

# This is the main prefix used for logging
LOGGER_BASENAME = 'oktasession'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())

DEFAULT_TIMEOUT = (5, 30)  # (connect, read)
RATE_LIMIT_STATUS = 429
RETRY_TOTAL = 3
RETRY_BACKOFF_FACTOR = 1.0
RETRY_BACKOFF_JITTER = 0.5
RETRY_BACKOFF_MAX = 60
SERVER_ERROR_STATUSES = (500, 502, 503, 504)
IDEMPOTENT_METHODS = frozenset({'DELETE', 'GET', 'HEAD', 'OPTIONS', 'PUT'})
DEFAULT_PAGE_SIZE = 100


class OktaRetry(Retry):
    """A retry policy that reads a rate limit differently from a server error.

    A 429 means Okta rejected the request outright rather than acting on it, so
    replaying it cannot make the same change twice and every verb is safe to retry.
    That matters here because creating users, groups and applications all go out as
    POSTs, and a rate limit is hit during exactly that kind of bulk work.

    A 500/502/503/504 is the opposite: it leaves it genuinely unknown whether Okta
    acted before failing, so those stay restricted to the idempotent verbs through
    ``allowed_methods``. Since ``allowed_methods`` is consulted for every retryable
    condition, the rate limit has to be exempted from it here rather than configured.
    """

    def is_retry(self, method: str, status_code: int, has_retry_after: bool = False) -> bool:
        """Decide whether a response is worth sending again.

        Args:
            method: HTTP verb.
            status_code: The status Okta answered with.
            has_retry_after: Whether the response carried a Retry-After header.

        Returns:
            bool: True if the request should be retried.

        """
        if status_code == RATE_LIMIT_STATUS:
            return True
        return super().is_retry(method, status_code, has_retry_after)


class RateLimitedSession(Session):
    """A requests session that retries what Okta says is worth retrying.

    The retrying itself happens in urllib3, mounted here as an adapter, so jittered
    exponential backoff and Retry-After parsing come for free rather than being
    implemented again. :class:`OktaRetry` decides which statuses are safe on which
    verbs.

    ``raise_on_status`` is off so that an exhausted budget comes back as a response
    instead of a ``RetryError``. A server error then reaches
    :meth:`OktaSession.validate_response` and becomes the ``ServerError`` callers
    already expect, and a rate limit is turned into ``ApiLimitReached`` by
    :meth:`request`, which keeps both documented exceptions intact.

    Connection and read failures are deliberately left unretried. Replaying them
    would multiply the read timeout by the retry budget, so a hung endpoint would
    block for minutes rather than ``DEFAULT_TIMEOUT``, and urllib3 would report the
    exhaustion as a ``ConnectionError`` on idempotent verbs while the others raise
    ``ReadTimeout`` for the very same failure.
    """

    def __init__(
        self,
        timeout: float | tuple[float, float] | None = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the session.

        Args:
            timeout: The default applied to any request that does not name its own,
                as seconds or a (connect, read) pair. requests applies no timeout of
                its own, so without this a hung endpoint blocks forever. Pass None
                for that behaviour deliberately.

        """
        super().__init__()
        logger_name = f'{LOGGER_BASENAME}.{self.__class__.__name__}'
        self._logger = logging.getLogger(logger_name)
        self.timeout = timeout
        adapter = HTTPAdapter(
            max_retries=OktaRetry(
                total=RETRY_TOTAL,
                connect=False,
                read=False,
                other=0,
                backoff_factor=RETRY_BACKOFF_FACTOR,
                backoff_jitter=RETRY_BACKOFF_JITTER,
                backoff_max=RETRY_BACKOFF_MAX,
                status_forcelist=SERVER_ERROR_STATUSES,
                allowed_methods=IDEMPOTENT_METHODS,
                respect_retry_after_header=True,
                raise_on_status=False,
            )
        )
        self.mount('https://', adapter)
        self.mount('http://', adapter)

    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        """Make a request, reporting a rate limit that outlasted the retries.

        Args:
            method: HTTP verb.
            url: The url to request.
            args: Positional arguments passed through to requests.
            kwargs: Keyword arguments passed through to requests. A ``timeout``
                given here wins over the session default, including an explicit
                None for no timeout at all.

        Raises:
            ApiLimitReached: The endpoint was still answering 429 once the retry
                budget was spent.

        Returns:
            Response: The response.

        """
        kwargs.setdefault('timeout', self.timeout)
        response = super().request(method, url, *args, **kwargs)
        if response.status_code == RATE_LIMIT_STATUS:
            self._logger.warning('Api is still exhausted for endpoint after retrying, giving up.')
            raise ApiLimitReached
        return response


class OktaSession(RateLimitedSession):
    """An authenticated session against one Okta instance.

    Knows where the instance is, so callers name an endpoint rather than assembling
    a url: ``session.get('/users')`` reaches ``{host}/api/v1/users``. A url that is
    already absolute is sent as it stands, which covers both the pagination links
    Okta hands back and the ``/oauth2/v1`` endpoints that sit outside ``/api/v1``.
    """

    def __init__(
        self,
        host: str,
        token: str,
        timeout: float | tuple[float, float] | None = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize and authenticate the session.

        Args:
            host: The host of the okta instance, e.g. https://dev.oktapreview.com
            token: The API token to use for authentication
            timeout: The default applied to any request that does not name its own.

        """
        super().__init__(timeout=timeout)
        self.host = host
        self.token = token
        self.authenticate()

    @property
    def api(self) -> str:
        """The root of the instance's rest api, for callers that need it spelled out.

        Returns:
            str: The api root, e.g. https://dev.oktapreview.com/api/v1

        """
        return f'{self.host}/api/v1'

    def authenticate(self) -> None:
        """Install the credentials on the session and confirm the token works.

        Raises:
            AuthFailed: Okta rejected the token.

        """
        self.get(self.host)
        self.headers.update(
            {
                'accept': 'application/json',
                'content-type': 'application/json',
                'authorization': f'SSWS {self.token}',
            }
        )
        response = self.get('/users/me/')
        if not response.ok:
            raise AuthFailed(response.content)

    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        """Resolve an endpoint against the instance and make the request.

        Args:
            method: HTTP verb.
            url: An endpoint such as ``/users``, resolved against :attr:`api`, or an
                absolute url, which is used as it stands.
            args: Positional arguments passed through to requests.
            kwargs: Keyword arguments passed through to requests.

        Returns:
            Response: The response.

        """
        if not url.startswith(('http://', 'https://')):
            url = f'{self.api}{url}'
        return super().request(method, url, *args, **kwargs)

    def get_paginated_url(
        self,
        url: str,
        result_limit: int = DEFAULT_PAGE_SIZE,
        params: dict[str, Any] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Gets the paginated data from a url.

        Args:
            url: The endpoint to get the data from
            result_limit: The number of results to get per page, defaults to 100
            params: Optional extra query parameters for the first request. Entries
                with a None value are dropped, so callers can pass optional
                filters through directly. Subsequent pages are followed by the
                link Okta returns, which already carries these parameters.

        Returns:
            generator: A generator of the data from the url

        """
        query: dict[str, Any] = {'limit': result_limit}
        query.update({key: value for key, value in (params or {}).items() if value is not None})
        response = self.validate_response(url, query)
        yield from response.json()
        next_link = response.links.get('next', {}).get('url')
        while next_link:
            response = self.validate_response(url=next_link)
            yield from response.json()
            next_link = response.links.get('next', {}).get('url')

    def validate_response(self, url: str, params: dict[str, Any] | None = None) -> Response:
        """Validate API response and raise appropriate exceptions on error.

        Args:
            url: The endpoint to request
            params: Optional query parameters for the request

        Returns:
            Response: The validated HTTP response object

        Raises:
            ServerError: If the response indicates an error (not ok status)

        """
        response = self.get(url=url, params=params)
        if not response.ok:
            try:
                error_message = response.json().get('errorSummary')
            except (ValueError, AttributeError):
                error_message = response.text
            raise ServerError(error_message) from None
        return response
