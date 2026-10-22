#!/usr/bin/env python
# File: oktasession.py
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
The http transport for oktalib.

Everything about talking to Okta's api lives here: resolving endpoints, recovering
from a token Okta stopped accepting, pagination and the translation of a failed
response into a ``ServerError``. The rest of the library names endpoints and
interprets payloads; it never assembles a url or decides how to retry.

The session is not authenticated here. An authenticator builds it, because only it
knows how to sign requests and how to tell whether that worked, and it is the session's
renewer: the one asked to renew when Okta stops accepting what the session signs with.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

import logging
from collections.abc import Generator
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from requests import Response

from .configuration import DEFAULT_PAGE_SIZE, DEFAULT_TIMEOUT
from .oktalibexceptions import AuthFailed, ServerError
from .ratelimitedsession import RateLimitedSession

# Only for the annotation: the authenticators build sessions, so importing them here at
# runtime would have each module import the other.
if TYPE_CHECKING:
    from .oktaauthenticators import OktaAuthenticator

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-09-15'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

LOGGER_BASENAME = 'oktasession'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


class OktaSession(RateLimitedSession):
    """A rate limited session against one Okta instance.

    Knows where the instance is, so callers name an endpoint rather than assembling
    a url: ``session.get('/users')`` reaches ``{host}/api/v1/users``. A url that is
    already absolute is sent as it stands, which covers both the pagination links
    Okta hands back and the ``/oauth2/v1`` endpoints that sit outside ``/api/v1``.

    Built by an :class:`oktalib.oktaauthenticators.OktaAuthenticator`, which signs it and
    renews what it signs with.
    """

    def __init__(
        self,
        host: str,
        renewer: 'OktaAuthenticator',
        timeout: float | tuple[float, float] | None = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the session.

        Args:
            host: The org root, e.g. https://dev.oktapreview.com
            renewer: The authenticator to ask for renewal when Okta answers 401.
            timeout: The default applied to any request that does not name its own.

        """
        super().__init__(timeout=timeout)
        self._logger = logging.getLogger(f'{LOGGER_BASENAME}.{self.__class__.__name__}')
        self.host = host
        self._renewer = renewer
        self.headers.update({'accept': 'application/json', 'content-type': 'application/json'})

    @property
    def api(self) -> str:
        """The root of the instance's rest api, for callers that need it spelled out.

        Returns:
            str: The api root, e.g. https://dev.oktapreview.com/api/v1

        """
        return f'{self.host}/api/v1'

    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        """Resolve an endpoint against the instance and make the request.

        A 401 means Okta stopped accepting what the session signs with part way through
        a run, a token revoked or expired early, so the renewer is asked to renew and the
        request is made once more. That is safe on any verb: Okta refused the request
        rather than acting on it, and the retry is signed afresh. A 403 is left alone,
        since it means a role or scope is missing, which no renewal can grant.

        Args:
            method: HTTP verb.
            url: An endpoint such as ``/users``, resolved against :attr:`api`, or an
                absolute url, which is used as it stands.
            args: Positional arguments passed through to requests.
            kwargs: Keyword arguments passed through to requests.

        Raises:
            AuthFailed: Okta still refused the session once it was renewed, or what it
                signs with cannot be renewed at all.

        Returns:
            Response: The response.

        """
        if not url.startswith(('http://', 'https://')):
            url = f'{self.api}{url}'
        response = super().request(method, url, *args, **kwargs)
        if response.status_code != HTTPStatus.UNAUTHORIZED:
            return response
        self._logger.debug(f'Okta refused {self._renewer.type} for {url}, renewing.')
        self._renewer.renew(self)
        response = super().request(method, url, *args, **kwargs)
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            raise AuthFailed(f'Okta refused {self._renewer.type} even once it was renewed.')
        return response

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
