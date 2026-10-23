#!/usr/bin/env python
# File: ratelimitedsession.py
#
# Copyright 2026 Yorick Hoorneman
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
A requests session that rides out Okta's rate limit.

It knows nothing about Okta beyond which answers are worth asking again for, so the
credentials can build their sessions on it without depending on the session that
talks to the api, and that session can depend on the credentials in turn.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

import logging
import random
import time
from contextlib import suppress
from typing import Any

from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InvalidHeader
from urllib3.util.retry import Retry

from .configuration import (
    DEFAULT_TIMEOUT,
    IDEMPOTENT_METHODS,
    RATE_LIMIT_STATUS,
    RETRY_BACKOFF_FACTOR,
    RETRY_BACKOFF_JITTER,
    RETRY_BACKOFF_MAX,
    RETRY_TOTAL,
    SERVER_ERROR_STATUSES,
)
from .oktalibexceptions import ApiLimitReached

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-09-15'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

LOGGER_BASENAME = 'ratelimitedsession'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


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
    resets, and it is obeyed as given: capping it would mean coming back early, to be
    refused again, against a limit that had already said how long it needed. urllib3
    clamps it to six hours, which is the only bound applied.

    Failing a header, this is urllib3's formula, jittered so that a fleet of clients
    throttled at the same moment does not come back in lockstep. One deliberate
    difference: urllib3 did not wait at all before its first retry, where this waits
    RETRY_BACKOFF_FACTOR, since retrying a rate limit immediately only spends another
    request on it.

    Args:
        attempt: Which attempt just failed, counting from one.
        retry_after: The Retry-After header Okta answered with, if any.

    Returns:
        float: Seconds to wait. A computed backoff is capped at RETRY_BACKOFF_MAX; a
            Retry-After is not.

    """
    if retry_after:
        with suppress(InvalidHeader):
            return Retry().parse_retry_after(retry_after)
    # Doubles with each attempt, so with the defaults the waits run 1s, 2s, 4s, ... up to
    # RETRY_BACKOFF_MAX, each pushed later by a random share of RETRY_BACKOFF_JITTER.
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
        response = self._ask_until_answered(method, url, *args, **kwargs)
        if response.status_code == RATE_LIMIT_STATUS:
            self._logger.warning('Api is still exhausted for endpoint after retrying, giving up.')
            raise ApiLimitReached
        return response

    def _ask_until_answered(self, method: str, url: str, *args: Any, **kwargs: Any) -> Response:
        """Keep asking while the answer is one :func:`should_retry` calls worth repeating.

        Each attempt goes out through ``Session.request``, so the credentials sign it
        again rather than the last signature being sent twice.

        Args:
            method: HTTP verb.
            url: The url to request.
            args: Positional arguments passed through to requests.
            kwargs: Keyword arguments passed through to requests.

        Returns:
            Response: The last response, retryable or not.

        """
        kwargs.setdefault('timeout', self.timeout)
        attempt = 0
        while True:
            response = super().request(method, url, *args, **kwargs)
            attempt += 1
            if attempt > RETRY_TOTAL or not should_retry(method, response.status_code):
                return response
            delay = retry_delay(attempt, response.headers.get('retry-after'))
            self._logger.debug(
                f'Okta answered {response.status_code} for {url}, '
                f'attempt {attempt} of {RETRY_TOTAL + 1}, waiting {delay:.1f}s.'
            )
            time.sleep(delay)
