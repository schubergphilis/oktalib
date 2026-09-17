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
import random
import time
from collections.abc import Generator
from contextlib import suppress
from http import HTTPStatus
from typing import Any

from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InvalidHeader
from urllib3.util.retry import Retry

from .oktacredentials import OktaCredentials
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
RATE_LIMIT_STATUS = HTTPStatus.TOO_MANY_REQUESTS
RETRY_TOTAL = 3
RETRY_BACKOFF_FACTOR = 1.0
RETRY_BACKOFF_JITTER = 0.5
RETRY_BACKOFF_MAX = 60
SERVER_ERROR_STATUSES = (
    HTTPStatus.INTERNAL_SERVER_ERROR,
    HTTPStatus.BAD_GATEWAY,
    HTTPStatus.SERVICE_UNAVAILABLE,
    HTTPStatus.GATEWAY_TIMEOUT,
)
IDEMPOTENT_METHODS = frozenset({'DELETE', 'GET', 'HEAD', 'OPTIONS', 'PUT'})
DEFAULT_PAGE_SIZE = 100


def should_retry(method: str, status_code: int) -> bool:
    """Decide whether a response is worth asking for again.

    A 429 means Okta rejected the request outright rather than acting on it, so
    replaying it cannot make the same change twice and every verb is safe to retry.
    That matters here because creating users, groups and applications all go out as
    POSTs, and a rate limit is hit during exactly that kind of bulk work.

    A 500/502/503/504 is the opposite: it leaves it genuinely unknown whether Okta
    acted before failing, so those stay restricted to the idempotent verbs.

    Args:
        method: HTTP verb.
        status_code: The status Okta answered with.

    Returns:
        bool: True if the request should be sent again.

    """
    if status_code == RATE_LIMIT_STATUS:
        return True
    return status_code in SERVER_ERROR_STATUSES and method.upper() in IDEMPOTENT_METHODS


def retry_delay(attempt: int, retry_after: str | None) -> float:
    """How long to wait before asking again.

    Okta's own Retry-After wins when it sends one, since it knows when the limit
    resets. Otherwise this is urllib3's formula, jittered so that a fleet of clients
    throttled at the same moment does not come back in lockstep.

    Args:
        attempt: Which attempt just failed, counting from one.
        retry_after: The Retry-After header Okta answered with, if any.

    Returns:
        float: Seconds to wait, never more than RETRY_BACKOFF_MAX.

    """
    if retry_after:
        with suppress(InvalidHeader):
            return min(Retry().parse_retry_after(retry_after), RETRY_BACKOFF_MAX)
    backoff = RETRY_BACKOFF_FACTOR * 2 ** (attempt - 1) + random.uniform(0, RETRY_BACKOFF_JITTER)
    return min(backoff, RETRY_BACKOFF_MAX)


class RateLimitedSession(Session):
    """A requests session that retries what Okta says is worth retrying.

    The retrying happens in :meth:`request` rather than in urllib3, because urllib3 is
    below the point where the credentials sign a request. requests signs while preparing
    one, in ``prepare_request``, and hands urllib3 the finished bytes, so a retry there
    replays whatever was signed: a DPoP proof would go out twice carrying a jti Okta has
    already recorded, and an iat aged by the whole backoff. Asking again from here runs
    ``prepare_request`` again, so every attempt is signed afresh. :func:`should_retry`
    decides which statuses are safe on which verbs.

    An exhausted budget comes back as a response rather than an exception. A server
    error then reaches :meth:`OktaSession.validate_response` and becomes the
    ``ServerError`` callers already expect, and a rate limit is turned into
    ``ApiLimitReached`` by :meth:`request`, which keeps both documented exceptions
    intact.

    Connection and read failures are deliberately left unretried. Replaying them
    would multiply the read timeout by the retry budget, so a hung endpoint would
    block for minutes rather than ``DEFAULT_TIMEOUT``.
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
        # Nothing is retried down here. urllib3 is handed a request that requests has
        # already passed through ``prepare_request``, which is where ``self.auth`` signs
        # it, so all urllib3 can do is send those same bytes again -- replaying a
        # signature the server has already seen. :meth:`request` asks again from above
        # that instead, and signing happens again on the way through.
        adapter = HTTPAdapter(max_retries=0)
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
        attempt = 0
        while True:
            response = super().request(method, url, *args, **kwargs)
            attempt += 1
            if attempt > RETRY_TOTAL or not should_retry(method, response.status_code):
                break
            delay = retry_delay(attempt, response.headers.get('retry-after'))
            self._logger.debug(
                f'Okta answered {response.status_code} for {url}, '
                f'attempt {attempt} of {RETRY_TOTAL + 1}, waiting {delay:.1f}s.'
            )
            time.sleep(delay)
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
        credentials: OktaCredentials,
        timeout: float | tuple[float, float] | None = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize and authenticate the session.

        Args:
            host: The host of the okta instance, e.g. https://dev.oktapreview.com
            credentials: What to authenticate with, an api token or a service app.
            timeout: The default applied to any request that does not name its own.

        """
        super().__init__(timeout=timeout)
        self.host = host
        self._credentials = credentials
        self.authenticate()

    @property
    def api(self) -> str:
        """The root of the instance's rest api, for callers that need it spelled out.

        Returns:
            str: The api root, e.g. https://dev.oktapreview.com/api/v1

        """
        return f'{self.host}/api/v1'

    def authenticate(self) -> None:
        """Install the credentials on the session and confirm they work.

        The credentials go on as ``auth`` rather than a header, so they are applied
        while each request is prepared. That is what lets a retry re-sign rather than
        replay, and it is the only reason a DPoP proof can be per request at all.

        Raises:
            AuthFailed: Okta rejected the credentials.

        """
        # Unauthenticated on purpose, and before the credentials are installed: it only
        # confirms the host answers, and a service app should not spend a token on it.
        self.get(self.host)
        self.headers.update(
            {
                'accept': 'application/json',
                'content-type': 'application/json',
            }
        )
        self._logger.debug(f'Authenticating with {self._credentials}.')
        self.auth = self._credentials.authenticator(self.host, self._token_session())
        probe = self._credentials.probe
        if probe is None:
            return
        response = self.get(probe)
        if not response.ok:
            raise AuthFailed(response.content)

    def _token_session(self) -> RateLimitedSession:
        """A session for credentials that have to call an endpoint to obtain authority.

        Deliberately not this session. This one labels every body as json, which would
        mislabel a form encoded token request, and it carries the very handler being
        renewed. It is still rate limited, so the token endpoint gets the same backoff
        as everything else.

        Returns:
            RateLimitedSession: A session to mint over.

        """
        return RateLimitedSession(timeout=self.timeout)

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
